#!/bin/python3
# import ansyncio
import logging
import os.path
import sys
import threading
import time
import uuid

import click
import cv2
import grpc
import requests
from google.protobuf import json_format
from influxdb import InfluxDBClient

from ace import analytic_pb2, analytic_pb2_grpc

logger = logging.getLogger(__name__)

class ConfigClient:
    def __init__(self, host="localhost", port="3000"):
        self.addr = "http://{!s}:{!s}".format(host, port)

    def config(self, src, analytic=None, frame_width=None, frame_height=None, messenger_addr=None, db_addr=None, tags=None, stream_id=None, return_frame=False):
        """Configure the analytic to process the stream at the address specified by 'src'"""
        req = analytic_pb2.StreamRequest()
        req.stream_source = src
        # req.kafka_addr = "broker:9092"
        if analytic:
            req.analytic.MergeFrom(analytic)
        
        req.return_frame = return_frame
        req.frame_width = frame_width or 0
        req.frame_height = frame_height or 0
        req.messenger_addr = messenger_addr or ""
        req.db_addr = db_addr or ""
        req.stream_id = stream_id or "default"
        req.return_frame = return_frame
        if tags:
            logger.debug("Adding tags")
            for key, value in tags.items():
                req.system_tags.update({key:value})


        req.session_id = str(uuid.uuid4())
        r = requests.put("{!s}/config".format(self.addr),
                         data=req.SerializeToString())
        results = {"status": {
            "code": r.status_code
           }
        }
        if r.status_code == requests.codes.ok:
            results["status"]["msg"] = r.reason

        logger.info(results)

    def kill(self):
        r = requests.post("{!s}/kill".format(self.addr))
        return r.status_code        


class FilterClient:
    def __init__(self, host="localhost", port="3000"):
        self.addr = "http://{!s}:{!s}/update".format(host, port)

    def update(self, **kwargs):
        r = requests.post(self.addr, json=kwargs)
        results = {"status": {
            "code": r.status_code
           }
        }
        if r.status_code == requests.codes.ok:
            results["status"]["msg"] = r.reason
        logger.debug(results)

class AnalyticClient(analytic_pb2_grpc.AnalyticStub):
    """Client for talking directly to a single ACE analytic"""

    def __init__(self, addr="localhost:50051"):
        self.addr = addr
        channel = grpc.insecure_channel(self.addr)
        super(AnalyticClient, self).__init__(channel)

    def check_status(self):
        self.CheckStatus(analytic_pb2.Empty())

    def process_frame(self, frame, **kwargs):
        """Receive a video frame (numpy array) and send as bytes to an analytic"""
        req = analytic_pb2.ProcessFrameRequest()
        if type(frame) != bytes:
            req.frame.frame.height = frame.shape[0]
            req.frame.frame.width = frame.shape[1]
            req.frame.frame.color = frame.shape[2]
            logging.info("Encoding as jpeg string")
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 100]
            frame = cv2.imencode(".jpeg", frame, encode_param)[1].tostring()

        req.frame.frame.img = frame
        req.session_id = kwargs.get("session_id", "")
        req.frame.frame_num = kwargs.get("frame_num", -1)
        req.frame.timestamp = kwargs.get("timestamp", -1)

        return self.ProcessVideoFrame(req)

    def multiprocess_frame(self, req, data, frame_meta=None):
        res = self.ProcessVideoFrame(req)
        if res.frame.frame.ByteSize() == 0:
            res.frame.MergeFrom(req.frame)
        data.results.append(res)


class AnalyticMultiClient:
    def __init__(self):
        self.clients = []

    def connect(self, addr):
        self.addr = addr
        for a in addr:
            self.clients.append(AnalyticClient(addr=a))

    def process_frame(self, frame, frame_req, resp, frame_meta=None):
        """ Send frame to all analytics"""
        threads = []
        req = analytic_pb2.ProcessFrameRequest()
        logging.info("Frame shape {!s}".format(frame.shape))
        logging.info("Encoding as byte string")
        img_shape = frame.shape
        req.frame.frame.height = img_shape[0]
        req.frame.frame.width = img_shape[1]
        req.frame.frame.color = img_shape[2]
        req.frame.frame.img = cv2.imencode(".jpeg", frame)[1].tostring()
        for a in frame_req.analytics:
            if frame_meta:
                req.frame.frame_num = frame_meta.get("frame_num", -1)
                req.frame.frame.timestamp = frame_meta.get("timestamp", -1)
            req.analytic.MergeFrom(a)
            c = AnalyticClient(addr=a.addr)
            t = threading.Thread(target=c.multiprocess_frame,
                                 kwargs=dict(req=req, data=resp))
            t.start()
            threads.append(t)

        for t in threads:
            t.join()
        return resp


class FrameServer:
    def __init__(self, addr):
        self.addr = addr
        self.port = int(self.addr.split(":")[-1])

    def serve(self, cap):
        """Function to serve a stream of video frames from an OpenCV capture object"""
        addr = []
        client = AnalyticMultiClient()

        def process(req, resp):
            ret, frame = cap.read()
            if not ret:
                raise ValueError("No frame returned from stream")

            resp = client.process_frame(frame, req, resp)

        if not cap or not cap.isOpened():
            logging.error("Unable to open video capture.")
            return

        svc = analyticservice.AnalyticService()
        svc.register_name("Frame Server")
        svc.RegisterGetFrame(process)
        logging.info("Registered function with 'GetFrame' endpoint")
        try:
            svc.Run(analytic_port=self.port)
        finally:
            cap.release()
        return


class AceDB:
    def __init__(self, host="localhost", port=8086, db_name="ace"):
        try:
            self.client = InfluxDBClient(host=host, port=port, database="ace")
            self.db_name = db_name
            # self.initialize_db(db_name)
        except requests.exceptions.ConnectionError:
            raise ValueError("Unable to connect to database")

    def write(self, **kwargs):
        data = self.build_json(kwargs)
        self._write(data)

    def write_proto(self, proto):
        data = self.json_from_resp(proto)
        if data:
            self._write(data)

    def _write(self, data):
        if not self.db_name:
            raise ValueError("No database initialized")
        self.client.write_points(data)

    def json_from_resp(self, resp, measurement="FrameInfo", tags=None, fields=None):
        data_list = []
        if not resp.data.roi:
            data = {
                    "measurement": measurement,
                    "tags": {
                        "analytic_name": resp.analytic.name,
                        "analytic_addr": resp.analytic.addr,
                        "classification": None,
                        "frame_num": resp.frame.frame_num,
                        "frame_timestamp": resp.frame.timestamp,
                        "stream_address": resp.data.stream_addr
                    },
                    "fields": {
                        "confidence": 0.0,
                        "analytic_start_time": resp.data.start_time_millis,
                        "analytic_end_time": resp.data.end_time_millis,
                        "frame_byte_size": resp.frame.frame_byte_size
                    }
                }

            data["tags"].update(resp.data.tags)
            data["fields"].update(resp.analytic.filters)
            return [data]

        for roi in resp.data.roi:

            data = {
                "measurement": measurement,
                "tags": {
                    "analytic_name": resp.analytic.name,
                    "analytic_addr": resp.analytic.addr,
                    "classification": roi.classification,
                    "frame_num": resp.frame.frame_num,
                    "frame_timestamp": resp.frame.timestamp,
                    "stream_address": resp.data.stream_addr,
                    "session_id": resp.session_id
                },
                "fields": {
                    "confidence": roi.confidence,
                    "analytic_start_time": resp.data.start_time_millis,
                    "analytic_end_time": resp.data.end_time_millis,
                    "frame_byte_size": resp.frame.frame_byte_size,
                    "box_x1": roi.box.corner1.x,
                    "box_y1": roi.box.corner1.y,
                    "box_x2": roi.box.corner2.x,
                    "box_y2": roi.box.corner2.y
                }
            }

            data["tags"].update(resp.data.tags)
            data["fields"].update(resp.analytic.filters)
        
            data_list.append(data)
        return data_list

    def build_json(self, d):
        data = {
            "measurement": "Frame Info",
            "tags": {
                "analytic": d["analytic"],
                "classification": d["classification"]
            },
            "fields": {
                "confidence": d["score"],
                "run_time": d["run_time"],
                "file_size": d["file_size"]
            }
        }
        data["fields"].update(d["filters"])
        return [data]
