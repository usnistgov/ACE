# Needed SHELL since I'm using zsh
SHELL := /bin/bash
.PHONY: all build_prep nistacedemo

# Decide which "no-cache" policy you want for your builds
#ACE_NOCACHE="--no-cache"
ACE_NOCACHE=

ACE_FROM_MACOS="datamachines/tensorflow_opencv:2.5.1_4.5.3-20210810"
ACE_FROM_LINUX="datamachines/cudnn_tensorflow_opencv:11.2.2_2.5.1_4.5.3-20210810"
# Make sure to check the python dependencies for TF in nist-ace_demo builds and reflect TF issues in setup.py

all:
	@echo "** Available Docker images to be built (make targets):"
	@echo "  nist-ace_demo:   Core"
	@echo "  nist-ace_extra:  Core + Extra components"
	@echo ""
	@echo "** To build all, use: make build_all"


build_prep:
	@$(eval CTO_OS=$(shell if [ "A"`uname` == "ADarwin" ]; then echo "Darwin"; else echo "Linux"; fi))
	@$(eval ACE_FROM=$(shell if [ "A${CTO_OS}" == "ADarwin" ]; then echo ${ACE_FROM_MACOS}; else echo ${ACE_FROM_LINUX}; fi ))
	@ACE_FROM=${ACE_FROM} make nistacedemo

nistacedemo:
	docker build ${ACE_NOCACHE} --build-arg ACE_FROM="${ACE_FROM}" -t datamachines/nist-ace:demo -f Dockerfile .

nist-ace_demo:
	@make build_prep

nist-ace_extra:
	@make build_prep
	cd lang/python/examples/analytics/opencv_object_detector
	docker build ${ACE_NOCACHE} -t ocv-ssd:demo .
	cd ../test_analytic
	docker build ${ACE_NOCACHE} -t ace-test-analytic:demo .
	cd ../activity-recognition
	docker build ${ACE_NOCACHE} -t act-recognition:demo .
