import cv2
import argparse
import concurrent.futures
import threading
import time
import os
import logging
import numpy as np
import signal
import traceback
from google.protobuf import json_format
from queue import PriorityQueue
from ace import analytic_pb2, analytic_pb2_grpc
from ace.utils import annotate_frame


os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;udp"
logger = logging.getLogger(__name__)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

class AnalyticWorker:
    def __init__(self, func, input_buffer, output_queue):
        # self.client = AnalyticClient(analytic_addr)
        self.buffer = input_buffer
        self.output_queue = output_queue
        self.func = func
        self.is_running = False

    def run(self, kill_event):
        """ When there are frames in the buffer, an individual frame is sent to an analytic and metadata is send back. That frame is then send to the the output queue."""
        self.is_running = True
        try:
            while not kill_event.is_set():
                if self.buffer.empty():
                    logger.info("No frames in queue, sleeping")
                    time.sleep(0.1)
                frame_obj = self.buffer.pop()
                # TODO pass flag for buffer size, allowing for frame buffers to be inserted instead of just frames (4-D tensor)
                if not frame_obj:
                    logger.info("Empty queue, skipping")
                    continue
                # Frame Object contains (timestamp, frame_number, frame)
                resp = self.func(frame_obj)
                # Reusing FrameBuffer class. Note that the "frame" is a CompositeResult object
                self.output_queue.push(
                    (resp, frame_obj[2]), frame_number=frame_obj[1], frame_timestamp=frame_obj[0])
        except Exception as e:
            logger.info("Analytic worker threw exception: {!s}".format(e))
        finally:
            self.is_running = False


class FrameWorker:
    def __init__(self, cap, buffer):
        self.cap = cap
        self.buffer = buffer
        self.is_running = False

    def run(self, kill_event):
        """ This checks if there's a valid video stream frame and checks if there's an event to stop the stream. It reads the frame and sends it to the queue. If the video stream is not valid, an even to kill the the stream and its workers is set. """
        self.is_running = True
        print(self.cap.isOpened())
        try:
            while self.cap.isOpened() and not kill_event.is_set():
                ret, frame = self.cap.read()
                if not ret:
                    logger.warning("Unable to pull frame")
                    time.sleep(0.1)
                self.buffer.push(frame)
        except Exception as e:
            logger.info("Frameworker threw exception: {!s}".format(e))
        finally:
            self.cap.release()
            if not kill_event.is_set():
                kill_event.is_set()
            self.is_running = False


class FrameBuffer(PriorityQueue):
    def __init__(self, realtime=True):
        self.queue = PriorityQueue(0)
        self.realtime = realtime
        self.curr_num = 0   # most recent frame added to the queue
        self.last_pop = 0   # the last frame popped off of the buffer
        self.log = {"push": {}, "pop": {}}

    def push(self, frame, frame_number=None, frame_timestamp=None):
        """Push a frame into the buffer with the timestamp and frame number.  If self.realtime is true then higher frames will be prioritized (negative of the framenumber is used for prioritization). Otherwise it functions as a normal priority queue."""
        self.curr_num += 1
        if not frame_number:
            frame_number = self.curr_num
        if not frame_timestamp:
            frame_timestamp = time.time()
        key = (-1 * self.realtime + 1 - self.realtime) * \
            frame_number  # frame_numnber =  -frame_number if realtime
        self.queue.put((key, (frame_timestamp, frame_number, frame)))
        self.log["push"][frame_timestamp] = self.curr_num

    def pop(self):
        """Returns frame object (timestamp, frame number, frame). If self.realtime is True, then it returns the most recently inserted frame_obj, otherwise it acts as a FIFO queue."""
        num, frame_obj = self.queue.get()
        if abs(num) < self.last_pop:
            return None
        self.last_pop = abs(num)
        self.log["pop"][frame_obj[0]] = abs(num)

        return frame_obj

    def empty(self):
        return self.queue.empty()

    def get_fps(self, window=1.0, action="pop"):
        """ Returns the calculated frames per second. 
        """
        curr_time = time.time()

        frames = [i for i in list(self.log[action].keys())
                  if i < curr_time and i > curr_time - window]
        logging.debug(frames)
        return len([i for i in list(self.log[action].keys()) if i < curr_time and i > curr_time - window])/(window)

    def flush(self):
        """ The frame queue is cleared."""
        with self.queue.mutex:
            self.queue.queue.clear()


class RTSPHandler:
    def __init__(self, videosrc, func, cap_width=None, cap_height=None, realtime=True, analytic_data=None,
                 producer=None, num_workers=1, verbose=True, render_frames=False):
        self.func = func
        self.src = videosrc
        self.num_workers = num_workers
        self.is_running = False
        self.kill = threading.Event()
        self.producer = producer
        self.db_client = None
        self.verbose = verbose
        self.render = render_frames

        self.cap = cv2.VideoCapture(self.src, cv2.CAP_FFMPEG)

        if not self.cap.isOpened():
            raise ValueError("No video stream")
        logger.info("Connected to video stream at: {!s}".format(self.src))

        self.buffer = FrameBuffer(realtime=realtime)
        self.output_queue = FrameBuffer(realtime=False)
        self.workers = self.create_workers()

        self.terminated = False
        self.termination_event = threading.Event()
        self.workers_running = False
        self.frames_loading = False

    def create_workers(self):
        """ Returns a FrameWorker equal to the number of analytics in use. The FrameWorker reads a frame and sends it to the queue."""
        workers = [FrameWorker(cap=self.cap, buffer=self.buffer)]
        for i in range(self.num_workers):
            wkr = AnalyticWorker(self.func, self.buffer, self.output_queue)
            workers.append(wkr)
        return workers

    def add_producer(self, producer):
        self.producer = producer

    def add_database(self, db_client):
        self.db_client = db_client

    def run(self):
        """
        Run service to read from RTSP stream and call registered function.
        """
        classes = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.num_workers+1) as executor:
            for i in range(len(self.workers)):
                executor.submit(self.workers[i].run, self.kill)
            while not self.kill.is_set():
                if self.output_queue.empty():
                    if self.verbose:
                        logger.debug("Empty output queue")
                    time.sleep(0.5)
                    continue

                output = self.output_queue.pop()
                resp, frame = output[2]
                if self.producer:
                    try:
                        topic = "{!s}.{!s}".format(
                            resp.analytic.name, resp.analytic.addr.split(":")[0])
                        logger.debug("Publishing to kafka topic: {!s}".format(topic))
                        self.producer.send(topic, value=resp)
                    except Exception as e:
                        logger.debug("Exception thrown while trying to publish results to Kafka (as topic {!s}): {!s}".format(
                            topic, e))
                if self.db_client:
                    try:
                        logger.debug("Database Entry: ",
                                self.db_client.json_from_resp(resp))
                        self.db_client.write_proto(resp)
                    except Exception as e:
                        raise ValueError("Error writing database entry: {!s}".format(e))

                if self.render:
                    frame = annotate_frame(resp, frame, classes, None)
                    cv2.imshow(self.src, frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break

                if self.verbose:
                    print(resp)

    def terminate(self):
        """ Safely turns quits the RTSP stream and it associated workers
        """
        logger.info("Termination signal received")
        self.kill.set()
        safe_shutoff = False
        while safe_shutoff == False:
            safe_shutoff = True
            for worker in self.workers:
                logger.info("Worker running: ", worker.is_running)
                if worker.is_running == True:
                    logger.info("Worker still running")
                    safe_shutoff = False
                    break
            time.sleep(0.2)
        logger.debug("Workers safely shut down")
        logger.info("RTSP service terminated")
