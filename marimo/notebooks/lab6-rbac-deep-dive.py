import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium", app_title="Lab 6 — Privileges & RBAC Deep Dive")


@app.cell(hide_code=True)
def _():
    import json
    import os

    import marimo as mo
    import pandas as pd
    import requests
    import urllib3
    from sqlalchemy import create_engine, text

    urllib3.disable_warnings()

    POLARIS = f"http://{os.environ.get('POLARIS_HOST', 'localhost')}:8181"
    POLARIS_HEALTH = f"http://{os.environ.get('POLARIS_HOST', 'localhost')}:8182/q/health"
    TRINO_HOST = os.environ.get("TRINO_HOST", "localhost")
    REALM = "POLARIS"
    CATALOG = "polaris_warehouse"

    # Every object this lab creates carries the lab6_ prefix (the Polaris instance is shared by all labs).
    ENG, ANALYST, INTERN = "lab6_eng_alice", "lab6_analytics_bob", "lab6_intern_charlie"
    ENG_PR, ANALYST_PR, INTERN_PR = "lab6_engineering_team", "lab6_analytics_team", "lab6_intern_team"
    ENG_CR, ANALYST_CR, INTERN_CR = "lab6_eng_full_access", "lab6_analytics_readonly", "lab6_intern_quake_only"

    trino_engine = create_engine(
        f"trino://admin:admin123@{TRINO_HOST}:8443/iceberg",
        connect_args={"http_scheme": "https", "verify": False},
    )
    return (
        ANALYST,
        ANALYST_CR,
        ANALYST_PR,
        CATALOG,
        ENG,
        ENG_CR,
        ENG_PR,
        INTERN,
        INTERN_CR,
        INTERN_PR,
        POLARIS,
        POLARIS_HEALTH,
        REALM,
        TRINO_HOST,
        json,
        mo,
        pd,
        requests,
        text,
        trino_engine,
    )


@app.cell(hide_code=True)
def _(POLARIS, REALM, mo, pd, requests, text):
    def get_token(client_id, client_secret, realm=REALM):
        resp = requests.post(
            f"{POLARIS}/api/catalog/v1/oauth/tokens",
            headers={"Polaris-Realm": realm},
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "PRINCIPAL_ROLE:ALL",
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    def mask(value, keep=8):
        value = str(value)
        return value if len(value) <= keep else f"{value[:keep]}…"

    def describe_grant(g):
        obj = ".".join(g.get("namespace", [])) + (f".{g['tableName']}" if g.get("tableName") else "")
        return obj or "(whole catalog)"

    def grants_frame(grants):
        return pd.DataFrame(
            [{"Privilege": g.get("privilege"), "Level": g.get("type"), "Object": describe_grant(g)} for g in grants],
            columns=["Privilege", "Level", "Object"],
        )

    def status_frame(rows):
        """rows: list of dicts with an 'HTTP' column; adds a readable outcome."""
        def _outcome(code):
            if 200 <= code < 300:
                return "OK"
            return {409: "already exists (re-run)", 403: "forbidden", 404: "not found"}.get(code, "error")

        return pd.DataFrame([{**r, "Outcome": _outcome(r["HTTP"])} for r in rows])

    def error_message(resp):
        try:
            return resp.json().get("error", {}).get("message", resp.text)
        except ValueError:
            return resp.text

    def ensure_shared_tables(engine):
        """Create iceberg.shop.orders / order_items (sample-queries.sql section 2) and a small
        iceberg.earthquakes.events sample when they are missing. Never drops anything."""
        status = {}
        with engine.connect() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS iceberg.shop WITH (location = 's3://warehouse/polaris_warehouse/shop')"))
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS iceberg.shop.orders (order_id BIGINT, customer_id BIGINT, "
                "order_date DATE, status VARCHAR, total_amount DECIMAL(10, 2)) WITH (format = 'PARQUET')"
            ))
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS iceberg.shop.order_items (item_id BIGINT, order_id BIGINT, "
                "product_id BIGINT, quantity INT, unit_price DECIMAL(10, 2)) WITH (format = 'PARQUET')"
            ))
            if conn.execute(text("SELECT count(*) FROM iceberg.shop.orders")).scalar() == 0:
                conn.execute(text("""
                    INSERT INTO iceberg.shop.orders VALUES
                    (1001, 1, DATE '2024-01-10', 'shipped', 1349.97), (1002, 2, DATE '2024-01-12', 'shipped', 89.98),
                    (1003, 3, DATE '2024-01-15', 'delivered', 449.99), (1004, 1, DATE '2024-01-20', 'delivered', 59.98),
                    (1005, 5, DATE '2024-02-01', 'shipped', 1299.99), (1006, 7, DATE '2024-02-05', 'processing', 199.99),
                    (1007, 10, DATE '2024-02-10', 'shipped', 639.98), (1008, 4, DATE '2024-02-14', 'delivered', 129.98),
                    (1009, 8, DATE '2024-02-20', 'shipped', 399.99), (1010, 6, DATE '2024-03-01', 'processing', 89.99),
                    (1011, 12, DATE '2024-03-05', 'shipped', 1749.97), (1012, 15, DATE '2024-03-10', 'delivered', 49.99),
                    (1013, 14, DATE '2024-03-15', 'processing', 269.98), (1014, 9, DATE '2024-03-20', 'shipped', 109.99),
                    (1015, 20, DATE '2024-03-25', 'delivered', 529.98)
                """)).fetchall()
                status["shop.orders"] = "created sample rows"
            else:
                status["shop.orders"] = "already present"
            if conn.execute(text("SELECT count(*) FROM iceberg.shop.order_items")).scalar() == 0:
                conn.execute(text("""
                    INSERT INTO iceberg.shop.order_items VALUES
                    (1, 1001, 1, 1, 1299.99), (2, 1001, 2, 1, 29.99), (3, 1001, 14, 1, 19.99), (4, 1002, 4, 1, 89.99),
                    (5, 1003, 7, 1, 449.99), (6, 1004, 3, 1, 49.99), (7, 1004, 10, 1, 8.99), (8, 1005, 1, 1, 1299.99),
                    (9, 1006, 13, 1, 199.99), (10, 1007, 6, 1, 599.99), (11, 1007, 8, 1, 39.99), (12, 1008, 17, 1, 109.99),
                    (13, 1008, 14, 1, 19.99), (14, 1009, 5, 1, 399.99), (15, 1010, 4, 1, 89.99), (16, 1011, 1, 1, 1299.99),
                    (17, 1011, 7, 1, 449.99), (18, 1012, 3, 1, 49.99), (19, 1013, 13, 1, 199.99), (20, 1013, 12, 1, 69.99),
                    (21, 1014, 17, 1, 109.99), (22, 1015, 5, 1, 399.99), (23, 1015, 11, 1, 79.99), (24, 1015, 3, 1, 49.99)
                """)).fetchall()
                status["shop.order_items"] = "created sample rows"
            else:
                status["shop.order_items"] = "already present"

            conn.execute(text(
                "CREATE SCHEMA IF NOT EXISTS iceberg.earthquakes WITH (location = 's3://warehouse/polaris_warehouse/earthquakes')"
            ))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS iceberg.earthquakes.events (
                    earthquake_id VARCHAR, magnitude DOUBLE, place VARCHAR,
                    event_time TIMESTAMP(6) WITH TIME ZONE, updated_time TIMESTAMP(6) WITH TIME ZONE,
                    longitude DOUBLE, latitude DOUBLE, depth_km DOUBLE, tsunami BOOLEAN,
                    event_type VARCHAR, title VARCHAR, status VARCHAR, magnitude_type VARCHAR,
                    significance BIGINT, felt_reports BIGINT, alert_level VARCHAR, url VARCHAR
                ) WITH (format = 'PARQUET')
            """))
            if conn.execute(text("SELECT count(*) FROM iceberg.earthquakes.events")).scalar() == 0:
                conn.execute(text("""
                    INSERT INTO iceberg.earthquakes.events VALUES
                    ('sample01', 4.6, '82 km SW of Kokopo, Papua New Guinea', TIMESTAMP '2026-11-01 02:14:07 UTC', TIMESTAMP '2026-11-01 03:00:00 UTC', 151.6, -4.9, 35.0, false, 'earthquake', 'M 4.6 - 82 km SW of Kokopo, Papua New Guinea', 'reviewed', 'mb', 326, NULL, NULL, 'https://earthquake.usgs.gov/'),
                    ('sample02', 2.1, '9 km NE of Aguanga, CA', TIMESTAMP '2026-11-01 05:41:22 UTC', TIMESTAMP '2026-11-01 05:50:00 UTC', -116.8, 33.5, 11.2, false, 'earthquake', 'M 2.1 - 9 km NE of Aguanga, CA', 'automatic', 'ml', 68, 3, NULL, 'https://earthquake.usgs.gov/'),
                    ('sample03', 5.4, 'Kermadec Islands region', TIMESTAMP '2026-11-01 09:03:51 UTC', TIMESTAMP '2026-11-01 10:12:00 UTC', -177.3, -30.1, 10.0, true, 'earthquake', 'M 5.4 - Kermadec Islands region', 'reviewed', 'mww', 449, NULL, 'green', 'https://earthquake.usgs.gov/'),
                    ('sample04', 1.3, '14 km S of Volcano, Hawaii', TIMESTAMP '2026-11-01 11:27:10 UTC', TIMESTAMP '2026-11-01 11:30:00 UTC', -155.2, 19.3, 2.4, false, 'earthquake', 'M 1.3 - 14 km S of Volcano, Hawaii', 'automatic', 'md', 26, NULL, NULL, 'https://earthquake.usgs.gov/'),
                    ('sample05', 3.2, '6 km W of Cobb, CA', TIMESTAMP '2026-11-01 14:55:43 UTC', TIMESTAMP '2026-11-01 15:20:00 UTC', -122.8, 38.8, 1.9, false, 'earthquake', 'M 3.2 - 6 km W of Cobb, CA', 'reviewed', 'md', 158, 12, NULL, 'https://earthquake.usgs.gov/'),
                    ('sample06', 4.9, '120 km E of Hachijo-jima, Japan', TIMESTAMP '2026-11-01 18:08:30 UTC', TIMESTAMP '2026-11-01 19:00:00 UTC', 141.1, 33.2, 44.6, false, 'earthquake', 'M 4.9 - 120 km E of Hachijo-jima, Japan', 'reviewed', 'mb', 369, 5, NULL, 'https://earthquake.usgs.gov/'),
                    ('sample07', 2.7, '33 km NNW of Anchorage, Alaska', TIMESTAMP '2026-11-01 21:36:12 UTC', TIMESTAMP '2026-11-01 21:45:00 UTC', -150.1, 61.5, 38.0, false, 'earthquake', 'M 2.7 - 33 km NNW of Anchorage, Alaska', 'reviewed', 'ml', 112, 8, NULL, 'https://earthquake.usgs.gov/'),
                    ('sample08', 0.9, '3 km E of Pahala, Hawaii', TIMESTAMP '2026-11-01 23:59:01 UTC', TIMESTAMP '2026-11-02 00:05:00 UTC', -155.4, 19.2, 30.8, false, 'quarry blast', 'M 0.9 Quarry Blast - 3 km E of Pahala, Hawaii', 'automatic', 'md', 12, NULL, NULL, 'https://earthquake.usgs.gov/')
                """)).fetchall()
                status["earthquakes.events"] = "created 8-row sample (dlt pipeline not run)"
            else:
                status["earthquakes.events"] = "already present"
        return status

    return (
        describe_grant,
        ensure_shared_tables,
        error_message,
        get_token,
        grants_frame,
        mask,
        status_frame,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.sidebar([mo.md("### Lab 6\n**Privileges & RBAC Deep Dive**"), mo.outline()])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.vstack(
        [
            mo.md(
                """
                # Lab 6 — Privileges & RBAC Deep Dive

                **Level:** 4 (Advanced) &nbsp;|&nbsp; **Time:** 35 minutes

                Lab 3 introduced the Polaris role hierarchy. This lab puts it to work in a realistic
                multi-team scenario: three principals with **progressively narrower permissions** on the same
                `polaris_warehouse` catalog, with enforcement verified through the API.
                """
            ),
            mo.callout(
                mo.md(
                    """
                    **What you'll do**

                    1. Create three principals, three principal roles and three catalog roles
                    2. Grant catalog-, namespace- and table-level privileges
                    3. Wire the roles together and verify the grants
                    4. Log in as the intern and see what is allowed and what is refused
                    5. Revoke a privilege and watch the effect immediately
                    """
                ),
                kind="info",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(CATALOG, POLARIS_HEALTH, TRINO_HOST, get_token, mo, requests):
    def _reachable(url, **kw):
        try:
            return requests.get(url, timeout=5, **kw).ok
        except requests.RequestException:
            return False

    _polaris_ok = _reachable(POLARIS_HEALTH)
    _trino_ok = _reachable(f"https://{TRINO_HOST}:8443/v1/info", verify=False)
    mo.stop(
        not (_polaris_ok and _trino_ok),
        mo.callout(
            mo.md(
                f"""
                **The lab stack isn't reachable.**
                Polaris: {"up" if _polaris_ok else "**down**"} &nbsp;·&nbsp; Trino: {"up" if _trino_ok else "**down**"}

                Start it with `podman compose --profile marimo up -d` (or `docker compose --profile marimo up -d`),
                then re-run this cell.
                """
            ),
            kind="danger",
        ),
    )
    get_token("root", "s3cr3t")

    mo.hstack(
        [
            mo.stat("Healthy", label="Polaris", caption="REST catalog :8181", bordered=True),
            mo.stat("Healthy", label="Trino", caption="used only to seed sample tables", bordered=True),
            mo.stat(CATALOG, label="Catalog", caption="realm POLARIS", bordered=True),
        ],
        widths="equal",
    )
    return


@app.cell(hide_code=True)
def _(ensure_shared_tables, mo, pd, trino_engine):
    with mo.status.spinner(title="Checking the tables the grants refer to…"):
        seed_status = ensure_shared_tables(trino_engine)

    _created = any(v.startswith("created") for v in seed_status.values())
    mo.vstack(
        [
            mo.md("### Sample data"),
            mo.ui.table(
                pd.DataFrame([{"Table": f"iceberg.{k}", "Status": v} for k, v in seed_status.items()]),
                selection=None,
                show_column_summaries=False,
            ),
            mo.callout(
                mo.md(
                    "Table-level grants need the table to exist (Polaris returns 404 otherwise), so the lab makes sure "
                    "`shop.orders`, `shop.order_items` and `earthquakes.events` are there. Missing ones were created with "
                    "sample rows; `earthquakes.events` normally comes from the dlt pipeline in Lab 4."
                ),
                kind="warn" if _created else "neutral",
            ),
        ]
    )
    return (seed_status,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## The scenario
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.ui.tabs(
        {
            "Three teams": mo.md(
                """
                | Team | Principal | Catalog role | Scope | Privileges |
                |------|-----------|--------------|-------|------------|
                | Engineering | `eng_alice` | `eng_full_access` | Entire catalog | `CATALOG_MANAGE_CONTENT` |
                | Analytics | `analytics_bob` | `analytics_readonly` | shop + earthquakes | `TABLE_LIST`, `TABLE_READ_DATA`, `TABLE_READ_PROPERTIES` |
                | Interns | `intern_charlie` | `intern_quake_only` | earthquakes only | `TABLE_LIST`, `TABLE_READ_DATA` (+ `TABLE_READ_PROPERTIES` on `events`) |

                Engineering gets full read/write on all namespaces, Analytics reads all data across namespaces,
                and Interns read earthquakes only.
                """
            ),
            "Two-layer access model": mo.vstack(
                [
                    mo.mermaid(
                        """
                        flowchart TB
                            R([Request arrives]) --> L1
                            L1["<b>Layer 1: Trino rules.json</b><br/>Which catalogs can this Trino user see?<br/>(Trino-level enforcement)"]
                            L1 -- allowed --> L2["<b>Layer 2: Polaris grants</b><br/>What operations on which tables / namespaces?<br/>(catalog-level enforcement)"]
                            L1 -- denied --> X1([Access Denied])
                            L2 -- allowed --> OK([Query runs])
                            L2 -- denied --> X2([HTTP 403])
                        """
                    ),
                    mo.md("**Both layers must allow the operation for it to succeed.** This lab exercises Layer 2 directly through the REST API."),
                ]
            ),
            "Object names in this notebook": mo.md(
                """
                Every lab shares one Polaris instance, so the notebook prefixes the objects it creates with **`lab6_`**:

                | Exercise guide | This notebook |
                |---|---|
                | `eng_alice`, `analytics_bob`, `intern_charlie` | `lab6_eng_alice`, `lab6_analytics_bob`, `lab6_intern_charlie` |
                | `engineering_team`, `analytics_team`, `intern_team` | `lab6_engineering_team`, `lab6_analytics_team`, `lab6_intern_team` |
                | `eng_full_access`, `analytics_readonly`, `intern_quake_only` | `lab6_eng_full_access`, `lab6_analytics_readonly`, `lab6_intern_quake_only` |
                """
            ),
        }
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.mermaid(
        """
        flowchart LR
            A["eng_alice"] --> EP["engineering_team"] --> EC["eng_full_access"] --> EG["CATALOG_MANAGE_CONTENT<br/>whole catalog"]
            B["analytics_bob"] --> AP["analytics_team"] --> AC["analytics_readonly"] --> AG["LIST / READ_DATA / READ_PROPERTIES<br/>namespaces shop + earthquakes"]
            C["intern_charlie"] --> IP["intern_team"] --> IC["intern_quake_only"] --> IG["LIST on earthquakes<br/>READ on earthquakes.events"]
        """
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## Step 1 — Get an OAuth token

    In the Admin UI: **API Explorer › OAuth2 (Catalog API) › Get Token**. From a terminal:

    ```bash
    TOKEN=$(curl -s -X POST http://localhost:8181/api/catalog/v1/oauth/tokens \
      -d 'grant_type=client_credentials&client_id=root&client_secret=s3cr3t&scope=PRINCIPAL_ROLE:ALL' \
      | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
    echo $TOKEN
    ```

    In Python:
    """)
    return


@app.cell
def _(POLARIS, REALM, requests):
    token_resp = requests.post(
        f"{POLARIS}/api/catalog/v1/oauth/tokens",
        headers={"Polaris-Realm": REALM},
        data={
            "grant_type": "client_credentials",
            "client_id": "root",
            "client_secret": "s3cr3t",
            "scope": "PRINCIPAL_ROLE:ALL",
        },
    ).json()
    TOKEN = token_resp["access_token"]
    AUTH = {"Authorization": f"Bearer {TOKEN}", "Polaris-Realm": REALM}
    return AUTH, TOKEN


@app.cell(hide_code=True)
def _(TOKEN, mask, mo):
    mo.callout(mo.md(f"Token acquired for **root**: `{mask(TOKEN, 20)}`"), kind="success")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 2 — Create three principals

    **Principals (Management) › Create Principal**, once per person. Save the `clientId` and
    `clientSecret` from each response; you'll need them in Step 9. Polaris shows a secret **only once**,
    so if a principal already exists (HTTP 409 on a re-run) we ask for an admin **reset** to get a new one.
    """)
    return


@app.cell
def _(ANALYST, AUTH, ENG, INTERN, POLARIS, requests):
    principals_to_create = [
        {"name": ENG, "properties": {"team": "engineering"}},
        {"name": ANALYST, "properties": {"team": "analytics"}},
        {"name": INTERN, "properties": {"team": "interns"}},
    ]
    saved_creds = {}
    principal_log = []
    for _p in principals_to_create:
        _resp = requests.post(
            f"{POLARIS}/api/management/v1/principals",
            headers=AUTH,
            json={"principal": _p, "credentialRotationRequired": False},
        )
        _first = _resp.status_code
        if _resp.status_code == 409:
            _resp = requests.post(f"{POLARIS}/api/management/v1/principals/{_p['name']}/reset", headers=AUTH, json={})
        _resp.raise_for_status()
        _c = _resp.json()["credentials"]
        saved_creds[_p["name"]] = {"clientId": _c["clientId"], "clientSecret": _c["clientSecret"]}
        principal_log.append({"Principal": _p["name"], "Team": _p["properties"]["team"], "HTTP": _first,
                              "clientId": _c["clientId"]})
    return principal_log, saved_creds


@app.cell(hide_code=True)
def _(mask, mo, principal_log, saved_creds, status_frame):
    _df = status_frame(principal_log)
    _df["Outcome"] = ["created" if r["HTTP"] == 201 else "existed → credentials reset" for r in principal_log]
    _df["clientSecret"] = [mask(saved_creds[r["Principal"]]["clientSecret"]) for r in principal_log]
    mo.ui.table(_df, selection=None, show_column_summaries=False)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 3 — Create three principal roles

    **Principal Roles (Management) › Create Principal Role.** A 409 on a re-run simply means the role is already there.
    """)
    return


@app.cell
def _(ANALYST_PR, AUTH, ENG_PR, INTERN_PR, POLARIS, requests, status_frame):
    roles = [
        {"name": ENG_PR, "properties": {"description": "Full catalog access for engineers"}},
        {"name": ANALYST_PR, "properties": {"description": "Read-only across all namespaces"}},
        {"name": INTERN_PR, "properties": {"description": "Restricted to earthquakes namespace"}},
    ]
    _log = []
    for _r in roles:
        _resp = requests.post(
            f"{POLARIS}/api/management/v1/principal-roles",
            headers=AUTH,
            json={"principalRole": _r},
        )
        _log.append({"Principal role": _r["name"], "Description": _r["properties"]["description"], "HTTP": _resp.status_code})
    principal_roles_log = status_frame(_log)
    principal_roles_log
    return principal_roles_log, roles


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 4 — Assign principals to their roles

    **Role Assignments (Management) › Assign Role to Principal.** Assignments are `PUT`s, so they are idempotent.
    """)
    return


@app.cell
def _(
    ANALYST,
    ANALYST_PR,
    AUTH,
    ENG,
    ENG_PR,
    INTERN,
    INTERN_PR,
    POLARIS,
    principal_roles_log,
    requests,
    saved_creds,
    status_frame,
):
    assignments = [
        (ENG, ENG_PR),
        (ANALYST, ANALYST_PR),
        (INTERN, INTERN_PR),
    ]
    _log = []
    for _principal, _role in assignments:
        _resp = requests.put(
            f"{POLARIS}/api/management/v1/principals/{_principal}/principal-roles",
            headers=AUTH,
            json={"principalRole": {"name": _role}},
        )
        _log.append({"Principal": _principal, "→ Principal role": _role, "HTTP": _resp.status_code})
    principal_assignments_log = status_frame(_log)
    principal_assignments_log
    return (principal_assignments_log,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 5 — Create three catalog roles

    **Catalog Roles & Grants (Management) › Create Catalog Role**, with `{catalogName}` = `polaris_warehouse`.
    """)
    return


@app.cell
def _(ANALYST_CR, AUTH, CATALOG, ENG_CR, INTERN_CR, POLARIS, requests, status_frame):
    cat_roles = [ENG_CR, ANALYST_CR, INTERN_CR]
    _log = []
    for _cr in cat_roles:
        _resp = requests.post(
            f"{POLARIS}/api/management/v1/catalogs/{CATALOG}/catalog-roles",
            headers=AUTH,
            json={"catalogRole": {"name": _cr, "properties": {}}},
        )
        _log.append({"Catalog role": _cr, "HTTP": _resp.status_code})
    catalog_roles_log = status_frame(_log)
    catalog_roles_log
    return cat_roles, catalog_roles_log


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 6 — Grant privileges

    **Catalog Roles & Grants (Management) › Add Grant.** Each grant goes in a `{"grant": {...}}` envelope.
    Adding a grant that already exists is a no-op, so re-runs are safe.

    ### Engineering: full catalog access

    This **single grant** gives full read/write on everything in the catalog.
    """)
    return


@app.cell
def _(AUTH, CATALOG, ENG_CR, POLARIS, catalog_roles_log, requests, status_frame):
    _resp = requests.put(
        f"{POLARIS}/api/management/v1/catalogs/{CATALOG}/catalog-roles/{ENG_CR}/grants",
        headers=AUTH,
        json={"grant": {"type": "catalog", "privilege": "CATALOG_MANAGE_CONTENT"}},
    )
    eng_grant_log = status_frame([{"Catalog role": ENG_CR, "Privilege": "CATALOG_MANAGE_CONTENT", "On": "catalog", "HTTP": _resp.status_code}])
    eng_grant_log
    return (eng_grant_log,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Analytics: read access to the `shop` and `earthquakes` namespaces

    Six **namespace-level** grants: list, read data and read properties, for each namespace.
    """)
    return


@app.cell
def _(ANALYST_CR, AUTH, CATALOG, POLARIS, catalog_roles_log, requests, status_frame):
    analytics_grants = [
        {"type": "namespace", "privilege": "TABLE_LIST", "namespace": ["shop"]},
        {"type": "namespace", "privilege": "TABLE_READ_DATA", "namespace": ["shop"]},
        {"type": "namespace", "privilege": "TABLE_READ_PROPERTIES", "namespace": ["shop"]},
        {"type": "namespace", "privilege": "TABLE_LIST", "namespace": ["earthquakes"]},
        {"type": "namespace", "privilege": "TABLE_READ_DATA", "namespace": ["earthquakes"]},
        {"type": "namespace", "privilege": "TABLE_READ_PROPERTIES", "namespace": ["earthquakes"]},
    ]
    _log = []
    for _g in analytics_grants:
        _r = requests.put(
            f"{POLARIS}/api/management/v1/catalogs/{CATALOG}/catalog-roles/{ANALYST_CR}/grants",
            headers=AUTH,
            json={"grant": _g},
        )
        _log.append({"Privilege": _g["privilege"], "On namespace": _g["namespace"][0], "HTTP": _r.status_code})
    analytics_grant_log = status_frame(_log)
    analytics_grant_log
    return analytics_grant_log, analytics_grants


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Intern: read access to `earthquakes.events` only

    One namespace-level `TABLE_LIST`, then **table-level** read grants on `events`.
    """)
    return


@app.cell
def _(AUTH, CATALOG, INTERN_CR, POLARIS, catalog_roles_log, requests, seed_status, status_frame):
    intern_grants = [
        {"type": "namespace", "privilege": "TABLE_LIST", "namespace": ["earthquakes"]},
        {"type": "table", "privilege": "TABLE_READ_DATA", "namespace": ["earthquakes"], "tableName": "events"},
        {"type": "table", "privilege": "TABLE_READ_PROPERTIES", "namespace": ["earthquakes"], "tableName": "events"},
    ]
    _log = []
    for _g in intern_grants:
        _r = requests.put(
            f"{POLARIS}/api/management/v1/catalogs/{CATALOG}/catalog-roles/{INTERN_CR}/grants",
            headers=AUTH,
            json={"grant": _g},
        )
        _scope = ".".join(_g["namespace"]) + (f".{_g['tableName']}" if "tableName" in _g else "")
        _log.append({"Privilege": _g["privilege"], "Level": _g["type"], "On": _scope, "HTTP": _r.status_code})
    intern_grant_log = status_frame(_log)
    intern_grant_log
    return intern_grant_log, intern_grants


@app.cell(hide_code=True)
def _(mo):
    mo.callout(
        mo.md(
            "**Question:** Notice the intern gets **table-level** grants (specific to `events`) while the analyst gets "
            "**namespace-level** grants (all tables in a namespace). What's the practical difference?"
        ),
        kind="neutral",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 7 — Assign catalog roles to principal roles

    **Role Assignments (Management) › Assign Catalog Role to PR**, with `{catalogName}` = `polaris_warehouse`.
    """)
    return


@app.cell
def _(
    ANALYST_CR,
    ANALYST_PR,
    AUTH,
    CATALOG,
    ENG_CR,
    ENG_PR,
    INTERN_CR,
    INTERN_PR,
    POLARIS,
    analytics_grant_log,
    eng_grant_log,
    intern_grant_log,
    principal_assignments_log,
    requests,
    status_frame,
):
    cr_assignments = [
        (ENG_PR, ENG_CR),
        (ANALYST_PR, ANALYST_CR),
        (INTERN_PR, INTERN_CR),
    ]
    _log = []
    for _pr, _cr in cr_assignments:
        _resp = requests.put(
            f"{POLARIS}/api/management/v1/principal-roles/{_pr}/catalog-roles/{CATALOG}",
            headers=AUTH,
            json={"catalogRole": {"name": _cr}},
        )
        _log.append({"Principal role": _pr, "→ Catalog role": _cr, "HTTP": _resp.status_code})
    cr_assignment_log = status_frame(_log)
    cr_assignment_log
    return (cr_assignment_log,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 8 — Verify the role graph and the grants

    The **Role Graph** tab in Polaris Admin (http://localhost:3000) should show three distinct paths.
    Here we rebuild that graph from the API: principal → principal roles → catalog roles → grants.
    """)
    return


@app.cell
def _(ANALYST, AUTH, CATALOG, ENG, INTERN, POLARIS, cr_assignment_log, requests):
    role_chain = {}
    for _principal in (ENG, ANALYST, INTERN):
        _prs = requests.get(f"{POLARIS}/api/management/v1/principals/{_principal}/principal-roles", headers=AUTH).json()
        _chain = []
        for _pr in _prs.get("roles", []):
            _crs = requests.get(
                f"{POLARIS}/api/management/v1/principal-roles/{_pr['name']}/catalog-roles/{CATALOG}", headers=AUTH
            ).json()
            for _cr in _crs.get("roles", []):
                _grants = requests.get(
                    f"{POLARIS}/api/management/v1/catalogs/{CATALOG}/catalog-roles/{_cr['name']}/grants", headers=AUTH
                ).json()
                _chain.append({"principal_role": _pr["name"], "catalog_role": _cr["name"], "grants": _grants.get("grants", [])})
        role_chain[_principal] = _chain
    return (role_chain,)


@app.cell(hide_code=True)
def _(describe_grant, grants_frame, mo, role_chain):
    _lines = ["flowchart LR"]
    _tabs = {}
    for _i, (_principal, _chain) in enumerate(role_chain.items()):
        _lines.append(f'    P{_i}["{_principal}"]')
        _all = []
        for _j, _link in enumerate(_chain):
            _lines.append(f'    P{_i} --> PR{_i}_{_j}["{_link["principal_role"]}"] --> CR{_i}_{_j}["{_link["catalog_role"]}<br/>{len(_link["grants"])} grants"]')
            _all.extend(_link["grants"])
        _tabs[f"{_principal} ({len(_all)} grants)"] = mo.ui.table(grants_frame(_all), selection=None, show_column_summaries=False)
    mo.vstack([mo.mermaid("\n".join(_lines)), mo.ui.tabs(_tabs)])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## Step 9 — Test access with the intern's token

    Log in with the intern's saved credentials. From a terminal it looks like this:

    ```bash
    INTERN_TOKEN=$(curl -s -X POST http://localhost:8181/api/catalog/v1/oauth/tokens \
      -H "Content-Type: application/x-www-form-urlencoded" \
      -H "Polaris-Realm: POLARIS" \
      -d "grant_type=client_credentials&client_id=<intern_client_id>&client_secret=<intern_client_secret>&scope=PRINCIPAL_ROLE:ALL" \
      | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
    ```
    """)
    return


@app.cell
def _(INTERN, POLARIS, REALM, requests, role_chain, saved_creds):
    intern_creds = saved_creds[INTERN]
    interntoken_resp = requests.post(
        f"{POLARIS}/api/catalog/v1/oauth/tokens",
        headers={"Polaris-Realm": REALM},
        data={
            "grant_type": "client_credentials",
            "client_id": intern_creds["clientId"],
            "client_secret": intern_creds["clientSecret"],
            "scope": "PRINCIPAL_ROLE:ALL",
        },
    ).json()
    INTERN_TOKEN = interntoken_resp["access_token"]
    INTERN_AUTH = {"Authorization": f"Bearer {INTERN_TOKEN}", "Polaris-Realm": REALM}
    return INTERN_AUTH, INTERN_TOKEN


@app.cell
def _(CATALOG, INTERN_AUTH, POLARIS, requests):
    # List namespaces as the intern
    r_ns = requests.get(f"{POLARIS}/api/catalog/v1/{CATALOG}/namespaces", headers=INTERN_AUTH)

    # List tables in earthquakes as the intern (should succeed)
    r1 = requests.get(f"{POLARIS}/api/catalog/v1/{CATALOG}/namespaces/earthquakes/tables", headers=INTERN_AUTH)

    # Try listing tables in shop as the intern (should fail or return empty)
    r2 = requests.get(f"{POLARIS}/api/catalog/v1/{CATALOG}/namespaces/shop/tables", headers=INTERN_AUTH)
    return r1, r2, r_ns


@app.cell(hide_code=True)
def _(error_message, mo, r1, r2, r_ns):
    def _card(title, resp, expect):
        _ok = resp.ok
        if _ok:
            _names = [t["name"] for t in resp.json().get("identifiers", [])] if "identifiers" in resp.json() else [
                ".".join(n) for n in resp.json().get("namespaces", [])
            ]
            _detail = "Returned: " + (", ".join(f"`{n}`" for n in _names) or "_nothing_")
        else:
            _detail = f"> {error_message(resp)[:220]}"
        return mo.callout(
            mo.md(f"**{title}** → HTTP **{resp.status_code}** (expected {expect})\n\n{_detail}"),
            kind="success" if _ok else "danger",
        )

    mo.vstack(
        [
            mo.hstack(
                [
                    _card("List tables in earthquakes", r1, "200"),
                    _card("List tables in shop", r2, "403"),
                ],
                widths="equal",
                align="start",
            ),
            _card("List namespaces", r_ns, "403 — no catalog-level privilege"),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.callout(
        mo.md(
            "**Question:** What response does the intern get for `shop`? Is it an explicit \"access denied\" or an empty result?"
        ),
        kind="neutral",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Access matrix: all three teams

    The same probes for every principal. Each cell is the HTTP status Polaris returned.
    *Load + read creds* sends `X-Iceberg-Access-Delegation: vended-credentials`, which requires `TABLE_READ_DATA`;
    a plain *load* only needs `TABLE_READ_PROPERTIES`.
    """)
    return


@app.cell(hide_code=True)
def _(CATALOG, POLARIS, get_token, requests, saved_creds):
    def probe_access(principals):
        """Return {principal: {operation: http_status}} for a fixed set of Catalog API calls."""
        _base = f"{POLARIS}/api/catalog/v1/{CATALOG}"
        _vended = {"X-Iceberg-Access-Delegation": "vended-credentials"}
        _ops = [
            ("List namespaces", "GET", "/namespaces", {}),
            ("List shop tables", "GET", "/namespaces/shop/tables", {}),
            ("Load shop.orders", "GET", "/namespaces/shop/tables/orders", {}),
            ("Load shop.orders + read creds", "GET", "/namespaces/shop/tables/orders", _vended),
            ("List earthquakes tables", "GET", "/namespaces/earthquakes/tables", {}),
            ("Load earthquakes.events", "GET", "/namespaces/earthquakes/tables/events", {}),
            ("Load earthquakes.events + read creds", "GET", "/namespaces/earthquakes/tables/events", _vended),
            ("Create namespace lab6_scratch", "POST", "/namespaces", {}),
        ]
        out = {}
        for _name in principals:
            _c = saved_creds[_name]
            _h = {"Authorization": f"Bearer {get_token(_c['clientId'], _c['clientSecret'])}", "Polaris-Realm": "POLARIS"}
            out[_name] = {}
            for _label, _method, _path, _extra in _ops:
                _body = {"namespace": ["lab6_scratch"]} if _method == "POST" else None
                _resp = requests.request(_method, _base + _path, headers={**_h, **_extra}, json=_body)
                out[_name][_label] = _resp.status_code
                if _method == "POST" and _resp.ok:
                    requests.delete(f"{_base}/namespaces/lab6_scratch", headers=_h)  # leave no trace
        return out

    return (probe_access,)


@app.cell(hide_code=True)
def _(ANALYST, ENG, INTERN, mo, pd, probe_access):
    with mo.status.spinner(title="Probing access for all three principals…"):
        access_before = probe_access([ENG, ANALYST, INTERN])

    def _style(v):
        return f"allowed ({v})" if 200 <= v < 300 else f"DENIED ({v})"

    access_matrix = pd.DataFrame(access_before).apply(lambda col: col.map(_style))
    access_matrix.index.name = "Operation"
    mo.ui.table(access_matrix.reset_index(), selection=None, show_column_summaries=False)
    return access_before, access_matrix


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 10 — Revoke a privilege and see the effect

    **Catalog Roles & Grants (Management) › Revoke Grant.** Revoke the intern's `TABLE_READ_DATA` on
    `earthquakes.events`. The revoke endpoint is a **`POST`** to the same `/grants` path with the grant to remove.
    (Re-running the notebook restores the grant in Step 6.)
    """)
    return


@app.cell
def _(AUTH, CATALOG, INTERN_CR, POLARIS, access_before, mo, r1, r2, requests):
    _resp = requests.post(
        f"{POLARIS}/api/management/v1/catalogs/{CATALOG}/catalog-roles/{INTERN_CR}/grants",
        headers=AUTH,
        json={
            "grant": {
                "type": "table",
                "privilege": "TABLE_READ_DATA",
                "namespace": ["earthquakes"],
                "tableName": "events",
            }
        },
    )
    revoke_status = _resp.status_code
    mo.callout(
        mo.md(f"Revoke `TABLE_READ_DATA` on `earthquakes.events` from `{INTERN_CR}` → HTTP **{revoke_status}**"),
        kind="success" if _resp.ok else "danger",
    )
    return (revoke_status,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    Now repeat the intern's calls. The intern's **existing token** is reused: authorization is checked on every
    request, so the revocation takes effect immediately, with no new login.

    ```bash
    curl -s http://localhost:8181/api/catalog/v1/polaris_warehouse/namespaces/earthquakes/tables \
      -H "Authorization: Bearer $INTERN_TOKEN" \
      -H "Polaris-Realm: POLARIS" | python3 -m json.tool
    ```
    """)
    return


@app.cell
def _(CATALOG, INTERN_AUTH, POLARIS, requests, revoke_status):
    _base = f"{POLARIS}/api/catalog/v1/{CATALOG}/namespaces/earthquakes/tables"
    after_revoke = {
        "List earthquakes tables": requests.get(_base, headers=INTERN_AUTH),
        "Load earthquakes.events (metadata)": requests.get(f"{_base}/events", headers=INTERN_AUTH),
        "Load earthquakes.events + read creds": requests.get(
            f"{_base}/events", headers={**INTERN_AUTH, "X-Iceberg-Access-Delegation": "vended-credentials"}
        ),
    }
    return (after_revoke,)


@app.cell(hide_code=True)
def _(INTERN, access_before, after_revoke, error_message, mo, pd):
    _key = {
        "List earthquakes tables": "List earthquakes tables",
        "Load earthquakes.events (metadata)": "Load earthquakes.events",
        "Load earthquakes.events + read creds": "Load earthquakes.events + read creds",
    }
    _rows = []
    for _label, _resp in after_revoke.items():
        _rows.append(
            {
                "Intern call": _label,
                "Before revoke": access_before[INTERN][_key[_label]],
                "After revoke": _resp.status_code,
                "Detail": "" if _resp.ok else error_message(_resp)[:140],
            }
        )
    mo.vstack(
        [
            mo.ui.table(pd.DataFrame(_rows), selection=None, show_column_summaries=False),
            mo.callout(
                mo.md(
                    "The intern **still sees the table listed** (`TABLE_LIST`) and can still load its metadata "
                    "(`TABLE_READ_PROPERTIES`), but Polaris now refuses to hand out **read credentials** for the data files: "
                    "the operation `LOAD_TABLE_WITH_READ_DELEGATION` needs `TABLE_READ_DATA`."
                ),
                kind="info",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.callout(
        mo.md(
            "**Question:** The intern still has `TABLE_LIST` but lost `TABLE_READ_DATA`. Can they see the table exists "
            "but not read its data? What's the difference between `TABLE_LIST` and `TABLE_READ_DATA`?"
        ),
        kind="neutral",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 11 — Verify grants via the API

    **Catalog Roles & Grants (Management) › List Grants** for each catalog role confirms the final state.
    """)
    return


@app.cell
def _(AUTH, CATALOG, POLARIS, cat_roles, requests, revoke_status):
    final_grants = {}
    for _role_name in cat_roles:
        _resp = requests.get(
            f"{POLARIS}/api/management/v1/catalogs/{CATALOG}/catalog-roles/{_role_name}/grants",
            headers=AUTH,
        ).json()
        final_grants[_role_name] = _resp.get("grants", [])
    return (final_grants,)


@app.cell(hide_code=True)
def _(final_grants, grants_frame, mo):
    _expected = {"lab6_eng_full_access": 1, "lab6_analytics_readonly": 6, "lab6_intern_quake_only": 2}
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(
                        len(_g),
                        label=_name,
                        caption=f"expected {_expected[_name]}" + (" (after revocation)" if "intern" in _name else ""),
                        bordered=True,
                    )
                    for _name, _g in final_grants.items()
                ],
                widths="equal",
            ),
            mo.ui.tabs(
                {_name: mo.ui.table(grants_frame(_g), selection=None, show_column_summaries=False) for _name, _g in final_grants.items()}
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Wrap-up
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.accordion(
        {
            "Key takeaways": mo.md(
                """
                1. Access is a chain: **principal → principal role → catalog role → grants**
                2. One catalog-level `CATALOG_MANAGE_CONTENT` grant = full read/write; use it sparingly
                3. **Namespace-level** grants cover every current and future table in the namespace;
                   **table-level** grants cover one table and require it to exist
                4. `TABLE_LIST` lets you see a table; `TABLE_READ_PROPERTIES` lets you load its metadata;
                   `TABLE_READ_DATA` is what unlocks credentials for the data files
                5. Missing privileges give an explicit **HTTP 403**, not an empty result
                6. Revocation is immediate, even for tokens that were already issued
                7. Polaris grants are layer 2; Trino's `rules.json` is layer 1 and both must allow the operation
                """
            ),
            "Exercises": mo.md(
                """
                1. **Re-grant the revoked privilege** to `intern_quake_only` and verify the intern can read `earthquakes.events` again.
                2. **Add a new namespace grant** to `intern_quake_only` for the `shop` namespace (`TABLE_LIST` only).
                   Verify the intern can list shop tables but cannot read their data.
                3. **Create a `data_steward` principal** with a new catalog role that has `TABLE_DROP` on `shop.orders`.
                   Verify the permission exists by listing grants. (**Don't actually drop the table!**)
                4. **Test additive permissions:** assign both `analytics_readonly` AND `intern_quake_only` to the `intern_team`
                   principal role. Does the intern now get the union of both roles' permissions?
                5. **Challenge:** write a function that takes a principal name and prints the full access chain
                   (principal → principal roles → catalog roles → grants). Step 8 is a starting point.
                6. **Challenge:** use `curl` to script the entire setup (Steps 2–7) into a single bash script: start from
                   the token and create all three principals, roles and grants programmatically.
                """
            ),
            "Re-running this notebook": mo.md(
                """
                Everything is idempotent. Existing roles answer **409**, grants and assignments are `PUT`s, and existing
                principals get fresh secrets through `POST /principals/{name}/reset`. Step 6 re-adds the grant that
                Step 10 revokes. The namespace probe in the access matrix is deleted straight after it's created.
                Objects owned by this lab all start with `lab6_`.
                """
            ),
            "Next lab": mo.md("**Lab 7 — Realms:** multi-tenant isolation with a second Polaris realm."),
        },
        multiple=True,
    )
    return


if __name__ == "__main__":
    app.run()
