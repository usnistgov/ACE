import argparse
import json
import os
import sys
import time

import cv2
import numpy as np

from ace import analytic_pb2, analyticservice, grpcservice


def detect(handler):
    print("Processing frame!!")
    frame = handler.get_frame()

    img_ht, img_width, _ = frame.shape
    net.setInput(cv2.dnn.blobFromImage(frame, size=(300, 300), swapRB=True))
    output = net.forward()
    
    for detection in output[0, 0, :, :]:
        confidence = detection[2]
        if confidence > confThreshold:
            classification = classes[str(int(detection[1]))]
            handler.add_bounding_box(classification=classification, 
                    confidence=confidence, x1=int(detection[3] * img_width), y1=int(detection[4] * img_ht), 
                    x2=int(detection[5] * img_width), y2=int(detection[6] * img_ht))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--grpc", default=False, help="If true, this analytic will set up a gRPC service instead of a REST service.", action="store_true")
    parser.add_argument("--grpc_port", default=50051, help="Port the analytic will run on.")
    parser.add_argument("--model", default="models/ssd_mobilenet_v2_coco_2018_03_29/frozen_inference_graph.pb", help="Model file to load")
    parser.add_argument("--model_config", default="models/ssd_mobilenet_v2_coco_2018_03_29/ssd_mobilenet_v2_coco_2018_03_29.pbtxt", help="Model config file location")
    parser.add_argument("--classes", default="coco.json", help="JOSN file mapping output vector to class names")
    parser.add_argument("--verbose", "-v", default=False, help="Display additional output.", action="store_true")
    parser.add_argument("--confidence_threshold", default=0.5, help="Confidence threshold for detection. Any object with a confidence socre less than this will not be considered a detection. Default 0.5")

    args = parser.parse_args()
    confThreshold = args.confidence_threshold
    with open(args.classes, 'r') as f:
        classes = json.load(f)

    net = cv2.dnn.readNet(args.model, args.model_config)
    
    if args.grpc:
        svc = grpcservice.AnalyticServiceGRPC()
        svc.register_name("opencv_object_detector")
        svc.RegisterProcessVideoFrame(detect)
        sys.exit(svc.Run(analytic_port=args.grpc_port))
    else:
        svc = analyticservice.AnalyticService(__name__, verbose=args.verbose)  
        svc.register_name("opencv_object_detector")
        svc.RegisterProcessVideoFrame(detect)
        sys.exit(svc.Run())
