import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium", app_title="Lab 5 — API Mastery")


@app.cell(hide_code=True)
def _():
    import base64
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
    ADMIN_UI = "http://localhost:3000"

    trino_engine = create_engine(
        f"trino://admin:admin123@{TRINO_HOST}:8443/iceberg",
        connect_args={"http_scheme": "https", "verify": False},
    )
    return (
        ADMIN_UI,
        CATALOG,
        POLARIS,
        POLARIS_HEALTH,
        REALM,
        TRINO_HOST,
        base64,
        json,
        mo,
        pd,
        requests,
        text,
        trino_engine,
    )


@app.cell(hide_code=True)
def _(POLARIS, REALM, base64, json, mo, pd, requests, text):
    def get_token(client_id, client_secret, realm=REALM):
        """Client-credentials OAuth flow against the Polaris token endpoint."""
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

    def auth_headers(token, realm=REALM):
        return {"Authorization": f"Bearer {token}", "Polaris-Realm": realm}

    def mask(value, keep=8):
        value = str(value)
        return value if len(value) <= keep else f"{value[:keep]}…"

    def jwt_claims(token):
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))

    def body_of(resp):
        try:
            return resp.json()
        except ValueError:
            return None

    def show_response(resp, label="", conflict_ok=True):
        """Render an HTTP response: a status callout plus the JSON body (if any)."""
        code = resp.status_code
        if 200 <= code < 300:
            kind, note = "success", "OK"
        elif code == 409 and conflict_ok:
            kind, note = "neutral", "already exists (expected on a re-run)"
        else:
            kind, note = "danger", "failed"
        _req = resp.request
        _head = mo.callout(
            mo.md(f"**{label or _req.method + ' ' + _req.path_url}** → HTTP **{code}** — {note}"),
            kind=kind,
        )
        _body = body_of(resp)
        if _body:
            return mo.vstack([_head, mo.accordion({"Response body": mo.json(_body)})])
        return _head

    def grants_frame(grants):
        return pd.DataFrame(
            [
                {
                    "Privilege": g.get("privilege"),
                    "Level": g.get("type"),
                    "Object": ".".join(g.get("namespace", []))
                    + (f".{g['tableName']}" if g.get("tableName") else "")
                    or "(whole catalog)",
                }
                for g in grants
            ],
            columns=["Privilege", "Level", "Object"],
        )

    def ensure_shared_tables(engine):
        """Create iceberg.shop.orders / order_items (sample-queries.sql section 2) and
        a small iceberg.earthquakes.events sample if they are missing. Never drops anything."""
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
        auth_headers,
        body_of,
        ensure_shared_tables,
        get_token,
        grants_frame,
        jwt_claims,
        mask,
        show_response,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.sidebar([mo.md("### Lab 5\n**API Mastery**"), mo.outline()])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.vstack(
        [
            mo.md(
                """
                # Lab 5 — API Mastery

                **Level:** 5 (Advanced) &nbsp;|&nbsp; **Time:** 30 minutes

                Everything you did in the Admin UI in Lab 3 can be done programmatically through the
                Polaris REST API. This is how production systems manage Polaris: automation, CI/CD pipelines
                and Infrastructure-as-Code. In this lab you build a complete RBAC setup from scratch with
                nothing but HTTP calls, then verify access control end to end.
                """
            ),
            mo.callout(
                mo.md(
                    """
                    **What you'll do**

                    1. Get an OAuth token and look inside it
                    2. Create a principal, a principal role and a catalog role
                    3. Grant fine-grained privileges on `shop.orders` and wire the role chain together
                    4. Verify the chain through the Management API
                    5. Explore namespaces and table metadata through the Catalog API, as `root` and as your new user
                    6. Rotate the new principal's credentials
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
    get_token("root", "s3cr3t")  # fail fast if the bootstrap credentials don't work

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
    with mo.status.spinner(title="Checking the sample tables this lab grants access to…"):
        seed_status = ensure_shared_tables(trino_engine)

    _sampled = any("sample" in v for v in seed_status.values() if "created" in v)
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
                    "The grants below target real tables, so the lab makes sure `shop.orders`, `shop.order_items` "
                    "and `earthquakes.events` exist. Missing tables were created with sample rows "
                    "(`earthquakes.events` normally comes from the dlt pipeline in Lab 4)."
                ),
                kind="warn" if _sampled else "neutral",
            ),
        ]
    )
    return (seed_status,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Concepts — two API families
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.ui.tabs(
        {
            "Management API": mo.md(
                """
                **`/api/management/v1`** — Polaris-specific administration.

                | Resource | Example endpoint |
                |---|---|
                | Catalogs | `GET /catalogs` |
                | Principals | `POST /principals`, `POST /principals/{name}/rotate` |
                | Principal roles | `POST /principal-roles` |
                | Role assignments | `PUT /principals/{name}/principal-roles` |
                | Catalog roles & grants | `PUT /catalogs/{catalog}/catalog-roles/{role}/grants` |
                """
            ),
            "Catalog API": mo.md(
                """
                **`/api/catalog/v1`** — the standard **Iceberg REST catalog spec**. Trino, Spark and PyIceberg speak it.

                | Resource | Example endpoint |
                |---|---|
                | OAuth tokens | `POST /oauth/tokens` |
                | Namespaces | `GET /{prefix}/namespaces` |
                | Tables | `GET /{prefix}/namespaces/{ns}/tables/{table}` |
                | Views | `GET /{prefix}/namespaces/{ns}/views` |

                `{prefix}` is the catalog name, here `polaris_warehouse`.
                """
            ),
            "Every request needs": mo.md(
                """
                | Header | Value |
                |---|---|
                | `Authorization` | `Bearer <access_token>` from the token endpoint |
                | `Polaris-Realm` | `POLARIS` (the realm, see Lab 7) |
                | `Content-Type` | `application/json` for bodies (`requests` sets it when you pass `json=`) |

                Prefer clicking? The **API Explorer** tab in Polaris Admin (http://localhost:3000)
                exposes the same endpoints with editable bodies and an **Execute** button.
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
            P["Principal<br/>lab5_user"] -- "Step 5" --> PR["Principal role<br/>lab5_readers"]
            PR -- "Step 8" --> CR["Catalog role<br/>lab5_shop_readonly"]
            CR -- "Step 7" --> G["Grants on<br/>shop / shop.orders"]
            G --> T[("polaris_warehouse")]
        """
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 1 — Get an OAuth token

    Every API call starts here. The body is a form-encoded **client-credentials** grant
    (in the API Explorer: **OAuth2 (Catalog API) › Get Token**). The Admin UI does exactly this
    behind the scenes on every call.
    """)
    return


@app.cell
def _(POLARIS, REALM, requests):
    token_resp = requests.post(
        f"{POLARIS}/api/catalog/v1/oauth/tokens",
        headers={"Polaris-Realm": REALM},
        # requests form-encodes a dict: grant_type=client_credentials&client_id=root&client_secret=s3cr3t&scope=...
        data={
            "grant_type": "client_credentials",
            "client_id": "root",
            "client_secret": "s3cr3t",
            "scope": "PRINCIPAL_ROLE:ALL",
        },
    ).json()
    TOKEN = token_resp["access_token"]
    AUTH = {"Authorization": f"Bearer {TOKEN}", "Polaris-Realm": REALM}
    return AUTH, TOKEN, token_resp


@app.cell(hide_code=True)
def _(TOKEN, jwt_claims, mask, mo, pd, token_resp):
    _claims = jwt_claims(TOKEN)
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(mask(TOKEN, 16), label="access_token", caption="a signed JWT", bordered=True),
                    mo.stat(token_resp.get("token_type", "?"), label="token_type", bordered=True),
                    mo.stat(f"{int(token_resp.get('expires_in', 0)) // 60} min", label="expires_in", bordered=True),
                ],
                widths="equal",
            ),
            mo.md("**Inside the token** (the JWT payload, base64-decoded):"),
            mo.ui.table(
                pd.DataFrame([{"Claim": k, "Value": str(v)} for k, v in _claims.items()]),
                selection=None,
                show_column_summaries=False,
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 2 — List existing principals

    **Principals (Management) › List Principals**
    """)
    return


@app.cell
def _(AUTH, POLARIS, requests):
    principals = requests.get(f"{POLARIS}/api/management/v1/principals", headers=AUTH).json()
    return (principals,)


@app.cell(hide_code=True)
def _(mo, pd, principals):
    _rows = [
        {"name": p["name"], "clientId": p.get("clientId"), "properties": str(p.get("properties", {}))}
        for p in principals.get("principals", [])
    ]
    mo.vstack(
        [
            mo.stat(len(_rows), label="Principals in realm POLARIS", bordered=True),
            mo.ui.table(pd.DataFrame(_rows), selection=None, show_column_summaries=False),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 3 — Create a new principal

    **Principals (Management) › Create Principal.** The response contains the credentials,
    and **Polaris shows the secret only once**. If `lab5_user` already exists (HTTP 409 on a re-run),
    the cell asks Polaris, as `root`, to **reset** the credentials so we have a usable secret again.
    """)
    return


@app.cell
def _(AUTH, POLARIS, requests):
    _resp = requests.post(
        f"{POLARIS}/api/management/v1/principals",
        headers=AUTH,
        json={
            "principal": {
                "name": "lab5_user",
                "properties": {"team": "students", "created_by": "lab5"},
            },
            "credentialRotationRequired": False,
        },
    )
    principal_created = _resp.status_code == 201
    if _resp.status_code == 409:
        # Already there from an earlier run: an admin reset issues a fresh secret.
        _resp = requests.post(f"{POLARIS}/api/management/v1/principals/lab5_user/reset", headers=AUTH, json={})
    _resp.raise_for_status()
    lab5_creds = _resp.json()
    lab5_client_id = lab5_creds["credentials"]["clientId"]
    lab5_secret = lab5_creds["credentials"]["clientSecret"]
    return lab5_client_id, lab5_creds, lab5_secret, principal_created


@app.cell(hide_code=True)
def _(lab5_client_id, lab5_creds, lab5_secret, mask, mo, principal_created):
    mo.vstack(
        [
            mo.callout(
                mo.md(
                    ("Created principal **`lab5_user`**. " if principal_created else "`lab5_user` already existed, so its credentials were **reset**. ")
                    + "**Save these credentials!** In a real system you'd put them in a secrets manager now."
                ),
                kind="success",
            ),
            mo.hstack(
                [
                    mo.stat(lab5_client_id, label="clientId", bordered=True),
                    mo.stat(mask(lab5_secret), label="clientSecret", caption="kept in `lab5_secret`", bordered=True),
                    mo.stat(str(lab5_creds["principal"].get("properties", {})), label="properties", bordered=True),
                ],
                widths="equal",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 4 — Create a principal role

    **Principal Roles (Management) › Create Principal Role.** A principal role is what you assign to
    people and services.
    """)
    return


@app.cell
def _(AUTH, POLARIS, requests, show_response):
    _resp = requests.post(
        f"{POLARIS}/api/management/v1/principal-roles",
        headers=AUTH,
        json={
            "principalRole": {
                "name": "lab5_readers",
                "properties": {"description": "Read-only role for Lab 5 exercises"},
            }
        },
    )
    show_response(_resp, "Create principal role lab5_readers")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 5 — Assign the principal to the principal role

    **Role Assignments (Management) › Assign Role to Principal**, with `{principalName}` = `lab5_user`.
    Assignments are `PUT`s, so repeating them is harmless.
    """)
    return


@app.cell
def _(AUTH, POLARIS, lab5_creds, requests, show_response):
    _resp = requests.put(
        f"{POLARIS}/api/management/v1/principals/lab5_user/principal-roles",
        headers=AUTH,
        json={"principalRole": {"name": "lab5_readers"}},
    )
    assign_pr_status = _resp.status_code
    show_response(_resp, f"Assign {lab5_creds['principal']['name']} → lab5_readers")
    return (assign_pr_status,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 6 — Create a catalog role

    **Catalog Roles & Grants (Management) › Create Catalog Role**, with `{catalogName}` = `polaris_warehouse`.
    Catalog roles live **inside one catalog** and hold the actual privileges.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.callout(
        mo.md(
            "**Naming note:** the exercise guide calls this role `shop_readonly`. Because several labs share "
            "this Polaris instance, the notebook prefixes it with the lab number: **`lab5_shop_readonly`**."
        ),
        kind="neutral",
    )
    return


@app.cell
def _(AUTH, CATALOG, POLARIS, requests, show_response):
    SHOP_ROLE = "lab5_shop_readonly"
    _resp = requests.post(
        f"{POLARIS}/api/management/v1/catalogs/{CATALOG}/catalog-roles",
        headers=AUTH,
        json={"catalogRole": {"name": SHOP_ROLE, "properties": {}}},
    )
    show_response(_resp, f"Create catalog role {SHOP_ROLE}")
    return (SHOP_ROLE,)


@app.cell(hide_code=True)
def _(mo):
    mo.vstack(
        [
            mo.md("""
            ---
            ## Step 7 — Add grants to the catalog role

            **Catalog Roles & Grants (Management) › Add Grant.** Your first instinct might be one catalog-wide grant:

            ```json
            {"grant": {"type": "catalog", "privilege": "CATALOG_MANAGE_CONTENT"}}
            ```
            """),
            mo.callout(
                mo.md(
                    "**Wait — that's far too permissive.** `CATALOG_MANAGE_CONTENT` lets the holder create, "
                    "write and drop anything in the catalog. Use **fine-grained grants** instead:"
                ),
                kind="warn",
            ),
            mo.md("""
            | # | Level | Privilege | Object | Allows |
            |---|---|---|---|---|
            | 1 | namespace | `TABLE_LIST` | `shop` | list tables in `shop` |
            | 2 | table | `TABLE_READ_DATA` | `shop.orders` | read the data files (vended read credentials) |
            | 3 | table | `TABLE_READ_PROPERTIES` | `shop.orders` | load the table metadata |

            Each grant is wrapped in a `{"grant": {...}}` envelope.
            """),
        ]
    )
    return


@app.cell
def _(AUTH, CATALOG, POLARIS, SHOP_ROLE, pd, requests):
    grants = [
        {"type": "namespace", "privilege": "TABLE_LIST", "namespace": ["shop"]},
        {"type": "table", "privilege": "TABLE_READ_DATA", "namespace": ["shop"], "tableName": "orders"},
        {"type": "table", "privilege": "TABLE_READ_PROPERTIES", "namespace": ["shop"], "tableName": "orders"},
    ]
    _results = []
    for _g in grants:
        _r = requests.put(
            f"{POLARIS}/api/management/v1/catalogs/{CATALOG}/catalog-roles/{SHOP_ROLE}/grants",
            headers=AUTH,
            json={"grant": _g},
        )
        _results.append({"Privilege": _g["privilege"], "On": _g.get("tableName", _g["namespace"][0]), "HTTP": _r.status_code})
    grant_results = pd.DataFrame(_results)
    grant_results
    return grant_results, grants


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 8 — Assign the catalog role to the principal role

    **Role Assignments (Management) › Assign Catalog Role to PR**, with `{principalRoleName}` = `lab5_readers`
    and `{catalogName}` = `polaris_warehouse`. This is the link that connects people to privileges.
    """)
    return


@app.cell
def _(AUTH, CATALOG, POLARIS, SHOP_ROLE, assign_pr_status, grant_results, requests, show_response):
    _resp = requests.put(
        f"{POLARIS}/api/management/v1/principal-roles/lab5_readers/catalog-roles/{CATALOG}",
        headers=AUTH,
        json={"catalogRole": {"name": SHOP_ROLE}},
    )
    chain_ready = _resp.ok and assign_pr_status < 300 and len(grant_results) == 3
    show_response(_resp, f"Assign {SHOP_ROLE} → lab5_readers")
    return (chain_ready,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 9 — Verify the chain

    Three read-only calls walk the chain you built: principal → principal roles → catalog roles → grants.
    """)
    return


@app.cell
def _(AUTH, CATALOG, POLARIS, SHOP_ROLE, chain_ready, requests):
    # 1. Role Assignments › List Roles of Principal
    r1 = requests.get(f"{POLARIS}/api/management/v1/principals/lab5_user/principal-roles", headers=AUTH).json()

    # 2. Role Assignments › Get Catalog Roles of PR
    r2 = requests.get(
        f"{POLARIS}/api/management/v1/principal-roles/lab5_readers/catalog-roles/{CATALOG}", headers=AUTH
    ).json()

    # 3. Catalog Roles & Grants › List Grants
    r3 = requests.get(
        f"{POLARIS}/api/management/v1/catalogs/{CATALOG}/catalog-roles/{SHOP_ROLE}/grants", headers=AUTH
    ).json()
    return r1, r2, r3


@app.cell(hide_code=True)
def _(grants_frame, mo, r1, r2, r3):
    _prs = [r["name"] for r in r1.get("roles", [])]
    _crs = [r["name"] for r in r2.get("roles", [])]
    _grants = r3.get("grants", [])
    _lines = ["flowchart LR", '    P["Principal<br/>lab5_user"]']
    for _i, _pr in enumerate(_prs):
        _lines.append(f'    P --> PR{_i}["Principal role<br/>{_pr}"]')
    _reader = _prs.index("lab5_readers") if "lab5_readers" in _prs else 0
    for _j, _cr in enumerate(_crs):
        _lines.append(f'    PR{_reader} --> CR{_j}["Catalog role<br/>{_cr}"]')
    for _k, _g in enumerate(_grants):
        _obj = ".".join(_g.get("namespace", [])) + (f".{_g['tableName']}" if _g.get("tableName") else "")
        _lines.append(f'    CR0 --> G{_k}["{_g["privilege"]}<br/>{_obj}"]')

    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(", ".join(_prs) or "none", label="1 · Roles of lab5_user", caption="expect lab5_readers", bordered=True),
                    mo.stat(", ".join(_crs) or "none", label="2 · Catalog roles of lab5_readers", caption="expect lab5_shop_readonly", bordered=True),
                    mo.stat(len(_grants), label="3 · Grants on the catalog role", caption="expect 3", bordered=True),
                ],
                widths="equal",
            ),
            mo.mermaid("\n".join(_lines)),
            mo.ui.table(grants_frame(_grants), selection=None, show_column_summaries=False),
            mo.accordion({"Raw responses": mo.vstack([mo.json(r1), mo.json(r2), mo.json(r3)])}),
            mo.callout(
                mo.md("Open the **Role Graph** tab in Polaris Admin (http://localhost:3000): the new roles and edges appear there too."),
                kind="info",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 10 — Namespace and table operations (Catalog API)

    Switch to the Iceberg REST endpoints. `{prefix}` is the catalog name.
    """)
    return


@app.cell
def _(AUTH, CATALOG, POLARIS, requests):
    # Namespaces › List Namespaces
    namespaces = requests.get(f"{POLARIS}/api/catalog/v1/{CATALOG}/namespaces", headers=AUTH).json()

    # Namespaces › Get Namespace
    shop_namespace = requests.get(f"{POLARIS}/api/catalog/v1/{CATALOG}/namespaces/shop", headers=AUTH).json()

    # Tables › List Tables
    tables = requests.get(f"{POLARIS}/api/catalog/v1/{CATALOG}/namespaces/shop/tables", headers=AUTH).json()
    return namespaces, shop_namespace, tables


@app.cell(hide_code=True)
def _(mo, namespaces, pd, shop_namespace, tables):
    mo.hstack(
        [
            mo.vstack(
                [
                    mo.md("**Namespaces**"),
                    mo.ui.table(
                        pd.DataFrame({"namespace": [".".join(n) for n in namespaces.get("namespaces", [])]}),
                        selection=None,
                        show_column_summaries=False,
                    ),
                ]
            ),
            mo.vstack(
                [
                    mo.md("**Properties of `shop`**"),
                    mo.ui.table(
                        pd.DataFrame([{"key": k, "value": v} for k, v in shop_namespace.get("properties", {}).items()]),
                        selection=None,
                        show_column_summaries=False,
                    ),
                ]
            ),
            mo.vstack(
                [
                    mo.md("**Tables in `shop`**"),
                    mo.ui.table(
                        pd.DataFrame({"table": [t["name"] for t in tables.get("identifiers", [])]}),
                        selection=None,
                        show_column_summaries=False,
                    ),
                ]
            ),
        ],
        widths="equal",
        align="start",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Load table metadata

    **Tables (Catalog API) › Load Table Metadata.** This is exactly what Trino and Spark read when they
    query a table: schema, partition spec, snapshots and the `metadata-location` pointer.
    """)
    return


@app.cell
def _(AUTH, CATALOG, POLARIS, requests):
    table_meta = requests.get(
        f"{POLARIS}/api/catalog/v1/{CATALOG}/namespaces/shop/tables/orders",
        headers=AUTH,
    ).json()
    return (table_meta,)


@app.cell(hide_code=True)
def _(mo, pd, table_meta):
    _md = table_meta.get("metadata", {})
    _schema = next(
        (s for s in _md.get("schemas", []) if s.get("schema-id") == _md.get("current-schema-id")),
        {"fields": []},
    )
    _spec = next((s for s in _md.get("partition-specs", []) if s.get("spec-id") == _md.get("default-spec-id")), {})
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(_md.get("format-version"), label="Format version", bordered=True),
                    mo.stat(len(_md.get("snapshots", [])), label="Snapshots", bordered=True),
                    mo.stat(len(_schema["fields"]), label="Columns", bordered=True),
                    mo.stat(len(_spec.get("fields", [])) or "none", label="Partition fields", bordered=True),
                ],
                widths="equal",
            ),
            mo.md(f"**metadata-location:** `{table_meta.get('metadata-location', 'N/A')}`"),
            mo.ui.tabs(
                {
                    "Schema": mo.ui.table(
                        pd.DataFrame(
                            [{"id": f["id"], "name": f["name"], "type": str(f["type"]), "required": f["required"]} for f in _schema["fields"]]
                        ),
                        selection=None,
                        show_column_summaries=False,
                    ),
                    "Snapshots": mo.ui.table(
                        pd.DataFrame(
                            [
                                {
                                    "snapshot-id": str(s["snapshot-id"]),
                                    "operation": s.get("summary", {}).get("operation"),
                                    "added-records": s.get("summary", {}).get("added-records"),
                                    "timestamp-ms": s["timestamp-ms"],
                                }
                                for s in _md.get("snapshots", [])
                            ],
                            columns=["snapshot-id", "operation", "added-records", "timestamp-ms"],
                        ),
                        selection=None,
                        show_column_summaries=False,
                    ),
                    "Full response": mo.json(table_meta),
                }
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### The same calls, as `lab5_user`

    So far we used `root`. Now get a token with **`lab5_user`'s** credentials and repeat the calls.
    Only what the three grants allow should succeed.
    """)
    return


@app.cell
def _(CATALOG, POLARIS, REALM, chain_ready, lab5_client_id, lab5_secret, mo, requests):
    mo.stop(not chain_ready, mo.callout("The role chain from Steps 5–8 isn't complete yet.", kind="warn"))
    _user_token = requests.post(
        f"{POLARIS}/api/catalog/v1/oauth/tokens",
        headers={"Polaris-Realm": REALM},
        data={
            "grant_type": "client_credentials",
            "client_id": lab5_client_id,
            "client_secret": lab5_secret,
            "scope": "PRINCIPAL_ROLE:ALL",
        },
    ).json()["access_token"]
    USER_AUTH = {"Authorization": f"Bearer {_user_token}", "Polaris-Realm": REALM}

    _base = f"{POLARIS}/api/catalog/v1/{CATALOG}"
    user_checks = [
        ("List namespaces", "GET", f"{_base}/namespaces", {}, "403 (no LIST_NAMESPACES)"),
        ("List tables in shop", "GET", f"{_base}/namespaces/shop/tables", {}, "200 (TABLE_LIST)"),
        ("Load shop.orders metadata", "GET", f"{_base}/namespaces/shop/tables/orders", {}, "200 (TABLE_READ_PROPERTIES)"),
        ("Load shop.orders + read credentials", "GET", f"{_base}/namespaces/shop/tables/orders",
         {"X-Iceberg-Access-Delegation": "vended-credentials"}, "200 (TABLE_READ_DATA)"),
        ("Load shop.order_items", "GET", f"{_base}/namespaces/shop/tables/order_items", {}, "403 (no grant)"),
        ("Create namespace lab5_probe", "POST", f"{_base}/namespaces", {}, "403 (read-only role)"),
    ]
    user_results = []
    for _name, _method, _url, _extra, _expect in user_checks:
        _body = {"namespace": ["lab5_probe"]} if _method == "POST" else None
        _r = requests.request(_method, _url, headers={**USER_AUTH, **_extra}, json=_body)
        user_results.append({"Call": _name, "Expected": _expect, "Actual": _r.status_code})
    return USER_AUTH, user_results


@app.cell(hide_code=True)
def _(mo, pd, user_results):
    _df = pd.DataFrame(user_results)
    _match = sum(str(r["Actual"]) == r["Expected"][:3] for r in user_results)
    mo.vstack(
        [
            mo.ui.table(_df, selection=None, show_column_summaries=False),
            mo.callout(
                mo.md(
                    f"**{_match} of {len(user_results)} calls behaved as the grants predict.** "
                    "Polaris answers a missing privilege with an explicit **HTTP 403 ForbiddenException**, "
                    "not an empty list."
                ),
                kind="success" if _match == len(user_results) else "warn",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 11 — Rotate credentials

    **Principals (Management) › Rotate Credentials.** Rotation is a **self-service** operation:
    the principal calls `/rotate` with **its own token**. An admin who needs to replace someone else's
    secret uses `/reset` instead (that's what Step 3 does on a re-run).
    """)
    return


@app.cell
def _(POLARIS, REALM, USER_AUTH, lab5_client_id, lab5_secret, requests, user_results):
    # An admin can't rotate someone else's secret: root gets 403 here.
    _root_token = requests.post(
        f"{POLARIS}/api/catalog/v1/oauth/tokens",
        headers={"Polaris-Realm": REALM},
        data={"grant_type": "client_credentials", "client_id": "root", "client_secret": "s3cr3t", "scope": "PRINCIPAL_ROLE:ALL"},
    ).json()["access_token"]
    root_rotate = requests.post(
        f"{POLARIS}/api/management/v1/principals/lab5_user/rotate",
        headers={"Authorization": f"Bearer {_root_token}", "Polaris-Realm": REALM},
    )

    # lab5_user rotates its own credentials.
    _resp = requests.post(f"{POLARIS}/api/management/v1/principals/lab5_user/rotate", headers=USER_AUTH)
    _resp.raise_for_status()
    new_creds = _resp.json()

    def _token_status(client_id, secret):
        return requests.post(
            f"{POLARIS}/api/catalog/v1/oauth/tokens",
            headers={"Polaris-Realm": REALM},
            data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": secret, "scope": "PRINCIPAL_ROLE:ALL"},
        ).status_code

    rotation_checks = {
        "New secret → new token": _token_status(lab5_client_id, new_creds["credentials"]["clientSecret"]),
        "Previous secret → new token": _token_status(lab5_client_id, lab5_secret),
        "Token issued before rotation → list shop tables": requests.get(
            f"{POLARIS}/api/catalog/v1/polaris_warehouse/namespaces/shop/tables", headers=USER_AUTH
        ).status_code,
    }
    return new_creds, root_rotate, rotation_checks


@app.cell(hide_code=True)
def _(lab5_secret, mask, mo, new_creds, pd, root_rotate, rotation_checks):
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(f"HTTP {root_rotate.status_code}", label="root → /rotate lab5_user", caption="admins use /reset", bordered=True),
                    mo.stat(mask(lab5_secret), label="Old clientSecret", bordered=True),
                    mo.stat(mask(new_creds["credentials"]["clientSecret"]), label="New clientSecret", caption="returned once", bordered=True),
                ],
                widths="equal",
            ),
            mo.ui.table(
                pd.DataFrame([{"Check": k, "HTTP": v} for k, v in rotation_checks.items()]),
                selection=None,
                show_column_summaries=False,
            ),
            mo.callout(
                mo.md(
                    "**What the checks show.** Polaris keeps the *previous* secret valid until the **next** rotation "
                    "(a two-secret scheme, so clients can roll over without downtime). Access tokens that were already "
                    "issued stay valid until they expire, because they are signed JWTs, not database sessions."
                ),
                kind="info",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.callout(
        mo.md("**Question:** Why is credential rotation important? What happens to active sessions when you rotate?"),
        kind="neutral",
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
                1. The **Management API** administers principals, roles and grants; the **Catalog API** is the Iceberg REST spec engines use
                2. Every call carries a bearer token from `/oauth/tokens` and a `Polaris-Realm` header
                3. Access flows **principal → principal role → catalog role → grants**; each link is one API call
                4. Prefer fine-grained namespace/table grants over `CATALOG_MANAGE_CONTENT`
                5. Missing privileges produce an explicit **403**, so failures are easy to diagnose
                6. `/rotate` is self-service; `/reset` is the admin's tool. Secrets are shown only once
                """
            ),
            "Exercises": mo.md(
                """
                1. **Create a second catalog role** called `earthquake_readonly` with read access to `earthquakes.events`.
                   Assign it to `lab5_readers`. Verify the grants via the API.
                2. **Create a `lab5_writers` principal role** with a catalog role that has `TABLE_WRITE_DATA` on `shop.orders`.
                   Assign it to `lab5_user`. Now `lab5_user` has both reader and writer roles — what can it do?
                   (Hint: permissions are additive.)
                3. **Use the Check Table Exists endpoint** (`HEAD /api/catalog/v1/polaris_warehouse/namespaces/shop/tables/orders`)
                   to verify `shop.orders` exists. What HTTP status do you get? Try a non-existent table.
                4. **Create a new namespace** called `lab5` via the Namespaces API with properties `owner=student`.
                   Then list namespaces to confirm.
                5. **Challenge:** automate Steps 3–8 into a single Python function that takes a principal name and returns
                   the full RBAC chain — or write it as a bash script with `curl`, the way you'd automate Polaris in CI/CD:

                ```bash
                # Get token
                TOKEN=$(curl -s -X POST http://localhost:8181/api/catalog/v1/oauth/tokens \\
                  -d 'grant_type=client_credentials&client_id=root&client_secret=s3cr3t&scope=PRINCIPAL_ROLE:ALL' \\
                  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

                # Use token in subsequent calls
                curl -s -X GET http://localhost:8181/api/management/v1/principals \\
                  -H "Authorization: Bearer $TOKEN" \\
                  -H "Polaris-Realm: POLARIS"
                ```
                """
            ),
            "Re-running this notebook": mo.md(
                """
                Everything is idempotent: existing roles return **409** (shown as *already exists*), assignments and grants
                are `PUT`s, and `lab5_user` gets a fresh secret through `/reset`. The objects this lab owns are
                `lab5_user`, `lab5_readers` and `lab5_shop_readonly`.
                """
            ),
            "Next lab": mo.md("**Lab 6 — Privileges & RBAC Deep Dive:** a multi-team scenario with three principals and progressively narrower access."),
        },
        multiple=True,
    )
    return


if __name__ == "__main__":
    app.run()
