FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    "dlt[pyiceberg]" \
    pyarrow \
    s3fs \
    requests \
    "sqlalchemy>=2.0.18"

COPY ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

COPY .dlt/ .dlt/
COPY pipeline.py .

CMD ["python", "pipeline.py"]
