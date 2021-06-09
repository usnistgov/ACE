#!/bin/python

import functools
import json
import logging
import sys
import threading
import uuid
from queue import Queue

import click
import cv2
import grpc
import numpy as np
from google.protobuf import json_format
from grpc_health.v1 import health_pb2, health_pb2_grpc

from ace import aceclient, analytic_pb2, analyticservice, grpcservice
from ace.rtsp import RTSPHandler
from ace.streamproxy import StreamingProxy, TestClient
from ace.utils import FrameFilter, render

logger = logging.getLogger(__name__)


class Context:
    pass


def parse_tag(s):
    if not s:
        raise ValueError("Empty tag key")
    pieces = s.split('=', 1)
    while len(pieces) < 2:
        pieces.append('')
    return {pieces[0]: pieces[1]}


logger.setLevel(logging.INFO)


@click.group()
@click.option("--debug/--no-debug", "-d", default=None, help="Run with debug logging level")
@click.pass_context
def main(ctx, debug):
    """
    The ACE command line client provides a tool for configuring analytics and other ACE components as well 
    as providing users with a means of sending frames directly to analytics running in the system. This CLI can also be 
    used to run other ACE services, such as creating an RTSP server or starting and configuring a filtering service. 
    """
    if debug:
        logger.setLevel(logging.DEBUG)


@main.command()
@click.pass_context
@click.option("--stream_source", "-s", required=True, help="Address of the stream for the analytic to process.")
@click.option("--msg_addr", "-k", default=None, help="Address of the message broker to which the analytic will send output metadata.")
@click.option("--db_addr", "-d", default=None, help="Address of the database to which the analytic will write output.")
@click.option("--analytic_host", default="localhost", help="Address of the analytic to connect to.")
@click.option("--analytic_port", default=3000, help="Port that the configuration endpoint runs on for the analytic.")
@click.option("--tags", "-t",  multiple=True, help="Tag to add to the analytic output. Format is 'key=value'")
def config(ctx, stream_source, msg_addr, db_addr, analytic_host, analytic_port, tags):
    """
    Command used to configure the specified analytic to connect to an RTSP stream, process the video, and publish 
    the results to the specified database and message brokers (if any).
    """
    tag_map = {}
    for tag_str in tags:
        tag_map.update(parse_tag(tag_str))
    a = analytic_pb2.AnalyticData(
        addr="{!s}:{!s}".format(analytic_host, analytic_port))
    client = aceclient.ConfigClient(host=analytic_host, port=analytic_port)
    client.config(src=stream_source, analytic=a,
                  messenger_addr=msg_addr, db_addr=db_addr, stream_id=str(uuid.uuid4()), tags=tag_map)


@main.command()
@click.pass_context
@click.option("--analytic_host", "-h",  default="localhost", help="Host address of the analytic process to terminate")
@click.option("--analytic_port", "-p", default=3000, help="Port the analytic services is running on.")
def kill(ctx, analytic_host, analytic_port):
    """" 
    Terminate the connection between the specified analytic and the video source. Does not terminate the service, 
    so the service will still accept new configuration requests.
    """
    client = aceclient.ConfigClient(host=analytic_host, port=analytic_port)
    client.kill()


@main.command()
@click.pass_context
@click.option("--fil", "-f", multiple=True, default=None, help="Filters to applied to the stream, of the form '<filter>=<value>'.")
@click.option("--filter_host", "-h", default="localhost", help="Host address of the filter")
@click.option("--filter_port", "-p", default=50000, help="Port for the filtering service")
def filter(ctx, fil, filter_host, filter_port):
    """ Applies the specified filter(s) to the stream processed by the StreamFilter at the host and port specified."""
    if not fil:
        raise ValueError("Must specify at least one filtering operaion (of the form '<filter>=<value>'")
    client = aceclient.FilterClient(host=filter_host, port=filter_port)
    filters = {}
    for f in fil:
        filters.update(parse_tag(f))
    client.update(**filters)


@main.group()
@click.option("--host", "-h", default="localhost", help="Host the service runs listens on.")
@click.option("--port", "-p", default="50052", help="Port the service runs listens on.")
@click.pass_context
def serve(ctx, host, port):
    """ Subcommnad for serving video for use by ACE components. """
    pass


@serve.command()
@click.option("--src", help="Source of the stream.")
@click.option("--endpoint", default="stream", help="Endpoint of for the RTSP stream")
@click.option("--verbose/--no-verbose", "-v", default=False, help="Show additional debug info")
@click.pass_context
def rtsp(ctx, src, endpoint, verbose):
    """ Starts a GStreamer Server using the source provided (can be connected camera or external RTSP stream) on the specified endpoint."""
    import gi
    gi.require_version('Gst', '1.0')
    gi.require_version('GstRtspServer', '1.0')
    from gi.repository import GObject, Gst, GstRtspServer

    from ace.rtspserver import GstServer
    GObject.threads_init()
    Gst.init(None)

    if src.isdigit():
        src = int(src)
    cap = cv2.VideoCapture(src)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    server = GstServer(cap, "/{!s}".format(endpoint), verbose)

    loop = GObject.MainLoop()
    loop.run()


@serve.command()
@click.option("--port", "-p", default="3000", help="Port the configuration endpoint runs on.")
@click.option("--analytic_addr", "-a", default="localhost:50051", help="Address of the analytic to process the stream")
@click.pass_context
def proxy(ctx, port, analytic_addr):
    """ Starts a proxy server which connects to an RTSP stream and forwards frames to an analytic or StreamFilter using the gRPC service library."""
    proxy_svc = StreamingProxy(
        name=__name__, port=port, analytic_addr=analytic_addr)
    sys.exit(proxy_svc.Run())


@serve.command()
@click.option("--grpc/--no-grpc", default=True, help="If true, runs the filter with the grpc service.")
@click.option("--grpc_port", default=50051, help="Port that the gRPC endpoint runs on (if configured).")
@click.option("--port", "-p", default=3000, help="Port the configuration endpoint runs on.")
@click.option("--filter_port", default=50000, help="Port that the filtering service runs on.")
@click.option("--analytic_addr", "-a", default="localhost:50051", help="Address of the analytic to process the stream")
@click.option("--verbose/--no-verbose", "-v", default=False, help="Display verbose output of the service.")
@click.pass_context
def streamfilter(ctx, grpc, grpc_port, port, filter_port, analytic_addr, verbose):
    """ 
    Start up a 'StreamFilter' server which can be used to modify indivdual frames en route to an analytic. The endpoint 
    running on the 'filter_port' can be used to change the types and magnitudes of the filters applied to each frame.
    """
    frame_filter = FrameFilter()
    client = aceclient.AnalyticClient(addr=analytic_addr)

    def degrade_grpc(handler):
        orig_frame = handler.get_frame()
        frame = frame_filter.filter(orig_frame, handler)
        resp = client.process_frame(frame)
        handler.merge_response(resp)
        handler.add_encoded_frame(frame)

    if grpc:
        svc = grpcservice.AnalyticServiceGRPC(verbose=verbose)
        svc.RegisterProcessVideoFrame(degrade_grpc)
        proxysvc = grpcservice.ProxySvc(__name__, frame_filter, port=filter_port)
        t1 = threading.Thread(target=svc.Run, kwargs=dict(analytic_port=int(grpc_port)), daemon=True)
        t2 = threading.Thread(target=proxysvc.run)
        print("Starting grpc service.")
        t1.start()
        print("Starting filter service.")
        t2.start()
    else:
        print("RTSP filter not implemented")
        return


@main.group()
@click.pass_context
@click.option("--db_addr", "-d", default=None, help="Address of the influx database to use")
def stream(ctx, db_addr):
    """Subcommand for directly streaming video (frame by frame) to an analytic running the gRPC service"""
    ctx.ensure_object(Context)
    ctx.obj.db = None
    if db_addr:
        addr_list = db_addr.split(":")
        if len(addr_list) != 2:
            raise ValueError("Address must be of the form <host>:<port>")
        logging.info("Connecting to database. Host: {!s} Port: {!s}".format(
            addr_list[0], addr_list[1]))
        ctx.obj.db = aceclient.AceDB(host=addr_list[0], port=addr_list[1])


@stream.command()
@click.pass_context
@click.option('--video-file', '-v', help='Path to video file being processed.', type=click.Path())
@click.option("--analytic_addr", "-a", default=[], multiple=True, help="Address of the analytic to process the stream.")
def video(ctx, video_file, analytic_addr):
    """Stream the contents of a video file to an analytic"""
    if not analytic_addr:
        analytic_addr = ["localhost:50051"]
    db = ctx.obj.db
    client = aceclient.AnalyticMultiClient()
    classes = {}
    cap = cv2.VideoCapture(video_file)
    window_names = []
    f_req = analytic_pb2.FrameRequest()
    for a in analytic_addr:
        analytic = analytic_pb2.AnalyticData()
        analytic.addr = a
        f_req.analytics.append(analytic)
    # Load all frames into a queue buffer
    buf = Queue()
    while (cap.isOpened()):
        ret, frame = cap.read()
        if not ret:
            break
        buf.put(frame)
    try:
        while not buf.empty():
            frame = buf.get(block=False)
            resp = analytic_pb2.CompositeResults()
            resp = client.process_frame(frame, f_req, resp)
            render(resp, window_names, classes, frame, db)
    finally:
        cv2.destroyAllWindows()
        print("Shutting down")


@stream.command()
@click.option("--analytic_addr", "-a", default=[], multiple=True, help="Address of the analytic to process the stream.")
@click.option('--cam_id', '-c', default=0, help="The numerical identifier for the camera/webcam.  Default is 0.")
@click.option("--width", '-w', default=640, help="Width of the video (pixels)")
@click.option("--height", '-h', default=480, help="Height of the video (pixels)")
@click.pass_context
def camera(ctx, cam_id, analytic_addr, width, height):
    """Stream the live camera feed from "cam_id" to an analytic"""
    if not analytic_addr:
        analytic_addr = ["localhost:50051"]
    db = ctx.obj.db
    client = aceclient.AnalyticMultiClient()
    cap = cv2.VideoCapture(int(cam_id))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(width))
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(height))
    classes = {}
    window_names = []
    f_req = analytic_pb2.FrameRequest()
    for a in analytic_addr:
        analytic = analytic_pb2.AnalyticData()
        analytic.addr = a
        f_req.analytics.append(analytic)
    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                print("Stream unavailable. Exiting.")
                break
            resp = analytic_pb2.CompositeResults()
            resp = client.process_frame(frame, f_req, resp)
            print(len(window_names))
            render(resp, window_names, classes, frame, db)
    finally:
        cv2.destroyAllWindows()
        print("Shutting down")


@main.group()
@click.pass_context
def test(ctx):
    """ Perform simple functionality tests to ensure that the system is configured properly"""
    pass


@test.command()
@click.option("--src", required=True, help="Stream source to send to analytic")
@click.option("--analytic_addr", default="localhost:50051", help="Analytic to process the stream.")
@click.option("--verbose/--no-verbose", default=False, help="Displays additional output.")
@click.pass_context
def analytic(ctx, src, analytic_addr, verbose):
    """
    Process a stream using an ACE analytic and display the output (with any bounding boxes) to the user. The 
    verbose flag can be used to output the analytic output data to the terminal"""

    client = TestClient(src, analytic_addr=analytic_addr, verbose=False)
    client.run()


@test.command()
@click.option("--src", required=True, help="Source of the RTSP stream to test")
@click.option("--verbose/--no-verbose", default=False, help="Displays additional output.")
@click.pass_context
def rtsp(ctx, src, verbose):
    print("Testing RTSP stream. Streaming directly to host. No analytics used.")
    client = TestClient(src, analytic_addr=None, verbose=verbose)
    client.run()


@test.command()
@click.pass_context
@click.option('--cam_id', '-c', default=0, help="The numerical identifier for the camera/webcam.  Default is 0.")
@click.option("--verbose/--no-verbose", '-v', default=True, help="Prints additional debug output if true")
def camera(ctx, cam_id, verbose):
    """Test that the client is able to access the camera. Displays live feed from specified camera"""
    client = ctx.obj.client
    cap = cv2.VideoCapture(cam_id)
    frame_num = 1
    classes = {}
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Stream unavailable. Exiting.")
                break
            if verbose:
                print(frame)
            cv2.imshow('Camera Feed', frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
            frame_num += 1
    except:
        pass

    cap.release()
    cv2.destroyAllWindows()


if __name__ == '__main__':
    main(obj=Context())
