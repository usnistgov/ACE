import argparse
import concurrent.futures
import logging
import os
import signal
import threading
import time
import traceback
from queue import PriorityQueue

import cv2
import numpy as np
from google.protobuf import json_format

from ace import analytic_pb2, analytic_pb2_grpc
from ace.utils import annotate_frame

os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;udp"
logger = logging.getLogger(__name__)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class AnalyticWorker:
    def __init__(self, func, input_buffer, output_queue, params=None):
        self.buffer = input_buffer
        self.output_queue = output_queue
        self.func = func
        self.is_running = False
        self.params = params or {}
        self.batch_size = self.params.get("batch_size", 1)

    def run(self, kill_event):
        """ When there are frames in the buffer, an individual frame is sent to an analytic and metadata is send back. That frame is then send to the the output queue."""
        self.is_running = True
        try:
            while not kill_event.is_set():
                if self.buffer.empty():
                    logger.info("No frames in queue, sleeping")
                    time.sleep(0.1)
                    continue
                frame_batch_obj = self.buffer.pop()
                # TODO pass flag for buffer size, allowing for frame buffers to be inserted instead of just frames (4-D tensor)
                if not frame_batch_obj:
                    logger.info("Empty queue, skipping")
                    continue
                # Frame Object contains (timestamp, frame_number, frame)
                resp = self.func(frame_batch_obj)
                # Reusing FrameBuffer class. Note that the "frame" is a CompositeResult object
                # print("PUSHING RESULTS")
                self.push_results(resp, frame_batch_obj)
                # self.output_queue.push(
                #     (resp, frame_batch_obj[2]), frame_number=frame_obj[1], frame_timestamp=frame_obj[0])
        except Exception as e:
            logger.exception(f"Analytic worker threw exception while trying to process frame: {e}")
        finally:
            self.is_running = False

    def push_results(self, resp, frame_batch_obj):
        if resp.DESCRIPTOR.name == 'ProcessedFrame':
            self.output_queue.push((resp, frame_batch_obj[0][2]), frame_number=frame_batch_obj[0][1], frame_timestamp=frame_batch_obj[0][0])
            return

        for i, r in enumerate(resp.processed_frames):
            self.output_queue.push((r, frame_batch_obj[i][2]), frame_number=frame_batch_obj[i][1], frame_timestamp=frame_batch_obj[i][0])


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
                    time.sleep(0.5)
                    continue
                self.buffer.push(frame)
        except Exception:
            logger.exception("Frameworker threw exception while trying to pull frame")
        finally:
            self.cap.release()
            if not kill_event.is_set():
                kill_event.is_set()
            self.is_running = False


class FrameBuffer(PriorityQueue):
    def __init__(self, realtime=True, q_size=0):
        self.queue = PriorityQueue(q_size)
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
        # print("Pushing frame {!s}".format(self.curr_num))

    def pop(self, num_frames=1):
        #TODO
        """Returns frame object (timestamp, frame number, frame). If self.realtime is True, then it returns the most recently inserted frame_obj, otherwise it acts as a FIFO queue."""
        frame_batch_obj = []
        # print("Popping frame/batch")
        for i in range(num_frames):
            num, frame_obj = self.queue.get()
            # print("\t - Popping frame: {!s}. Last popped was {!s}".format(abs(num), self.last_pop))
            if abs(num) < self.last_pop:
                # TODO inspect queue before popping to see if there are N frames to grab
                print("\t - Frames out of order")
                for frame_obj in frame_batch_obj:
                    print("Adding frame {!s} back into the queue".format(frame_obj[1]))
                    self.push(frame_obj[2], frame_number=frame_obj[1], frame_timestamp=frame_obj[0])
                return None    
            if not frame_batch_obj or frame_obj[1] > frame_batch_obj[-1][1]:
                frame_batch_obj.append(frame_obj)
                continue
            self.log["pop"][frame_obj[0]] = abs(num)
            frame_batch_obj.insert(0, frame_obj)
        
        self.last_pop = abs(num)
       

        return frame_batch_obj

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
                 producer=None, num_workers=1, verbose=True, return_frame=False, stream_id=None, params=None):
        self.func = func
        self.src = videosrc
        self.num_workers = num_workers
        self.is_running = False
        self.kill = threading.Event()
        self.producer = producer
        self.db_client = None
        self.verbose = verbose
        self.return_frame = return_frame
        self.params = params

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

        try:
            self.subject = "stream.{!s}.analytic.{!s}".format(
                                stream_id, analytic_data.addr.split(":")[0])
        except Exception as e:
            print("ERROR CREATING TOPIC NAME: {!s}".format(e))
            self.subject = "stream.default.analytic.default"

        if self.producer:
            print("WRITING UPDATES TO SUBJECT {!s} AT ADDRESS {!s}".format(sefl.subject, self.producer.addr))
        else:
            print("No NATS address given.") 

    def create_workers(self):
        """ Returns a FrameWorker equal to the number of analytics in use. The FrameWorker reads a frame and sends it to the queue."""
        workers = [FrameWorker(cap=self.cap, buffer=self.buffer)]
        for i in range(self.num_workers):
            wkr = AnalyticWorker(self.func, self.buffer, self.output_queue, params=self.params)
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
        print("Starting run function")
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.num_workers+1) as executor:
            for i in range(len(self.workers)):
                executor.submit(self.workers[i].run, self.kill)
            print("Created workers. entering while loop")
            while not self.kill.is_set():
                try:
                    if self.output_queue.empty():
                        logger.debug("Empty output queue")
                        if self.verbose:
                            print("No frames in output queue. Sleeping...")
                        time.sleep(0.5)
                        continue
                    
                    frame_batch_output = self.output_queue.pop()
                    resp, frame = frame_batch_output[0][2]
                    
                    if self.producer:
                        try:
                            logger.debug("Publishing to topic: {!s}".format(self.subject))
                            print("Publishing to topic: {!s}".format(self.subject))
                            self.producer.send(subject=self.subject, msg=resp)
                        except Exception:
                            logger.exception("Trying to publish results to message service (as topic {!s})".format(
                                self.subject))
                    if self.db_client:
                        try:
                            logger.debug("Database Entry: \n{}".format(self.db_client.json_from_resp(resp)))
                            self.db_client.write_proto(resp)
                        except Exception as e:
                            raise ValueError("Error writing database entry: {!s}".format(e))


                    if self.verbose:
                        print(resp)
                except Exception as e:
                    logger.exception(e)

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
