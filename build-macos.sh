docker build -t datamachines/nist-ace:demo -f Dockerfile-macos .
cd lang/python/examples/analytics/opencv_object_detector
docker build -t ocv-ssd:demo .
cd ../test_analytic
docker build -t ace-test-analytic:demo .
cd ../activity-recognition
docker build -t act-recognition:demo .
