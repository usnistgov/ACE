import argparse
import json
import logging
import os
import sys

import cv2
import numpy as np

from ace import analytic_pb2, analyticservice, grpcservice


def detect(handler):
    logger.debug("I/O test: Getting frame batch from handler")
    batch = handler.get_frame_batch()
    logging.info("I/O test: Frame batch size: {!s}. Frames of shape {!s}".format(len(batch), batch[0].shape))
    

    logger.info("Library test: Adding bounding box with classification 'test")
    handler.add_bounding_box(classification="test", confidence=0.314,
                             x1=int(len(batch[0][:, 0, 0])/3),
                             y1=int(len(batch[0][0, :, 0])/3),
                             x2=int(len(batch[0][:, 0, 0])*2/3),
                             y2=int(len(batch[0][0, :, 0])*2/3))
    logger.info("Library test: Bounding box added to middle of image")
    logger.info("Library test: Frame numbers {!s}, Frame timestamps {!s}".format(handler.frame_numbers, handler.timestamps))
    logger.info("Library test: Analytic Metadata: {!s}".format(handler.get_analytic_metadata))
    logger.info("Adding frame to response")
    handler.add_frame_info(include_frame=True)
    logger.info("Adding tags 'test=True' and 'LuckyNumber=7'")
    handler.add_tags(test=True, LuckyNumber=7)
    logger.info("Finished tests for frame")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config_port", default=3000, help="Port the analaytic configuration endpoint runs on.")

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    args = parser.parse_args()


    svc = analyticservice.AnalyticService(__name__)
    svc.register_name("test_frame_analytic")
    svc.RegisterProcessFrameBatch(detect, batch_size=16)
    sys.exit(svc.Run())
