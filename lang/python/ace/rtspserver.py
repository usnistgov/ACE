
import argparse
import logging
import os
import signal
import threading
import time
from queue import PriorityQueue

import cv2
import gi
import numpy as np
from gi.repository import GObject, Gst, GstRtspServer

from ace import analytic_pb2, analytic_pb2_grpc
from ace.utils import annotate_frame

gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')


def data_from_cap(self, src, length):
    """ Once there's a valid video stream, the GStreamer buffer is set with the type of metadata needed for data transfer.
    """
    if self.cap.isOpened():
        ret, frame = self.cap.read()
        if ret:
            data = frame.tostring()
            buf = Gst.Buffer.new_allocate(None, len(data), None)
            buf.fill(0, data)
            buf.duration = self.duration
            timestamp = self.number_frames * self.duration
            buf.pts = buf.dts = int(timestamp)
            buf.offset = timestamp
            self.number_frames += 1
            retval = src.emit('push-buffer', buf)
            if self.verbose:
                print('pushed buffer, frame {}'.format(self.number_frames))
            if retval != Gst.FlowReturn.OK:
                print(retval)


class SensorFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self, cap, width=640, height=480, on_need_data=data_from_cap, verbose=False, **properties):
        super(SensorFactory, self).__init__(**properties)
        self.verbose = verbose
        self.data_func = on_need_data
        self.cap = cap
        print("Capture device status: {!s}".format(
            {True: "Opened", False: "Closed"}[self.cap.isOpened()]))
        self.number_frames = 0
        self.fps = 30.0
        self.duration = 1 / self.fps * Gst.SECOND  # duration of a frame in nanoseconds
        self.launch_string = 'appsrc name=source is-live=true block=true format=GST_FORMAT_TIME ' \
                             'caps=video/x-raw,format=BGR,width={!s},height={!s},framerate=30/1 ' \
                             '! videoconvert ! video/x-raw,format=I420 ' \
                             '! x264enc speed-preset=ultrafast tune=zerolatency threads=4 ' \
                             '! rtph264pay config-interval=1 name=pay0 pt=96'.format(
                                 width, height)

    def on_need_data(self, src, length):
        self.data_func(self, src, length)

    def do_create_element(self, url):
        return Gst.parse_launch(self.launch_string)

    def do_configure(self, rtsp_media):
        self.number_frames = 0
        appsrc = rtsp_media.get_element().get_child_by_name('source')
        appsrc.connect('need-data', self.on_need_data)


class GstServer(GstRtspServer.RTSPServer):
    def __init__(self, cap, endpoint="/test", verbose=False, **properties):
        super(GstServer, self).__init__(**properties)
        self.factory = SensorFactory(cap, verbose=verbose)
        self.factory.set_shared(True)
        self.get_mount_points().add_factory(endpoint, self.factory)
        self.attach(None)
        print("Running on {!s}:{!s}{!s}".format(
            self.get_address(), self.get_service(), endpoint))
