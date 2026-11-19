FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    "dlt[pyiceberg]" \
    pyarrow \
    s3fs \
    requests \
    "sqlalchemy>=2.0.18"

COPY .dlt/ .dlt/
COPY pipeline.py .

CMD ["python", "pipeline.py"]
