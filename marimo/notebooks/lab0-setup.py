import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium", app_title="Lab 0 — Environment Setup")


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
    S3_HOST = os.environ.get("S3_HOST", "localhost")
    JAEGER_HOST = os.environ.get("JAEGER_HOST", "localhost")

    POLARIS_HEALTH = f"http://{POLARIS_HOST}:8182/q/health"
    S3_ENDPOINT = f"http://{S3_HOST}:4566"
    TRINO_INFO = f"http://{TRINO_HOST}:8080/v1/info"
    JAEGER_UI = f"http://{JAEGER_HOST}:16686"
    # Inside the marimo container, services are reached by container name; on the host, via localhost.
    _in_compose = TRINO_HOST != "localhost"
    POLARIS_ADMIN_UI = "http://polaris-admin:80" if _in_compose else "http://localhost:3000"
    JUPYTER_UI = "http://spark-jupyter:8888" if _in_compose else "http://localhost:8888"
    EXPECTED_CATALOGS = ["iceberg", "memory", "postgres", "system", "tpcds", "tpch"]
    return (
        EXPECTED_CATALOGS,
        JAEGER_UI,
        JUPYTER_UI,
        POLARIS_ADMIN_UI,
        POLARIS_HEALTH,
        S3_ENDPOINT,
        TRINO_HOST,
        TRINO_INFO,
        create_engine,
        mo,
        pd,
        requests,
        text,
    )


@app.cell(hide_code=True)
def _(mo, pd, requests, text):
    def reachable(url, timeout=3):
        try:
            return requests.get(url, timeout=timeout).status_code < 500
        except requests.RequestException:
            return False

    def run_sql(engine, sql):
        with engine.connect() as conn:
            return pd.read_sql(text(sql), conn)

    def show(df):
        return mo.ui.table(df, selection=None, show_column_summaries=False)

    return reachable, run_sql, show


@app.cell(hide_code=True)
def _(mo):
    mo.sidebar(
        [
            mo.md("### Lab 0\n**Environment Setup**"),
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
                # Lab 0 — Environment Setup

                **Level:** 0 (Beginner) &nbsp;|&nbsp; **Time:** 10 minutes

                **Goal:** Verify all services are running and run your first Trino query.
                """
            ),
            mo.callout(
                mo.md(
                    """
                    **What you'll do**

                    1. Check that the lab containers are running
                    2. Confirm Polaris reports itself healthy
                    3. Open the web UIs
                    4. Run your first Trino queries (catalogs, customers, products)
                    5. Tick off the checkpoint, which this notebook fills in for you
                    """
                ),
                kind="info",
            ),
            mo.callout(
                mo.md(
                    "Some steps (like `podman ps` / `docker ps`) must be run in a **terminal**. "
                    "This notebook covers the steps that can run from inside marimo and shows the terminal commands for the rest."
                ),
                kind="neutral",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.mermaid(
        """
        flowchart LR
            subgraph core["Core stack (always on)"]
                T["trino<br/>:8080 UI · :8443 SQL"]
                P["polaris<br/>:8181 API · :8182 health"]
                PG[("postgres")]
                L[("localstack<br/>S3 + STS :4566")]
                A["polaris-admin<br/>:3000"]
            end
            subgraph ondemand["On demand (profiles)"]
                J["spark-jupyter :8888"]
                M["marimo :2718"]
            end
            T --> P
            T --> PG
            P --> PG
            P --> L
            T --> L
            A --> P
            J --> P
            M --> T
            M --> P
        """
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## Step 1 — Check Running Services

    Run this in your **terminal** (not in marimo):

    ```bash
    podman ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    # or: docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    ```

    You should see these containers running:

    | Container | Expected Status |
    |-----------|----------------|
    | trino | Up |
    | postgres | Up (healthy) |
    | polaris | Up (healthy) |
    | localstack | Up (healthy) |
    | polaris-admin | Up |
    | spark-jupyter | Up (on demand) |
    | marimo | Up (on demand) |

    `spark-jupyter` and `marimo` are on demand and not started by default. Start them when a lab needs them:

    ```bash
    podman compose --profile spark up -d      # Spark Jupyter (:8888)
    podman compose --profile marimo up -d     # marimo (:2718)
    podman compose stop spark-jupyter marimo  # free the memory again
    ```

    The `polaris-setup`, `localstack-setup` and `dlt-earthquakes` containers show **Exited (0)**. That's normal:
    they are one-shot init jobs. If a service is not running, check its logs with `podman logs <container-name>`
    (or `docker logs <container-name>`).

    From inside the notebook we can't run `podman ps`, but we **can** probe each service over the network:
    """)
    return


@app.cell(hide_code=True)
def _(JAEGER_UI, JUPYTER_UI, POLARIS_ADMIN_UI, POLARIS_HEALTH, S3_ENDPOINT, TRINO_INFO, mo, pd, reachable):
    _services = [
        ("trino", "Core", TRINO_INFO),
        ("polaris", "Core", POLARIS_HEALTH),
        ("localstack", "Core", f"{S3_ENDPOINT}/_localstack/health"),
        ("polaris-admin", "Core (UI)", POLARIS_ADMIN_UI),
        ("jaeger", "Observability", JAEGER_UI),
        ("spark-jupyter", "On demand", JUPYTER_UI),
    ]
    service_status = pd.DataFrame(
        [{"Container": n, "Group": g, "Probe": u, "Reachable": reachable(u)} for n, g, u in _services]
    )
    _core = service_status[service_status["Group"] == "Core"]
    core_ok = bool(_core["Reachable"].all())

    mo.stop(
        not core_ok,
        mo.callout(
            mo.md(
                "**The core lab stack isn't reachable.** "
                + " &nbsp;·&nbsp; ".join(
                    f"{r.Container}: {'up' if r.Reachable else '**down**'}" for r in _core.itertuples()
                )
                + "\n\nStart it with `podman compose up -d` (add `--profile marimo` for this notebook server; "
                "`docker compose` works the same), then re-run this cell."
            ),
            kind="danger",
        ),
    )

    _display = service_status.assign(Reachable=service_status["Reachable"].map({True: "up", False: "not reachable"}))
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(f"{int(_core['Reachable'].sum())}/{len(_core)}", label="Core services", caption="trino · polaris · localstack", bordered=True),
                    mo.stat(
                        f"{int(service_status['Reachable'].sum())}/{len(service_status)}",
                        label="All probed services",
                        caption="UIs and on-demand ones are optional",
                        bordered=True,
                    ),
                ],
                widths="equal",
            ),
            mo.ui.table(_display, selection=None, show_column_summaries=False),
        ]
    )
    return core_ok, service_status


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 2 — Polaris Health Check

    Polaris (a Quarkus app) exposes a health endpoint on its management port **8182**.
    From a terminal: `curl -s http://localhost:8182/q/health | python3 -m json.tool`. From Python:
    """)
    return


@app.cell
def _(POLARIS_HEALTH, core_ok, requests):
    assert core_ok
    health = requests.get(POLARIS_HEALTH, timeout=5).json()
    health
    return (health,)


@app.cell(hide_code=True)
def _(health, mo, pd):
    _up = health.get("status") == "UP"
    mo.vstack(
        [
            mo.callout(
                mo.md(f"Polaris reports **`\"status\": \"{health.get('status')}\"`**" + (". Expected: `UP`." if not _up else ", as expected.")),
                kind="success" if _up else "danger",
            ),
            mo.ui.table(
                pd.DataFrame([{"Check": c.get("name"), "Status": c.get("status")} for c in health.get("checks", [])]),
                selection=None,
                show_column_summaries=False,
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo, service_status):
    _up = dict(zip(service_status["Container"], service_status["Reachable"]))

    def _ui(title, url, container, notes):
        return mo.vstack(
            [
                mo.md(f"**[{title}]({url})**"),
                mo.md(notes),
                mo.callout(
                    "Reachable now" if _up.get(container) else "Not reachable from here right now",
                    kind="success" if _up.get(container) else "warn",
                ),
            ]
        )

    mo.vstack(
        [
            mo.md("""
            ---
            ## Step 3 — Open the Web UIs

            Open each of these in your browser:
            """),
            mo.hstack(
                [
                    _ui(
                        "1. Trino Web UI",
                        "http://localhost:8080",
                        "trino",
                        "http://localhost:8080 — shows running and completed queries. No login required (monitoring only).",
                    ),
                    _ui(
                        "2. Polaris Admin",
                        "http://localhost:3000",
                        "polaris-admin",
                        "http://localhost:3000 — Client ID = `root`, Secret = `s3cr3t`, Realm = `POLARIS`. "
                        "You should see the Dashboard with catalogs and roles.",
                    ),
                    _ui(
                        "3. Spark Jupyter",
                        "http://localhost:8888?token=spark123",
                        "spark-jupyter",
                        "http://localhost:8888?token=spark123 — PySpark notebook environment "
                        "(after `podman compose --profile spark up -d`).",
                    ),
                ],
                widths="equal",
                align="start",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ---
    ## Step 4 — Your First Trino Query

    In a terminal you would connect with the Trino CLI as admin:

    ```bash
    podman exec -e TRINO_PASSWORD=admin123 -it trino \
      trino --server https://localhost:8443 --user admin --password --insecure
    ```

    (`docker exec …` works the same; type `quit` to exit the CLI.) For a one-off query without the interactive CLI:

    ```bash
    podman exec -e TRINO_PASSWORD=admin123 trino \
      trino --server https://localhost:8443 --user admin --password --insecure \
      --execute "SELECT name, country FROM postgres.public.customers ORDER BY country LIMIT 5"
    ```

    Here we use SQLAlchemy instead. The connection URL carries the user, password and default catalog:
    """)
    return


@app.cell
def _(TRINO_HOST, core_ok, create_engine):
    assert core_ok
    trino_engine = create_engine(
        f"trino://admin:admin123@{TRINO_HOST}:8443/iceberg",
        connect_args={"http_scheme": "https", "verify": False},
    )
    return (trino_engine,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### `SHOW CATALOGS`

    Expected: `iceberg`, `memory`, `postgres`, `system`, `tpcds`, `tpch`
    """)
    return


@app.cell
def _(run_sql, trino_engine):
    df_catalogs = run_sql(trino_engine, "SHOW CATALOGS")
    return (df_catalogs,)


@app.cell(hide_code=True)
def _(EXPECTED_CATALOGS, df_catalogs, mo, show):
    _found = set(df_catalogs["Catalog"])
    missing_catalogs = [c for c in EXPECTED_CATALOGS if c not in _found]
    _extra = sorted(_found - set(EXPECTED_CATALOGS))
    if missing_catalogs:
        _note = mo.callout(mo.md(f"Missing catalog(s): {', '.join(f'`{c}`' for c in missing_catalogs)}. Check `podman logs trino`."), kind="danger")
    elif _extra:
        _note = mo.callout(
            mo.md(
                f"All 6 expected catalogs are present, plus {', '.join(f'`{c}`' for c in _extra)}. "
                "Extra catalogs come from optional exercises (e.g. `exercises/global-sales-setup.sh`) and are fine."
            ),
            kind="success",
        )
    else:
        _note = mo.callout("All 6 expected catalogs are present.", kind="success")

    mo.vstack(
        [
            mo.hstack(
                [mo.stat(len(df_catalogs), label="Catalogs", caption="expected 6", bordered=True), _note],
                widths=[1, 3],
                align="center",
            ),
            show(df_catalogs),
        ]
    )
    return (missing_catalogs,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Customers from Postgres

    You should see customer records with `customer_id`, `name`, `email`, `country`.
    """)
    return


@app.cell
def _(run_sql, trino_engine):
    df_customers = run_sql(trino_engine, "SELECT * FROM postgres.public.customers LIMIT 5")
    return (df_customers,)


@app.cell(hide_code=True)
def _(df_customers, show):
    show(df_customers)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Product count

    Expected: `20`
    """)
    return


@app.cell
def _(run_sql, trino_engine):
    df_count = run_sql(trino_engine, "SELECT count(*) AS total_products FROM postgres.public.products")
    return (df_count,)


@app.cell(hide_code=True)
def _(df_count, mo):
    total_products = int(df_count["total_products"][0])
    mo.hstack(
        [
            mo.stat(total_products, label="total_products", caption="expected 20", bordered=True),
            mo.callout(
                "Matches the expected count." if total_products == 20 else f"Expected 20 products, got {total_products}.",
                kind="success" if total_products == 20 else "warn",
            ),
        ],
        widths=[1, 3],
        align="center",
    )
    return (total_products,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### One-off query

    The same query as the `--execute` example above:
    """)
    return


@app.cell
def _(run_sql, show, trino_engine):
    show(run_sql(trino_engine, "SELECT name, country FROM postgres.public.customers ORDER BY country LIMIT 5"))
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Checkpoint
    """)
    return


@app.cell(hide_code=True)
def _(df_customers, health, missing_catalogs, mo, pd, service_status, show, total_products):
    _up = dict(zip(service_status["Container"], service_status["Reachable"]))
    _checks = [
        ("All core services running (`podman ps`)", all(_up[c] for c in ("trino", "polaris", "localstack"))),
        ("Trino Web UI loads at :8080", _up["trino"]),
        ("Polaris Admin loads at :3000 with Dashboard", _up["polaris-admin"]),
        ("Jupyter loads at :8888", _up["spark-jupyter"]),
        ("Polaris health check returns `UP`", health.get("status") == "UP"),
        ("`SHOW CATALOGS` returns the 6 catalogs", not missing_catalogs),
        ("`SELECT` from customers returns data", len(df_customers) > 0),
        ("Product count is 20", total_products == 20),
    ]
    _required = _checks[:2] + _checks[4:]
    _passed = sum(ok for _, ok in _required)
    mo.vstack(
        [
            mo.callout(
                mo.md(
                    f"**{_passed}/{len(_required)} required checks pass.** "
                    + (
                        "Your environment is ready."
                        if _passed == len(_required)
                        else "Fix the failing items before moving on."
                    )
                    + " The Polaris Admin and Jupyter UIs are optional here; Jupyter only runs with `--profile spark`."
                ),
                kind="success" if _passed == len(_required) else "danger",
            ),
            show(pd.DataFrame([{"Check": c, "Result": "pass" if ok else "not yet"} for c, ok in _checks])),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.accordion(
        {
            "Key takeaways": mo.md(
                """
                1. The core stack is **Trino + Polaris + Postgres + LocalStack**, plus the Polaris Admin UI
                2. Spark Jupyter and marimo are on-demand compose **profiles**
                3. Polaris health lives on port **8182** (`/q/health`); its REST API is on **8181**
                4. Trino speaks HTTPS on **8443** (password auth) and serves its UI on **8080**
                """
            ),
            "Troubleshooting": mo.md(
                """
                - A container is missing: `podman compose up -d` (or `docker compose up -d`)
                - A container keeps restarting: `podman logs <container-name>`
                - `dlt-earthquakes` failed: it needs internet access to the USGS feed; re-run it with `podman restart dlt-earthquakes`
                """
            ),
            "Next lab": mo.md("**Lab 1 — Exploring Catalogs**: catalogs, schemas, tables and your first aggregations."),
        },
        multiple=True,
    )
    return


if __name__ == "__main__":
    app.run()
