FROM datamachines/cudnn_tensorflow_opencv:10.2_2.2.0_4.3.0-20200615

ENV DEBIAN_FRONTEND noninteractive

ENV LC_ALL C.UTF-8
ENV LANG C.UTF-8

##### 
RUN apt-get -y update \
    && apt-get install -y  gir1.2-gst-rtsp-server-1.0 gstreamer1.0-rtsp gstreamer1.0-rtsp-dbg \
    libgstrtspserver-1.0-0 libgstrtspserver-1.0-0-dbg libgstrtspserver-1.0-dev libgstrtspserver-1.0-doc \
    libgstreamer-plugins-bad1.0-0 libgstreamer-plugins-base1.0-0 libgstreamer-plugins-base1.0-dev \
    libgstreamer1.0 libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev libgtk-3-dev gstreamer1.0-plugins-ugly

ADD . /ace
RUN pip3 install /ace

CMD ["/bin/bash"]
