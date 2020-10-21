from __future__ import print_function, division, unicode_literals, absolute_import
import cv2
import grpc
import logging
import os
import sys
import time

from ace import analytic_pb2, analytic_pb2_grpc
from ace.analyticservice import AnalyticHandler
from flask import Flask, jsonify, request, Response
from ace.rtsp import RTSPHandler
from concurrent import futures

from google.protobuf import json_format

logger = logging.getLogger(__name__)


class EndpointAction(object):

    def __init__(self, action):
        self.action = action

    def __call__(self, *args):
        answer = self.action()
        return answer


class ProxySvc:
    def __init__(self, name, frame_filter, host="::", port=3000, debug=False):
        self.app = Flask(name)
        self.add_endpoint("/update", "update", self.update, methods=["POST"])
        self.host = host
        self.port = port
        self.handler = None
        self.filter = frame_filter

    def run(self):
        print("Running on {!s}::{!s}".format(self.host, self.port))
        self.app.run(host=self.host, port=self.port)

    def update(self):
        data = request.json
        self.filter.update(data)
        logger.info("Applying Filters: ", self.filter.filters)
        return {"code": 200}

    def add_endpoint(self, endpoint=None, endpoint_name=None, handler=None, methods=None):
        self.app.add_url_rule(endpoint, endpoint_name,
                              EndpointAction(handler), methods=methods)


class _AnalyticServicer(analytic_pb2_grpc.AnalyticServicer):
    """The class registered with gRPC, handles endpoints."""

    def __init__(self, svc):
        """Create a servicer using the given Service object as implementation."""
        self.svc = svc

    def ProcessVideoFrame(self, req, ctx):
        handler = AnalyticHandler()
        handler.from_request(req)
        handler.set_start_time()
        self.svc._CallEndpoint(self.svc.PROCESS_FRAME, handler, ctx)
        handler.set_end_time()
        handler.update_analytic_metadata(name=self.svc.get_name())
        return handler.get_response()

    def ProcessVideoStream(self, req, ctx):
        raise NotImplementedError()

    def GetFrame(self, req, ctx):
        return self.svc._CallEndpoint(self.svc.GET_FRAME, req, analytic_pb2.CompositeResults(), ctx)

    def CheckStatus(self, req, ctx):
        resp = analytic_pb2.AnalyticStatus()
        resp.status = "Running"
        return resp


class AnalyticServiceGRPC:
    """Actual implementation of the service, with function registration."""

    PROCESS_FRAME = "ProcessFrame"
    PROCESS_STREAM = "ProcessStream"
    GET_FRAME = "GetFrame"

    _ALLOWED_IMPLS = frozenset([PROCESS_FRAME, GET_FRAME])

    def __init__(self, verbose=False):
        self.verbose = verbose
        self._impls = {}
        self.analytic_name = None
        # self._health_servicer = health.HealthServicer()

    def get_name(self):
        return self.analytic_name

    def register_name(self, name):
        self.analytic_name = name

    def Start(self, analytic_port=50051, max_workers=10, concurrency_safe=False):
        self.concurrency_safe = concurrency_safe
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers),
                             options=(('grpc.so_reuseport', 0),))
        analytic_pb2_grpc.add_AnalyticServicer_to_server(
            _AnalyticServicer(self), server)
        # health_pb2_grpc.add_HealthServicer_to_server(self._health_servicer, server)
        if not server.add_insecure_port('[::]:{:d}'.format(analytic_port)):
            raise RuntimeError(
                "can't bind to port {}: already in use".format(analytic_port))
        server.start()
        # self._health_servicer.set('', health_pb2.HealthCheckResponse.SERVING)
        logger.info("Analytic server started on port {} with PID {}".format(
            analytic_port, os.getpid()), file=sys.stderr)
        return server

    def Run(self, analytic_port=50051, max_workers=10, concurrency_safe=False):
        server = self.Start(analytic_port=analytic_port,
                            max_workers=max_workers, concurrency_safe=concurrency_safe)
        logger.info("Serving {!s}".format(self.analytic_name))
        try:
            while True:
                time.sleep(3600 * 24)
        except KeyboardInterrupt:
            server.stop(0)
            logging.info("Server stopped")
            return 0
        except Exception as e:
            server.stop(0)
            logging.error("Caught exception: %s", e)
            return -1

    def RegisterProcessVideoFrame(self, f):
        return self._RegisterImpl(self.PROCESS_FRAME, f)

    def RegiterProcessVideoStream(self, f):
        return self._RegisterImpl(self.PROCESS_STREAM, f)

    def RegisterGetFrame(self, f):
        return self._RegisterImpl(self.GET_FRAME, f)

    def _RegisterImpl(self, type_name, f):
        if type_name not in self._ALLOWED_IMPLS:
            raise ValueError(
                "unknown implementation type {} specified".format(type_name))
        if type_name in self._impls:
            raise ValueError(
                "implementation for {} already present".format(type_name))
        self._impls[type_name] = f
        return self

    def _CallEndpoint(self, ep_type, handler, ctx):
        """Implements calling endpoints and handling various exceptions that can come back.

        Args:
            ep_type: The name of the manipulation, e.g., "image". Should be in ALLOWED_IMPLS.
            handler: The analytic handler object for getting the frame(s) and providing analytic output.
            ctx: The context, used mainly for aborting with error codes.

        Returns:
            An appropriate response object for the endpoint type specified.
        """
        ep_func = self._impls.get(ep_type)
        if not ep_func:
            ctx.abort(grpc.StatusCode.UNIMPLEMENTED,
                      "Endpoint {!r} not implemented".format(ep_type))

        try:
            logger.debug("Calling function for: {!s}".format(ep_type))

            ep_func(handler)
            logger.debug("Function returned response: {!s}".format(handler.get_response()))
        except ValueError as e:
            logger.exception('invalid input')
            ctx.abort(grpc.StatusCode.INVALID_ARGUMENT,
                      "Endpoint {!r} invalid input: {}".format(ep_type, e))
        except NotImplementedError as e:
            logger.warn('unimplemented endpoint {}'.format(ep_type))
            ctx.abort(grpc.StatusCode.UNIMPLEMENTED,
                      "Endpoint {!r} not implemented: {}".format(ep_type, e))
        except Exception as e:
            logger.exception('unknown error')
            ctx.abort(grpc.StatusCode.UNKNOWN,
                      "Error processing endpoint {!r}: {}".format(ep_type, e))
        # return handler.get_response()
