import os
import sys

def iter_protos(parent=None):
    for root, _, files in os.walk('proto'):
        if not files:
            continue
        dest = root if not parent else os.path.join(parent, root)
        yield dest, [os.path.join(root, f) for f in files]

from setuptools import setup, find_packages

pkg_name = 'ace'

setup(name=pkg_name, 
        package_dir={
            '':'lang/python',
            },
        version='0.1.0',
        description='Protocol wrapper for streaming video analytics',
        author='Nick Burnett, Data Machines Corp.',
        author_email='nicholasburnett@datamachines.io',
        url='github.com/github.com/datamachines/nist-ace/analyticframework/lang/py',
        license='Apache License, Version 2.0',
        packages=["ace"],
        install_requires=[
          'setuptools>=41.0.0',
          'grpcio>=1.24.3, ==1.34.1', # required by TF 2.5.1
          'grpcio_health_checking>=1.15.0',
          'protobuf>=3.6.1',
          'googleapis-common-protos>=1.6.0',
          'Click>=7.0',
          'dataclasses>=0.6',
          'six>=1.12.0',
          'requests>=2.0.0',
          'flask>=1.0.0',
          'influxdb~=5.2.3',
          'kafka-python>=2.0.0',
          'asyncio-nats-client',
          'PyGObject'
            ],
        data_files=list(iter_protos(pkg_name)),
        py_modules = [
            'ace.analytic_pb2',
            'ace.analytic_pb2_grpc',
            'ace.analyticservice',
            'ace.aceclient',
            'ace.cli',
            'ace.google/rpc/__init__',
            'ace.google/rpc/status_pb2',
            'ace.google/rpc/code_pb2',
            'ace.google/rpc/error_details_pb2',
            "ace.rtsp",
            "ace.rtspserver",
            'ace.__main__',
            'ace.streamproxy'
            ])


