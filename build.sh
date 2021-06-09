docker build --no-cache -t datamachines/nist-ace:demo .
cd lang/python/examples/analytics/opencv_object_detector
docker build --no-cache -t ocv-ssd:demo .
cd ../test_analytic
docker build --no-cache -t ace-test-analytic:demo .
cd ../activity-recognition
docker build --no-cache -t act-recognition:demo .
