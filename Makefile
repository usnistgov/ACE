# Needed SHELL since I'm using zsh
SHELL := /bin/bash
.PHONY: all build_prep nistacedemo

# Decide which "no-cache" policy you want for your builds
#ACE_NOCACHE="--no-cache"
ACE_NOCACHE=

ACE_FROM_CPU="datamachines/tensorflow_opencv:2.5.1_4.5.3-20210810"
ACE_FROM_GPU="datamachines/cudnn_tensorflow_opencv:11.2.2_2.5.1_4.5.3-20210810"
# Make sure to check the python dependencies for TF in nist-ace_demo builds and reflect TF issues in setup.py

all:
	@echo "** Available Docker images to be built (make targets):"
	@echo "  GPU core base container: ${ACE_FROM_GPU}"
	@echo "    gpu_nist-ace_demo:   Core with GPU base container"
	@echo "    gpu_nist-ace_extra:  Core (with GPU) + Extra components"
	@echo "  CPU core base container: ${ACE_FROM_CPU}"
	@echo "    cpu_nist-ace_demo:   Core without GPU base container"
	@echo "    cpu_nist-ace_extra:  Core (without GPU) + Extra components"

build_gpu:
	@ACE_FROM=${ACE_FROM_GPU} make nistacedemo

build_cpu:
	@ACE_FROM=${ACE_FROM_CPU} make nistacedemo

nistacedemo:
	docker build ${ACE_NOCACHE} --build-arg ACE_FROM="${ACE_FROM}" -t datamachines/nist-ace:demo -f Dockerfile .

build_ace_extra:
	cd lang/python/examples/analytics/opencv_object_detector && docker build ${ACE_NOCACHE} -t ocv-ssd:demo .
	cd lang/python/examples/analytics/test_analytic && docker build ${ACE_NOCACHE} -t ace-test-analytic:demo .
	cd lang/python/examples/analytics/activity_recognition && docker build ${ACE_NOCACHE} -t act-recognition:demo .
	cd lang/python/examples/camera_stream && docker build ${ACE_NOCACHE} -t camera_stream:demo .

gpu_nist-ace_demo:
	@make build_gpu

gpu_nist-ace_extra:
	@make gpu_nist-ace_demo
	@make build_ace_extra

cpu_nist-ace_demo:
	@make build_cpu

cpu_nist-ace_extra:
	@make cpu_nist-ace_demo
	@make build_ace_extra
