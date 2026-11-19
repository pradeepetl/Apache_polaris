# Lab 3 — Access Control

**Level:** 3 (Intermediate) | **Time:** 25 minutes

**Goal:** Understand Polaris role hierarchy. Create roles, assign grants, and verify access restrictions.

---

## Concepts

Polaris uses a layered access model:

```
Principal (user with credentials)
    │
    ▼
Principal Role (grouping of principals)
    │
    ▼
Catalog Role (permissions container, scoped to a catalog)
    │
    ▼
Grants (specific privileges: TABLE_READ_DATA, NAMESPACE_LIST, etc.)
```

- A **Principal** is a user/service with credentials (client ID + secret)
- A **Principal Role** groups principals (like "analysts", "engineers")
- A **Catalog Role** holds permissions for one catalog
- **Grants** are the actual privileges attached to catalog roles

## Step 1: Explore Existing Roles

Open Polaris Admin (http://localhost:3000) and go to **Access Control**.

Expand each principal role to see:
- Which catalog roles are assigned
- What grants each catalog role has

Alternatively, use the **Role Graph** tab to see the visual mapping.

## Step 2: Test the Analyst User

Connect as the analyst (read-only user):

```bash
docker exec -e TRINO_PASSWORD=analyst123 -it trino \
  trino --server https://localhost:8443 --user analyst --password --insecure
```

```sql
-- This should work (read access)
SELECT * FROM postgres.public.customers LIMIT 3;
SELECT * FROM iceberg.shop.orders LIMIT 3;
```

```sql
-- This should FAIL (no write access)
CREATE TABLE iceberg.shop.test_table (id int);
```

```sql
-- This should FAIL (analyst can't see these catalogs)
SHOW SCHEMAS IN tpch;
SHOW SCHEMAS IN memory;
```

**Question:** What error messages do you get? Why?

Type `quit` to exit.

## Step 3: Create a New Catalog Role via Admin UI

1. In Polaris Admin, go to **Access Control**
2. Click **+ New Role / Grant**
3. Under "New Catalog Role":
   - Catalog: `polaris_warehouse`
   - Name: `earthquake_reader`
4. Click **Create**

## Step 4: Add Grants to the New Role

Still in the Create form:

1. Under "Grant Privilege":
   - Catalog: `polaris_warehouse`
   - Catalog Role: `earthquake_reader`
   - Scope: **Namespace**
   - Privilege: `TABLE_LIST`
   - Namespace: `earthquakes`
2. Click **Grant**

Repeat for these privileges:
- Scope: **Table**, Privilege: `TABLE_READ_DATA`, Namespace: `earthquakes`, Table: `events`
- Scope: **Table**, Privilege: `TABLE_READ_PROPERTIES`, Namespace: `earthquakes`, Table: `events`

## Step 5: Assign the Catalog Role

Under "Assign Catalog Role to Principal Role":
- Principal Role: pick an existing one (e.g., the analyst's role)
- Catalog: `polaris_warehouse`
- Catalog Role: `earthquake_reader`
- Click **Assign**

## Step 6: Verify in the Role Graph

Switch to the **Role Graph** tab. You should see a new edge connecting the principal role to `earthquake_reader`.

## Step 7: Create a New Principal via API Explorer

1. Go to the **API Explorer** tab
2. Find **Principals (Management)** > **Create Principal**
3. Edit the body:
```json
{
  "principal": {
    "name": "student_user",
    "properties": {}
  },
  "credentialRotationRequired": false
}
```
4. Click **Execute**
5. **Save the response** — it contains the `clientId` and `clientSecret`

## Step 8: Assign a Principal Role to the New Principal

In API Explorer, find **Role Assignments** > **Assign Role to Principal**:
- Set `{principalName}` = `student_user`
- Body:
```json
{
  "principalRole": {
    "name": "service_admin"
  }
}
```
- Execute

## Step 9: Verify Trino Access Rules

Look at the Trino access control rules:

```bash
cat etc/rules.json
```

These rules map Trino users to catalog access. Polaris controls Iceberg catalog access at the API level. Trino's `rules.json` adds another layer for all catalogs.

**Key insight:** Polaris controls *what data the catalog exposes*. Trino's rules control *which catalogs each user can see*.

---

## Exercises

1. **Create a new principal role** called `data_engineers` using the Admin UI.
2. **Create a catalog role** called `shop_writer` with `TABLE_WRITE_DATA` on `shop.orders`.
3. **Assign** `shop_writer` to `data_engineers` and verify in the Role Graph.
4. **Use the API Explorer** to list all grants for your new catalog role.
5. **Challenge:** What happens if a principal has two catalog roles with conflicting permissions? Is it union (most permissive) or intersection (most restrictive)? Test it.

**Next:** [Lab 4 — Data Ingestion](lab4-data-ingestion.md)
