#!/usr/bin/python3
"""
THE CODE COPIED FROM HERE AND UPDATED TO STREAM VIDEO FILES AND MODIFIED TO INCLUDE STREAMING FROM FILE/VIDEO UrL
https://gist.github.com/n3wtron/4624820


Author: Igor Maculan - n3wtron@gmail.com
A Simple mjpg stream http server
"""
import argparse
import http
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

import cv2


class CamHandler(BaseHTTPRequestHandler):

    def __init__(self, request, client_address, server):
        img_src = 'http://{}:{}/cam.mjpg'.format(server.server_address[0], server.server_address[1])
        self.html_page = """
            <html>
                <head></head>
                <body>
                    <img src="{}"/>
                </body>
            </html>""".format(img_src)
        self.html_404_page = """
            <html>
                <head></head>
                <body>
                    <h1>NOT FOUND</h1>
                </body>
            </html>"""
        BaseHTTPRequestHandler.__init__(self, request, client_address, server)

    def do_GET(self):
        if self.path.endswith('.mjpg'):
            self.send_response(http.HTTPStatus.OK)
            self.send_header('Content-type', 'multipart/x-mixed-replace; boundary=--jpgboundary')
            self.end_headers()
            while True:
                try:
                    img = self.server.read_frame()
                    retval, jpg = cv2.imencode('.jpg', img)
                    if not retval:
                        raise RuntimeError('Could not encode img to JPEG')
                    jpg_bytes = jpg.tobytes()
                    self.wfile.write("--jpgboundary\r\n".encode())
                    self.send_header('Content-type', 'image/jpeg')
                    self.send_header('Content-length', len(jpg_bytes))
                    self.end_headers()
                    self.wfile.write(jpg_bytes)
                    time.sleep(self.server.read_delay)

                except (IOError, ConnectionError):
                    break
        elif self.path.endswith('.html'):
            self.send_response(http.HTTPStatus.OK)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(self.html_page.encode())
        else:
            self.send_response(http.HTTPStatus.NOT_FOUND)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(self.html_404_page.encode())    


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in a separate thread."""

    def __init__(self, capture_path, server_address, loop_play, RequestHandlerClass, bind_and_activate=True):
        HTTPServer.__init__(self, server_address, RequestHandlerClass, bind_and_activate)
        ThreadingMixIn.__init__(self)
        try:
            # verifies whether is a webcam
            capture_path = int(capture_path)
        except TypeError:
            pass
        except ValueError:
            pass
        self._capture_path = capture_path
        fps = 30
        self.read_delay = 1. / fps
        self._lock = threading.Lock()
        self._camera = cv2.VideoCapture(capture_path)
        self.loop_play = loop_play

    def open_video(self):
        if not self._camera.open(self._capture_path):
            raise IOError('Could not open video {}'.format(self._capture_path))

    def read_frame(self):
        with self._lock:
            retval, img = self._camera.read()
            if not retval:
                self.open_video()
                if self.loop_play:
                    retval, img = self._camera.read()
                    return img
        return img

    def serve_forever(self, poll_interval=0.5):
        self.open_video()
        try:
            super().serve_forever(poll_interval)
        except KeyboardInterrupt:
            self._camera.release()

    # def serve_with_interrupt(self, poll_interval=0.5):
    #     self.open_video()
    #     try:



class VideoFileServer(ThreadedHTTPServer):
    def __init__(self, video_path:str, address:str = "0.0.0.0", port: int = 6420, loop: bool = True):
        ThreadedHTTPServer.__init__(self, video_path, (address, port), loop, CamHandler)

    def run(self):
        self.serve_forever()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--video-input', required=True ,help='Specify a video file path, rtsp stream address or camera value')
    parser.add_argument('-p', '--port', default=6420, type=int)
    parser.add_argument('-a', '--address', default="0.0.0.0")
    parser.add_argument("--loop", default=True, action="store_true", help="Loop video")
    args = parser.parse_args()
    server = VideoFileServer(args.video_input, args.address, args.port, args.loop)

    print("project credit https://gist.github.com/n3wtron/4624820")
    print('{} served on http://{}:{}/cam.mjpg'.format(args.video_input, args.address, args.port))
    server.run()


if __name__ == '__main__':
    main()
