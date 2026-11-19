import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium", app_title="Getting Started — Trino, Polaris & PyIceberg")


@app.cell(hide_code=True)
def _():
    import os

    import marimo as mo
    import pandas as pd
    import requests
    import urllib3
    from pyiceberg.catalog import load_catalog
    from pyiceberg.exceptions import NoSuchNamespaceError
    from sqlalchemy import create_engine, text

    urllib3.disable_warnings()

    TRINO_HOST = os.environ.get("TRINO_HOST", "localhost")
    POLARIS_HOST = os.environ.get("POLARIS_HOST", "localhost")
    S3_HOST = os.environ.get("S3_HOST", "localhost")

    POLARIS = f"http://{POLARIS_HOST}:8181"
    POLARIS_HEALTH = f"http://{POLARIS_HOST}:8182/q/health"
    S3_ENDPOINT = f"http://{S3_HOST}:4566"
    TRINO_INFO = f"http://{TRINO_HOST}:8080/v1/info"
    CATALOG_NAME = "polaris_warehouse"
    return (
        CATALOG_NAME,
        NoSuchNamespaceError,
        POLARIS,
        POLARIS_HEALTH,
        S3_ENDPOINT,
        TRINO_HOST,
        TRINO_INFO,
        create_engine,
        load_catalog,
        mo,
        pd,
        requests,
        text,
    )


@app.cell(hide_code=True)
def _(mo, pd, stack_ok, text):
    _ = stack_ok  # helpers become available only once the health check passes

    def run_sql(engine, sql):
        """Run a query on Trino and return a DataFrame."""
        with engine.connect() as conn:
            return pd.read_sql(text(sql), conn)

    def run_statement(engine, sql):
        """Run DDL / DML on Trino (no result set needed)."""
        with engine.begin() as conn:
            conn.execute(text(sql))

    def show(df):
        return mo.ui.table(df, selection=None, show_column_summaries=False)

    SHOP_ORDERS = [
        "(1001, 1, DATE '2024-01-10', 'shipped', 1349.97)",
        "(1002, 2, DATE '2024-01-12', 'shipped', 89.98)",
        "(1003, 3, DATE '2024-01-15', 'delivered', 449.99)",
        "(1004, 1, DATE '2024-01-20', 'delivered', 59.98)",
        "(1005, 5, DATE '2024-02-01', 'shipped', 1299.99)",
        "(1006, 7, DATE '2024-02-05', 'processing', 199.99)",
        "(1007, 10, DATE '2024-02-10', 'shipped', 639.98)",
        "(1008, 4, DATE '2024-02-14', 'delivered', 129.98)",
        "(1009, 8, DATE '2024-02-20', 'shipped', 399.99)",
        "(1010, 6, DATE '2024-03-01', 'processing', 89.99)",
        "(1011, 12, DATE '2024-03-05', 'shipped', 1749.97)",
        "(1012, 15, DATE '2024-03-10', 'delivered', 49.99)",
        "(1013, 14, DATE '2024-03-15', 'processing', 269.98)",
        "(1014, 9, DATE '2024-03-20', 'shipped', 109.99)",
        "(1015, 20, DATE '2024-03-25', 'delivered', 529.98)",
    ]
    SHOP_ORDER_ITEMS = [
        "(1, 1001, 1, 1, 1299.99)", "(2, 1001, 2, 1, 29.99)", "(3, 1001, 14, 1, 19.99)",
        "(4, 1002, 4, 1, 89.99)", "(5, 1003, 7, 1, 449.99)", "(6, 1004, 3, 1, 49.99)",
        "(7, 1004, 10, 1, 8.99)", "(8, 1005, 1, 1, 1299.99)", "(9, 1006, 13, 1, 199.99)",
        "(10, 1007, 6, 1, 599.99)", "(11, 1007, 8, 1, 39.99)", "(12, 1008, 17, 1, 109.99)",
        "(13, 1008, 14, 1, 19.99)", "(14, 1009, 5, 1, 399.99)", "(15, 1010, 4, 1, 89.99)",
        "(16, 1011, 1, 1, 1299.99)", "(17, 1011, 7, 1, 449.99)", "(18, 1012, 3, 1, 49.99)",
        "(19, 1013, 13, 1, 199.99)", "(20, 1013, 12, 1, 69.99)", "(21, 1014, 17, 1, 109.99)",
        "(22, 1015, 5, 1, 399.99)", "(23, 1015, 11, 1, 79.99)", "(24, 1015, 3, 1, 49.99)",
    ]

    def ensure_shop_tables(engine):
        """Create iceberg.shop.orders / order_items if missing (sample-queries.sql section 2).
        Rows are inserted only when a table is empty, so re-runs never duplicate data."""
        run_statement(
            engine,
            "CREATE SCHEMA IF NOT EXISTS iceberg.shop WITH (location = 's3://warehouse/polaris_warehouse/shop')",
        )
        run_statement(
            engine,
            """CREATE TABLE IF NOT EXISTS iceberg.shop.orders (
                order_id BIGINT, customer_id BIGINT, order_date DATE,
                status VARCHAR, total_amount DECIMAL(10, 2)
            ) WITH (format = 'PARQUET')""",
        )
        run_statement(
            engine,
            """CREATE TABLE IF NOT EXISTS iceberg.shop.order_items (
                item_id BIGINT, order_id BIGINT, product_id BIGINT,
                quantity INT, unit_price DECIMAL(10, 2)
            ) WITH (format = 'PARQUET')""",
        )
        loaded = []
        for table, rows in (("orders", SHOP_ORDERS), ("order_items", SHOP_ORDER_ITEMS)):
            count = int(run_sql(engine, f"SELECT count(*) AS n FROM iceberg.shop.{table}")["n"][0])
            if count == 0:
                run_statement(engine, f"INSERT INTO iceberg.shop.{table} VALUES " + ", ".join(rows))
                loaded.append(table)
        counts = {
            t: int(run_sql(engine, f"SELECT count(*) AS n FROM iceberg.shop.{t}")["n"][0])
            for t in ("orders", "order_items")
        }
        return loaded, counts

    return ensure_shop_tables, run_sql, show


@app.cell(hide_code=True)
def _(mo):
    mo.sidebar(
        [
            mo.md("### Getting Started\n**Trino, Polaris & PyIceberg**"),
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
                # Polaris Lab — Getting Started

                This notebook connects to **Trino** (SQL) and **Polaris** (PyIceberg) running in your
                Podman / Docker stack. It's a five-minute tour of the two ways you'll talk to the lakehouse
                in every later lab.
                """
            ),
            mo.callout(
                mo.md(
                    """
                    **What you'll do**

                    1. Query Trino with SQL: list catalogs and Iceberg schemas
                    2. Explore Iceberg namespaces and tables directly through Polaris with PyIceberg
                    3. Run a federated query against Postgres through the same Trino connection
                    """
                ),
                kind="info",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.mermaid(
        """
        flowchart LR
            NB["This notebook<br/>(marimo)"]
            NB -- "SQL (SQLAlchemy)" --> T["Trino :8443"]
            NB -- "Iceberg REST (PyIceberg)" --> P["Polaris :8181"]
            T -- "postgres connector" --> PG[("Postgres<br/>customers, products")]
            T -- "iceberg connector" --> P
            P -- "table metadata" --> S3[("LocalStack S3<br/>Parquet + metadata")]
            T -. "reads data files" .-> S3
            NB -. "reads data files<br/>(vended credentials)" .-> S3
        """
    )
    return


@app.cell(hide_code=True)
def _(POLARIS_HEALTH, S3_ENDPOINT, TRINO_INFO, mo, requests):
    def _reachable(url):
        try:
            return requests.get(url, timeout=5).ok
        except requests.RequestException:
            return False

    _status = {
        "Trino": _reachable(TRINO_INFO),
        "Polaris": _reachable(POLARIS_HEALTH),
        "LocalStack": _reachable(f"{S3_ENDPOINT}/_localstack/health"),
    }
    mo.stop(
        not all(_status.values()),
        mo.callout(
            mo.md(
                "**The lab stack isn't reachable.** "
                + " &nbsp;·&nbsp; ".join(f"{k}: {'up' if v else '**down**'}" for k, v in _status.items())
                + "\n\nStart it with `podman compose --profile marimo up -d` "
                "(or `docker compose --profile marimo up -d`), then re-run this cell."
            ),
            kind="danger",
        ),
    )
    stack_ok = True
    mo.hstack(
        [
            mo.stat("Healthy", label="Trino", caption="SQL engine", bordered=True),
            mo.stat("Healthy", label="Polaris", caption="Iceberg REST catalog", bordered=True),
            mo.stat("Healthy", label="LocalStack", caption="S3 storage", bordered=True),
        ],
        widths="equal",
    )
    return (stack_ok,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## 1. Query Trino via SQL

    Trino is reached through SQLAlchemy. The URL names the user, password, host and the default catalog (`iceberg`).
    The lab uses a self-signed certificate, so TLS verification is switched off.
    """)
    return


@app.cell
def _(TRINO_HOST, create_engine):
    trino_engine = create_engine(
        f"trino://admin:admin123@{TRINO_HOST}:8443/iceberg",
        connect_args={"http_scheme": "https", "verify": False},
    )
    return (trino_engine,)


@app.cell(hide_code=True)
def _(ensure_shop_tables, mo, trino_engine):
    with mo.status.spinner(title="Making sure the sample shop tables exist…"):
        shop_loaded, shop_counts = ensure_shop_tables(trino_engine)

    mo.callout(
        mo.md(
            (
                f"Loaded sample data into `iceberg.shop.{', '.join(shop_loaded)}` "
                if shop_loaded
                else "Sample tables `iceberg.shop.orders` and `iceberg.shop.order_items` are present "
            )
            + f"({shop_counts['orders']} orders, {shop_counts['order_items']} order items). "
            "They're used in section 2; this setup step is idempotent and never drops data."
        ),
        kind="success" if not shop_loaded else "info",
    )
    return


@app.cell
def _(run_sql, trino_engine):
    df_catalogs = run_sql(trino_engine, "SHOW CATALOGS")
    df_schemas = run_sql(trino_engine, "SHOW SCHEMAS IN iceberg")
    return df_catalogs, df_schemas


@app.cell(hide_code=True)
def _(df_catalogs, df_schemas, mo, show):
    mo.hstack(
        [
            mo.vstack([mo.md("**`SHOW CATALOGS`**"), mo.stat(len(df_catalogs), label="Catalogs", bordered=True), show(df_catalogs)]),
            mo.vstack(
                [mo.md("**`SHOW SCHEMAS IN iceberg`**"), mo.stat(len(df_schemas), label="Iceberg schemas", bordered=True), show(df_schemas)]
            ),
        ],
        widths="equal",
        align="start",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## 2. Explore Iceberg Tables with PyIceberg

    PyIceberg talks to Polaris directly over the **Iceberg REST API**, no Trino involved.
    Note that the config has **no S3 keys**: the `X-Iceberg-Access-Delegation` header asks Polaris to
    vend short-lived credentials for each table it loads (Lab 16 covers this in depth).
    """)
    return


@app.cell
def _(CATALOG_NAME, POLARIS, S3_ENDPOINT, load_catalog):
    catalog = load_catalog(
        "polaris",
        **{
            "type": "rest",
            "uri": f"{POLARIS}/api/catalog",
            "warehouse": CATALOG_NAME,
            "credential": "root:s3cr3t",
            "scope": "PRINCIPAL_ROLE:ALL",
            "header.Polaris-Realm": "POLARIS",
            "header.X-Iceberg-Access-Delegation": "vended-credentials",
            "s3.endpoint": S3_ENDPOINT,
            "s3.path-style-access": "true",
            "s3.region": "us-east-1",
        },
    )

    namespaces = catalog.list_namespaces()
    namespaces
    return catalog, namespaces


@app.cell
def _(NoSuchNamespaceError, catalog):
    try:
        tables = catalog.list_tables("earthquakes")
    except NoSuchNamespaceError:  # init/polaris/setup.sh normally creates it
        tables = []
    tables
    return (tables,)


@app.cell(hide_code=True)
def _(mo, tables):
    mo.callout(
        mo.md(
            f"`earthquakes` holds **{len(tables)}** table(s): "
            + ", ".join(f"`{'.'.join(t)}`" for t in tables)
            + ". The `events` table is written by the **dlt** pipeline from the live USGS feed (Lab 4)."
        )
        if tables
        else mo.md(
            "The `earthquakes` namespace is **empty**: the `dlt-earthquakes` job hasn't registered "
            "`earthquakes.events` yet (it needs internet access to the USGS feed). Re-run it with "
            "`podman restart dlt-earthquakes` (or `docker restart dlt-earthquakes`). Nothing else in this notebook depends on it."
        ),
        kind="success" if tables else "warn",
    )
    return


@app.cell(hide_code=True)
def _(catalog, mo, namespaces, pd, show):
    _rows = []
    for _ns in namespaces:
        try:
            _ns_tables = catalog.list_tables(_ns)
        except Exception:  # another lab may be dropping its namespace right now
            _ns_tables = []
        _rows.append(
            {
                "Namespace": ".".join(_ns),
                "Tables": len(_ns_tables),
                "Names": ", ".join(t[-1] for t in _ns_tables) or "—",
            }
        )
    mo.vstack(
        [
            mo.md("**Every namespace in `polaris_warehouse`** (one `list_tables` call per namespace):"),
            show(pd.DataFrame(_rows)),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Load one table

    `load_table` returns the table's metadata: schema, snapshots, location. `scan()` then reads the
    Parquet files from S3 straight into Arrow / pandas.
    """)
    return


@app.cell
def _(catalog):
    orders = catalog.load_table("shop.orders")
    orders_df = orders.scan().to_pandas()
    return orders, orders_df


@app.cell(hide_code=True)
def _(mo, orders, orders_df, pd, show):
    _schema = pd.DataFrame(
        [{"Field ID": f.field_id, "Column": f.name, "Type": str(f.field_type), "Required": f.required} for f in orders.schema().fields]
    )
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(len(orders_df), label="Rows", bordered=True),
                    mo.stat(len(orders.history()), label="Snapshots", bordered=True),
                    mo.stat(f"v{orders.format_version}", label="Format version", bordered=True),
                ],
                widths="equal",
            ),
            mo.md(f"**Location:** `{orders.location()}`"),
            mo.ui.tabs({"Schema": show(_schema), "Data": show(orders_df)}),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## 3. Query Postgres via Trino

    The same Trino connection reaches the `postgres` catalog. Fully qualified names
    (`catalog.schema.table`) let one query mix sources; Lab 2 joins these customers with the Iceberg orders.
    """)
    return


@app.cell
def _(run_sql, trino_engine):
    df_customers = run_sql(trino_engine, "SELECT * FROM postgres.public.customers LIMIT 10")
    return (df_customers,)


@app.cell(hide_code=True)
def _(df_customers, show):
    show(df_customers)
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
                1. **Trino** is the SQL front door: one connection, many catalogs (`iceberg`, `postgres`, `tpch`, …)
                2. **Polaris** is the Iceberg REST catalog; Trino's `iceberg` catalog and PyIceberg both use it
                3. **PyIceberg** reads table metadata from Polaris and data files from S3, without any SQL engine
                4. Polaris can vend S3 credentials, so client configs don't need static keys
                """
            ),
            "Next lab": mo.md("**Lab 0 — Environment Setup**: check every service and run your first Trino queries."),
        },
        multiple=True,
    )
    return


if __name__ == "__main__":
    app.run()
