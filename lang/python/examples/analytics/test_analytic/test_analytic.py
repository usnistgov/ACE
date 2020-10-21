import argparse
import cv2
import json
import logging
import os
import sys

import numpy as np

from ace import analyticservice, analytic_pb2, grpcservice


def detect(handler):
    logger.debug("I/O test: Getting frame from handler")
    frame = handler.get_frame()
    logging.info("I/O test: Frame size: {!s}".format(frame.shape))
    logger.debug("I/O test: Getting frame as jpeg from handler")
    # frame_jpeg = handler.get_frame(format="JPEG")
    # logger.info("I/O test: Got frame as jpeg. Size: {!s} bytes".format(len(frame_jpeg)))

    logger.info("Library test: Adding bounding box with classification 'test")
    handler.add_bounding_box(classification="test", confidence=0.314,
                             x1=int(len(frame[:, 0, 0])/3),
                             y1=int(len(frame[0, :, 0])/3),
                             x2=int(len(frame[:, 0, 0])*2/3),
                             y2=int(len(frame[0, :, 0])*2/3))
    logger.info("Library test: Bounding box added to middle of image")
    logger.info("Library test: Frame number {!s}, Frame timestamp {!s}".format(handler.frame_number, handler.timestamp))
    logger.info("Library test: Analytic Metadata: {!s}".format(handler.get_analytic_metadata))
    logger.info("Adding frame to response")
    handler.add_frame_info(include_frame=True)
    logger.info("Adding tags 'test=True' and 'LuckyNumber=7'")
    handler.add_tags(test=True, LuckyNumber=7)
    logger.info("Finished tests for frame")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--grpc", default=False, help="If true this analytic will set up a gRPC frame processing service rather than a REST config service", action="store_true")
    parser.add_argument("--grpc_port", default=50051, help="Port the analytic will run on when in 'gRPC mode.'")
    parser.add_argument("--config_port", default=3000, help="Port the analaytic configuration endpoint runs on.")

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    args = parser.parse_args()

    if args.grpc:
        svc = grpcservice.AnalyticServiceGRPC()
        svc.register_name("test_frame_analytic_grpc")
        svc.RegisterProcessVideoFrame(detect)
        sys.exit(svc.Run(analytic_port=args.grpc_port))
    else:
        svc = analyticservice.AnalyticService(__name__)
        svc.register_name("test_frame_analytic")
        svc.RegisterProcessVideoFrame(detect)
        sys.exit(svc.Run())
