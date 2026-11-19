import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium", app_title="Lab 3 — Access Control")


@app.cell(hide_code=True)
def _():
    import os
    import re
    from datetime import datetime, timedelta, timezone

    import marimo as mo
    import pandas as pd
    import requests
    import urllib3
    from pyiceberg.catalog import load_catalog
    from sqlalchemy import create_engine, text

    urllib3.disable_warnings()

    TRINO_HOST = os.environ.get("TRINO_HOST", "localhost")
    POLARIS_HOST = os.environ.get("POLARIS_HOST", "localhost")
    POLARIS = f"http://{POLARIS_HOST}:8181"
    POLARIS_HEALTH = f"http://{POLARIS_HOST}:8182/q/health"
    TRINO_INFO = f"https://{TRINO_HOST}:8443/v1/info"
    S3_ENDPOINT = f"http://{os.environ.get('S3_HOST', 'localhost')}:4566"
    REALM = "POLARIS"
    CATALOG_NAME = "polaris_warehouse"

    trino = create_engine(
        f"trino://admin:admin123@{TRINO_HOST}:8443/iceberg",
        connect_args={"http_scheme": "https", "verify": False},
    )
    return (
        CATALOG_NAME,
        POLARIS,
        POLARIS_HEALTH,
        REALM,
        S3_ENDPOINT,
        TRINO_HOST,
        TRINO_INFO,
        create_engine,
        datetime,
        load_catalog,
        mo,
        pd,
        re,
        requests,
        text,
        timedelta,
        timezone,
        trino,
    )


@app.cell(hide_code=True)
def _(datetime, mo, pd, text, timedelta, timezone, trino):
    def run_sql(sql, engine=None):
        """Run one Trino statement. Returns a DataFrame for queries, None for DDL/DML."""
        with (engine or trino).connect() as conn:
            result = conn.execute(text(sql))
            if result.returns_rows:
                return pd.DataFrame(result.fetchall(), columns=list(result.keys()))
        return None

    def show(df):
        return mo.ui.table(df, selection=None, show_column_summaries=False)

    def trino_error(exc):
        """Shorten a Trino/SQLAlchemy error to its message."""
        msg = str(getattr(exc, "orig", exc))
        if 'message="' in msg:
            msg = msg.split('message="', 1)[1].split('", query_id', 1)[0]
        return msg

    def ensure_earthquake_events():
        """Create a stand-in for the dlt table iceberg.earthquakes.events, only if it is missing.

        Same columns as the rows dlt/pipeline.py yields (the real dlt table also has _dlt_load_id/_dlt_id).
        Returns True if it created the sample. Never drops or overwrites an existing table.
        """
        run_sql("CREATE SCHEMA IF NOT EXISTS iceberg.earthquakes")
        exists = not run_sql(
            "SELECT table_name FROM iceberg.information_schema.tables "
            "WHERE table_schema = 'earthquakes' AND table_name = 'events'"
        ).empty
        if exists:
            return False
        run_sql(
            """
            CREATE TABLE IF NOT EXISTS iceberg.earthquakes.events (
                earthquake_id VARCHAR, magnitude DOUBLE, place VARCHAR,
                event_time TIMESTAMP(6) WITH TIME ZONE, updated_time TIMESTAMP(6) WITH TIME ZONE,
                longitude DOUBLE, latitude DOUBLE, depth_km DOUBLE, tsunami BOOLEAN,
                event_type VARCHAR, title VARCHAR, status VARCHAR, magnitude_type VARCHAR,
                significance BIGINT, felt_reports BIGINT, alert_level VARCHAR, url VARCHAR
            ) WITH (format = 'PARQUET')
            """
        )
        if run_sql("SELECT count(*) AS n FROM iceberg.earthquakes.events")["n"][0] > 0:
            return False
        # (id, mag, place, lon, lat, depth_km, magType, hours_ago, tsunami, felt, alert, status)
        quakes = [
            ("ak0256p1kq9", 1.8, "42 km NW of Talkeetna, Alaska", -150.95, 62.66, 48.3, "ml", 0.4, False, None, None, "automatic"),
            ("nc75093312", 0.9, "2 km NW of The Geysers, CA", -122.77, 38.79, 2.1, "md", 0.9, False, None, None, "automatic"),
            ("ci41068952", 2.4, "11 km SE of Ridgecrest, CA", -117.58, 35.56, 7.9, "ml", 1.6, False, 4, None, "reviewed"),
            ("hv74512387", 2.1, "8 km SW of Volcano, Hawaii", -155.29, 19.38, 1.6, "md", 2.2, False, None, None, "automatic"),
            ("pr71473215", 3.1, "45 km N of Hatillo, Puerto Rico", -66.81, 18.89, 34.0, "md", 2.8, False, None, None, "reviewed"),
            ("nn00891234", 1.4, "28 km SE of Mina, Nevada", -117.88, 38.20, 8.5, "ml", 3.5, False, None, None, "automatic"),
            ("us7000q4ab", 4.7, "63 km W of Iquique, Chile", -70.75, -20.21, 35.4, "mb", 4.1, False, None, None, "reviewed"),
            ("us7000q4ac", 5.6, "off the coast of Jalisco, Mexico", -105.80, 19.10, 10.0, "mww", 4.9, False, 12, "green", "reviewed"),
            ("ok2026vxyz", 2.6, "4 km E of Perry, Oklahoma", -97.24, 36.29, 5.0, "ml", 5.6, False, 7, None, "reviewed"),
            ("uw62012345", 1.0, "9 km NE of Mount St. Helens, Washington", -122.12, 46.25, 3.2, "ml", 6.3, False, None, None, "automatic"),
            ("ak0256p2abc", 3.4, "Andreanof Islands, Aleutian Islands, Alaska", -175.60, 51.40, 22.0, "ml", 7.0, False, None, None, "reviewed"),
            ("us7000q4ad", 4.3, "Tonga Islands", -174.20, -18.80, 80.0, "mb", 7.8, False, None, None, "reviewed"),
            ("us7000q4ae", 4.4, "central Mid-Atlantic Ridge", -24.80, 0.90, 10.0, "mb", 8.4, False, None, None, "reviewed"),
            ("us7000q4af", 4.1, "Crete, Greece", 25.40, 35.20, 18.0, "mb", 9.1, False, 6, None, "reviewed"),
            ("us7000q4ag", 4.8, "15 km S of Sindirgi, Turkey", 28.20, 39.10, 9.0, "mww", 9.9, False, 35, None, "reviewed"),
            ("us7000q4ah", 4.0, "3 km SE of Montereale, Italy", 13.25, 42.50, 9.0, "mb", 10.6, False, 20, None, "reviewed"),
            ("us7000q4ai", 3.2, "Reykjanes Peninsula, Iceland", -22.40, 63.90, 5.0, "ml", 11.2, False, 3, None, "reviewed"),
            ("us7000q4aj", 4.5, "southern Iran", 56.90, 27.40, 10.0, "mb", 12.0, False, None, None, "reviewed"),
            ("us7000q4ak", 4.6, "Afar region, Ethiopia", 40.30, 11.20, 10.0, "mb", 12.7, False, None, None, "reviewed"),
            ("us7000q4al", 6.6, "84 km E of Hachinohe, Japan", 142.50, 40.50, 30.0, "mww", 13.5, True, 48, "green", "reviewed"),
            ("us7000q4am", 5.1, "Kepulauan Talaud, Indonesia", 126.70, 4.20, 45.0, "mb", 14.2, False, None, None, "reviewed"),
            ("us7000q4an", 4.9, "12 km SE of Sablayan, Philippines", 121.00, 12.70, 25.0, "mb", 15.0, False, 2, None, "reviewed"),
            ("us7000q4ap", 4.4, "New Britain region, Papua New Guinea", 151.60, -5.60, 55.0, "mb", 15.8, False, None, None, "reviewed"),
            ("us7000q4aq", 5.3, "south of the Fiji Islands", 178.90, -25.20, 560.0, "mb", 16.5, False, None, None, "reviewed"),
            ("us7000q4ar", 6.9, "near the east coast of Kamchatka, Russia", 160.80, 52.90, 19.0, "mww", 17.3, True, 5, "yellow", "reviewed"),
            ("us7000q4as", 4.2, "Hindu Kush region, Afghanistan", 70.90, 36.50, 210.0, "mb", 18.1, False, None, None, "reviewed"),
            ("us7000q4at", 4.3, "Nepal", 85.30, 28.10, 12.0, "mb", 18.9, False, 9, None, "reviewed"),
            ("us7000q4au", 5.0, "Molucca Sea", 126.50, 1.50, 30.0, "mb", 19.6, False, None, None, "reviewed"),
            ("us7000q4av", 4.0, "Kuril Islands", 150.70, 45.80, 40.0, "mb", 20.4, False, None, None, "reviewed"),
            ("us7000q4aw", 5.8, "off the coast of central Chile", -72.60, -33.90, 25.0, "mww", 21.2, False, 64, "green", "reviewed"),
            ("ci41069012", 0.8, "4 km SW of Anza, CA", -116.70, 33.53, 11.8, "ml", 22.0, False, None, None, "automatic"),
            ("ak0256p3def", 1.3, "61 km SE of Cantwell, Alaska", -148.30, 63.05, 70.4, "ml", 23.3, False, None, None, "automatic"),
        ]

        def lit(v):
            if v is None:
                return "NULL"
            if isinstance(v, bool):
                return "true" if v else "false"
            if isinstance(v, (int, float)):
                return repr(v)
            if isinstance(v, datetime):
                return f"TIMESTAMP '{v.strftime('%Y-%m-%d %H:%M:%S.%f')} UTC'"
            return "'" + str(v).replace("'", "''") + "'"

        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        rows = []
        for (qid, mag, place, lon, lat, depth, mag_type, hours_ago, tsunami, felt, alert, status) in quakes:
            event_time = now - timedelta(hours=hours_ago)
            values = [
                qid, mag, place, event_time, event_time + timedelta(minutes=25), lon, lat, depth, tsunami,
                "earthquake", f"M {mag} - {place}", status, mag_type, int(round(mag * 100 * mag / 6.5)),
                felt, alert, f"https://earthquake.usgs.gov/earthquakes/eventpage/{qid}",
            ]
            rows.append("(" + ", ".join(lit(v) for v in values) + ")")
        run_sql("INSERT INTO iceberg.earthquakes.events VALUES\n" + ",\n".join(rows))
        return True

    return ensure_earthquake_events, run_sql, show, trino_error


@app.cell(hide_code=True)
def _(mo):
    mo.sidebar(
        [
            mo.md("### Lab 3\n**Access Control**"),
            mo.outline(),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.vstack(
        [
            mo.md(
                """
                # Lab 3 — Access Control

                **Level:** 3 (Intermediate) &nbsp;|&nbsp; **Time:** 25 minutes

                **Goal:** understand the Polaris role hierarchy. Create roles, assign grants and verify the
                access restrictions, then see how Trino's own access rules add a second layer on top.
                """
            ),
            mo.callout(
                mo.md(
                    """
                    **What you'll do**

                    1. Get an OAuth token and explore the existing principal and catalog roles
                    2. Connect to Trino as the read-only `analyst` user and watch writes get refused
                    3. Create the catalog role `earthquake_reader` and give it three grants
                    4. Create the principal `student_user`, wire it to the new role and test what it can reach
                    5. Compare the two layers: Trino's `rules.json` and Polaris grants
                    """
                ),
                kind="info",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(POLARIS_HEALTH, TRINO_INFO, mo, requests):
    def _reachable(url, **kw):
        try:
            return requests.get(url, timeout=5, **kw).ok
        except requests.RequestException:
            return False

    _polaris_ok = _reachable(POLARIS_HEALTH)
    _trino_ok = _reachable(TRINO_INFO, verify=False)
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
    stack_ok = True
    mo.hstack(
        [
            mo.stat("Healthy", label="Polaris", caption="REST catalog + management API", bordered=True),
            mo.stat("Healthy", label="Trino", caption="HTTPS :8443", bordered=True),
        ],
        widths="equal",
    )
    return (stack_ok,)


@app.cell(hide_code=True)
def _(ensure_earthquake_events, mo, run_sql, stack_ok):
    # Table-level grants (Step 5) need iceberg.earthquakes.events to exist. It normally comes from the dlt
    # pipeline; if it's missing, create a small sample stand-in with the same columns. Never dropped.
    assert stack_ok
    with mo.status.spinner(title="Checking iceberg.earthquakes.events…"):
        _created = ensure_earthquake_events()
        _rows = int(run_sql("SELECT count(*) AS n FROM iceberg.earthquakes.events")["n"][0])
        _from_dlt = "_dlt_load_id" in set(run_sql("DESCRIBE iceberg.earthquakes.events")["Column"])
    events_ready = True
    mo.callout(
        mo.md(
            f"**`iceberg.earthquakes.events` was missing**, so this notebook created a stand-in with "
            f"{_rows} sample earthquakes (same columns as `dlt/pipeline.py`). The real data comes from the dlt "
            "pipeline: `podman compose up dlt-earthquakes` (or `docker compose up dlt-earthquakes`). Lab 4 covers it."
            if _created
            else f"`iceberg.earthquakes.events` exists ({_rows} rows, "
            + ("loaded by dlt" if _from_dlt else "a sample stand-in because the dlt pipeline hasn't run")
            + "). Step 5 grants access to it."
        ),
        kind="warn" if _created else "neutral",
    )
    return (events_ready,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Concepts: the Polaris access model
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.hstack(
        [
            mo.mermaid(
                """
                flowchart TD
                    P["Principal<br/>user or service with credentials"] -->|"assigned to"| PR["Principal role<br/>groups principals"]
                    PR -->|"assigned"| CR["Catalog role<br/>permission container, one catalog"]
                    CR -->|"holds"| G["Grants<br/>TABLE_READ_DATA, NAMESPACE_LIST, …"]
                """
            ),
            mo.md(
                """
                - A **principal** is a user or service with credentials (client ID + secret)
                - A **principal role** groups principals (like "analysts", "engineers")
                - A **catalog role** holds permissions for **one** catalog
                - **Grants** are the actual privileges attached to catalog roles

                Privileges never attach to a principal directly. You always go
                principal → principal role → catalog role → grant.
                """
            ),
        ],
        widths=[2, 3],
        align="center",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 1 — Get an OAuth token

    Every Polaris API call needs a bearer token. We use the bootstrap `root` principal and the
    OAuth2 client-credentials flow. The `Polaris-Realm` header picks the realm.
    """)
    return


@app.cell
def _(POLARIS, REALM, requests, stack_ok):
    assert stack_ok
    token_resp = requests.post(
        f"{POLARIS}/api/catalog/v1/oauth/tokens",
        headers={"Polaris-Realm": REALM},
        data={
            "grant_type": "client_credentials",
            "client_id": "root",
            "client_secret": "s3cr3t",
            "scope": "PRINCIPAL_ROLE:ALL",
        },
        timeout=10,
    ).json()
    TOKEN = token_resp["access_token"]
    AUTH = {"Authorization": f"Bearer {TOKEN}", "Polaris-Realm": REALM}
    return AUTH, TOKEN, token_resp


@app.cell(hide_code=True)
def _(TOKEN, mo, token_resp):
    mo.hstack(
        [
            mo.stat(f"{TOKEN[:20]}…", label="Access token", caption="truncated", bordered=True),
            mo.stat(token_resp.get("token_type", "?"), label="Token type", bordered=True),
            mo.stat(f"{int(token_resp.get('expires_in', 0)) // 60} min", label="Expires in", bordered=True),
        ],
        widths="equal",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 2 — Explore the existing roles

    List the principal roles and the catalog roles of `polaris_warehouse`.
    """)
    return


@app.cell
def _(AUTH, CATALOG_NAME, POLARIS, requests):
    principal_roles = requests.get(f"{POLARIS}/api/management/v1/principal-roles", headers=AUTH, timeout=10).json()
    catalog_roles = requests.get(
        f"{POLARIS}/api/management/v1/catalogs/{CATALOG_NAME}/catalog-roles", headers=AUTH, timeout=10
    ).json()
    return catalog_roles, principal_roles


@app.cell(hide_code=True)
def _(catalog_roles, mo, pd, principal_roles):
    def _frame(roles):
        return pd.DataFrame(
            [{"Name": r["name"], "Properties": r.get("properties") or "", "Version": r.get("entityVersion")} for r in roles]
        )

    mo.hstack(
        [
            mo.vstack(
                [
                    mo.md(f"**Principal roles** ({len(principal_roles['roles'])})"),
                    mo.ui.table(_frame(principal_roles["roles"]), selection=None, show_column_summaries=False),
                ]
            ),
            mo.vstack(
                [
                    mo.md(f"**Catalog roles in `polaris_warehouse`** ({len(catalog_roles['roles'])})"),
                    mo.ui.table(_frame(catalog_roles["roles"]), selection=None, show_column_summaries=False),
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
    ### Which catalog roles and grants does each principal role have?

    The Polaris Admin UI (http://localhost:3000, **Access Control** tab) shows this when you expand a principal role.
    Here we ask the API directly. Pick a principal role:
    """)
    return


@app.cell(hide_code=True)
def _(mo, principal_roles):
    _names = sorted(r["name"] for r in principal_roles["roles"])
    role_picker = mo.ui.dropdown(
        _names, value="service_admin" if "service_admin" in _names else _names[0], label="Principal role"
    )
    role_picker
    return (role_picker,)


@app.cell(hide_code=True)
def _(AUTH, CATALOG_NAME, POLARIS, mo, pd, requests, role_picker):
    def _object(g):
        parts = list(g.get("namespace") or [])
        if g.get("tableName"):
            parts.append(g["tableName"])
        return ".".join(parts) or CATALOG_NAME

    _crs = requests.get(
        f"{POLARIS}/api/management/v1/principal-roles/{role_picker.value}/catalog-roles/{CATALOG_NAME}",
        headers=AUTH,
        timeout=10,
    ).json().get("roles", [])
    _rows = []
    for _cr in _crs:
        _grants = requests.get(
            f"{POLARIS}/api/management/v1/catalogs/{CATALOG_NAME}/catalog-roles/{_cr['name']}/grants",
            headers=AUTH,
            timeout=10,
        ).json().get("grants", [])
        for _g in _grants or [{}]:
            _rows.append(
                {
                    "Catalog role": _cr["name"],
                    "Privilege": _g.get("privilege", "(no grants)"),
                    "Scope": _g.get("type", ""),
                    "Object": _object(_g) if _g else "",
                }
            )
    (
        mo.ui.table(pd.DataFrame(_rows), selection=None, show_column_summaries=False)
        if _rows
        else mo.callout(mo.md(f"`{role_picker.value}` has no catalog roles in `{CATALOG_NAME}`."), kind="neutral")
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 3 — Test the analyst user via SQL

    Trino has its own users. The `analyst` user (password `analyst123`) is **read-only** on the
    `postgres` and `iceberg` catalogs and can't see `tpch` or `memory` at all. Trino's `etc/rules.json` defines this.
    We connect as `analyst` and try each statement from the lab.
    """)
    return


@app.cell
def _(TRINO_HOST, create_engine, events_ready, run_sql, trino_error):
    assert events_ready
    trino_analyst = create_engine(
        f"trino://analyst:analyst123@{TRINO_HOST}:8443/iceberg",
        connect_args={"http_scheme": "https", "verify": False},
    )

    analyst_statements = [
        ("Read", "SELECT * FROM postgres.public.customers LIMIT 3", "works (read access)"),
        ("Read", "SELECT * FROM iceberg.shop.orders LIMIT 3", "works (read access)"),
        ("Write", "CREATE TABLE iceberg.shop.test_table (id int)", "FAILS (no write access)"),
        ("Catalog", "SHOW SCHEMAS IN tpch", "FAILS (can't see this catalog)"),
        ("Catalog", "SHOW SCHEMAS IN memory", "FAILS (can't see this catalog)"),
    ]
    analyst_results = []
    analyst_previews = {}
    for _kind, _sql, _expected in analyst_statements:
        try:
            _df = run_sql(_sql, engine=trino_analyst)
            _outcome, _detail = "Allowed", f"{0 if _df is None else len(_df)} rows"
            if _df is not None:
                analyst_previews[_sql] = _df
            if _sql.startswith("CREATE TABLE"):
                # Shouldn't happen, but try not to leave a stray table behind if the rules were loosened.
                try:
                    run_sql("DROP TABLE IF EXISTS iceberg.shop.test_table")
                except Exception:
                    pass
        except Exception as e:
            _outcome, _detail = "Denied", trino_error(e)
        analyst_results.append(
            {"Type": _kind, "Statement": _sql, "Expected": _expected, "Result": _outcome, "Trino says": _detail}
        )
    return analyst_previews, analyst_results


@app.cell(hide_code=True)
def _(analyst_previews, analyst_results, mo, pd):
    _df = pd.DataFrame(analyst_results)
    _ok = all(
        (r["Result"] == "Allowed") == r["Expected"].startswith("works") for r in analyst_results
    )
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(int((_df["Result"] == "Allowed").sum()), label="Allowed", bordered=True),
                    mo.stat(int((_df["Result"] == "Denied").sum()), label="Denied", bordered=True),
                ],
                widths="equal",
            ),
            mo.ui.table(_df, selection=None, show_column_summaries=False),
            mo.ui.tabs(
                {
                    _sql.split(" FROM ")[1].split(" ")[0]: mo.ui.table(_p, selection=None, show_column_summaries=False)
                    for _sql, _p in analyst_previews.items()
                }
            ),
            mo.callout(
                mo.md(
                    "Every statement behaved as expected: the analyst can read but can't write or see `tpch` / `memory`."
                    if _ok
                    else "Some statements didn't behave as expected. Check `etc/rules.json`."
                ),
                kind="success" if _ok else "warn",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.accordion(
        {
            "Question: What error messages do you get? Why?": mo.md(
                """
                - `Access Denied: Cannot create table iceberg.shop.test_table`: `rules.json` gives `analyst`
                  `"allow": "read-only"` on `iceberg`, so Trino refuses DDL/DML **before** it ever calls Polaris.
                - `Access Denied: Cannot access catalog tpch` / `memory`: the rule `"allow": "none"` hides those catalogs completely.

                Both refusals come from **Trino's** access control. Polaris never sees the request. Trino talks to
                Polaris as `root` (see `etc/catalog/iceberg.properties`), so Polaris grants don't distinguish Trino users.
                """
            ),
            "Try it in the Trino CLI": mo.md(
                """
                ```bash
                podman exec -e TRINO_PASSWORD=analyst123 -it trino \\
                  trino --server https://localhost:8443 --user analyst --password --insecure
                # or: docker exec -e TRINO_PASSWORD=analyst123 -it trino trino --server https://localhost:8443 --user analyst --password --insecure
                ```

                Run the statements above, then type `quit` to exit.
                """
            ),
        },
        multiple=True,
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 4 — Create a new catalog role: `earthquake_reader`

    In the Admin UI this is **Access Control → + New Role / Grant → New Catalog Role**
    (catalog `polaris_warehouse`, name `earthquake_reader`). Here's the same thing through the management API.
    A `409 Conflict` just means the role already exists from an earlier run.
    """)
    return


@app.cell
def _(AUTH, CATALOG_NAME, POLARIS, requests):
    create_role_resp = requests.post(
        f"{POLARIS}/api/management/v1/catalogs/{CATALOG_NAME}/catalog-roles",
        headers={**AUTH, "Content-Type": "application/json"},
        json={"catalogRole": {"name": "earthquake_reader", "properties": {}}},
        timeout=10,
    )
    return (create_role_resp,)


@app.cell(hide_code=True)
def _(create_role_resp, mo):
    _code = create_role_resp.status_code
    mo.callout(
        mo.md(
            {
                201: "**HTTP 201 Created.** Catalog role `earthquake_reader` now exists in `polaris_warehouse`.",
                409: "**HTTP 409 Conflict.** `earthquake_reader` already exists (from an earlier run), which is fine.",
            }.get(_code, f"**HTTP {_code}.** {create_role_resp.text[:300]}")
        ),
        kind="success" if _code in (201, 409) else "danger",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 5 — Add grants to `earthquake_reader`

    Three grants: list the tables in the `earthquakes` namespace, and read the data and the properties
    of the `events` table. Each one is a `PUT` with a body wrapped in `{"grant": {...}}`.
    Granting the same privilege twice is harmless.
    """)
    return


@app.cell
def _(AUTH, CATALOG_NAME, POLARIS, events_ready, requests):
    assert events_ready  # table-level grants need the table to exist
    grants = [
        {"type": "namespace", "privilege": "TABLE_LIST", "namespace": ["earthquakes"]},
        {
            "type": "table",
            "privilege": "TABLE_READ_DATA",
            "namespace": ["earthquakes"],
            "tableName": "events",
        },
        {
            "type": "table",
            "privilege": "TABLE_READ_PROPERTIES",
            "namespace": ["earthquakes"],
            "tableName": "events",
        },
    ]
    grant_results = []
    for grant in grants:
        _resp = requests.put(
            f"{POLARIS}/api/management/v1/catalogs/{CATALOG_NAME}/catalog-roles/earthquake_reader/grants",
            headers={**AUTH, "Content-Type": "application/json"},
            json={"grant": grant},
            timeout=10,
        )
        grant_results.append({"Privilege": grant["privilege"], "Scope": grant["type"], "HTTP status": _resp.status_code})
    return (grant_results,)


@app.cell(hide_code=True)
def _(grant_results, mo, pd):
    _ok = all(r["HTTP status"] in (200, 201) for r in grant_results)
    mo.vstack(
        [
            mo.ui.table(pd.DataFrame(grant_results), selection=None, show_column_summaries=False),
            mo.callout(
                "All three grants were accepted." if _ok else "Some grants were rejected. Check the status codes.",
                kind="success" if _ok else "danger",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 6 — Verify the grants

    Read the grants back from Polaris.
    """)
    return


@app.cell
def _(AUTH, CATALOG_NAME, POLARIS, grant_results, requests):
    assert grant_results
    grants_list = requests.get(
        f"{POLARIS}/api/management/v1/catalogs/{CATALOG_NAME}/catalog-roles/earthquake_reader/grants",
        headers=AUTH,
        timeout=10,
    ).json()
    return (grants_list,)


@app.cell(hide_code=True)
def _(grants_list, mo, pd):
    mo.ui.table(
        pd.DataFrame(
            [
                {
                    "Privilege": g["privilege"],
                    "Scope": g["type"],
                    "Namespace": ".".join(g.get("namespace", [])),
                    "Table": g.get("tableName", ""),
                }
                for g in grants_list.get("grants", [])
            ]
        ),
        selection=None,
        show_column_summaries=False,
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 7 — Create a new principal via the API

    In the Admin UI this is **API Explorer → Principals (Management) → Create Principal**.
    The response contains the `clientId` and `clientSecret`. **Polaris shows the secret only once.**
    On a re-run the principal already exists (`409`), so we ask Polaris to **reset** its credentials,
    which returns a fresh secret.
    """)
    return


@app.cell
def _(AUTH, POLARIS, requests):
    _resp = requests.post(
        f"{POLARIS}/api/management/v1/principals",
        headers={**AUTH, "Content-Type": "application/json"},
        json={
            "principal": {"name": "student_user", "properties": {}},
            "credentialRotationRequired": False,
        },
        timeout=10,
    )
    student_created = _resp.status_code == 201
    if _resp.status_code == 409:
        _resp = requests.post(
            f"{POLARIS}/api/management/v1/principals/student_user/reset",
            headers={**AUTH, "Content-Type": "application/json"},
            json={},
            timeout=10,
        )
    _resp.raise_for_status()
    student_creds = _resp.json()["credentials"]
    return student_created, student_creds


@app.cell(hide_code=True)
def _(mo, student_created, student_creds):
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(student_creds["clientId"], label="clientId", bordered=True),
                    mo.stat(f"{student_creds['clientSecret'][:6]}…", label="clientSecret", caption="masked", bordered=True),
                ],
                widths="equal",
            ),
            mo.callout(
                mo.md(
                    ("Created principal **`student_user`**. " if student_created else "**`student_user`** already existed, so its credentials were reset. ")
                    + "Save these credentials. The full secret is in the `student_creds` variable."
                ),
                kind="success",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 8 — Wire the principal to the catalog role

    A catalog role does nothing until a **principal role** holds it and a **principal** holds that principal role.
    The paper lab assigns an existing role (e.g. `service_admin`). That gives `student_user` admin rights and
    would hide the restriction, so here we create a dedicated principal role, `earthquake_readers`.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.mermaid(
        """
        flowchart LR
            P["Principal<br/>student_user"] --> PR["Principal role<br/>earthquake_readers"]
            PR --> CR["Catalog role<br/>earthquake_reader"]
            CR --> G1["TABLE_LIST<br/>namespace earthquakes"]
            CR --> G2["TABLE_READ_DATA<br/>earthquakes.events"]
            CR --> G3["TABLE_READ_PROPERTIES<br/>earthquakes.events"]
        """
    )
    return


@app.cell
def _(AUTH, CATALOG_NAME, POLARIS, grant_results, requests, student_creds):
    assert grant_results and student_creds
    _json = {**AUTH, "Content-Type": "application/json"}
    wiring = {}

    # 1. principal role (409 = already exists)
    wiring["create principal role"] = requests.post(
        f"{POLARIS}/api/management/v1/principal-roles",
        headers=_json,
        json={"principalRole": {"name": "earthquake_readers", "properties": {}}},
        timeout=10,
    ).status_code
    # 2. catalog role -> principal role
    wiring["assign catalog role"] = requests.put(
        f"{POLARIS}/api/management/v1/principal-roles/earthquake_readers/catalog-roles/{CATALOG_NAME}",
        headers=_json,
        json={"catalogRole": {"name": "earthquake_reader"}},
        timeout=10,
    ).status_code
    # 3. principal role -> principal  (API Explorer: Role Assignments > Assign Role to Principal)
    wiring["assign to student_user"] = requests.put(
        f"{POLARIS}/api/management/v1/principals/student_user/principal-roles",
        headers=_json,
        json={"principalRole": {"name": "earthquake_readers"}},
        timeout=10,
    ).status_code
    return (wiring,)


@app.cell(hide_code=True)
def _(mo, pd, wiring):
    mo.ui.table(
        pd.DataFrame([{"Step": k, "HTTP status": v, "OK": v in (200, 201, 409)} for k, v in wiring.items()]),
        selection=None,
        show_column_summaries=False,
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Verify in the role graph

    The Admin UI's **Role Graph** tab draws the principal → principal role → catalog role mapping.
    Here's the same graph built from the API. You should see the new edge from `earthquake_readers`
    to `earthquake_reader`. Other labs' roles may show up too.
    """)
    return


@app.cell(hide_code=True)
def _(AUTH, CATALOG_NAME, POLARIS, mo, re, requests, wiring):
    assert wiring

    def _id(prefix, name):
        return prefix + re.sub(r"\W", "_", name)

    _get = lambda path: requests.get(f"{POLARIS}/api/management/v1{path}", headers=AUTH, timeout=10).json()
    _lines = ["flowchart LR"]
    _seen_prs = set()
    for _p in _get("/principals").get("principals", []):
        _lines.append(f'    {_id("p_", _p["name"])}(["{_p["name"]}"])')
        for _pr in _get(f"/principals/{_p['name']}/principal-roles").get("roles", []):
            _lines.append(f'    {_id("p_", _p["name"])} --> {_id("pr_", _pr["name"])}["{_pr["name"]}"]')
            _seen_prs.add(_pr["name"])
    for _pr in sorted(_seen_prs):
        for _cr in _get(f"/principal-roles/{_pr}/catalog-roles/{CATALOG_NAME}").get("roles", []):
            _lines.append(f'    {_id("pr_", _pr)} --> {_id("cr_", _cr["name"])}[/"{_cr["name"]}"/]')
    _lines += [
        "    classDef new fill:#d1fae5,stroke:#059669",
        f"    class {_id('p_', 'student_user')},{_id('pr_', 'earthquake_readers')},{_id('cr_', 'earthquake_reader')} new",
    ]
    mo.vstack(
        [
            mo.mermaid("\n".join(_lines)),
            mo.md("_Rounded = principal, rectangle = principal role, slanted = catalog role. Green = created in this lab._"),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Does the restriction hold?

    Log in as `student_user` and call the Iceberg REST API directly, next to `root` for comparison.
    """)
    return


@app.cell
def _(AUTH, CATALOG_NAME, POLARIS, REALM, requests, student_creds, wiring):
    assert wiring
    student_token = requests.post(
        f"{POLARIS}/api/catalog/v1/oauth/tokens",
        headers={"Polaris-Realm": REALM},
        data={
            "grant_type": "client_credentials",
            "client_id": student_creds["clientId"],
            "client_secret": student_creds["clientSecret"],
            "scope": "PRINCIPAL_ROLE:ALL",
        },
        timeout=10,
    ).json()["access_token"]
    STUDENT_AUTH = {"Authorization": f"Bearer {student_token}", "Polaris-Realm": REALM}

    _base = f"{POLARIS}/api/catalog/v1/{CATALOG_NAME}"
    access_checks = {
        "List tables in earthquakes": f"{_base}/namespaces/earthquakes/tables",
        "Load table earthquakes.events": f"{_base}/namespaces/earthquakes/tables/events",
        "List tables in shop": f"{_base}/namespaces/shop/tables",
        "Load table shop.orders": f"{_base}/namespaces/shop/tables/orders",
        "List all namespaces": f"{_base}/namespaces",
    }
    access_matrix = [
        {
            "Request": _name,
            "root": requests.get(_url, headers=AUTH, timeout=10).status_code,
            "student_user": requests.get(_url, headers=STUDENT_AUTH, timeout=10).status_code,
        }
        for _name, _url in access_checks.items()
    ]
    return STUDENT_AUTH, access_matrix


@app.cell(hide_code=True)
def _(access_matrix, mo, pd):
    def _label(code):
        return f"{code} allowed" if code < 300 else f"{code} denied"

    _df = pd.DataFrame(
        [{"Request": r["Request"], "root": _label(r["root"]), "student_user": _label(r["student_user"])} for r in access_matrix]
    )
    _student_ok = [r["student_user"] < 300 for r in access_matrix]
    mo.vstack(
        [
            mo.ui.table(_df, selection=None, show_column_summaries=False),
            mo.callout(
                mo.md(
                    "`student_user` can list `earthquakes` and load `earthquakes.events`, and **nothing else**. "
                    "It gets `403 Forbidden` on `shop` and on the catalog-wide namespace listing, "
                    "because no grant covers them."
                ),
                kind="success" if _student_ok[:2] == [True, True] and not any(_student_ok[2:]) else "warn",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    And the data itself: PyIceberg as `student_user`, using **vended credentials** (no S3 keys in the config).
    """)
    return


@app.cell
def _(CATALOG_NAME, POLARIS, S3_ENDPOINT, load_catalog, student_creds, wiring):
    assert wiring
    student_catalog = load_catalog(
        "student",
        **{
            "type": "rest",
            "uri": f"{POLARIS}/api/catalog",
            "warehouse": CATALOG_NAME,
            "credential": f"{student_creds['clientId']}:{student_creds['clientSecret']}",
            "scope": "PRINCIPAL_ROLE:ALL",
            "header.Polaris-Realm": "POLARIS",
            "header.X-Iceberg-Access-Delegation": "vended-credentials",
            "s3.endpoint": S3_ENDPOINT,
            "s3.path-style-access": "true",
            "s3.region": "us-east-1",
        },
    )
    try:
        student_quakes = (
            student_catalog.load_table("earthquakes.events")
            .scan(selected_fields=("earthquake_id", "magnitude", "place", "event_time"), limit=5)
            .to_pandas()
        )
        student_read_error = None
    except Exception as e:
        student_quakes, student_read_error = None, f"{type(e).__name__}: {e}"
    return student_quakes, student_read_error


@app.cell(hide_code=True)
def _(mo, student_quakes, student_read_error):
    (
        mo.vstack(
            [
                mo.callout(mo.md("`student_user` read `earthquakes.events` through Polaris-vended credentials."), kind="success"),
                mo.ui.table(student_quakes, selection=None, show_column_summaries=False),
            ]
        )
        if student_read_error is None
        else mo.callout(mo.md(f"Couldn't read the data as `student_user`:\n\n> {student_read_error[:400]}"), kind="warn")
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 9 — Two layers of access control

    **Key insight:** Polaris controls *what data the catalog exposes*. Trino's `rules.json` controls
    *which catalogs each Trino user can see*.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.hstack(
        [
            mo.mermaid(
                """
                flowchart TD
                    R["Request arrives<br/>(SQL from a Trino user)"] --> L1{"Layer 1: Trino rules.json<br/>Which catalogs can this Trino user see?<br/>read-only / all / none"}
                    L1 -->|denied| X1["Access Denied<br/>(Trino)"]
                    L1 -->|allowed| L2{"Layer 2: Polaris grants<br/>What operations on which<br/>namespaces / tables?"}
                    L2 -->|denied| X2["403 Forbidden<br/>(Polaris)"]
                    L2 -->|allowed| OK["Metadata + data files"]
                """
            ),
            mo.md(
                """
                **`etc/rules.json`** (look at it with `cat etc/rules.json`):

                | Trino user | Catalogs | Access |
                |------------|----------|--------|
                | `admin` | `.*` (all) | `all` |
                | `analyst` | `postgres`, `iceberg`, `global_sales` | `read-only` |
                | `analyst` | `system`, `tpch`, `tpcds`, `memory` | `none` |

                Rules match top to bottom, and the first match wins.

                Trino authenticates to Polaris with **one** principal (`root`, from
                `etc/catalog/iceberg.properties`). Polaris grants apply to that principal,
                so layer 1 is the only per-user check for Trino queries. Engines that log in to Polaris
                as themselves, like PyIceberg as `student_user` above, are checked by layer 2.
                """
            ),
        ],
        widths=[2, 3],
        align="start",
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
                1. Polaris chains **principal → principal role → catalog role → grants**; privileges never attach to a principal directly
                2. Catalog roles are scoped to one catalog; principal roles are realm-wide
                3. Grants can target the catalog, a namespace or a single table. Table grants need the table to exist
                4. Secrets are shown once. Use `/principals/{name}/reset` as an admin to issue new ones
                5. Trino's `rules.json` is a separate, coarser layer that decides which catalogs each Trino user may use
                """
            ),
            "Exercises": mo.md(
                """
                1. **Create a new principal role** called `data_engineers` (Admin UI or the API).
                2. **Create a catalog role** called `shop_writer` with `TABLE_WRITE_DATA` on `shop.orders`.
                3. **Assign** `shop_writer` to `data_engineers` and verify the grants (Role Graph, or re-run the graph cell above).
                4. **Use the API Explorer** (or `requests.get(...)`) to list all grants for your new catalog role.
                5. **Challenge:** what happens if a principal has two catalog roles with conflicting permissions?
                   Is it union (most permissive) or intersection (most restrictive)? Test it.
                   (Hint: permissions are additive.)
                6. **Try it:** assign `service_admin` to `student_user` (as the paper lab does) and re-run the access check. What changes?
                """
            ),
            "Next lab": mo.md("**Lab 4 — Data Ingestion**: dlt and Spark write Iceberg tables, and Trino reads them all through Polaris."),
        },
        multiple=True,
    )
    return


if __name__ == "__main__":
    app.run()
