# OpenCV Object Detector Analytic

## Dependencies
* python3
* OpenCV >=4.0.0
* ACE Library
* Model files (Default model files can be downloaded to the default location using the commands listed below. This allows you to run the object detector using the default arguments. Different model files and classes can be specified as flags when running the object detector but it is left to the user to obtain them.)
```bash
$ wget http://download.tensorflow.org/models/object_detection/ssd_mobilenet_v2_coco_2018_03_29.tar.gz \
    && tar -C models -xvf  ssd_mobilenet_v2_coco_2018_03_29.tar.gz \
    && rm ssd_mobilenet_v2_coco_2018_03_29.tar.gz

$ wget https://raw.githubusercontent.com/opencv/opencv_extra/master/testdata/dnn/ssd_mobilenet_v2_coco_2018_03_29.pbtxt -P models/ssd_mobilenet_v2_coco_2018_03_29
```

## Running the Object Detector
To run the object detector with default parameters:
```bash
$ python3 run_detector.py
```
By default the object detector uses the ssd_mobilenet_v2 trained on the COCO dataset ([tensorflow model files](https://github.com/tensorflow/models/blob/master/research/object_detection/g3doc/tf1_detection_zoo.md), [opencv dnn files](https://github.com/opencv/opencv_extra/tree/master/testdata/dnn)). It also uses the RTSP wrapper by default, allowing it to connect directly to an RTSP stream and process individual frames. When running the object detector in this way use the `confg` command on the python cli to send a configuration request to the object detector, providing the detector with the address of the RTSP stream and the address of the Kafka broker and/or database to use for publishing detector outputs.

The detector supports multiple flags:
```
--grpc      If true the object detector will use the grpc wrapper, allowing GRPC "ProcessFrameRequests" to be sent to the analytic in lieu of connecting to an RTSP stream

--grpc_port     The port that the object detector will run on if using the grpc wrapper.

--model        Path to the model file to load.

--model_config  Path to the prototext config file for the model.

--classes       Path to a json file mapping detector output to classes. The file "coco.json" is provided by default.

--verbose       Provides more verbose output for debugging.
```

To run the analytic either build and run the analyic container (using the provided Dockerfile) or run the detector in a terminal or tmux session. While the analytic is running use the CLI to test the object detector.


## Quick Test
To run a quick test, start the analytic with the `--grpc` flag and then use the CLI to connect to the object detector.

To stream a webcam to the object detector: 
```bash
$ python -m ace stream camera 
```
If you have multiple cameras you can specify the ID of the camera:
```bash
$ python -m ace stream camera --cam_id <id>
```

To process an RTSP stream use the `test rtsp` command:
```bash
$ python -m ace test rtsp --src <rtsp stream address>
```

While not the best for showcasing this particular object detector you can use the following stream from a highway camera to test the object detector:
```bash
$ python -m ace test rtsp --src rtsp://170.93.143.139/rtplive/470011e600ef003a004ee33696235daa
```