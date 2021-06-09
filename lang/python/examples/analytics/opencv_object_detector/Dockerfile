FROM datamachines/nist-ace:local

ENV DEBIAN_FRONTEND noninteractive

COPY . /app

WORKDIR /app

RUN wget http://download.tensorflow.org/models/object_detection/ssd_mobilenet_v2_coco_2018_03_29.tar.gz \
    && tar -C /app/models -xvf  ssd_mobilenet_v2_coco_2018_03_29.tar.gz \
    && rm ssd_mobilenet_v2_coco_2018_03_29.tar.gz

RUN wget https://raw.githubusercontent.com/opencv/opencv_extra/master/testdata/dnn/ssd_mobilenet_v2_coco_2018_03_29.pbtxt -P /app/models/ssd_mobilenet_v2_coco_2018_03_29

EXPOSE 3000

EXPOSE 50051

ENTRYPOINT ["python3", "run_detector.py"]

