FROM python:3.11-slim

COPY trino.crt /usr/local/share/ca-certificates/trino.crt
RUN update-ca-certificates
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

RUN pip install --no-cache-dir \
    marimo \
    "trino[sqlalchemy]" \
    "pyiceberg[s3fs,pyarrow]" \
    pandas \
    boto3 \
    requests

RUN useradd -m marimo
USER marimo
WORKDIR /home/marimo/notebooks

EXPOSE 2718

ENTRYPOINT ["marimo", "edit", "--host", "0.0.0.0", "--port", "2718", "--no-token", "/home/marimo/notebooks"]
