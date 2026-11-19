#!/bin/sh
set -e

until mc alias set myminio http://minio:9000 minioadmin minioadmin 2>/dev/null; do
  echo "Waiting for MinIO..."
  sleep 2
done

mc mb myminio/warehouse --ignore-existing
mc mb myminio/iceberg-catalog --ignore-existing

echo "MinIO buckets created successfully"
