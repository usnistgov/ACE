docker build --no-cache -t datamachines/nist-ace:0.1 .
cd lang/python/examples/analytics/opencv_object_detector
docker build --no-cache -t ocv-ssd:0.1 .
cd ../test_analytic
docker build --no-cache -t ace-test-analytic:0.1 .
