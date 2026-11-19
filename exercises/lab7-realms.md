# Lab 7 — Realms (Multi-Tenant Isolation)

**Level:** 5 (Advanced) | **Time:** 30 minutes

**Goal:** Configure a second Polaris realm to demonstrate complete multi-tenant isolation. Show that catalogs, principals, and roles in one realm are invisible from another.

---

## Concepts

A **realm** is a top-level logical partition in Polaris. Everything — catalogs, principals, roles, grants — lives inside a realm. Two realms on the same Polaris server are completely isolated from each other.

```
┌─────────────────────────────────────────────────────────┐
│                    Polaris Server                        │
│                                                         │
│  ┌────────────────────┐    ┌────────────────────┐       │
│  │   Realm: POLARIS   │    │  Realm: TRAINING   │       │
│  │                    │    │                    │       │
│  │  polaris_warehouse │    │  training_catalog  │       │
│  │  ├── shop          │    │  ├── sandbox       │       │
│  │  └── earthquakes   │    │  └── demos         │       │
│  │                    │    │                    │       │
│  │  Principals:       │    │  Principals:       │       │
│  │  root, eng_alice   │    │  root (separate!)  │       │
│  │                    │    │                    │       │
│  │  Roles:            │    │  Roles:            │       │
│  │  trino_role, ...   │    │  student_role, ... │       │
│  └────────────────────┘    └────────────────────┘       │
│                                                         │
│  No cross-realm visibility. Separate tokens. Separate   │
│  credentials. Separate everything.                      │
└─────────────────────────────────────────────────────────┘
```

**Use cases for realms:**
- **SaaS multi-tenancy** — each customer gets their own realm
- **Environment isolation** — separate dev, staging, prod realms
- **Team boundaries** — engineering, data science, compliance each in their own realm

**Key rule:** The `Polaris-Realm` HTTP header determines which realm a request targets. Tokens are scoped to the realm they were issued in.

---

## Step 1: Check the Current Realm Configuration

Your stack currently has one realm: `POLARIS`. Verify by looking at the Polaris environment variable in `docker-compose.yml`:

```bash
grep "realm" docker-compose.yml
```

You should see:

```yaml
polaris.realm-context.realms: POLARIS
```

Also verify the bootstrap credentials:

```yaml
POLARIS_BOOTSTRAP_CREDENTIALS: POLARIS,root,s3cr3t
```

The format is `REALM_NAME,client_id,client_secret`.

## Step 2: Add a Second Realm

Edit `docker-compose.yml` and update the Polaris service environment to add the `TRAINING` realm.

Change the `polaris` service environment section:

```yaml
  polaris:
    image: apache/polaris:latest
    container_name: polaris
    ports:
      - "8181:8181"
      - "8182:8182"
    depends_on:
      localstack:
        condition: service_healthy
    environment:
      AWS_REGION: us-east-1
      AWS_ACCESS_KEY_ID: test
      AWS_SECRET_ACCESS_KEY: test
      AWS_ENDPOINT_URL: http://localstack:4566
      POLARIS_BOOTSTRAP_CREDENTIALS: POLARIS,root,s3cr3t;TRAINING,trainadmin,train123
      polaris.realm-context.realms: POLARIS,TRAINING
      quarkus.otel.sdk.disabled: "true"
```

Two changes:
1. `polaris.realm-context.realms` now includes `TRAINING`
2. `POLARIS_BOOTSTRAP_CREDENTIALS` now bootstraps both realms (semicolon-separated)

## Step 3: Restart the Polaris Container

Apply the changes:

```bash
docker compose up -d polaris
```

Wait for it to become healthy:

```bash
docker compose ps polaris
```

Check the logs to confirm both realms were bootstrapped:

```bash
docker logs polaris 2>&1 | grep -i "realm\|bootstrap"
```

## Step 4: Get Tokens for Both Realms

**Token for the POLARIS realm (existing):**

```bash
POLARIS_TOKEN=$(curl -s -X POST http://localhost:8181/api/catalog/v1/oauth/tokens \
  -H "Polaris-Realm: POLARIS" \
  -d 'grant_type=client_credentials&client_id=root&client_secret=s3cr3t&scope=PRINCIPAL_ROLE:ALL' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "POLARIS token: $POLARIS_TOKEN"
```

**Token for the TRAINING realm (new):**

```bash
TRAINING_TOKEN=$(curl -s -X POST http://localhost:8181/api/catalog/v1/oauth/tokens \
  -H "Polaris-Realm: TRAINING" \
  -d 'grant_type=client_credentials&client_id=trainadmin&client_secret=train123&scope=PRINCIPAL_ROLE:ALL' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "TRAINING token: $TRAINING_TOKEN"
```

**Question:** What happens if you try to use the POLARIS realm's credentials (`root`/`s3cr3t`) with `Polaris-Realm: TRAINING`? Try it.

## Step 5: Demonstrate Realm Isolation — Catalogs

**List catalogs in the POLARIS realm:**

```bash
curl -s http://localhost:8181/api/management/v1/catalogs \
  -H "Authorization: Bearer $POLARIS_TOKEN" \
  -H "Polaris-Realm: POLARIS" | python3 -m json.tool
```

You should see `polaris_warehouse`.

**List catalogs in the TRAINING realm:**

```bash
curl -s http://localhost:8181/api/management/v1/catalogs \
  -H "Authorization: Bearer $TRAINING_TOKEN" \
  -H "Polaris-Realm: TRAINING" | python3 -m json.tool
```

This should return an empty list — the TRAINING realm has no catalogs yet.

**Key insight:** The `polaris_warehouse` catalog exists only in the POLARIS realm. The TRAINING realm cannot see it, even though both realms run on the same server.

## Step 6: Create a Catalog in the TRAINING Realm

```bash
curl -s -X POST http://localhost:8181/api/management/v1/catalogs \
  -H "Authorization: Bearer $TRAINING_TOKEN" \
  -H "Polaris-Realm: TRAINING" \
  -H "Content-Type: application/json" \
  -d '{
    "catalog": {
      "name": "training_catalog",
      "type": "INTERNAL",
      "readOnly": false,
      "properties": {
        "default-base-location": "s3://warehouse/training"
      },
      "storageConfigInfo": {
        "storageType": "S3",
        "allowedLocations": ["s3://warehouse/training/"],
        "roleArn": "arn:aws:iam::000000000000:role/polaris-s3-role",
        "endpoint": "http://localhost:4566",
        "endpointInternal": "http://localstack:4566",
        "pathStyleAccess": true,
        "region": "us-east-1"
      }
    }
  }' | python3 -m json.tool
```

## Step 7: Create a Namespace in the TRAINING Realm

```bash
curl -s -X POST http://localhost:8181/api/catalog/v1/training_catalog/namespaces \
  -H "Authorization: Bearer $TRAINING_TOKEN" \
  -H "Polaris-Realm: TRAINING" \
  -H "Content-Type: application/json" \
  -d '{"namespace": ["sandbox"]}' | python3 -m json.tool
```

## Step 8: Verify Cross-Realm Isolation

Now prove that the two realms are fully isolated.

**Try to see `training_catalog` from the POLARIS realm:**

```bash
curl -s http://localhost:8181/api/management/v1/catalogs \
  -H "Authorization: Bearer $POLARIS_TOKEN" \
  -H "Polaris-Realm: POLARIS" | python3 -m json.tool
```

Only `polaris_warehouse` should appear — no `training_catalog`.

**Try to use POLARIS token with TRAINING realm header:**

```bash
curl -s http://localhost:8181/api/management/v1/catalogs \
  -H "Authorization: Bearer $POLARIS_TOKEN" \
  -H "Polaris-Realm: TRAINING"
```

This should fail with an authentication error. Tokens are realm-scoped.

**Try to list POLARIS principals from TRAINING realm:**

```bash
curl -s http://localhost:8181/api/management/v1/principals \
  -H "Authorization: Bearer $TRAINING_TOKEN" \
  -H "Polaris-Realm: POLARIS"
```

This should also fail — TRAINING credentials don't work in the POLARIS realm.

## Step 9: Build RBAC in the TRAINING Realm

Set up a minimal role structure in the TRAINING realm:

**Create a principal role:**

```bash
curl -s -X POST http://localhost:8181/api/management/v1/principal-roles \
  -H "Authorization: Bearer $TRAINING_TOKEN" \
  -H "Polaris-Realm: TRAINING" \
  -H "Content-Type: application/json" \
  -d '{"principalRole": {"name": "student_role", "properties": {}}}' | python3 -m json.tool
```

**Create a catalog role with read access:**

```bash
curl -s -X POST http://localhost:8181/api/management/v1/catalogs/training_catalog/catalog-roles \
  -H "Authorization: Bearer $TRAINING_TOKEN" \
  -H "Polaris-Realm: TRAINING" \
  -H "Content-Type: application/json" \
  -d '{"catalogRole": {"name": "sandbox_reader", "properties": {}}}' | python3 -m json.tool
```

**Grant namespace-level read access:**

```bash
curl -s -X PUT http://localhost:8181/api/management/v1/catalogs/training_catalog/catalog-roles/sandbox_reader/grants \
  -H "Authorization: Bearer $TRAINING_TOKEN" \
  -H "Polaris-Realm: TRAINING" \
  -H "Content-Type: application/json" \
  -d '{"type": "namespace", "privilege": "TABLE_LIST", "namespace": ["sandbox"]}' | python3 -m json.tool
```

**Assign catalog role to principal role:**

```bash
curl -s -X PUT http://localhost:8181/api/management/v1/principal-roles/student_role/catalog-roles/training_catalog \
  -H "Authorization: Bearer $TRAINING_TOKEN" \
  -H "Polaris-Realm: TRAINING" \
  -H "Content-Type: application/json" \
  -d '{"catalogRole": {"name": "sandbox_reader"}}' | python3 -m json.tool
```

## Step 10: Compare Both Realms Side by Side

Run these two commands back to back to see the contrast:

```bash
echo "=== POLARIS Realm ==="
echo "Catalogs:"
curl -s http://localhost:8181/api/management/v1/catalogs \
  -H "Authorization: Bearer $POLARIS_TOKEN" \
  -H "Polaris-Realm: POLARIS" | python3 -c "import sys,json; [print(f'  - {c[\"name\"]}') for c in json.load(sys.stdin).get('catalogs',[])]"

echo "Principal Roles:"
curl -s http://localhost:8181/api/management/v1/principal-roles \
  -H "Authorization: Bearer $POLARIS_TOKEN" \
  -H "Polaris-Realm: POLARIS" | python3 -c "import sys,json; [print(f'  - {r[\"name\"]}') for r in json.load(sys.stdin).get('roles',[])]"

echo ""
echo "=== TRAINING Realm ==="
echo "Catalogs:"
curl -s http://localhost:8181/api/management/v1/catalogs \
  -H "Authorization: Bearer $TRAINING_TOKEN" \
  -H "Polaris-Realm: TRAINING" | python3 -c "import sys,json; [print(f'  - {c[\"name\"]}') for c in json.load(sys.stdin).get('catalogs',[])]"

echo "Principal Roles:"
curl -s http://localhost:8181/api/management/v1/principal-roles \
  -H "Authorization: Bearer $TRAINING_TOKEN" \
  -H "Polaris-Realm: TRAINING" | python3 -c "import sys,json; [print(f'  - {r[\"name\"]}') for r in json.load(sys.stdin).get('roles',[])]"
```

Each realm has its own completely independent set of catalogs, roles, and principals.

---

## Exercises

1. **Create a new principal** called `student_1` in the TRAINING realm. Get a token for `student_1` and verify it can only see `training_catalog`.

2. **Try cross-realm access** — use `student_1`'s token with `Polaris-Realm: POLARIS`. Document the exact error response you receive.

3. **Create a second catalog** called `exam_catalog` in the TRAINING realm. Verify it's invisible from the POLARIS realm.

4. **Challenge:** Write a bash script that takes a realm name as an argument and prints a summary of all catalogs, principal roles, and catalog roles in that realm. Test it with both `POLARIS` and `TRAINING`.

5. **Discussion:** In a SaaS scenario, each customer gets a realm. What are the advantages of realm-level isolation over just using separate catalogs within the same realm? When would you choose one over the other?

**Next:** [Lab 8 — Observability](lab8-observability.md)
