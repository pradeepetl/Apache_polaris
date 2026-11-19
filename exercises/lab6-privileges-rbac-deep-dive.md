# Lab 6 — Privileges & RBAC Deep Dive

**Level:** 4 (Advanced) | **Time:** 35 minutes

**Goal:** Build a multi-team access control scenario from scratch. Create three principals with progressively narrower permissions and verify enforcement through the API.

---

## Concepts

Lab 3 introduced the Polaris role hierarchy. This lab puts it to work with a realistic multi-team scenario.

**Scenario:** Your organization has three teams:

```
Engineering Team         Analytics Team          Intern Team
─────────────────       ─────────────────       ─────────────────
Full read/write          Read all data           Read earthquakes only
on all namespaces        across namespaces       (single namespace)
```

Each team gets a different level of access to the same `polaris_warehouse` catalog:

| Team | Catalog Role | Scope | Privileges |
|------|-------------|-------|------------|
| Engineering | `eng_full_access` | Entire catalog | `CATALOG_MANAGE_CONTENT` |
| Analytics | `analytics_readonly` | shop + earthquakes | `TABLE_LIST`, `TABLE_READ_DATA`, `TABLE_READ_PROPERTIES` |
| Interns | `intern_quake_only` | earthquakes only | `TABLE_LIST`, `TABLE_READ_DATA` |

**Two-layer access model:**

```
Request arrives
    │
    ▼
┌─────────────────────────────┐
│  Layer 1: Trino rules.json  │  ← Which catalogs can this Trino user see?
│  (Trino-level enforcement)  │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│  Layer 2: Polaris Grants    │  ← What operations on which tables/namespaces?
│  (Catalog-level enforcement)│
└─────────────────────────────┘
```

Both layers must allow the operation for it to succeed.

---

## Step 1: Get an OAuth Token

Open **Polaris Admin** (http://localhost:3000) and go to the **API Explorer** tab.

Find **OAuth2 (Catalog API)** > **Get Token** and execute with the default body:

```
grant_type=client_credentials&client_id=root&client_secret=s3cr3t&scope=PRINCIPAL_ROLE:ALL
```

Alternatively, from the terminal:

```bash
TOKEN=$(curl -s -X POST http://localhost:8181/api/catalog/v1/oauth/tokens \
  -d 'grant_type=client_credentials&client_id=root&client_secret=s3cr3t&scope=PRINCIPAL_ROLE:ALL' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo $TOKEN
```

## Step 2: Create Three Principals

In API Explorer, find **Principals (Management)** > **Create Principal**.

Create each principal one at a time:

**Principal 1 — Engineer:**
```json
{
  "principal": {
    "name": "eng_alice",
    "properties": { "team": "engineering" }
  },
  "credentialRotationRequired": false
}
```

**Principal 2 — Analyst:**
```json
{
  "principal": {
    "name": "analytics_bob",
    "properties": { "team": "analytics" }
  },
  "credentialRotationRequired": false
}
```

**Principal 3 — Intern:**
```json
{
  "principal": {
    "name": "intern_charlie",
    "properties": { "team": "interns" }
  },
  "credentialRotationRequired": false
}
```

Save the `clientId` and `clientSecret` from each response. You'll need them later.

## Step 3: Create Three Principal Roles

Find **Principal Roles (Management)** > **Create Principal Role**.

**Role 1:**
```json
{
  "principalRole": {
    "name": "engineering_team",
    "properties": { "description": "Full catalog access for engineers" }
  }
}
```

**Role 2:**
```json
{
  "principalRole": {
    "name": "analytics_team",
    "properties": { "description": "Read-only across all namespaces" }
  }
}
```

**Role 3:**
```json
{
  "principalRole": {
    "name": "intern_team",
    "properties": { "description": "Restricted to earthquakes namespace" }
  }
}
```

## Step 4: Assign Principals to Their Roles

Find **Role Assignments (Management)** > **Assign Role to Principal**.

Execute three times:

| `{principalName}` | Body |
|---|---|
| `eng_alice` | `{"principalRole": {"name": "engineering_team"}}` |
| `analytics_bob` | `{"principalRole": {"name": "analytics_team"}}` |
| `intern_charlie` | `{"principalRole": {"name": "intern_team"}}` |

## Step 5: Create Three Catalog Roles

Find **Catalog Roles & Grants (Management)** > **Create Catalog Role**.

Set `{catalogName}` = `polaris_warehouse` for all three.

**Catalog Role 1 — Full access:**
```json
{
  "catalogRole": {
    "name": "eng_full_access",
    "properties": {}
  }
}
```

**Catalog Role 2 — Read all:**
```json
{
  "catalogRole": {
    "name": "analytics_readonly",
    "properties": {}
  }
}
```

**Catalog Role 3 — Earthquakes only:**
```json
{
  "catalogRole": {
    "name": "intern_quake_only",
    "properties": {}
  }
}
```

## Step 6: Grant Privileges to Each Catalog Role

Find **Catalog Roles & Grants (Management)** > **Add Grant**.

Set `{catalogName}` = `polaris_warehouse` for all.

### Engineering: `eng_full_access`

Set `{catalogRoleName}` = `eng_full_access` and execute:

```json
{
  "type": "catalog",
  "privilege": "CATALOG_MANAGE_CONTENT"
}
```

This single grant gives full read/write on everything in the catalog.

### Analytics: `analytics_readonly`

Set `{catalogRoleName}` = `analytics_readonly` and execute each grant:

**Grant 1 — List tables in shop:**
```json
{
  "type": "namespace",
  "privilege": "TABLE_LIST",
  "namespace": ["shop"]
}
```

**Grant 2 — Read shop tables:**
```json
{
  "type": "namespace",
  "privilege": "TABLE_READ_DATA",
  "namespace": ["shop"]
}
```

**Grant 3 — Read shop table properties:**
```json
{
  "type": "namespace",
  "privilege": "TABLE_READ_PROPERTIES",
  "namespace": ["shop"]
}
```

**Grant 4 — List tables in earthquakes:**
```json
{
  "type": "namespace",
  "privilege": "TABLE_LIST",
  "namespace": ["earthquakes"]
}
```

**Grant 5 — Read earthquakes tables:**
```json
{
  "type": "namespace",
  "privilege": "TABLE_READ_DATA",
  "namespace": ["earthquakes"]
}
```

**Grant 6 — Read earthquakes table properties:**
```json
{
  "type": "namespace",
  "privilege": "TABLE_READ_PROPERTIES",
  "namespace": ["earthquakes"]
}
```

### Intern: `intern_quake_only`

Set `{catalogRoleName}` = `intern_quake_only` and execute each grant:

**Grant 1 — List tables in earthquakes:**
```json
{
  "type": "namespace",
  "privilege": "TABLE_LIST",
  "namespace": ["earthquakes"]
}
```

**Grant 2 — Read earthquakes.events:**
```json
{
  "type": "table",
  "privilege": "TABLE_READ_DATA",
  "namespace": ["earthquakes"],
  "tableName": "events"
}
```

**Grant 3 — Read earthquakes.events properties:**
```json
{
  "type": "table",
  "privilege": "TABLE_READ_PROPERTIES",
  "namespace": ["earthquakes"],
  "tableName": "events"
}
```

**Question:** Notice the intern gets table-level grants (specific to `events`) while the analyst gets namespace-level grants (all tables in a namespace). What's the practical difference?

## Step 7: Assign Catalog Roles to Principal Roles

Find **Role Assignments (Management)** > **Assign Catalog Role to PR**.

Execute three times with `{catalogName}` = `polaris_warehouse`:

| `{principalRoleName}` | Body |
|---|---|
| `engineering_team` | `{"catalogRole": {"name": "eng_full_access"}}` |
| `analytics_team` | `{"catalogRole": {"name": "analytics_readonly"}}` |
| `intern_team` | `{"catalogRole": {"name": "intern_quake_only"}}` |

## Step 8: Verify the Complete Role Graph

Go to the **Role Graph** tab in Polaris Admin. You should see three distinct paths:

```
eng_alice ──► engineering_team ──► eng_full_access
analytics_bob ──► analytics_team ──► analytics_readonly
intern_charlie ──► intern_team ──► intern_quake_only
```

## Step 9: Test Access with Tokens

Now test that each principal can only see what they're granted. Use the saved credentials from Step 2.

**Get a token as the intern:**

```bash
INTERN_TOKEN=$(curl -s -X POST http://localhost:8181/api/catalog/v1/oauth/tokens \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Polaris-Realm: POLARIS" \
  -d "grant_type=client_credentials&client_id=<intern_client_id>&client_secret=<intern_client_secret>&scope=PRINCIPAL_ROLE:ALL" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

**List namespaces as the intern:**

```bash
curl -s http://localhost:8181/api/catalog/v1/polaris_warehouse/namespaces \
  -H "Authorization: Bearer $INTERN_TOKEN" \
  -H "Polaris-Realm: POLARIS" | python3 -m json.tool
```

**Try listing tables in `shop` as the intern (should fail or return empty):**

```bash
curl -s http://localhost:8181/api/catalog/v1/polaris_warehouse/namespaces/shop/tables \
  -H "Authorization: Bearer $INTERN_TOKEN" \
  -H "Polaris-Realm: POLARIS" | python3 -m json.tool
```

**List tables in `earthquakes` as the intern (should succeed):**

```bash
curl -s http://localhost:8181/api/catalog/v1/polaris_warehouse/namespaces/earthquakes/tables \
  -H "Authorization: Bearer $INTERN_TOKEN" \
  -H "Polaris-Realm: POLARIS" | python3 -m json.tool
```

**Question:** What response do you get when the intern tries to access `shop`? Is it an explicit "access denied" or just an empty result?

## Step 10: Revoke a Privilege and See the Effect

Let's revoke the intern's read access to `earthquakes.events`.

Find **Catalog Roles & Grants (Management)** > **Revoke Grant**.

- `{catalogName}` = `polaris_warehouse`
- `{catalogRoleName}` = `intern_quake_only`

```json
{
  "type": "table",
  "privilege": "TABLE_READ_DATA",
  "namespace": ["earthquakes"],
  "tableName": "events"
}
```

Now repeat the table listing from Step 9:

```bash
curl -s http://localhost:8181/api/catalog/v1/polaris_warehouse/namespaces/earthquakes/tables \
  -H "Authorization: Bearer $INTERN_TOKEN" \
  -H "Polaris-Realm: POLARIS" | python3 -m json.tool
```

**Question:** Does the intern still see the table listed? Can they still read its data? What's the difference between `TABLE_LIST` and `TABLE_READ_DATA`?

## Step 11: Verify Grants via API

List all grants for each catalog role to confirm the state.

Find **Catalog Roles & Grants (Management)** > **List Grants**.

Check each role:
- `{catalogName}` = `polaris_warehouse`, `{catalogRoleName}` = `eng_full_access` → 1 grant
- `{catalogName}` = `polaris_warehouse`, `{catalogRoleName}` = `analytics_readonly` → 6 grants
- `{catalogName}` = `polaris_warehouse`, `{catalogRoleName}` = `intern_quake_only` → 2 grants (after revocation)

---

## Exercises

1. **Re-grant the revoked privilege** to `intern_quake_only` and verify the intern can read `earthquakes.events` again.

2. **Add a new namespace grant** to `intern_quake_only` for the `shop` namespace (`TABLE_LIST` only). Verify the intern can list shop tables but cannot read their data.

3. **Create a `data_steward` principal** with a new catalog role that has `TABLE_DROP` on `shop.orders`. Verify the permission exists by listing grants. (Don't actually drop the table!)

4. **Test additive permissions:** Assign both `analytics_readonly` AND `intern_quake_only` to the `intern_team` principal role. Does the intern now get the union of both roles' permissions?

5. **Challenge:** Use `curl` to script the entire setup (Steps 2-7) into a single bash script. Start from the token and create all three principals, roles, and grants programmatically.

**Next:** [Lab 7 — Realms](lab7-realms.md)
