import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium", app_title="Lab 2 — Query Federation")


@app.cell(hide_code=True)
def _():
    import os
    import re

    import marimo as mo
    import pandas as pd
    import requests
    import urllib3
    from sqlalchemy import create_engine, text

    urllib3.disable_warnings()

    TRINO_HOST = os.environ.get("TRINO_HOST", "localhost")
    TRINO_INFO = f"https://{TRINO_HOST}:8443/v1/info"
    trino = create_engine(
        f"trino://admin:admin123@{TRINO_HOST}:8443/iceberg",
        connect_args={"http_scheme": "https", "verify": False},
    )
    return TRINO_INFO, mo, pd, re, requests, text, trino


@app.cell(hide_code=True)
def _(mo, pd, text, trino):
    def run_sql(sql):
        """Run one Trino statement. Returns a DataFrame for queries, None for DDL/DML."""
        with trino.connect() as conn:
            result = conn.execute(text(sql))
            if result.returns_rows:
                # Fetching also makes Trino finish DDL/DML statements.
                return pd.DataFrame(result.fetchall(), columns=list(result.keys()))
        return None

    def show(df):
        return mo.ui.table(df, selection=None, show_column_summaries=False)

    return run_sql, show


@app.cell(hide_code=True)
def _(mo):
    mo.sidebar(
        [
            mo.md("### Lab 2\n**Query Federation**"),
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
                # Lab 2 — Query Federation

                **Level:** 2 (Intermediate) &nbsp;|&nbsp; **Time:** 20 minutes

                **Goal:** join data across Postgres and Iceberg in a single SQL query, Trino's core superpower.

                **Query federation** means querying several data sources in one SQL statement.
                Without Trino you'd need ETL to copy everything into one system first.
                With Trino you just use fully qualified names: `catalog.schema.table`.
                """
            ),
            mo.callout(
                mo.md(
                    """
                    **What you'll do**

                    1. Join Postgres customers with Iceberg orders
                    2. Run a four-table join across two catalogs and two storage backends
                    3. Aggregate across sources: top customers, revenue by category, revenue by country
                    4. Keep intermediate results in Trino's in-memory catalog
                    5. Read the query plan to see which part runs against which source
                    """
                ),
                kind="info",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(TRINO_INFO, mo, requests):
    def _trino_info():
        try:
            resp = requests.get(TRINO_INFO, timeout=5, verify=False)
            return resp.json() if resp.ok else None
        except requests.RequestException:
            return None

    _info = _trino_info()
    mo.stop(
        _info is None or _info.get("starting", True),
        mo.callout(
            mo.md(
                """
                **Trino isn't reachable** (or is still starting).

                Start the stack with `podman compose --profile marimo up -d`
                (or `docker compose --profile marimo up -d`), wait for Trino to report healthy, then re-run this cell.
                """
            ),
            kind="danger",
        ),
    )
    trino_version = _info["nodeVersion"]["version"]
    return (trino_version,)


@app.cell(hide_code=True)
def _(mo, run_sql, trino_version):
    # Shared lab data: iceberg.shop.orders / order_items (sample-queries.sql, section 2).
    # Created only if missing and filled only if empty, so re-runs never duplicate rows or drop anything.
    with mo.status.spinner(title="Checking the shop tables in Iceberg…"):
        run_sql("CREATE SCHEMA IF NOT EXISTS iceberg.shop WITH (location = 's3://warehouse/polaris_warehouse/shop')")
        run_sql(
            """
            CREATE TABLE IF NOT EXISTS iceberg.shop.orders (
                order_id BIGINT, customer_id BIGINT, order_date DATE, status VARCHAR, total_amount DECIMAL(10, 2)
            ) WITH (format = 'PARQUET')
            """
        )
        run_sql(
            """
            CREATE TABLE IF NOT EXISTS iceberg.shop.order_items (
                item_id BIGINT, order_id BIGINT, product_id BIGINT, quantity INT, unit_price DECIMAL(10, 2)
            ) WITH (format = 'PARQUET')
            """
        )
        _seeded = []
        if run_sql("SELECT count(*) AS n FROM iceberg.shop.orders")["n"][0] == 0:
            run_sql(
                """
                INSERT INTO iceberg.shop.orders VALUES
                (1001, 1, DATE '2024-01-10', 'shipped', 1349.97), (1002, 2, DATE '2024-01-12', 'shipped', 89.98),
                (1003, 3, DATE '2024-01-15', 'delivered', 449.99), (1004, 1, DATE '2024-01-20', 'delivered', 59.98),
                (1005, 5, DATE '2024-02-01', 'shipped', 1299.99), (1006, 7, DATE '2024-02-05', 'processing', 199.99),
                (1007, 10, DATE '2024-02-10', 'shipped', 639.98), (1008, 4, DATE '2024-02-14', 'delivered', 129.98),
                (1009, 8, DATE '2024-02-20', 'shipped', 399.99), (1010, 6, DATE '2024-03-01', 'processing', 89.99),
                (1011, 12, DATE '2024-03-05', 'shipped', 1749.97), (1012, 15, DATE '2024-03-10', 'delivered', 49.99),
                (1013, 14, DATE '2024-03-15', 'processing', 269.98), (1014, 9, DATE '2024-03-20', 'shipped', 109.99),
                (1015, 20, DATE '2024-03-25', 'delivered', 529.98)
                """
            )
            _seeded.append("orders")
        if run_sql("SELECT count(*) AS n FROM iceberg.shop.order_items")["n"][0] == 0:
            run_sql(
                """
                INSERT INTO iceberg.shop.order_items VALUES
                (1, 1001, 1, 1, 1299.99), (2, 1001, 2, 1, 29.99), (3, 1001, 14, 1, 19.99), (4, 1002, 4, 1, 89.99),
                (5, 1003, 7, 1, 449.99), (6, 1004, 3, 1, 49.99), (7, 1004, 10, 1, 8.99), (8, 1005, 1, 1, 1299.99),
                (9, 1006, 13, 1, 199.99), (10, 1007, 6, 1, 599.99), (11, 1007, 8, 1, 39.99), (12, 1008, 17, 1, 109.99),
                (13, 1008, 14, 1, 19.99), (14, 1009, 5, 1, 399.99), (15, 1010, 4, 1, 89.99), (16, 1011, 1, 1, 1299.99),
                (17, 1011, 7, 1, 449.99), (18, 1012, 3, 1, 49.99), (19, 1013, 13, 1, 199.99), (20, 1013, 12, 1, 69.99),
                (21, 1014, 17, 1, 109.99), (22, 1015, 5, 1, 399.99), (23, 1015, 11, 1, 79.99), (24, 1015, 3, 1, 49.99)
                """
            )
            _seeded.append("order_items")

        _counts = run_sql(
            """
            SELECT
              (SELECT count(*) FROM postgres.public.customers) AS customers,
              (SELECT count(*) FROM postgres.public.products) AS products,
              (SELECT count(*) FROM iceberg.shop.orders) AS orders,
              (SELECT count(*) FROM iceberg.shop.order_items) AS order_items
            """
        ).iloc[0]

    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(trino_version, label="Trino", caption="healthy", bordered=True),
                    mo.stat(int(_counts["customers"]), label="Customers", caption="postgres.public", bordered=True),
                    mo.stat(int(_counts["products"]), label="Products", caption="postgres.public", bordered=True),
                    mo.stat(int(_counts["orders"]), label="Orders", caption="iceberg.shop", bordered=True),
                    mo.stat(int(_counts["order_items"]), label="Order items", caption="iceberg.shop", bordered=True),
                ],
                widths="equal",
            ),
            mo.callout(
                mo.md(f"Loaded the sample data into `iceberg.shop.{'` and `iceberg.shop.'.join(_seeded)}`.")
                if _seeded
                else mo.md("The shop tables already exist with data, so nothing was changed."),
                kind="success" if _seeded else "neutral",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## The data model

    Customers and products live in **PostgreSQL**. Orders and order items live in **Iceberg**,
    as Parquet files on S3 (LocalStack) catalogued by Polaris. Trino sees both as ordinary catalogs.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.hstack(
        [
            mo.mermaid(
                """
                erDiagram
                    CUSTOMERS ||--o{ ORDERS : places
                    ORDERS ||--|{ ORDER_ITEMS : contains
                    PRODUCTS ||--o{ ORDER_ITEMS : "sold as"
                    CUSTOMERS {
                        int customer_id PK
                        varchar name
                        varchar email
                        varchar city
                        varchar country
                        date signup_date
                    }
                    PRODUCTS {
                        int product_id PK
                        varchar name
                        varchar category
                        decimal price
                        int stock_quantity
                    }
                    ORDERS {
                        bigint order_id PK
                        bigint customer_id FK
                        date order_date
                        varchar status
                        decimal total_amount
                    }
                    ORDER_ITEMS {
                        bigint item_id PK
                        bigint order_id FK
                        bigint product_id FK
                        int quantity
                        decimal unit_price
                    }
                """
            ),
            mo.md(
                """
                | Table | Catalog | Storage |
                |-------|---------|---------|
                | `postgres.public.customers` | `postgres` | PostgreSQL rows |
                | `postgres.public.products` | `postgres` | PostgreSQL rows |
                | `iceberg.shop.orders` | `iceberg` | Parquet on S3, via Polaris |
                | `iceberg.shop.order_items` | `iceberg` | Parquet on S3, via Polaris |

                **Heads-up:** older versions of this lab used `customers.segment` and
                `order_items.line_total`, which the tables don't have. Here we group by
                `city` instead of `segment`, and compute `line_total` as
                `quantity * unit_price` in the query.
                """
            ),
        ],
        widths=[3, 2],
        align="center",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.mermaid(
        """
        flowchart LR
            Q["One SQL query"] --> T["Trino coordinator"]
            T -->|"postgres connector<br/>(pushes SQL down)"| PG[("PostgreSQL<br/>customers, products")]
            T -->|"iceberg connector<br/>(REST catalog)"| PO["Polaris"]
            PO -.->|"metadata pointers"| S3[("S3 / LocalStack<br/>orders, order_items<br/>Parquet files")]
            T -->|"reads Parquet"| S3
        """
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 1 — A simple cross-source JOIN

    Customers come from Postgres, orders from Iceberg.
    """)
    return


@app.cell
def _(run_sql, show):
    step1 = run_sql(
        """
        SELECT
          c.name AS customer, c.country,
          o.order_id, o.order_date, o.total_amount
        FROM iceberg.shop.orders o
        JOIN postgres.public.customers c ON o.customer_id = c.customer_id
        ORDER BY o.order_date
        """
    )
    show(step1)
    return (step1,)


@app.cell(hide_code=True)
def _(mo, step1):
    mo.accordion(
        {
            "Question: How many rows? Where does each column come from?": mo.md(
                f"""
                **{len(step1)} rows**, one per order. Every order's `customer_id` matches a customer.

                | Column | Source |
                |--------|--------|
                | `customer`, `country` | `postgres.public.customers` |
                | `order_id`, `order_date`, `total_amount` | `iceberg.shop.orders` |
                """
            )
        }
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 2 — A four-table cross-source JOIN

    Order items and orders (Iceberg) joined to customers and products (Postgres).
    """)
    return


@app.cell
def _(run_sql, show):
    step2 = run_sql(
        """
        SELECT
          c.name AS customer, p.name AS product, p.category,
          oi.quantity, oi.unit_price,
          oi.quantity * oi.unit_price AS line_total
        FROM iceberg.shop.order_items oi
        JOIN iceberg.shop.orders o ON oi.order_id = o.order_id
        JOIN postgres.public.customers c ON o.customer_id = c.customer_id
        JOIN postgres.public.products p ON oi.product_id = p.product_id
        ORDER BY c.name, o.order_id
        """
    )
    show(step2)
    return (step2,)


@app.cell(hide_code=True)
def _(mo, step2):
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(2, label="Catalogs", caption="postgres + iceberg", bordered=True),
                    mo.stat(4, label="Tables", bordered=True),
                    mo.stat(2, label="Storage backends", caption="PostgreSQL + S3 Parquet", bordered=True),
                    mo.stat(len(step2), label="Rows", caption="one per order item", bordered=True),
                ],
                widths="equal",
            ),
            mo.callout(
                mo.md("This single query hits **2 catalogs, 4 tables and 2 different storage backends**, with no ETL."),
                kind="success",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 3 — Aggregations across sources

    ### Top customers by spend
    """)
    return


@app.cell
def _(run_sql, show):
    top_customers = run_sql(
        """
        SELECT
          c.name, c.country, c.city,
          count(DISTINCT o.order_id) AS num_orders,
          round(sum(o.total_amount), 2) AS total_spent
        FROM iceberg.shop.orders o
        JOIN postgres.public.customers c ON o.customer_id = c.customer_id
        GROUP BY c.name, c.country, c.city
        ORDER BY total_spent DESC
        """
    )
    show(top_customers)
    return (top_customers,)


@app.cell(hide_code=True)
def _(mo, top_customers):
    _top = top_customers.iloc[0]
    mo.callout(
        mo.md(
            f"**{_top['name']}** ({_top['city']}, {_top['country']}) is the top customer: "
            f"**{_top['total_spent']}** across {_top['num_orders']} orders. The grouping columns come "
            "from Postgres and the measures from Iceberg."
        ),
        kind="info",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Revenue by product category
    """)
    return


@app.cell
def _(run_sql, show):
    by_category = run_sql(
        """
        SELECT
          p.category,
          count(*) AS items_sold,
          sum(oi.quantity) AS total_qty,
          round(sum(oi.quantity * oi.unit_price), 2) AS revenue
        FROM iceberg.shop.order_items oi
        JOIN postgres.public.products p ON oi.product_id = p.product_id
        GROUP BY p.category
        ORDER BY revenue DESC
        """
    )
    show(by_category)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 4 — Revenue by country
    """)
    return


@app.cell
def _(run_sql, show):
    by_country = run_sql(
        """
        SELECT
          c.country,
          count(DISTINCT c.customer_id) AS customers,
          count(DISTINCT o.order_id) AS orders,
          round(sum(o.total_amount), 2) AS total_revenue,
          round(avg(o.total_amount), 2) AS avg_order_value
        FROM iceberg.shop.orders o
        JOIN postgres.public.customers c ON o.customer_id = c.customer_id
        GROUP BY c.country
        ORDER BY total_revenue DESC
        """
    )
    show(by_country)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 5 — The memory catalog for intermediate results

    Trino's `memory` catalog keeps tables in the workers' RAM. It's handy for staging a federated
    result once and querying it many times. This cell drops and rebuilds its own
    `memory.analytics.customer_summary`, so re-running it always gives fresh numbers.
    """)
    return


@app.cell
def _(run_sql, show):
    run_sql("CREATE SCHEMA IF NOT EXISTS memory.analytics")
    run_sql("DROP TABLE IF EXISTS memory.analytics.customer_summary")
    run_sql(
        """
        CREATE TABLE memory.analytics.customer_summary AS
        SELECT
          c.customer_id, c.name, c.country, c.city,
          count(DISTINCT o.order_id) AS total_orders,
          round(sum(o.total_amount), 2) AS lifetime_value
        FROM iceberg.shop.orders o
        JOIN postgres.public.customers c ON o.customer_id = c.customer_id
        GROUP BY c.customer_id, c.name, c.country, c.city
        """
    )
    customer_summary = run_sql("SELECT * FROM memory.analytics.customer_summary ORDER BY lifetime_value DESC")
    show(customer_summary)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.callout(
        mo.md(
            "**Memory catalog data is lost when Trino restarts.** It's useful for ad-hoc analysis, not for persistence. "
            "For results you want to keep, use `CREATE TABLE iceberg.<schema>.<table> AS ...` instead."
        ),
        kind="warn",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 6 — Check the query plan

    How does Trino split a federated query? `EXPLAIN` shows the plan. Each source gets its own scan node,
    and the Postgres connector **pushes SQL down** to the database, so only the needed columns travel to Trino.

    Pick one of the queries above to see its scans.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    _queries = {
        "Step 1 — customers + orders": """
            SELECT c.name AS customer, c.country, o.order_id, o.order_date, o.total_amount
            FROM iceberg.shop.orders o
            JOIN postgres.public.customers c ON o.customer_id = c.customer_id
            ORDER BY o.order_date""",
        "Step 2 — four-table join": """
            SELECT c.name AS customer, p.name AS product, p.category,
                   oi.quantity, oi.unit_price, oi.quantity * oi.unit_price AS line_total
            FROM iceberg.shop.order_items oi
            JOIN iceberg.shop.orders o ON oi.order_id = o.order_id
            JOIN postgres.public.customers c ON o.customer_id = c.customer_id
            JOIN postgres.public.products p ON oi.product_id = p.product_id
            ORDER BY c.name, o.order_id""",
        "Step 3 — revenue by category": """
            SELECT p.category, count(*) AS items_sold, sum(oi.quantity) AS total_qty,
                   round(sum(oi.quantity * oi.unit_price), 2) AS revenue
            FROM iceberg.shop.order_items oi
            JOIN postgres.public.products p ON oi.product_id = p.product_id
            GROUP BY p.category ORDER BY revenue DESC""",
    }
    plan_picker = mo.ui.dropdown(_queries, value="Step 2 — four-table join", label="Query to explain")
    plan_picker
    return (plan_picker,)


@app.cell
def _(plan_picker, run_sql):
    query_plan = run_sql("EXPLAIN " + plan_picker.value).iloc[0, 0]
    return (query_plan,)


@app.cell(hide_code=True)
def _(mo, pd, query_plan, re):
    def _scans(plan):
        rows = []
        for line in plan.splitlines():
            m = re.search(r"(\w+)\[table = (\w+):(.*)", line)
            if not m:
                continue
            node, catalog, detail = m.groups()
            if detail.startswith("Query["):
                read = detail[len("Query[") :].split("] columns=")[0]
            else:
                read = re.split(r"[$@,\]]", detail)[0]
            rows.append({"Plan node": node, "Catalog": catalog, "What is read": read})
        return pd.DataFrame(rows)

    _df = _scans(query_plan)
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(int((_df["Catalog"] == "postgres").sum()), label="Postgres scans", bordered=True),
                    mo.stat(int((_df["Catalog"] == "iceberg").sum()), label="Iceberg scans", bordered=True),
                ],
                widths="equal",
            ),
            mo.ui.table(_df, selection=None, show_column_summaries=False),
            mo.accordion({"Full EXPLAIN output": mo.md(f"```text\n{query_plan}\n```")}),
            mo.callout(
                mo.md(
                    "**In the Trino Web UI:** open [http://localhost:8080](http://localhost:8080) (log in as `admin`), "
                    "click a completed federation query and open the **Query Plan** (or *Live Plan*) tab. "
                    "You'll see a separate `TableScan` / `ScanFilterProject` node for each catalog.\n\n"
                    "**Question:** can you tell which parts read from Postgres and which from Iceberg? "
                    "(Hint: the Postgres scans show the SQL Trino sent to the database.)"
                ),
                kind="info",
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
                1. Federation means one SQL statement over several sources, addressed as `catalog.schema.table`
                2. Trino joins Postgres rows and Iceberg Parquet files without moving data first
                3. Connectors push work down: Postgres receives a SQL query, Iceberg scans are pruned by metadata
                4. The `memory` catalog is a fast scratch space, but it's gone after a Trino restart
                5. `EXPLAIN` and the Trino Web UI show which plan nodes read from which source
                """
            ),
            "Exercises": mo.md(
                """
                1. **Find customers who have NOT placed any orders.** (Hint: `LEFT JOIN` + check for `NULL`)
                2. **What is the most popular product** by quantity sold?
                3. **Which country has the highest average order value?**
                4. **Create a memory table** with monthly revenue (hint: `date_trunc('month', o.order_date)`)
                5. **Bonus:** Join `tpch.tiny.nation` with Postgres customers on `country`. Which TPC-H nations match?
                   (Hint: TPC-H names are upper case, e.g. `upper(c.country) = n.name`, and Postgres uses short names like `USA`.)

                Try them in a new cell with `run_sql(\"\"\"...\"\"\")`, or in the Trino CLI:
                `podman exec -e TRINO_PASSWORD=admin123 -it trino trino --server https://localhost:8443 --user admin --password --insecure`
                (or the same with `docker exec`).
                """
            ),
            "Next lab": mo.md("**Lab 3 — Access Control**: Polaris principals, roles and grants, plus Trino's own access rules."),
        },
        multiple=True,
    )
    return


if __name__ == "__main__":
    app.run()
