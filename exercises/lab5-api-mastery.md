# Lab 5 — API Mastery

**Level:** 5 (Advanced) | **Time:** 30 minutes

**Goal:** Use the Polaris REST API directly to build a complete RBAC setup from scratch. Create a principal, roles, grants, and verify end-to-end access control — all through API calls.

---

## Concepts

Everything you did in the Admin UI in Lab 3 can be done programmatically via the REST API. This is how real production systems manage Polaris — through automation, CI/CD pipelines, and Infrastructure-as-Code.

Two API families:
- **Management API** (`/api/management/v1`) — principals, roles, grants, catalogs
- **Catalog API** (`/api/catalog/v1`) — namespaces, tables, views (Iceberg REST spec)

## Setup

Open the **API Explorer** tab in Polaris Admin (http://localhost:3000).

All exercises below use the API Explorer. For each step:
1. Find the endpoint in the correct group
2. Fill in path parameters
3. Edit the request body
4. Click **Execute**
5. Read the response

## Step 1: Get an OAuth Token

Find **OAuth2 (Catalog API)** > **Get Token**

The default body already works:
```
grant_type=client_credentials&client_id=root&client_secret=s3cr3t&scope=PRINCIPAL_ROLE:ALL
```

Click **Execute**. You should see an `access_token` in the response.

> The Admin UI already uses a token — this step shows what happens behind the scenes on every API call.

## Step 2: List Existing Principals

Find **Principals (Management)** > **List Principals**

Click **Execute**. Note the existing principals.

## Step 3: Create a New Principal

Find **Principals (Management)** > **Create Principal**

Edit the body:
```json
{
  "principal": {
    "name": "lab5_user",
    "properties": {
      "team": "students",
      "created_by": "lab5"
    }
  },
  "credentialRotationRequired": false
}
```

**Execute.** The response contains credentials — save the `clientId` and `clientSecret`.

## Step 4: Create a Principal Role

Find **Principal Roles (Management)** > **Create Principal Role**

```json
{
  "principalRole": {
    "name": "lab5_readers",
    "properties": {
      "description": "Read-only role for Lab 5 exercises"
    }
  }
}
```

**Execute.**

## Step 5: Assign Principal to the Principal Role

Find **Role Assignments (Management)** > **Assign Role to Principal**

- `{principalName}` = `lab5_user`
- Body:
```json
{
  "principalRole": {
    "name": "lab5_readers"
  }
}
```

**Execute.**

## Step 6: Create a Catalog Role

Find **Catalog Roles & Grants (Management)** > **Create Catalog Role**

- `{catalogName}` = `polaris_warehouse`
- Body:
```json
{
  "catalogRole": {
    "name": "shop_readonly",
    "properties": {}
  }
}
```

**Execute.**

## Step 7: Add Grants to the Catalog Role

Find **Catalog Roles & Grants (Management)** > **Add Grant**

- `{catalogName}` = `polaris_warehouse`
- `{catalogRoleName}` = `shop_readonly`

Execute this body **three times**, changing the grant each time:

**Grant 1 — List namespaces:**
```json
{
  "type": "catalog",
  "privilege": "CATALOG_MANAGE_CONTENT"
}
```

Wait — that's too permissive. Let's use fine-grained grants:

**Grant 1 — List tables in shop namespace:**
```json
{
  "type": "namespace",
  "privilege": "TABLE_LIST",
  "namespace": ["shop"]
}
```

**Grant 2 — Read order data:**
```json
{
  "type": "table",
  "privilege": "TABLE_READ_DATA",
  "namespace": ["shop"],
  "tableName": "orders"
}
```

**Grant 3 — Read order properties:**
```json
{
  "type": "table",
  "privilege": "TABLE_READ_PROPERTIES",
  "namespace": ["shop"],
  "tableName": "orders"
}
```

## Step 8: Assign Catalog Role to Principal Role

Find **Role Assignments (Management)** > **Assign Catalog Role to PR**

- `{principalRoleName}` = `lab5_readers`
- `{catalogName}` = `polaris_warehouse`
- Body:
```json
{
  "catalogRole": {
    "name": "shop_readonly"
  }
}
```

**Execute.**

## Step 9: Verify the Chain

Now verify the complete chain you built:

1. **List Principal's Roles:** Find **Role Assignments** > **List Roles of Principal**
   - `{principalName}` = `lab5_user`
   - Execute — should show `lab5_readers`

2. **List Catalog Roles of PR:** Find **Role Assignments** > **Get Catalog Roles of PR**
   - `{principalRoleName}` = `lab5_readers`
   - `{catalogName}` = `polaris_warehouse`
   - Execute — should show `shop_readonly`

3. **List Grants:** Find **Catalog Roles & Grants** > **List Grants**
   - `{catalogName}` = `polaris_warehouse`
   - `{catalogRoleName}` = `shop_readonly`
   - Execute — should show your 3 grants

4. **Check the Role Graph** tab — your new roles and edges should appear.

## Step 10: Namespace and Table Operations

Switch to Catalog API endpoints.

**List namespaces:**
Find **Namespaces (Catalog API)** > **List Namespaces**
- `{prefix}` = `polaris_warehouse`
- Execute

**Get namespace properties:**
Find **Namespaces** > **Get Namespace**
- `{prefix}` = `polaris_warehouse`
- `{namespace}` = `shop`
- Execute

**Load table metadata:**
Find **Tables (Catalog API)** > **Load Table Metadata**
- `{prefix}` = `polaris_warehouse`
- `{namespace}` = `shop`
- `{table}` = `orders`
- Execute

Study the response: schema, partition spec, snapshots, metadata-location. This is what Trino and Spark read when they query the table.

## Step 11: Rotate Credentials

Find **Principals (Management)** > **Rotate Credentials**

- `{principalName}` = `lab5_user`
- Execute

The response contains a **new** `clientSecret`. The old one is now invalid.

**Question:** Why is credential rotation important? What happens to active sessions when you rotate?

---

## Exercises

1. **Create a second catalog role** called `earthquake_readonly` with read access to `earthquakes.events`. Assign it to `lab5_readers`. Verify grants via API.

2. **Create a `lab5_writers` principal role** with a catalog role that has `TABLE_WRITE_DATA` on `shop.orders`. Assign it to `lab5_user`. Now `lab5_user` has both reader and writer roles — what happens? (Hint: permissions are additive)

3. **Use the Check Table Exists** endpoint (HEAD) to verify `shop.orders` exists — what HTTP status do you get? Try a non-existent table.

4. **Create a new namespace** called `lab5` via the Namespaces API. Set properties `owner=student`. Then list namespaces to confirm.

5. **Challenge:** Write a bash script using `curl` that automates Steps 3-8 (create principal, create roles, assign grants). Use the OAuth token endpoint to get a token first. This is how you'd automate Polaris setup in CI/CD.

Hint for the challenge:
```bash
# Get token
TOKEN=$(curl -s -X POST http://localhost:8181/api/catalog/v1/oauth/tokens \
  -d 'grant_type=client_credentials&client_id=root&client_secret=s3cr3t&scope=PRINCIPAL_ROLE:ALL' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Use token in subsequent calls
curl -s -X GET http://localhost:8181/api/management/v1/principals \
  -H "Authorization: Bearer $TOKEN" \
  -H "Polaris-Realm: POLARIS"
```

**Congratulations!** You've completed all labs. You now understand Trino federation, Polaris access control, multi-engine data interop, and the full REST API.
