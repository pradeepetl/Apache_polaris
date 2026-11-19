import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium", app_title="Lab 1 — Exploring Catalogs")


@app.cell(hide_code=True)
def _():
    import os

    import marimo as mo
    import pandas as pd
    import requests
    import urllib3
    from sqlalchemy import create_engine, text

    urllib3.disable_warnings()

    TRINO_HOST = os.environ.get("TRINO_HOST", "localhost")
    POLARIS_HOST = os.environ.get("POLARIS_HOST", "localhost")

    POLARIS = f"http://{POLARIS_HOST}:8181"
    POLARIS_HEALTH = f"http://{POLARIS_HOST}:8182/q/health"
    TRINO_INFO = f"http://{TRINO_HOST}:8080/v1/info"
    REALM = "POLARIS"
    CATALOG_NAME = "polaris_warehouse"
    return (
        CATALOG_NAME,
        POLARIS,
        POLARIS_HEALTH,
        REALM,
        TRINO_HOST,
        TRINO_INFO,
        create_engine,
        mo,
        pd,
        requests,
        text,
    )


@app.cell(hide_code=True)
def _(mo, pd, text):
    def run_sql(engine, sql):
        """Run a query on Trino and return a DataFrame."""
        with engine.connect() as conn:
            return pd.read_sql(text(sql), conn)

    def run_statement(engine, sql):
        """Run DDL / DML on Trino."""
        with engine.begin() as conn:
            conn.execute(text(sql))

    def show(df):
        return mo.ui.table(df, selection=None, show_column_summaries=False)

    def sql_result(engine, sql, note=None):
        """Render a query next to its result: the SQL is the lesson, the table is the answer."""
        df = run_sql(engine, sql)
        parts = [mo.md(f"```sql\n{sql.strip()}\n```")]
        if note:
            parts.append(mo.md(note))
        parts.append(mo.md(f"_{len(df)} row(s)_"))
        parts.append(show(df))
        return mo.vstack(parts)

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

    return ensure_shop_tables, run_sql, show, sql_result


@app.cell(hide_code=True)
def _(mo):
    mo.sidebar(
        [
            mo.md("### Lab 1\n**Exploring Catalogs**"),
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
                # Lab 1 — Exploring Catalogs

                **Level:** 1 (Beginner) &nbsp;|&nbsp; **Time:** 15 minutes

                **Goal:** Understand how Trino organizes data across catalogs, schemas, and tables.
                """
            ),
            mo.callout(
                mo.md(
                    """
                    **What you'll do**

                    1. List every catalog Trino knows about and what backs it
                    2. Drill down into schemas and tables in `postgres`, `iceberg` and `tpch`
                    3. Inspect column types, preview rows and run your first aggregations
                    4. Run a TPC-H benchmark join and look at an Iceberg table's metadata in Polaris
                    """
                ),
                kind="info",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(POLARIS_HEALTH, TRINO_INFO, mo, requests):
    def _reachable(url):
        try:
            return requests.get(url, timeout=5).ok
        except requests.RequestException:
            return False

    _trino_ok = _reachable(TRINO_INFO)
    _polaris_ok = _reachable(POLARIS_HEALTH)
    mo.stop(
        not (_trino_ok and _polaris_ok),
        mo.callout(
            mo.md(
                f"""
                **The lab stack isn't reachable.**
                Trino: {"up" if _trino_ok else "**down**"} &nbsp;·&nbsp; Polaris: {"up" if _polaris_ok else "**down**"}

                Start it with `podman compose --profile marimo up -d` (or `docker compose --profile marimo up -d`),
                then re-run this cell.
                """
            ),
            kind="danger",
        ),
    )
    trino_version = requests.get(TRINO_INFO, timeout=5).json().get("nodeVersion", {}).get("version", "?")
    mo.hstack(
        [
            mo.stat("Healthy", label="Trino", caption=f"version {trino_version}", bordered=True),
            mo.stat("Healthy", label="Polaris", caption="backs the iceberg catalog", bordered=True),
        ],
        widths="equal",
    )
    return (trino_version,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Concepts

    Trino uses a three-level naming hierarchy:

    ```
    catalog.schema.table
    ```

    - **Catalog** — a data source connector (e.g., `postgres`, `iceberg`, `tpch`)
    - **Schema** — a namespace within a catalog (e.g., `public`, `shop`, `tiny`)
    - **Table** — the actual data
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.mermaid(
        """
        flowchart LR
            T(("Trino"))
            T --> C1["postgres"]
            T --> C2["iceberg"]
            T --> C3["tpch"]
            C1 --> S1["public"]
            S1 --> T1["customers"]
            S1 --> T2["products"]
            C2 --> S2["shop"]
            S2 --> T3["orders"]
            S2 --> T4["order_items"]
            C3 --> S3["tiny"]
            S3 --> T5["customer"]
            S3 --> T6["nation"]
            classDef cat fill:#dbeafe,stroke:#2563eb
            classDef sch fill:#fef3c7,stroke:#d97706
            classDef tbl fill:#dcfce7,stroke:#16a34a
            class C1,C2,C3 cat
            class S1,S2,S3 sch
            class T1,T2,T3,T4,T5,T6 tbl
        """
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ### Connect to Trino

    In a terminal you would use the Trino CLI as admin:

    ```bash
    podman exec -e TRINO_PASSWORD=admin123 -it trino \
      trino --server https://localhost:8443 --user admin --password --insecure
    ```

    (`docker exec …` works the same.) In this notebook we use SQLAlchemy with the same credentials:
    """)
    return


@app.cell
def _(TRINO_HOST, create_engine, trino_version):
    assert trino_version  # wait for the health check
    trino = create_engine(
        f"trino://admin:admin123@{TRINO_HOST}:8443/iceberg",
        connect_args={"http_scheme": "https", "verify": False},
    )
    return (trino,)


@app.cell(hide_code=True)
def _(ensure_shop_tables, mo, trino):
    with mo.status.spinner(title="Making sure the sample shop tables exist…"):
        shop_loaded, shop_counts = ensure_shop_tables(trino)

    mo.callout(
        mo.md(
            (
                f"Created and loaded `iceberg.shop.{', '.join(shop_loaded)}` from `sample-queries.sql` "
                if shop_loaded
                else "Sample tables `iceberg.shop.orders` and `iceberg.shop.order_items` are present "
            )
            + f"({shop_counts['orders']} orders, {shop_counts['order_items']} order items). "
            "This setup step is idempotent: it only creates what is missing and never drops data."
        ),
        kind="info" if shop_loaded else "success",
    )
    return (shop_counts,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 1 — List All Catalogs
    """)
    return


@app.cell
def _(run_sql, shop_counts, trino):
    assert shop_counts
    df_catalogs = run_sql(trino, "SHOW CATALOGS")
    return (df_catalogs,)


@app.cell(hide_code=True)
def _(df_catalogs, mo, pd, show):
    _backends = {
        "postgres": "PostgreSQL database",
        "iceberg": "Iceberg tables via Polaris REST Catalog",
        "tpch": "In-memory TPC-H benchmark data",
        "tpcds": "In-memory TPC-DS benchmark data",
        "memory": "JVM heap (empty, create your own)",
        "system": "Trino internal metadata",
    }
    _table = pd.DataFrame(
        [
            {
                "Catalog": c,
                "Backend": _backends.get(c, "Added by an optional exercise (e.g. a second Polaris catalog)"),
            }
            for c in df_catalogs["Catalog"]
        ]
    )
    mo.vstack(
        [
            mo.md("```sql\nSHOW CATALOGS\n```"),
            mo.hstack(
                [
                    mo.stat(len(df_catalogs), label="Catalogs", caption="6 in a fresh stack", bordered=True),
                    show(_table),
                ],
                widths=[1, 3],
                align="start",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 2 — Explore Schemas
    """)
    return


@app.cell(hide_code=True)
def _(mo, sql_result, trino):
    mo.ui.tabs(
        {
            "postgres": sql_result(trino, "SHOW SCHEMAS IN postgres"),
            "iceberg": sql_result(
                trino,
                "SHOW SCHEMAS IN iceberg",
                "Each Iceberg schema is a **Polaris namespace**. Other labs add their own (e.g. `lab16`).",
            ),
            "tpch": sql_result(trino, "SHOW SCHEMAS IN tpch"),
        }
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.vstack(
        [
            mo.md("**Question:** What schemas exist in `tpch`? What do `tiny`, `sf1`, `sf100` mean?"),
            mo.accordion(
                {
                    "Answer": mo.md(
                        "They are scale factors. `tiny` has a few hundred rows, `sf1` has ~6M rows in `lineitem`, "
                        "`sf100` has 600M. The data is generated on the fly, so every scale factor costs nothing to store."
                    )
                }
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 3 — Explore Tables
    """)
    return


@app.cell(hide_code=True)
def _(mo, sql_result, trino):
    mo.ui.tabs(
        {
            "postgres.public": sql_result(trino, "SHOW TABLES IN postgres.public"),
            "iceberg.shop": sql_result(trino, "SHOW TABLES IN iceberg.shop"),
            "tpch.tiny": sql_result(trino, "SHOW TABLES IN tpch.tiny"),
        }
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Try it: walk the hierarchy

    Pick a catalog, then a schema. Each choice runs `SHOW SCHEMAS IN …` / `SHOW TABLES IN …` for you.
    """)
    return


@app.cell(hide_code=True)
def _(df_catalogs, mo):
    catalog_picker = mo.ui.dropdown(
        [c for c in df_catalogs["Catalog"] if c != "system"], value="iceberg", label="Catalog"
    )
    catalog_picker
    return (catalog_picker,)


@app.cell(hide_code=True)
def _(catalog_picker, mo, run_sql, trino):
    _schemas = [s for s in run_sql(trino, f"SHOW SCHEMAS IN {catalog_picker.value}")["Schema"] if s != "information_schema"]
    _default = next((s for s in ("shop", "public", "tiny") if s in _schemas), _schemas[0] if _schemas else None)
    schema_picker = mo.ui.dropdown(_schemas, value=_default, label=f"Schema in `{catalog_picker.value}`")
    schema_picker
    return (schema_picker,)


@app.cell(hide_code=True)
def _(catalog_picker, mo, schema_picker, sql_result, trino):
    mo.stop(schema_picker.value is None, mo.callout("This catalog has no schemas yet.", kind="neutral"))
    sql_result(trino, f"SHOW TABLES IN {catalog_picker.value}.{schema_picker.value}")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 4 — Inspect Table Structure
    """)
    return


@app.cell
def _(run_sql, trino):
    df_customers_cols = run_sql(trino, "DESCRIBE postgres.public.customers")
    df_orders_cols = run_sql(trino, "SHOW COLUMNS FROM iceberg.shop.orders")
    return df_customers_cols, df_orders_cols


@app.cell(hide_code=True)
def _(df_customers_cols, df_orders_cols, mo, show):
    mo.hstack(
        [
            mo.vstack([mo.md("**`DESCRIBE postgres.public.customers`**"), show(df_customers_cols)]),
            mo.vstack([mo.md("**`SHOW COLUMNS FROM iceberg.shop.orders`**"), show(df_orders_cols)]),
        ],
        widths="equal",
        align="start",
    )
    return


@app.cell(hide_code=True)
def _(df_orders_cols, mo):
    _type = dict(zip(df_orders_cols["Column"], df_orders_cols["Type"])).get("total_amount", "?")
    mo.vstack(
        [
            mo.md("**Question:** What data type is `total_amount` in `iceberg.shop.orders`?"),
            mo.accordion(
                {
                    "Answer": mo.md(
                        f"`{_type}`: a fixed-point decimal with 10 digits, 2 after the point. "
                        "`DESCRIBE` and `SHOW COLUMNS` are equivalent; both work on any catalog."
                    )
                }
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 5 — Preview Data
    """)
    return


@app.cell(hide_code=True)
def _(mo, sql_result, trino):
    mo.ui.tabs(
        {
            "customers (postgres)": sql_result(trino, "SELECT * FROM postgres.public.customers LIMIT 5"),
            "products (postgres)": sql_result(trino, "SELECT * FROM postgres.public.products LIMIT 5"),
            "orders (iceberg)": sql_result(trino, "SELECT * FROM iceberg.shop.orders LIMIT 5"),
            "order_items (iceberg)": sql_result(trino, "SELECT * FROM iceberg.shop.order_items LIMIT 5"),
        }
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.vstack(
        [
            mo.md("**Question:** How are `orders` and `order_items` related? Which column links them?"),
            mo.accordion(
                {
                    "Answer": mo.md(
                        "`order_items.order_id` references `orders.order_id`: one order has one or more items "
                        "(a one-to-many relationship). `order_items.product_id` and `orders.customer_id` point at the "
                        "Postgres `products` and `customers` tables, which Lab 2 joins across catalogs."
                    )
                }
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.mermaid(
        """
        erDiagram
            CUSTOMERS ||--o{ ORDERS : "customer_id"
            ORDERS ||--|{ ORDER_ITEMS : "order_id"
            PRODUCTS ||--o{ ORDER_ITEMS : "product_id"
            CUSTOMERS { bigint customer_id PK  string name  string country }
            ORDERS { bigint order_id PK  bigint customer_id FK  date order_date  string status  decimal total_amount }
            ORDER_ITEMS { bigint item_id PK  bigint order_id FK  bigint product_id FK  int quantity  decimal unit_price }
            PRODUCTS { bigint product_id PK  string name  string category  decimal price }
        """
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 6 — Basic Aggregations
    """)
    return


@app.cell
def _(run_sql, trino):
    df_by_country = run_sql(
        trino,
        """
        -- Customers per country
        SELECT country, count(*) AS num_customers
        FROM postgres.public.customers
        GROUP BY country ORDER BY num_customers DESC
        """,
    )
    df_items_per_order = run_sql(
        trino,
        """
        -- Items per order
        SELECT order_id, count(*) AS items, sum(quantity) AS total_qty
        FROM iceberg.shop.order_items
        GROUP BY order_id ORDER BY total_qty DESC
        """,
    )
    return df_by_country, df_items_per_order


@app.cell(hide_code=True)
def _(df_by_country, df_items_per_order, mo, show):
    mo.hstack(
        [
            mo.vstack(
                [
                    mo.md("**Customers per country** (Postgres)"),
                    mo.stat(len(df_by_country), label="Countries", caption=f"{int(df_by_country['num_customers'].sum())} customers", bordered=True),
                    show(df_by_country),
                ]
            ),
            mo.vstack(
                [
                    mo.md("**Items per order** (Iceberg)"),
                    mo.stat(len(df_items_per_order), label="Orders", caption=f"{int(df_items_per_order['items'].sum())} items", bordered=True),
                    show(df_items_per_order),
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
    ---
    ## Step 7 — TPC-H Benchmark Query

    `tpch` generates data on demand, so you can run realistic joins with no setup.
    """)
    return


@app.cell
def _(run_sql, trino):
    df_tpch = run_sql(
        trino,
        """
        SELECT n.name AS nation, count(*) AS customers
        FROM tpch.tiny.customer c
        JOIN tpch.tiny.nation n ON c.nationkey = n.nationkey
        GROUP BY n.name
        ORDER BY customers DESC LIMIT 5
        """,
    )
    return (df_tpch,)


@app.cell(hide_code=True)
def _(df_tpch, show):
    show(df_tpch)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 8 — Use the Polaris Admin Data Browser

    1. Open http://localhost:3000
    2. Click **Data Browser** in the sidebar
    3. Expand a catalog > namespace > click a table
    4. Observe the schema (columns, types, Iceberg format version, snapshot count)

    The Data Browser gets that information from the Polaris REST API. Here is the same `loadTable` call,
    so you can compare with what the UI shows:
    """)
    return


@app.cell
def _(CATALOG_NAME, POLARIS, REALM, requests, trino_version):
    assert trino_version  # wait for the health check
    _token = requests.post(
        f"{POLARIS}/api/catalog/v1/oauth/tokens",
        headers={"Polaris-Realm": REALM},
        data={
            "grant_type": "client_credentials",
            "client_id": "root",
            "client_secret": "s3cr3t",
            "scope": "PRINCIPAL_ROLE:ALL",
        },
        timeout=10,
    ).json()["access_token"]

    orders_meta = requests.get(
        f"{POLARIS}/api/catalog/v1/{CATALOG_NAME}/namespaces/shop/tables/orders",
        headers={"Authorization": f"Bearer {_token}", "Polaris-Realm": REALM},
        timeout=10,
    ).json()["metadata"]
    return (orders_meta,)


@app.cell(hide_code=True)
def _(mo, orders_meta, pd, show):
    _schema = next(s for s in orders_meta["schemas"] if s["schema-id"] == orders_meta["current-schema-id"])
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(f"v{orders_meta['format-version']}", label="Format version", bordered=True),
                    mo.stat(len(orders_meta.get("snapshots", [])), label="Snapshots", bordered=True),
                    mo.stat(len(_schema["fields"]), label="Columns", bordered=True),
                ],
                widths="equal",
            ),
            mo.md(f"**Location:** `{orders_meta['location']}`"),
            show(
                pd.DataFrame(
                    [{"ID": f["id"], "Column": f["name"], "Iceberg type": str(f["type"]), "Required": f["required"]} for f in _schema["fields"]]
                )
            ),
            mo.callout(
                mo.md(
                    "Note the **Iceberg** types (`long`, `decimal(10, 2)`, `date`): Trino maps them to its own "
                    "(`bigint`, `decimal(10,2)`, `date`) in Step 4."
                ),
                kind="neutral",
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
                1. Every Trino object has a three-part name: `catalog.schema.table`
                2. A catalog is a connector instance; `iceberg` is backed by Polaris, `postgres` by a live database
                3. `SHOW CATALOGS / SCHEMAS / TABLES` and `DESCRIBE` work the same on every catalog
                4. `tpch` / `tpcds` generate benchmark data on the fly at different scale factors
                5. Iceberg schemas are Polaris namespaces; Polaris also stores each table's format version and snapshots
                """
            ),
            "Exercises": mo.md(
                """
                1. Find the most expensive product in `postgres.public.products`.
                2. List all distinct `status` values in `iceberg.shop.orders`.
                3. How many tables exist in `tpch.sf1`? Same count as `tpch.tiny`?
                4. What is the total number of order items in `iceberg.shop.order_items`?
                5. In Polaris Admin Data Browser, find the Iceberg format version of `shop.orders`.
                """
            ),
            "Next lab": mo.md("**Lab 2 — Query Federation**: join Postgres customers with Iceberg orders in one query."),
        },
        multiple=True,
    )
    return


@app.cell(hide_code=True)
def _(mo):
    show_solutions = mo.ui.switch(label="Show exercise solutions")
    show_solutions
    return (show_solutions,)


@app.cell(hide_code=True)
def _(mo, orders_meta, run_sql, show, show_solutions, sql_result, trino):
    mo.stop(not show_solutions.value)
    _sf1 = len(run_sql(trino, "SHOW TABLES IN tpch.sf1"))
    _tiny = len(run_sql(trino, "SHOW TABLES IN tpch.tiny"))
    mo.ui.tabs(
        {
            "1. Most expensive product": sql_result(
                trino, "SELECT name, category, price FROM postgres.public.products ORDER BY price DESC LIMIT 1"
            ),
            "2. Order statuses": sql_result(trino, "SELECT DISTINCT status FROM iceberg.shop.orders ORDER BY status"),
            "3. tpch.sf1 vs tiny": mo.vstack(
                [
                    mo.md("```sql\nSHOW TABLES IN tpch.sf1;\nSHOW TABLES IN tpch.tiny;\n```"),
                    mo.hstack(
                        [mo.stat(_sf1, label="tpch.sf1 tables", bordered=True), mo.stat(_tiny, label="tpch.tiny tables", bordered=True)],
                        widths="equal",
                    ),
                    mo.md("Same tables in every scale factor; only the row counts differ."),
                ]
            ),
            "4. Total order items": sql_result(
                trino, "SELECT count(*) AS order_items, sum(quantity) AS total_quantity FROM iceberg.shop.order_items"
            ),
            "5. Format version": mo.vstack(
                [
                    mo.md(f"`shop.orders` uses Iceberg format **v{orders_meta['format-version']}** (from Step 8)."),
                    show(run_sql(trino, 'SELECT * FROM iceberg.shop."orders$properties"')),
                ]
            ),
        }
    )
    return


if __name__ == "__main__":
    app.run()
