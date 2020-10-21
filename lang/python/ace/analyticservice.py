from __future__ import print_function, division, unicode_literals, absolute_import
import cv2
import contextlib
import json
import logging
import numpy as np
import os
import select
import sys
import threading
import time
import traceback

from concurrent import futures
from kafka import KafkaProducer
from flask import Flask, jsonify, request, Response
from ace import analytic_pb2, analytic_pb2_grpc
from ace.rtsp import RTSPHandler
import grpc
from ace.aceclient import AceDB

from google.protobuf import json_format


logger = logging.getLogger(__name__)


class EndpointAction(object):

    def __init__(self, action):
        self.action = action

    def __call__(self, *args):
        answer = self.action()
        return answer


class AnalyticHandler:
    def __init__(self, frame_obj=None, input_type="frame", stream_addr="", session_id=""):

        self.input_frame = analytic_pb2.InputFrame()
        self.analytic = analytic_pb2.AnalyticData()
        self.resp = analytic_pb2.ProcessedFrame()
        self.resp.data.stream_addr = stream_addr
        self.resp.session_id = session_id
        if not frame_obj:
            return

        self.frame = frame_obj[2]
        self.input_frame.frame_num = frame_obj[1]
        self.input_frame.timestamp = frame_obj[0]

    def from_request(self, req):
        self.input_frame.MergeFrom(req.frame)
        self.analytic.MergeFrom(req.analytic)
        self.jpeg = self.input_frame.frame.img
        self.frame = cv2.imdecode(np.fromstring(self.jpeg, dtype=np.uint8), 1)

    def get_frame(self, format=None):
        if format == "JPEG":
            logger.info("Getting image as jpeg")
            if not self.jpeg:
                self.jpeg = cv2.imencode(".jpeg", self.frame, [int(cv2.IMWRITE_JPEG_QUALITY), 100])[
                    1].tostring()
            return self.jpeg
        return self.frame

    def add_bounding_box(self, classification, confidence, x1, y1, x2, y2, supplement=None):
        """Add bounding box for classification to the response"""
        if self.frame is not None:
            x1 = max(min(x1, self.frame.shape[1]-2), 2)
            x2 = max(min(x2, self.frame.shape[1]-2), 2)
            y1 = max(min(y1, self.frame.shape[0]-2), 2)
            y2 = max(min(y2, self.frame.shape[0]-2), 2)
        box = analytic_pb2.RegionOfInterest(
            box=analytic_pb2.BoundingBox(corner1=analytic_pb2.Point(
                x=x1, y=y1), corner2=analytic_pb2.Point(x=x2, y=y2)),
            classification=classification, confidence=confidence, supplement=supplement)
        self.resp.data.roi.extend([box])

    def frame_number(self):
        return self.input_frame.frame_num

    def timestamp(self):
        return self.input_frame.timestamp

    def get_response(self):
        self.resp.analytic.MergeFrom(self.analytic)
        self.add_frame_info()
        return self.resp

    def get_analytic_metadata(self):
        return self.analytic

    def add_frame_info(self, include_frame=False):
        self.resp.frame.frame_num = self.input_frame.frame_num
        self.resp.frame.timestamp = self.input_frame.timestamp
        self.resp.frame.frame_byte_size = len(cv2.imencode(".jpeg", self.frame, [int(cv2.IMWRITE_JPEG_QUALITY), 100])[1].tostring())
        if include_frame:
            self.add_frame()

    def add_frame(self, quality=70):
        self.resp.frame.frame.height = self.frame.shape[0]
        self.resp.frame.frame.width = self.frame.shape[1]
        self.resp.frame.frame.color = self.frame.shape[2]
        self.resp.frame.frame.img = cv2.imencode(
            ".jpeg", self.frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])[1].tostring()
        self.resp.frame.frame_byte_size = self.resp.frame.frame.ByteSize()

    def add_encoded_frame(self, enc_frame):
        self.resp.frame.frame.img = enc_frame
        self.resp.frame.frame_byte_size = self.resp.frame.frame.ByteSize()

    def update_analytic_metadata(self, **kwargs):
        name = kwargs.get("name")
        addr = kwargs.get("addr")
        gpu = kwargs.get("requires_gpu")
        operations = kwargs.get("operations")
        filters = kwargs.get("filters")
        replica_addrs = kwargs.get("replica_addrs")

        if name:
            self.analytic.name = name
        if gpu:
            self.analytic.requires_gpu = gpu
        if addr:
            self.analytic.addr = addr
        if operations:
            self.analytic.operations = operations
        if filters:
            self.analytic.filters = filters
        if replica_addrs:
            self.analytic.replica_addrs

    def add_filter(self, f, value):
        logger.info("Adding filter: {!s} = {!s}".format(f, value))
        self.resp.analytic.filters[f] = str(value)

    def merge_response(self, resp):
        self.resp.MergeFrom(resp)

    def add_frame_if_missing(self, frame):
        if self.resp.frame.ByteSize() > 0:
            return False
        logger.info("No frame in response. Adding frame.")
        self.add_frame(frame)
        return True

    def set_name(self, name):
        self.resp.analytic.name = name

    def add_operation(self, operation):
        self.resp.analytic.operations.append(operation)

    def set_start_time(self):
        self.resp.data.start_time_millis = int(round(time.time()*1000))

    def set_end_time(self):
        self.resp.data.end_time_millis = int(round(time.time()*1000))

    def add_tags(self, **kwargs):
        for key, value in kwargs.items():
            self.resp.data.tags[key] = str(value)


class AnalyticService:
    """ """

    def __init__(self, name, port=3000, debug=False, stream_video=False, verbose=False, num_workers=1):
        self.app = Flask(name)
        self._add_endpoint("/config", "config", self.config, methods=["PUT"])
        self._add_endpoint("/kill", "kill", self.kill, methods=["POST"])
        self.analytic = analytic_pb2.AnalyticData()
        self.port = port
        self.handler = None
        self.stream_video = stream_video
        self.num_workers = num_workers
        self.verbose = verbose

    def Run(self):
        """ """
        logger.info("REST config service running on ::{!s}".format(self.port))
        self.app.run(host="::", port=self.port)

    def config(self):
        """ """
        if self.handler:
            logger.info("Shutting down RTSP connection.")
            self.handler.terminate()

        data = request.get_data(as_text=False)
        req = analytic_pb2.StreamRequest().FromString(data)
        logger.debug("Request: ", req)
        self.analytic.MergeFrom(req.analytic)
        if self.verbose:
            print("Creating RTSP handler with verbose option")
            print("Config Request :", req)
        self.handler = RTSPHandler(req.stream_source,
                                   self._call_endpoint,
                                   cap_width=req.frame_width,
                                   cap_height=req.frame_height,
                                   analytic_data=req.analytic,
                                   verbose=self.verbose,
                                   num_workers=self.num_workers)  # TODO Untested.
        self.system_tags = dict(req.system_tags)
        self.stream_addr = req.stream_source
        if req.kafka_addr:
            self.handler.add_producer(producer=KafkaProducer(
                bootstrap_servers=req.kafka_addr, value_serializer=lambda value: value.SerializeToString()))
        if req.db_addr:
            host, port = req.db_addr.split(":")
            self.handler.add_database(db_client=AceDB(host=host, port=port))
        t = threading.Thread(target=self.handler.run)
        t.start()
        return {"code": 200}

    def kill(self):
        """ """
        if not self.handler:
            logger.info("Nothing running")
            return
        logger.info("Shutting down RTSP connection")
        self.handler.terminate()
        return {"code": 200}

    def RegisterProcessVideoFrame(self, f):
        """ """
        self.register_func(f, input_type="frame")

    def RegisterProcessFrameBatch(self, f):
        """ """
        raise NotImplementedError

    def register_name(self, name):
        """ """
        self.analytic.name = name

    def register_func(self, f, input_type="frame"):
        """ """
        self.func = f
        self.func_type = input_type

    def _add_endpoint(self, endpoint=None, endpoint_name=None, handler=None, methods=None):
        self.app.add_url_rule(endpoint, endpoint_name,
                              EndpointAction(handler), methods=methods)

    def _call_endpoint(self, frame_obj):
        handler = AnalyticHandler(
            frame_obj, input_type=self.func_type, stream_addr=self.stream_addr)
        handler.update_analytic_metadata(
            name=self.analytic.name, addr=self.analytic.addr)
        handler.set_start_time()
        self.func(handler)
        handler.set_end_time()
        for key, value in self.system_tags.items():
            handler.resp.data.tags.update({key: value})

        return handler.get_response()
