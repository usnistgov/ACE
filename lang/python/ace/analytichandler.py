from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import asyncio
import contextlib
import json
import logging
import os
import select
import sys
import threading
import time
import traceback
import uuid
from concurrent import futures

import cv2
import numpy as np
from flask import Flask, Response, jsonify, request
from google.protobuf import json_format
from kafka import KafkaProducer

from ace import analytic_pb2
from ace.aceclient import AceDB
from ace.messenger import ACEProducer
from ace.rtsp import RTSPHandler

logger = logging.getLogger(__name__)


def get_analytic_handler(frame_batch_obj, input_type, stream_addr, session_id):
    handler_class = HANDLERS.get(input_type)
    if not handler_class:
        raise ValueError("Invalid input type specifiec: {!s}. Must be on of: {!s}".format(input_type, list(HANDLERS.keys())))
    return handler_class(frame_batch_obj, stream_addr, session_id)


def crop_box_to_frame(frame, box_rect):
    x1, y1, x2, y2 = box_rect

    def crop_one(val, frame_val):
        return max(min(val, frame_val - 2), 2)
    return [crop_one(x1, frame.shape[1]),
            crop_one(y1, frame.shape[0]),
            crop_one(x2, frame.shape[1]),
            crop_one(y2, frame.shape[0])
            ]


class FrameHandler:
    @classmethod
    def from_request(cls, req):
        self = cls()
        self.input_frame = req.frame
        self.analytic = req.analytic
        self.jpeg = self.input_frame.frame.img
        self.frame = cv2.imdecode(np.fromstring(self.jpeg, dtype=np.uint8), 1)
        self.resp = analytic_pb2.ProcessedFrame()

        return self

    def __init__(self, frame_batch_obj=None, stream_addr="", session_id=""):

        if not frame_batch_obj:
            return None

        self.input_frame = analytic_pb2.InputFrame()
        self.analytic = analytic_pb2.AnalyticData()
        self.resp = analytic_pb2.ProcessedFrame()
        self.resp.data.stream_addr = stream_addr
        self.resp.session_id = session_id

        self.frame = frame_batch_obj[0][2]
        self.input_frame.frame_num = frame_batch_obj[0][1]
        self.input_frame.timestamp = frame_batch_obj[0][0]

    def get_frame(self, format=None):
        if format == "JPEG":
            logger.info("Getting image as jpeg")
            if not self.jpeg:
                self.jpeg = cv2.imencode(".jpeg", self.frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])[
                    1].tostring()
            return self.jpeg
        return self.frame

    def add_bounding_box(self, classification, confidence, x1, y1, x2, y2, supplement=None):
        """Add bounding box for classification to the response"""
        if self.frame is not None:
            x1, y1, x2, y2 = crop_box_to_frame(self.frame, [x1, y1, x2, y2])

        box = analytic_pb2.RegionOfInterest(
            box=analytic_pb2.BoundingBox(corner1=analytic_pb2.Point(
                x=x1, y=y1), corner2=analytic_pb2.Point(x=x2, y=y2)),
            classification=classification, confidence=confidence, supplement=supplement)

        self.resp.data.roi.extend([box])

    @property
    def frame_number(self):
        return self.input_frame.frame_num

    @property
    def timestamp(self):
        return self.input_frame.timestamp

    def get_response(self, include_frame=False):
        self.resp.analytic.MergeFrom(self.analytic)
        self.add_frame_info(include_frame)
        return self.resp

    def get_analytic_metadata(self):
        return self.analytic

    def add_frame_info(self, include_frame=False):
        self.resp.frame.frame_num = self.input_frame.frame_num
        self.resp.frame.timestamp = self.input_frame.timestamp
        self.resp.frame.frame_byte_size = len(cv2.imencode(".jpeg", self.frame, [int(cv2.IMWRITE_JPEG_QUALITY), 100])[1].tostring())
        if include_frame:
            self.add_frame()

    def add_render_frame(self, quality=70, scale=None, class_tags=None):
        """Adds a frame if something only if something is detected adds overlays"""
        if len(self.resp.data.roi) == 0:
            if class_tags:
                for tag in class_tags:
                    if tag in self.resp.data.tags:
                        if self.resp.data.tags.get(tag) != False and self.resp.data.tags.get(tag) != 0:
                            self.add_frame(quality=quality, scale=scale)
            return
        annotated_frame = self.frame.copy()
        for roi in self.resp.data.roi:
            if roi.HasField("box"):
                cv2.rectangle(annotated_frame, (roi.box.corner1.x, roi.box.corner1.y), (roi.box.corner2.x, roi.box.corner2.y), (255,0,0), 1)
        self.add_frame(annotated_frame, quality, scale)

    def add_frame(self, frame=None, quality=70, scale=None):
        if frame is None:        
            frame = self.frame.copy()
        self.resp.frame.frame.height = self.frame.shape[0]
        self.resp.frame.frame.width = self.frame.shape[1]
        self.resp.frame.frame.color = self.frame.shape[2]
        if scale:
            frame = cv2.resize(frame, (int(frame.shape[1] * scale), int(frame.shape[0] * scale)))
        self.resp.frame.frame.img = cv2.imencode(
            ".jpeg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])[1].tostring()
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


class BatchHandler:
    def __init__(self, frame_batch_obj=None, stream_addr="", session_id=""):
        """Analytic Handler provides the necessary interface for processing batches of frames ranging in size from 1 to N """
        if not frame_batch_obj:
            return
        # For organizing output data
        self.input_frames = []  # analytic_pb2.InputFrame()
        self.analytic = analytic_pb2.AnalyticData()
        self.resp = analytic_pb2.ProcessedFrameBatch()

        self.frames = [obj[2] for obj in frame_batch_obj]
        self.frame_nums = [obj[1] for obj in frame_batch_obj]
        self.timestamps = [obj[0] for obj in frame_batch_obj]

        self.frame_index = 0

        self.initialize_response(stream_addr, session_id)

    def initialize_response(self, stream_addr, session_id):
        for i in range(len(self.frames)):
            self.resp.processed_frames.extend([analytic_pb2.ProcessedFrame(
                frame=analytic_pb2.InputFrame(
                    # frame=self.frames[i],
                    frame_num=self.frame_nums[i],
                    timestamp=self.timestamps[i]
                ),
                data=analytic_pb2.FrameData(
                    stream_addr=stream_addr
                ),
                session_id=session_id
            )])

    def from_request(self, req):
        raise NotImplementedError()

    def get_next_frame(self):
        self.frame_index = min(self.frame_index + 1, len(self.frames) - 1)
        return self.frames[self.frame_index - 1]

    def get_frame_batch(self):
        return self.frames

    def add_bounding_box(self, classification, confidence, x1, y1, x2, y2, supplement=None, frame_index=None):
        """Add bounding box for classification to the response. If no frame index is specified, it will be applied to all frames"""
        if frame_index:
            x1, y1, x2, y2 = crop_box_to_frame(self.frame, [x1, y1, x2, y2])
            box = analytic_pb2.RegionOfInterest(
                box=analytic_pb2.BoundingBox(corner1=analytic_pb2.Point(
                    x=x1, y=y1), corner2=analytic_pb2.Point(x=x2, y=y2)),
                classification=classification, confidence=confidence, supplement=supplement)
            self.resp.processed_frames[frame_index].data.roi.extend([box])

        if not frame_index:
            for i, frame in enumerate(self.frames):
                x1, y1, x2, y2 = crop_box_to_frame(self.frame, [x1, y1, x2, y2])
                box = analytic_pb2.RegionOfInterest(
                    box=analytic_pb2.BoundingBox(corner1=analytic_pb2.Point(
                        x=x1, y=y1), corner2=analytic_pb2.Point(x=x2, y=y2)),
                    classification=classification, confidence=confidence, supplement=supplement)

                self.resp.processed_frames[i].data.roi.extend([box])

    def frame_numbers(self):
        return self.input_frame.frame_numbers

    def timestamps(self):
        return self.input_frame.timestamps

    def get_response(self, include_frame=False):
        for resp in self.resp.processed_frames:
            resp.analytic.MergeFrom(self.analytic)
        self.add_frame_info(include_frame=include_frame)
        return self.resp

    def get_analytic_metadata(self):
        return self.analytic

    def add_frame_info(self, include_frame=False, quality=70):
        for i in range(len(self.frames)):
            jpeg = cv2.imencode(".jpeg", self.frames[i], [int(cv2.IMWRITE_JPEG_QUALITY), quality])[1].tostring()
            self.resp.processed_frames[i].frame.frame_byte_size = len(jpeg)
        if include_frame:
            self.add_frames(quality)

    def add_render_frame(self, quality=70, scale=None, class_tags=None):
        """Temporary function to match single frame handler signature"""
        self.add_frame(quality, scale)

    def add_frame(self, quality=70, scale=None):
        """ Temporary for now. Allows the service to call this regardless of which handler is used"""
        self.add_frame(quality=quality, scale=scale)

    def add_frames(self, quality=70, scale=None):
        for i in range(len(self.frames)):
            frame = self.frames[i].copy()
            
            if scale:
                frame = cv2.resize(frame, (int(frame.shape[1] * scale), int(frame.shape[0] * scale)))
            jpeg = cv2.imencode(".jpeg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])[1].tostring()
            self.resp.processed_frames[i].frame.frame_byte_size = len(jpeg)
            self.resp.processed_frames[i].frame.frame.img = jpeg
            shape = self.frames[i].shape
            self.resp.processed_frames[i].frame.frame.height = shape[0]
            self.resp.processed_frames[i].frame.frame.width = shape[1]
            self.resp.processed_frames[i].frame.frame.color = shape[2]

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
        self.analytic.filters[f] = str(value)

    def merge_response(self, resp):
        self.resp.MergeFrom(resp)

    def add_frame_if_missing(self, frame):
        if self.resp.frame.ByteSize() > 0:
            return False
        logger.info("No frame in response. Adding frame.")
        self.add_frame(frame)
        return True

    def set_name(self, name):
        self.analytic.name = name

    def add_operation(self, operation):
        self.analytic.operations.append(operation)

    def set_start_time(self):
        start_time = int(round(time.time()*1000))
        for i in range(len(self.frames)):
            self.resp.processed_frames[i].data.start_time_millis = start_time

    def set_end_time(self):
        end_time = int(round(time.time()*1000))
        for i in range(len(self.frames)):
            self.resp.processed_frames[i].data.end_time_millis = end_time

    def add_tags(self, **kwargs):
        for key, value in kwargs.items():
            for i in range(len(self.frames)):
                self.resp.processed_frames[i].data.tags[key] = str(value)


HANDLERS = {"frame": FrameHandler, "batch": BatchHandler}
