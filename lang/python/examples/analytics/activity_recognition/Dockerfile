FROM datamachines/nist-ace:local

ENV DEBIAN_FRONTEND noninteractive

COPY . /app

WORKDIR /app

RUN wget -O resnet-34-kinetics.onnx https://www.dropbox.com/s/065l4vr8bptzohb/resnet-34_kinetics.onnx?dl=1

EXPOSE 3000

EXPOSE 50051

ENTRYPOINT ["python3", "run_detector.py"]

