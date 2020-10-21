import cv2
import argparse
import threading
import time
import os
import logging
import numpy as np
from queue import PriorityQueue

from ace import analytic_pb2, analytic_pb2_grpc
from ace.analyticservice import AnalyticService
from ace.aceclient import AnalyticClient
from ace.utils import annotate_frame

logger = logging.getLogger(__name__)

class StreamingProxy:
    def __init__(self, name, port=3000, analytic_addr=None):
        self.service = AnalyticService(name, port=port)
        self.service.RegisterProcessVideoFrame(self.proxy_process_frame)
        self.analytic_addr = analytic_addr
        if not analytic_addr:
            raise ValueError("Analytic address must be specified")
        self.client = AnalyticClient(addr=self.analytic_addr)

    def Run(self):
        self.service.Run()

    def proxy_process_frame(self, handler):
        resp = self.client.process_frame(handler.get_frame(), session_id=handler.resp.session_id)
        handler.resp = resp


class TestClient:
    def __init__(self, videosrc, analytic_addr="localhost:50051", verbose=False):
        self.src = videosrc
        self.analytic_addr = analytic_addr
        self.cap = cv2.VideoCapture(self.src, cv2.CAP_FFMPEG)
        self.verbose = verbose
        if self.verbose:
            print("Testing if stream is accessible and video is being captured: {!s}".format(self.verbose))
        if not self.cap.isOpened():
            raise ValueError("No video stream")
        if self.analytic_addr:
            print("Establishing gRPC connection with analytic at {!s}".format(self.analytic_addr))
            self.client = AnalyticClient(self.analytic_addr)
        self.current_frame = 0
        self.buffer = PriorityQueue()

    def load_frames(self):
        if self.verbose:
            print("Initializing frame loader")
        while self.cap.isOpened():
            ret, frame = self.cap.read()
            if not ret:
                print("Stream unavailable")
                return
            self.buffer.put(
                (-1 * self.current_frame, (time.time(), self.current_frame, frame)))
            self.current_frame += 1

    def start(self):
        t = threading.Thread(target=self.load_frames, daemon=True)
        t.start()
        while self.buffer.empty():
            print("Loading buffer")
            time.sleep(.5)
        print("Buffer loaded, starting stream")

    def run(self):
        self.start()
        analytic = analytic_pb2.AnalyticData()
        if self.analytic_addr:
            analytic.addr = self.analytic_addr
        window_names = ["Analytic Results"]
        classes = {}
        db = None
        curr_frame = 0
        while True:
            if self.buffer.empty():
                time.sleep(1)
            _, frame_obj = self.buffer.get()
            # print(frame_obj)
            if frame_obj[1] < curr_frame:
                time.sleep(0.1)
                continue
            curr_frame = frame_obj[1]
            frame = frame_obj[2]
            if self.analytic_addr:
                resp = self.client.process_frame(frame)
                resp.analytic.MergeFrom(analytic)
                if resp.frame.frame.ByteSize() > 0:
                    img_bytes = np.fromstring(resp.frame.frame.img, dtype=np.uint8)
                    frame = cv2.imdecode(img_bytes, 1)
                frame = annotate_frame(resp, frame, classes, db)
            cv2.imshow(window_names[0], frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", "-p", default=3000,
                        help="Port that the REST config service runs on.")
    parser.add_argument("--analytic_addr", "-a",
                        default="[::]:50051", help="Address of the gRPC analytic to send frames to.")
    args = parser.parse_args()
    proxy_svc = StreamingProxy(
        name=__name__, port=args.port, analytic_addr=args.analytic_addr)
    proxy_svc.Run()
