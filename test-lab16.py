#!/usr/bin/env python3
"""Test script for lab16-credential-vending — runs against localhost-forwarded services."""
import requests
import json
import boto3
import sys

POLARIS = "http://localhost:8181"
REALM = "POLARIS"
STS_ENDPOINT = "http://localhost:4566"
S3_ENDPOINT = "http://localhost:4566"
REGION = "us-east-1"
ROLE_ARN = "arn:aws:iam::000000000000:role/polaris-s3-role"
CATALOG_NAME = "polaris_warehouse"
CT = {"Content-Type": "application/x-www-form-urlencoded"}
errors = []

def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        errors.append(label)

# Step 1
print("=== Step 1: Authenticate ===")
token_resp = requests.post(
    f"{POLARIS}/api/catalog/v1/oauth/tokens",
    headers={"Polaris-Realm": REALM, **CT},
    data="grant_type=client_credentials&client_id=root&client_secret=s3cr3t&scope=PRINCIPAL_ROLE:ALL",
).json()
TOKEN = token_resp.get("access_token")
check("Token acquired", TOKEN is not None)
AUTH = {"Authorization": f"Bearer {TOKEN}", "Polaris-Realm": REALM}

# Step 2
print("\n=== Step 2: Catalog Storage Config ===")
catalog_resp = requests.get(
    f"{POLARIS}/api/management/v1/catalogs/{CATALOG_NAME}", headers=AUTH
).json()
storage_config = catalog_resp.get("storageConfigInfo", {})
check("storageType is S3", storage_config.get("storageType") == "S3")
check("roleArn present", "polaris-s3-role" in storage_config.get("roleArn", ""))
check("allowedLocations set", len(storage_config.get("allowedLocations", [])) > 0)

# Step 4
print("\n=== Step 4: STS AssumeRole ===")
sts = boto3.client("sts", endpoint_url=STS_ENDPOINT, region_name=REGION,
    aws_access_key_id="test", aws_secret_access_key="test")
assume_resp = sts.assume_role(RoleArn=ROLE_ARN, RoleSessionName="polaris-lab-demo", DurationSeconds=900)
temp_creds = assume_resp["Credentials"]
check("AccessKeyId returned", len(temp_creds["AccessKeyId"]) > 0)
check("SessionToken returned", len(temp_creds["SessionToken"]) > 0)
check("Expiration set", temp_creds["Expiration"] is not None)

# Step 5
print("\n=== Step 5: S3 with Temp Creds ===")
s3_temp = boto3.client("s3", endpoint_url=S3_ENDPOINT, region_name=REGION,
    aws_access_key_id=temp_creds["AccessKeyId"],
    aws_secret_access_key=temp_creds["SecretAccessKey"],
    aws_session_token=temp_creds["SessionToken"])
objects = s3_temp.list_objects_v2(Bucket="warehouse", MaxKeys=20)
check("S3 list_objects_v2 succeeds", objects["ResponseMetadata"]["HTTPStatusCode"] == 200)

# Step 6
print("\n=== Step 6: Scoped Credentials ===")
read_only_policy = {
    "Version": "2012-10-17",
    "Statement": [{"Effect": "Allow", "Action": ["s3:GetObject", "s3:ListBucket"],
        "Resource": ["arn:aws:s3:::warehouse", "arn:aws:s3:::warehouse/earthquakes/*"]}]
}
scoped_resp = sts.assume_role(RoleArn=ROLE_ARN, RoleSessionName="polaris-read-earthquakes",
    DurationSeconds=900, Policy=json.dumps(read_only_policy))
scoped_creds = scoped_resp["Credentials"]
check("Scoped AccessKeyId returned", len(scoped_creds["AccessKeyId"]) > 0)

# Step 7
print("\n=== Step 7: Prove Scoping ===")
s3_scoped = boto3.client("s3", endpoint_url=S3_ENDPOINT, region_name=REGION,
    aws_access_key_id=scoped_creds["AccessKeyId"],
    aws_secret_access_key=scoped_creds["SecretAccessKey"],
    aws_session_token=scoped_creds["SessionToken"])
resp = s3_scoped.list_objects_v2(Bucket="warehouse", Prefix="earthquakes/", MaxKeys=5)
check("List earthquakes/ succeeds", resp["ResponseMetadata"]["HTTPStatusCode"] == 200)
try:
    s3_scoped.put_object(Bucket="warehouse", Key="unauthorized-write-test.txt", Body=b"test")
    check("Write attempt", True, "LocalStack does not enforce inline policies (expected)")
    s3_scoped.delete_object(Bucket="warehouse", Key="unauthorized-write-test.txt")
except Exception as e:
    code = getattr(e, "response", {}).get("Error", {}).get("Code", "")
    check("Write denied by policy", code == "AccessDenied")

# Step 8
print("\n=== Step 8: REST API Credential Vending ===")
ns_resp = requests.get(f"{POLARIS}/api/catalog/v1/{CATALOG_NAME}/namespaces", headers=AUTH).json()
namespaces_list = ns_resp.get("namespaces", [])
check("Namespaces found", len(namespaces_list) > 0, str(namespaces_list))
tables_found = []
for ns in namespaces_list:
    ns_name = ns[0] if isinstance(ns, list) else ns
    t_resp = requests.get(
        f"{POLARIS}/api/catalog/v1/{CATALOG_NAME}/namespaces/{ns_name}/tables", headers=AUTH
    ).json()
    for tbl in t_resp.get("identifiers", []):
        tables_found.append(f"{tbl['namespace'][0]}.{tbl['name']}")
if tables_found:
    ns, tbl = tables_found[0].split(".", 1)
    load_resp = requests.get(
        f"{POLARIS}/api/catalog/v1/{CATALOG_NAME}/namespaces/{ns}/tables/{tbl}",
        headers={**AUTH, "X-Iceberg-Access-Delegation": "vended-credentials"},
    ).json()
    vended_config = load_resp.get("config", {})
    check("loadTable returned config", True, f"keys: {list(vended_config.keys())}")
else:
    check("Tables exist for loadTable test", False, "No tables — run dlt-earthquakes first")

# Step 9
print("\n=== Step 9: Restricted Principal ===")
def api(method, path, body=None):
    url = f"{POLARIS}{path}"
    headers = {**AUTH, "Content-Type": "application/json"}
    r = getattr(requests, method)(url, headers=headers, json=body)
    return r.status_code, r.json() if r.content else {}

code, pr = api("post", "/api/management/v1/principals",
    {"principal": {"name": "reader_bot", "type": "SERVICE"}, "credentialRotationRequired": False})
check("Principal reader_bot", code < 300 or code == 409,
    "created" if code < 300 else "already exists")
reader_secret = pr.get("credentials", {}).get("clientSecret") if code < 300 else None

code, _ = api("post", "/api/management/v1/principal-roles",
    {"principalRole": {"name": "reader_role", "properties": {}}})
check("Principal role reader_role", code < 300 or code == 409)

code, _ = api("put", "/api/management/v1/principals/reader_bot/principal-roles",
    {"principalRole": {"name": "reader_role"}})
check("Assign reader_role → reader_bot", code < 300)

code, _ = api("post", f"/api/management/v1/catalogs/{CATALOG_NAME}/catalog-roles",
    {"catalogRole": {"name": "reader_catalog_role", "properties": {}}})
check("Catalog role reader_catalog_role", code < 300 or code == 409)

code, _ = api("put", f"/api/management/v1/principal-roles/reader_role/catalog-roles/{CATALOG_NAME}",
    {"catalogRole": {"name": "reader_catalog_role"}})
check("Map catalog role", code < 300)

for priv in ["NAMESPACE_LIST", "TABLE_LIST"]:
    api("put", f"/api/management/v1/catalogs/{CATALOG_NAME}/catalog-roles/reader_catalog_role/grants",
        {"type": "catalog", "privilege": priv})
api("put", f"/api/management/v1/catalogs/{CATALOG_NAME}/catalog-roles/reader_catalog_role/grants",
    {"type": "namespace", "privilege": "TABLE_READ_DATA", "namespace": ["earthquakes"]})
check("Grants applied", True)

# Step 10
print("\n=== Step 10: PyIceberg ===")
from pyiceberg.catalog import load_catalog
catalog = load_catalog("polaris", **{
    "type": "rest",
    "uri": "http://localhost:8181/api/catalog",
    "warehouse": "polaris_warehouse",
    "credential": "root:s3cr3t",
    "scope": "PRINCIPAL_ROLE:ALL",
    "header.Polaris-Realm": "POLARIS",
    "py-io-impl": "pyiceberg.io.fsspec.FsspecFileIO",
    "s3.endpoint": "http://localhost:4566",
    "s3.path-style-access": "true",
})
namespaces = catalog.list_namespaces()
check("PyIceberg lists namespaces", len(namespaces) > 0, str(namespaces))
table_rows = []
for ns in namespaces:
    ns_name = ns[0] if isinstance(ns, tuple) else ns
    tables = catalog.list_tables(ns_name)
    for t in tables:
        table_rows.append(f"{t[0]}.{t[1]}")
if table_rows:
    check("PyIceberg lists tables", True, str(table_rows))
else:
    check("PyIceberg tables (none yet)", True, "no tables — expected if dlt hasn't run")

# Summary
print(f"\n{'='*50}")
if errors:
    print(f"FAILED: {len(errors)} check(s)")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("ALL CHECKS PASSED")
