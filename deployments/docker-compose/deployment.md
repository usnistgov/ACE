# Example Deployment
An example `docker-compose` file is included in the repository which provides a basic deployment that can be used to demonstrate the capabilities of the ACE framework. This docker-compose file includes:
 * `video_stream`: A service which will create an mjpeg stream from a video file. 
 * `object_detector`: An object detector using OpenCV's DNN object detector API and using the  ssd_mobilenet_v2 model trained on the COCO dataset.
 * `ace`: A utility container that has the ACE library installed and is not running any services. It's purpose is to allow you to exec into the container in order run ACE commands from within the docker-compose environment.
 * `influxdb`: A time series database which can be used to store analytic results.
 * `grafana`: Browser-based UI used to visualize analytic results stored in the database.
 * `nats_server`: A lightweight NATS server used to coordinate NATS messages sent by ACE analytics.

ACE supports GPU accelerated computing, and the base container comes with all the necessary utilities (CUDA_DNN, Tensorflow, OpenCV with FFMPEG and Gstreamer). For compatibility purposes and ease of testing, the example deployment provided *_does not_* require a GPU in order to run.

## Prerequisites
1) Build the ACE and analytic containers using the instructions in the [README](../../README.md) file.
2) Modify the [`.env file`](.env) to specify the location and name of the local file (if any) that you want to stream. If you don't plan to stream a local file and instead want to test the system on an available stream, comment out the `video_stream` section in the `docker-compose.yml`.
3) Create the required volumes.
    ```bash
    $ docker volume create grafana-storage
    $ docker volume create influxdb-storage
    ```

## Running the system
You can run the docker-compose system using the command:
```bash
$ docker-compose up
```
You may choose to use the `-f` flag to specify the docker-compose file location if running the command from outside of this directory. For more information on docker-compose consult the documentation [here]([link](https://docs.docker.com/compose/))

You can do a quick test of the system using the python command line interface (CLI).

#### Test the Stream
The following command will render the stream from the `video_stream` server using the ACE CLI. 
```bash
$ python -m ace test rtsp --src rtsp://0.0.0.0:8554/test
```
This is useful to ensure that the server is able to stream the video and that you are able to connect to that stream with the ACE library.

#### Process a Stream
Once you know that you are able to connect to the stream you can configure the object detector analytic to process a stream using the ACE CLI's `config` command. The following command will configure the object detector to process the stream produced by the `video_stream` server. 
```bash
$ python -m ace config -s http://video_stream:6420/cam.mjpg
```
Alternatively, you can use the address of any available rtsp stream after the `--src` option rather than the local address provided in the commands listed above.