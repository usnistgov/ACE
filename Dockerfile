ARG ACE_FROM
FROM ${ACE_FROM}

ENV DEBIAN_FRONTEND noninteractive

ENV LC_ALL C.UTF-8
ENV LANG C.UTF-8

# Upgade system packages
RUN apt-get update -y --fix-missing \
  && apt-get upgrade -y --no-install-recommends \
  && apt-get clean

# Install needed libraries
RUN apt-get -y update \
    && apt-get install -y  gir1.2-gst-rtsp-server-1.0 gstreamer1.0-rtsp gstreamer1.0-rtsp-dbg \
    libgstrtspserver-1.0-0 libgstrtspserver-1.0-0-dbg libgstrtspserver-1.0-dev libgstrtspserver-1.0-doc \
    libgstreamer-plugins-bad1.0-0 libgstreamer-plugins-base1.0-0 libgstreamer-plugins-base1.0-dev \
    libgstreamer1.0 libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev libgtk-3-dev gstreamer1.0-plugins-ugly \
    libgirepository1.0-dev \
    && apt-get clean

# Update pip
RUN wget -q -O /tmp/get-pip.py --no-check-certificate https://bootstrap.pypa.io/get-pip.py \
  && python3 /tmp/get-pip.py \
  && pip3 install -U pip \
  && rm /tmp/get-pip.py

ADD . /ace
RUN pip3 install  --use-feature=in-tree-build /ace

CMD ["/bin/bash"]
