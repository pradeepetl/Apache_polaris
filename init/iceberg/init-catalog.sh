#!/bin/bash
set -e

export PGPASSWORD=trino123

# Create iceberg_catalog database if it doesn't exist
DB_EXISTS=$(psql -h postgres -U trino -d trino_demo -tAc "SELECT 1 FROM pg_database WHERE datname='iceberg_catalog'")
if [ "$DB_EXISTS" != "1" ]; then
  psql -h postgres -U trino -d trino_demo -c "CREATE DATABASE iceberg_catalog;"
  echo "Created iceberg_catalog database"
fi

# Create Iceberg metadata tables
psql -h postgres -U trino -d iceberg_catalog <<'SQL'
CREATE TABLE IF NOT EXISTS iceberg_tables (
  catalog_name varchar(255) NOT NULL,
  table_namespace varchar(255) NOT NULL,
  table_name varchar(255) NOT NULL,
  metadata_location varchar(1000),
  previous_metadata_location varchar(1000),
  PRIMARY KEY(catalog_name, table_namespace, table_name)
);
CREATE TABLE IF NOT EXISTS iceberg_namespace_properties (
  catalog_name varchar(255) NOT NULL,
  namespace varchar(255) NOT NULL,
  property_key varchar(5500),
  property_value varchar(5500),
  PRIMARY KEY (catalog_name, namespace, property_key)
);
SQL

echo "Iceberg catalog initialized"
