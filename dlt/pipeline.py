import dlt
import requests
from datetime import datetime, timezone


USGS_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"

POLARIS_CONFIG = {
    "type": "rest",
    "uri": "http://polaris:8181/api/catalog",
    "warehouse": "polaris_warehouse",
    "credential": "root:s3cr3t",
    "scope": "PRINCIPAL_ROLE:ALL",
    "header.Polaris-Realm": "POLARIS",
    "py-io-impl": "pyiceberg.io.fsspec.FsspecFileIO",
    "s3.endpoint": "http://localstack:4566",
    "s3.access-key-id": "test",
    "s3.secret-access-key": "test",
    "s3.path-style-access": "true",
}


@dlt.resource(name="events", write_disposition="append", table_format="iceberg")
def earthquake_events():
    print("Fetching earthquakes from USGS...")
    resp = requests.get(USGS_URL, timeout=30, verify=False)
    resp.raise_for_status()
    data = resp.json()

    features = data.get("features", [])
    print(f"Got {len(features)} earthquake events")

    for f in features:
        props = f.get("properties", {})
        coords = f.get("geometry", {}).get("coordinates", [None, None, None])
        yield {
            "earthquake_id": f.get("id"),
            "magnitude": props.get("mag"),
            "place": props.get("place"),
            "event_time": datetime.fromtimestamp(props["time"] / 1000, tz=timezone.utc).isoformat() if props.get("time") else None,
            "updated_time": datetime.fromtimestamp(props["updated"] / 1000, tz=timezone.utc).isoformat() if props.get("updated") else None,
            "longitude": coords[0],
            "latitude": coords[1],
            "depth_km": coords[2],
            "tsunami": bool(props.get("tsunami")),
            "event_type": props.get("type"),
            "title": props.get("title"),
            "status": props.get("status"),
            "magnitude_type": props.get("magType"),
            "significance": props.get("sig"),
            "felt_reports": props.get("felt"),
            "alert_level": props.get("alert"),
            "url": props.get("url"),
        }


def register_in_polaris():
    """Ensure the Iceberg table in Polaris points to the latest metadata on S3."""
    from pyiceberg.catalog import load_catalog
    import s3fs

    cat = load_catalog("polaris", **POLARIS_CONFIG)

    try:
        cat.create_namespace("earthquakes")
        print("Created namespace 'earthquakes'")
    except Exception:
        pass

    fs = s3fs.S3FileSystem(endpoint_url="http://localstack:4566", key="test", secret="test")
    metadata_dir = "warehouse/polaris_warehouse/earthquakes/events/metadata"
    if not fs.exists(metadata_dir):
        print("No metadata found on S3 yet, skipping registration")
        return

    metadata_files = sorted([f for f in fs.ls(metadata_dir) if f.endswith(".metadata.json")])
    if not metadata_files:
        print("No metadata.json found, skipping registration")
        return

    latest = f"s3://{metadata_files[-1]}"

    existing = [t[1] for t in cat.list_tables("earthquakes")]
    if "events" in existing:
        tbl = cat.load_table("earthquakes.events")
        current = tbl.metadata_location
        if current == latest:
            print(f"Table already points to latest metadata")
            return
        print(f"Updating table: {current} -> {latest}")
        cat.drop_table("earthquakes.events")

    print(f"Registering table from {latest}")
    cat.register_table("earthquakes.events", latest)
    print("Table 'earthquakes.events' registered in Polaris!")


if __name__ == "__main__":
    print("=" * 50)
    print("dlt Earthquake Ingestion Pipeline")
    print("=" * 50)

    pipeline = dlt.pipeline(
        pipeline_name="earthquake_ingest",
        destination="filesystem",
        dataset_name="earthquakes",
    )

    info = pipeline.run(earthquake_events())
    print(f"\nPipeline load complete!")
    print(info)

    print("\nRegistering table in Polaris catalog...")
    register_in_polaris()
    print("\nDone!")
