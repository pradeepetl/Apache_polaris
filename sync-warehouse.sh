#!/usr/bin/env bash
# Sync S3 warehouse files from LocalStack to local ./data/warehouse/
# Run this after writing data to see Iceberg files on your host machine.
set -euo pipefail

cd "$(dirname "$0")"

echo "Syncing s3://warehouse/ → ./data/warehouse/ ..."
docker exec localstack awslocal s3 sync s3://warehouse/ /warehouse/ --delete
echo ""

echo "Iceberg files:"
find ./data/warehouse -type f | sort | while read -r f; do
  rel="${f#./data/warehouse/}"
  size=$(stat -f%z "$f" 2>/dev/null || stat -c%s "$f" 2>/dev/null)
  printf "  %-8s %s\n" "${size}B" "$rel"
done
echo ""
echo "Done. Browse ./data/warehouse/ to see Iceberg table structure."
