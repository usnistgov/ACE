# ACE
v1.0

## Table of Contents
- [ACE](#ace)
  - [Table of Contents](#table-of-contents)
  - [Overview](#overview)
  - [Demo Application](#demo-application)
  - [Quickstart](#quickstart)
    - [Preset Containers](#preset-containers)
    - [Prerequisites](#prerequisites)
    - [Python Installation](#python-installation)
    - [Example Deployment](#example-deployment)
    - [Testing the system](#testing-the-system)
  - [ACE API](#ace-api)
  - [ACE Command Line Tools](#ace-command-line-tools)
  - [ACE Services](#ace-services)
    - [Stream Filter](#stream-filter)
    - [Proxy](#proxy)
    - [RTSP Server](#rtsp-server)
  - [Analytic Wrapper](#analytic-wrapper)
    - [gRPC Wrapper](#grpc-wrapper)
    - [Using the Analytic Wrapper](#using-the-analytic-wrapper)
      - [Create a Docker Container for Analytic](#create-a-docker-container-for-analytic)
  - [Integrating Other Services with ACE](#integrating-other-services-with-ace)
      - [InfluxDB](#influxdb)
      - [Grafana](#grafana)
      - [Event Streaming](#event-streaming)


## Overview
The Analytics Container Environment (ACE) is a tool developed in support of the National
Institute of Standards and Technology (NIST) 
[Public Safety Communications Research](https://www.nist.gov/ctl/pscr/about-pscr) (PSCR) 
Division, which provides a modular framework for running containerized analytics on 
streaming video. As is under active development.

The purpose of the NIST ACE project is to enable easier prototyping of cutting edge analytics to the public safety community. ACE aims to overcome some of the current challenges in prototyping analytics to the public safety community, which include technical challenges such as the lack of standard interfaces between analytics, the experimental nature of analytics (not designed to function as a part of a pipeline or distributed system), and the “black box” nature of analytics. Public safety organizations face other logistical, policy, and resource challenges as well, but our hope is that by addressing the technical challenges and reducing the cost and complexity of deploying analytics over the course of the NIST ACE project, interested organizations will be able to experiment with and utilize analytics in their environments.

Thus far our goal has been to create an open source, modular, analytic microservice framework and toolkit that would serve several purposes: 
* To provide analytic researchers and developers with tools and libraries to easily turn their analytics into ACE microservices, allowing them to more easily incorporate their analytics into ACE-based systems, as well as providing them with a means of easily testing their analytics.
* To provide public safety end users with a simple framework that would allow them to easily deploy and use analytics without requiring subject matter expertise and significant coding.The goal is for adopters to be able to pick and choose the analytics that they want to run, deploy them, and have them begin working with minimal configuration.
* To provide open source tools which allow for easy test and experimentation using the framework. This includes collecting stream and analytic data throughout the pipeline and providing tools such as proxies and filters that allow users to modify a stream.

To attempt to accomplish these goals we have developed the ACE Framework, a scalable framework that uses containerized analytic microservices to create flexible, analytic workflows for processing streaming data. This microservice framework provides several advantages over standalone software or monolithic pipelines, including ease of customization (analytics can be added, removed, or updated without needing to stop or modify the code of an existing system), extensibility (new services can be added to extend or fork currently running analytic pipelines), and scalability (additional replicas of a given analytic can be deployed to better manage workloads).

ACE provides a suite of tools which can be used to construct analytic workflows as well as a set of well defined APIs for analytics and other services. Components have built in data collection utilities allowing for greater transparency of system and analytic performance. An overview of what has been developed is provided below:
* Well defined APIs for streaming video analytics which support tasks such as detection/classification, localization, and applying filters/operations to video frames.
* An analytic service library (wrapper) for creating an analytic service (that implements the API) from new or existing analytics. This limits development time/effort required to integrate an analytic within the system.
* A client library for communicating with analytic microservices and the framework API server. This library can be used by command-line tools or as a backend for graphical user interfaces (GUIs).
* A command-line interface (CLI), based on the client library, which can be used to talk to analytic microservices and other system components. The CLI can also be used to start up special containerized analytic tools called “StreamFilters”, which can be configured to modify stream parameters (such as applying additional compression, changing the resolution, or degrading the stream in other ways). These analytics expose a unique API, which allows these parameters to be altered in real-time.
* Dockerfile

## Demo Application
A demo application using ACE is available [here](https://github.com/usnistgov/ace-ui). This demo application uses a web-based UI to configure analytics and display detections and alerts to the user. In order to use the demo application you will need to build the ACE containers (run the `build.sh` script).

## Quickstart

### Preset Containers
To build the ACE base containers and analytic containers, run the `build.sh` script. This will build local ACE containers tagged as `datamachines/nist-ace:demo`.

### Prerequisites
ACE is a microservice framework whose components are designed to run as containerized microservices, ideally managed by an orchestration layer such as Kubernetes, Docker Swarm, or Docker Compose. 
ACE was built with Kubernetes in mind and will run best on Linux, however Docker Compose can be used for testing and prototyping deployments (an example deployment is included in this repository)
, and most services can be run on MacOS*. ACE does not currently run on Windows and support for Windows is not planned at this time.

ACE requires Python 3.8 or higher.

  \* Accessing the webcam using an ACE container is currently not possible on MacOS

### Python Installation
To run ACE command line tools first install ACE and dependencies
 * Install a virtual environment to manage Python packages for different projects. `virtualenv` allows users to avoid installing Python packages globally which could break system tools or other pojects.
    ```bash
   $ python3 -m pip install --user virtualenv
    ```
 * Create a virtualenv `env` in base directory of ACE repository
    ```bash
    $ python3 -m venv env
    ```

 * Activate virtualenv
    ```bash
    $ source env/bin/activate
    ```
    
 * Install OpenCV ([Linux Installation](https://docs.opencv.org/master/d7/d9f/tutorial_linux_install.html)) ([Mac Installation](https://docs.opencv.org/master/d0/db2/tutorial_macos_install.html)) or you can install via pip 
   ```bash
   $ pip install opencv-python
   ```
 * Install the ACE library and Kafka. 
   From the root of the repository run:
   ```bash
   $ pip install .
   ``` 

### Example Deployment
An example `docker-compose` file is included in the repository which provides a basic deployment that can be used to demonstrate the capabilities of the ACE framework. This docker-compose file includes:
 * `camera_stream`: A service which (if running on a linux machine) will create an RTSP stream using your webcam. It is commented out by default. Uncomment the section in the `docker-compose.yml` file in order to create the stream.
 * `object_detector`: An object detector using OpenCV's DNN object detector API and using the  ssd_mobilenet_v2 model trained on the COCO dataset.
 * `ace`: A utility container that has the ACE library installed and is not running any services. It's purpose is to allow you to exec into the container in order run ACE commands from within the docker-compose environment.
 * `influxdb`: A time series database which can be used to store analytic results.
 * `grafana`: Browser-based UI used to visualize analytic results stored in the database.

ACE supports GPU accelerated computing, and the base container comes with all the necessary utilities (CUDA_DNN, Tensorflow, OpenCV with FFMPEG and Gstreamer). For compatibility purposes and ease of testing, the example deployment provided *_does not_* require a GPU in order to run.

To use this deployment you will need to build the ACE and object detector containers as well as create two docker volumes. 
* You can run the `build.sh` script to build the containers used in the docker-compose deployment
  ```bash
  $ bash build.sh
  ```
* The necessary volumes can be built with the following commands
  ```bash
  $ docker volume create grafana-storage
  $ docker volume create influxdb-storage
  ```

Once the containers and volumes have been created you can bring up the deployment
```bash
$ docker-compose up
```
### Testing the system
You can do a quick test of the system using the python command line interface (CLI).
1) First start the docker-compose deployment. If running on linux, you can first uncomment the `camera_stream` section to create an RTSP stream from your webcam.
```bash
$ docker-compose up 
```
2) In another terminal, activate your virtual environment (e.g., `source env/bin/activate`) and then use the ACE CLI to process an RTSP stream using ACE. The following command will stream your webcam to the ACE CLI and test that you are able to successfully connect to the stream..
```bash
$ python -m ace test rtsp --src rtsp://0.0.0.0:8554/test
```
3) If the RTSP test was successful you can run the following command to test that the deployed analytic is able to process the stream:
```bash
$ python -m ace test analytic --src rtsp://0.0.0.0:8554/test
```
Alternatively, in both cases,you can use the address of any available rtsp stream after the `--src` option rather than the local address provided in the commands listed above..

## ACE API
ACE provides a consistent API for commuicating with streaming video analytics. This API is defined using Google Protocol Buffers and relies on a simple request/response pattern. While at the moment the ACE API only supports individual frames, support for additional analytic input types (e.g., small frame baches) is planned. The API can be found in the [analytic.proto](https://github.com/datamachines/NIST-ACE/blob/develop/proto/ace/analytic.proto) file. Any analytic that implements this API can be used with the ACE framework by leveraging the gRPC analytic proxy. This proxy (which is described in detail below) can be used to pass individual frames from a stream to an analytic via gRPC.

Alternatively, developers can use the analytic service library included with the ACE library
to create an analytic which can be easily incorporated into the ACE framework. This service  
library acts as a wrapper and decodes the video stream into individual frames and passes
them directly to the analytic without requiring encoding/decoding or additional network 
communication (as is the case when using the gRPC proxy). Additionally, as the API is 
improved to include support for other input types the wrapper will be updated as well.

## ACE Command Line Tools
The ACE Python command line interface (CLI) can be used to interact with ACE components and analytics. After installing the ACE library you can see a list of available ACE commands:
```bash
$ python -m ace --help

The ACE command line client provides a tool for configuring analytics and
  other ACE components as well  as providing users with a means of sending
  frames directly to analytics running in the system. This CLI can also be
  used to run other ACE services, such as creating an RTSP server.

Options:
  -d, --db_addr TEXT  Address of the database to connect to
  --help              Show this message and exit.

Commands:
  config  Command used to configure the specified analytic to connect to an...
  kill    Command used to terminate the connection between the specified analytic and the video source. 
  serve   Subcommnad for serving video for use by ACE components.
  stream  Subcommand for directly streaming video (frame by frame) to an...
  test    Perform simple functionality tests to ensure that the system is...
```
The CLI has two primary uses. 
1) The CLI can be used to configure ACE analytics, such as the deployed object detector, using the `config` command. This allows the user to
specify which stream the analytic should process and what the analytic should do with the results. Available options:
```
-s, --stream_source TEXT  Address of the stream for the analytic to process.[required]

-k, --kafka_addr TEXT     Address of the Kafka broker to which the analytic will send output metadata.

-d, --db_addr TEXT        Address of the database to which the analytic will write output.

--analytic_host TEXT      Address of the analytic to connect to.

--analytic_port INTEGER   Port that the configuration endpoint runs on for the analytic.
```
2) The CLI can be used to start up ACE services, such as an RTSP stream server, an analytic proxy, or a StreamFilter

## ACE Services

### Stream Filter
The stream filter is a service which can be used to apply filters to a stream before passing data to an analytic. At
present it applies filters on a frame by frame basis and serves as a proxy that modifies the frame prior to passing the 
request to the analytic. Currently the stream filter can do operations such as changing the level of JPEG compression, 
resizing the image, blurring the image, and pixelating the image (degrading it through a process where is resized to a 
smaller size and then back to the original size). The stream filter uses two APIs: The analytic API is used to receive the
request (and the analytic client is used to pass the request to the analytic), and a separate filter API is used to adjust 
the filters which are applied to the frames.

You can start up a stream filter service by using the `streamfilter` command:
```bash
$ python -m ace serve streamfilter --help
Start up a 'StreamFilter' server which can be used to modify indivdual
  frames en route to an analytic. The endpoint  running on the 'filter_port'
  can be used to change the types and magnitudes of the filters applied to
  each frame.

Options:
  --grpc / --no-grpc            If true, runs the filter with the grpc
                                service.

  --grpc_port INTEGER           Port that the gRPC endpoint runs on (if
                                configured).

  -p, --port INTEGER            Port the configuration endpoint runs on.
  --filter_port INTEGER         Port that the filtering service runs on.
  -a, --analytic_addr TEXT      Address of the analytic to process the stream
  -v, --verbose / --no-verbose  Display verbose output of the service.
  --help                        Show this message and exit.
```

A client command for adjusting the filters is provided in the CLI as well and can be used with the `filter` command
```bash
$ python -m ace filter --help
Applies the specified filter(s) to the stream processed by the
  StreamFilter at the host and port specified.

Options:
  -f, --fil TEXT             Filters to applied to the stream, of the form
                             '<filter>=<value>'.

  -h, --filter_host TEXT     Host address of the filter
  -p, --filter_port INTEGER  Port for the filtering service
  --help                     Show this message and exit.
```

### Proxy
The proxy service provides a way to process a stream send individual frames to an analytic microservice implementing the 
gRPC/Protobuf API. It can be very useful for running experiments when used in conjunction with the stream filter service. 
In most cases, the proxy connects to a video stream and passes individual frames to the analytic for which is acts as a 
proxy. When used with a stream filter it can instead be used to send individual frames to the filter, which in turn 
performs operations on those frames before sending them to the analytic (since it is itself a form of proxy). So while
 using the proxy can result in additional network traffic, it also provides a means to get better visibility into the 
analytic pipeline and perform additional measurements.

To create an analytic proxy, use the following command:
<pre>
python3 -m ace serve proxy -h [HOST] -p [PORT]
</pre>

The available flags are
<pre> 
-h, --host TEXT   Host the service runs listens on.
-p, --port TEXT   Port the service runs listens on. 
</pre>

### RTSP Server
An RTSP service can be started using the `serve rtsp` subcommands. 
```bash
$ python -m ace serve rtsp [options] --src [stream source]

Starts a GStreamer Server using the source provided (can be connected
  camera or external RTSP stream) on the specified endpoint.

Options:
  --src TEXT                    Source of the stream.
  --endpoint TEXT               Endpoint of for the RTSP stream
  -v, --verbose / --no-verbose  Show additional debug info
  --help                        Show this message and exit.
```

## Analytic Wrapper
The analytic wrapper is a service library which implements the necessary 
functions to process the stream and metadata. This library sets up a service 
which processes a specified stream. For convenience it allows developers to 
register functions with different endpoints based on what type of data the 
analytic processes (e.g., frames, frame batches, or an RTSP stream), though currently 
only the API for individual frames is supported. Once the 
library has connected to a stream it will process the data accordingly (extract 
frames or batches) and provide those to the registered function. That function 
receives a request message and returns a response message. These objects are 
defined in the .proto file. The exact objects used are dependent on the function 
registered, and helper functions are provided to simplify the process of 
retrieving data from the request object and inserting metadata into the response 
object. The service library handles the transmission of the analytic output 
metadata.

A separate configuration API allows for the analytic to be reconfigured once 
deployed. This provides a convenient mechanism for altering the stream that the 
analytic is watching. It also provides a way to tweak parameters in the service 
library, such as the encoding and resolution used for frames.

### gRPC Wrapper
Additionally, there is a gRPC wrapper, which implements a stricter version of 
the API defined in the protobuf. While the above wrapper connects directly to a 
stream and passes frames and metadata to the analytic, this wrapper sets up a 
gRPC endpoint which accepts requests to process individual frames. In essence it
splits the above wrapper into two steps separated by gRPC. In this case a proxy 
processes the stream, creates a request to process a frame, and then passes this 
to the analytic that implements the wrapper.

### Using the Analytic Wrapper

Example Python Wrapping Code:
<pre>
from ace import grpcservice, analytic_pb2, utils
from analytic import Detector   # algorithm created by analytic developer

def detect(req, resp):
    frame = util.load_frame(req)
    detector = Detector()
    results = detector.Detect(frame)
    resp = util.load_results(results)

if __name__ == "__main__":
    svc = grpcservice.AnalyticServiceGRPC()
    svc.register_name("My Analytic")
    svc.RegisterProcessVideoFrame(detect)
    sys.exit(svc.Run())
</pre>

#### Create a Docker Container for Analytic
To simplicfy the process of building and deploying ACE analytics, we provide
an ACE base container, built using the included `Dockerfile`, and hosted on 
dockerhub as `datamachines/nist-ace`. This container includes key analytic 
development libraries, such as OpenCV, Tensorflow, and Nvidia CUDA DNN 
libraries, as well as the ACE libary. Analytics deployed using this as a base 
container will be able to leverage GPU optimization and use cutting edge machine 
learning and computer vision libraries without needing to worry about 
installation and managing dependencies.

The ACE base container runs the command line tool by default, and can also be 
used to easily create other services, such as stream filters and proxies. The
example deployment provided (`docker-compose.yaml`) does exactly this.

Below is an example example Dockerfile showing how the ACE container can be used 
as a base container for an analytic:
<pre>
FROM datamachines/nist-ace:0.1

ENV DEBIAN_FRONTEND noninteractive

COPY . /app

WORKDIR /app

EXPOSE 3000

EXPOSE 50051

ENTRYPOINT ["python3", "my-analytic.py"]
</pre>

## Integrating Other Services with ACE
ACE provides a standard API for streaming video analytics, but it can leverage 
existing time-series databases and message queues to process the analytic output 
data. Currently ACE supports InfluxDB, NATS, and Kafka, with the analytic wrapper 
outputing data to the specified services (specified using the configuration API).

#### InfluxDB
ACE uses InfluxDB because ACE works with streaming data. InfluxDB is a time-series database, which works well with the streaming data. InfluxDB records every single object that is detected from metadata passed back from the analytic. This includes time, which analytics are being run, what object being detected, data metrics, file sizes, and runtime are put into InfluxDB. It pulls and records all of the elements necessary for analyzinng analytics in the ACE system. These metrics are designed to provide information to the user about what is happening with the analytic as a whole.

#### Grafana
Grafana's purpose is to accept the data from InfluxDB. InfluxDB is the datasource into Grafana. That data is able to be visualized to the user in real-time. Grafana is a tool that lets users to easily see the data as it is happening, which can be important to see the effects video manipulations have on analytic performance. In addition, Grafana is useful for visualizing logging, compute and system performance. This is opposed to looking at the raw data. Grafana allows users to view particular values of interest with query restraints.

Grafana allows users to create and/or modify dashboards that are relevant to analytics running in the ACE system. This gives users a great deal of customization. Any query possible in InfluxDB is possible to be visualized in Grafana.

[Adding data source in Grafana](https://grafana.com/docs/grafana/latest/features/datasources/influxdb/)


#### Event Streaming

ACE services can be configured to publish results to a message queue using event streaming platforms such as Kafka and NATS (support for both is included with the ACE library). Services can be written to consume analytic results from these queues for use by other programs or for displaying data to a user through a UI or log.
NATS is deployed as part of ACE within `Docker-Compose`. 

For more information regarding NATS, please refer to the [documentation.](https://nats.io/)
