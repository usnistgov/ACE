FROM datamachines/nist-ace:local

ENV DEBIAN_FRONTEND noninteractive

COPY . /app

WORKDIR /app

EXPOSE 3000

EXPOSE 50051

ENTRYPOINT ["python3", "test_analytic.py"]

