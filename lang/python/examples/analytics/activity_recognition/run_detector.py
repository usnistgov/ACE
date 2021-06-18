import argparse
import json
import logging
import os
import sys

import cv2
import numpy as np

from ace import analytic_pb2, analyticservice, grpcservice

SAMPLE_DURATION = 16
SAMPLE_SIZE = 112

def get_labels(filename):
    labels = []
    with open(filename) as f:
        for row in f:
            labels.append(row[:-1])
    return labels

def load_net(model):
    return cv2.dnn.readNet(model)

def detect(handler):
    
    frames = handler.get_frame_batch()   
    blob = cv2.dnn.blobFromImages(frames, 1.0, (SAMPLE_SIZE, SAMPLE_SIZE), (114.7748, 107.7354, 99.4750), swapRB=True, crop=True)
    blob = np.transpose(blob, (1, 0, 2, 3))
    blob = np.expand_dims(blob, axis=0)
    
    net.setInput(blob)
    outputs = net.forward()
    class_pred = np.argmax(outputs)  
    label = labels[class_pred]
    
    handler.add_tags(activity=label)
    

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config_port", default=3000, help="Port the analaytic configuration endpoint runs on.")
    parser.add_argument("--model", "-m", default="resnet-34-kinetics.onnx", help="Path to the model file to load")
    parser.add_argument("--labels", "-l", default="action_recognition_kinetics.txt", help="Path to class labels")
    args = parser.parse_args()
    
    net = load_net(args.model)
    labels = get_labels(args.labels)

    svc = analyticservice.AnalyticService(__name__, verbose=True)
    svc.register_name("test_frame_analytic")
    svc.RegisterProcessFrameBatch(detect, batch_size=16)
    sys.exit(svc.Run())
