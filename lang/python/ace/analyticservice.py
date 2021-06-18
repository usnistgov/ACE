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
from ace.analytichandler import FrameHandler, BatchHandler, get_analytic_handler
from ace.messenger import ACEProducer
from ace.rtsp import RTSPHandler

logger = logging.getLogger(__name__)

class EndpointAction(object):

    def __init__(self, action):
        self.action = action

    def __call__(self, *args):
        answer = self.action()
        return answer


class AnalyticService:
    """ """

    def __init__(self, name, port=3000, debug=False, stream_video=False, verbose=False, num_workers=1, messenger_type="NATS"):
        self.app = Flask(name)
        self._add_endpoint("/config", "config", self.config, methods=["PUT"])
        self._add_endpoint("/kill", "kill", self.kill, methods=["POST"])
        self.analytic = analytic_pb2.AnalyticData()
        self.port = port
        self.handler = None
        self.stream_video = stream_video
        self.num_workers = num_workers
        self.verbose = verbose
        self.loop = asyncio.new_event_loop()
        self.messenger_type = messenger_type
        self.return_frame = False

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
        self.return_frame = req.return_frame
        logger.debug("Request: ", req)
        self.analytic.MergeFrom(req.analytic)
        self.session_id = req.session_id
        if self.verbose:
            print("Creating RTSP handler with verbose option")
            print("Config Request :", req)
        self.handler = RTSPHandler(req.stream_source,
                                   self._call_endpoint,
                                   cap_width=req.frame_width,
                                   cap_height=req.frame_height,
                                   analytic_data=req.analytic,
                                   stream_id=req.stream_id,
                                   verbose=self.verbose,
                                   return_frame=req.return_frame,
                                   params=self.func_params)  # TODO Untested.
        self.system_tags = dict(req.system_tags)
        self.stream_addr = req.stream_source
        if req.messenger_addr:
            self.handler.add_producer(producer=ACEProducer(
                addr=req.messenger_addr, value_serializer=lambda value: value.SerializeToString(), loop=self.loop, messenger_type=self.messenger_type))
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
        self.register_func(f, input_type="frame", batch_size=1)

    def RegisterProcessFrameBatch(self, f, batch_size, sliding=False):
        """ """
        self.register_func(f, input_type="batch", batch_size=batch_size, sliding=sliding)

    def register_name(self, name):
        """ """
        self.analytic.name = name

    def register_func(self, f, input_type="frame", **kwargs):
        """ """
        self.func = f
        self.func_type = input_type
        self.func_params = kwargs

    def _add_endpoint(self, endpoint=None, endpoint_name=None, handler=None, methods=None):
        self.app.add_url_rule(endpoint, endpoint_name,
                              EndpointAction(handler), methods=methods)

    def _call_endpoint(self, frame_obj):
        handler = get_analytic_handler(frame_obj, input_type=self.func_type, stream_addr=self.stream_addr, session_id=self.session_id)
        if not handler:
            return None
        handler.update_analytic_metadata(
            name=self.analytic.name, addr=self.analytic.addr)
        handler.set_start_time()
        self.func(handler)
        handler.set_end_time()
        for key, value in self.system_tags.items():
            handler.resp.data.tags.update({key: value})
        if self.return_frame:
            handler.add_render_frame(scale=0.5)
        return handler.get_response()
