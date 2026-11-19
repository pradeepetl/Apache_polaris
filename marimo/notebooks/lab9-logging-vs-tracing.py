import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium", app_title="Lab 9 — Logging vs Tracing")


@app.cell(hide_code=True)
def _():
    import os
    from datetime import datetime, timedelta, timezone

    import marimo as mo
    import pandas as pd
    import requests
    import urllib3
    from sqlalchemy import create_engine, text

    urllib3.disable_warnings()

    TRINO_HOST = os.environ.get("TRINO_HOST", "localhost")
    JAEGER = f"http://{os.environ.get('JAEGER_HOST', 'localhost')}:16686"
    POLARIS = f"http://{os.environ.get('POLARIS_HOST', 'localhost')}:8181"
    POLARIS_HEALTH = f"http://{os.environ.get('POLARIS_HOST', 'localhost')}:8182/q/health"
    REALM = "POLARIS"
    STANDIN_COMMENT = "lab9 stand-in"

    trino_engine = create_engine(
        f"trino://admin:admin123@{TRINO_HOST}:8443/iceberg",
        connect_args={"http_scheme": "https", "verify": False},
    )
    return (
        JAEGER,
        POLARIS_HEALTH,
        STANDIN_COMMENT,
        datetime,
        mo,
        pd,
        requests,
        text,
        timedelta,
        timezone,
        trino_engine,
    )


@app.cell(hide_code=True)
def _(mo, pd, text, trino_engine):
    def sql(query):
        """Run a Trino query and return a DataFrame."""
        with trino_engine.connect() as _conn:
            return pd.read_sql(text(query), _conn)

    def execute(*statements):
        with trino_engine.connect() as _conn:
            for _s in statements:
                _conn.execute(text(_s))

    def show(df, page_size=10):
        return mo.ui.table(df, selection=None, show_column_summaries=False, page_size=page_size)

    return execute, show, sql


@app.cell(hide_code=True)
def _(mo):
    mo.sidebar([mo.md("### Lab 9\n**Logging vs Tracing**"), mo.outline()])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.vstack(
        [
            mo.md(
                """
                # Lab 9 — Logging vs Tracing: Real-World Analysis

                **Companion to:** Lab 8 (Observability) &nbsp;|&nbsp; **Time:** 30 minutes

                This notebook brings the concepts from `exercises/logging-vs-tracing.md` to life
                using **observability data stored in Iceberg tables**:
                `iceberg.observability.traces` (Jaeger spans) and `iceberg.observability.logs`
                (Polaris container logs). We query both with Trino to show when and why you'd use logging vs tracing.
                """
            ),
            mo.callout(
                mo.md(
                    """
                    **What you'll do**

                    1. Make sure the `observability` tables exist (load them from Jaeger if they don't)
                    2. Use **logs** for traffic analysis, audit trails and security alerting
                    3. Use **traces** for latency diagnosis, SLA percentiles and error rates
                    4. **Correlate** the two on `trace_id`, then explore live data from the Jaeger API
                    """
                ),
                kind="info",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(JAEGER, POLARIS_HEALTH, mo, requests, sql):
    def _reachable(url):
        try:
            return requests.get(url, timeout=5).ok
        except requests.RequestException:
            return False

    try:
        _trino_version = sql("SELECT version() AS v")["v"].iloc[0]
    except Exception:
        _trino_version = None
    _polaris_ok = _reachable(POLARIS_HEALTH)
    jaeger_ok = _reachable(f"{JAEGER}/api/services")

    mo.stop(
        _trino_version is None or not _polaris_ok,
        mo.callout(
            mo.md(
                f"""
                **The lab stack isn't reachable.**
                Trino: {"up" if _trino_version else "**down**"} &nbsp;·&nbsp; Polaris: {"up" if _polaris_ok else "**down**"}

                Start it with `podman compose --profile marimo up -d` (or `docker compose …`), then re-run this cell.
                """
            ),
            kind="danger",
        ),
    )
    mo.hstack(
        [
            mo.stat("Healthy", label="Trino", caption=f"version {_trino_version}", bordered=True),
            mo.stat("Healthy", label="Polaris", caption="REST catalog", bordered=True),
            mo.stat(
                "Healthy" if jaeger_ok else "Down",
                label="Jaeger",
                caption="trace collector :16686" if jaeger_ok else "live steps will be skipped",
                bordered=True,
            ),
        ],
        widths="equal",
    )
    return (jaeger_ok,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Step 0 — Load the observability tables

    The tables normally come from the ingest script, which pulls the last 500 Jaeger traces and the last
    500 Polaris log lines and writes them to Iceberg through Trino:

    ```bash
    bash exercises/ingest-observability.sh
    ```

    The script reads logs with `docker logs polaris`, which a notebook can't do. So if the tables are missing,
    the next cell builds **stand-ins**: it mirrors the script's `traces` table from the live Jaeger API, and
    derives `logs` rows from those spans (one access-log line per request, carrying the same request id and trace id
    Polaris writes to its real logs). It also adds a few sample rows for regional namespaces and failed logins,
    so the audit and security queries have something to find.
    Existing tables are never overwritten.
    """)
    return


@app.cell(hide_code=True)
def _(JAEGER, STANDIN_COMMENT, datetime, execute, jaeger_ok, mo, requests, sql, timedelta, timezone):
    def _esc(v):
        return str(v).replace("'", "''")

    def _ts(dt):
        return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    def _existing():
        try:
            return set(sql("SHOW TABLES FROM iceberg.observability")["Table"])
        except Exception:
            return set()

    def _jaeger_spans():
        if not jaeger_ok:
            return []
        _data = requests.get(
            f"{JAEGER}/api/traces", params={"service": "polaris-server", "limit": 500, "lookback": "6h"}, timeout=30
        ).json().get("data") or []
        _spans = []
        for _trace in _data:
            _proc = next(iter(_trace.get("processes", {}).values()), {})
            _version = next((t["value"] for t in _proc.get("tags", []) if t["key"] == "service.version"), "")
            for _s in _trace.get("spans", []):
                _tags = {t["key"]: t["value"] for t in _s.get("tags", [])}
                _spans.append(
                    {
                        "trace_id": _s["traceID"],
                        "span_id": _s["spanID"],
                        "operation_name": _s["operationName"],
                        "start": datetime.fromtimestamp(_s["startTime"] / 1_000_000, tz=timezone.utc),
                        "duration_us": int(_s["duration"]),
                        "http_method": _tags.get("http.request.method", ""),
                        "http_status": int(_tags.get("http.response.status_code", 0) or 0),
                        "url_path": _tags.get("url.path", ""),
                        "client_address": _tags.get("client.address", ""),
                        "realm_id": _tags.get("polaris.realm.id", ""),
                        "request_id": _tags.get("polaris.request.id", ""),
                        "service_name": _proc.get("serviceName", "polaris-server"),
                        "service_version": str(_version),
                    }
                )
        return _spans

    def _sample_spans(now):
        """Hand-written spans: regional sales lookups (audit) and failed/forbidden calls (security)."""
        _base = "/api/catalog/v1/polaris_warehouse/namespaces"
        _rows = [
            ("POST /api/catalog/v1/oauth/tokens", "POST", 200, "/api/catalog/v1/oauth/tokens", 31000),
            ("GET /api/catalog/v1/{prefix}/namespaces/{namespace}/views/{view}", "GET", 404, f"{_base}/ap_india/views/products", 19000),
            ("GET /api/catalog/v1/{prefix}/namespaces/{namespace}/tables/{table}", "GET", 200, f"{_base}/ap_india/tables/products", 77000),
            ("POST /api/catalog/v1/{prefix}/namespaces/{namespace}/tables/{table}/metrics", "POST", 204, f"{_base}/ap_india/tables/products/metrics", 6000),
            ("GET /api/catalog/v1/{prefix}/namespaces/{namespace}/tables/{table}", "GET", 200, f"{_base}/ap_india/tables/sales", 64000),
            ("GET /api/catalog/v1/{prefix}/namespaces/{namespace}/tables/{table}", "GET", 200, f"{_base}/eu_germany/tables/sales", 58000),
            ("GET /api/catalog/v1/{prefix}/namespaces/{namespace}/tables/{table}", "GET", 403, f"{_base}/eu_germany/tables/customers", 4100),
            ("POST /api/catalog/v1/oauth/tokens", "POST", 401, "/api/catalog/v1/oauth/tokens", 2900),
            ("POST /api/catalog/v1/oauth/tokens", "POST", 401, "/api/catalog/v1/oauth/tokens", 3100),
            ("POST /api/catalog/v1/oauth/tokens", "POST", 401, "/api/catalog/v1/oauth/tokens", 2700),
            ("GET /api/catalog/v1/{prefix}/namespaces/{namespace}/tables", "GET", 500, f"{_base}/na_usa/tables", 30_012_000),
        ]
        _out = []
        for _i, (_op, _m, _st, _path, _dur) in enumerate(_rows):
            _out.append(
                {
                    "trace_id": f"5a{_i:030x}",
                    "span_id": f"5b{_i:014x}",
                    "operation_name": _op,
                    "start": now - timedelta(minutes=30) + timedelta(seconds=7 * _i),
                    "duration_us": _dur,
                    "http_method": _m,
                    "http_status": _st,
                    "url_path": _path,
                    "client_address": "10.89.1.147",
                    "realm_id": "POLARIS",
                    "request_id": f"sample-{_i:03d}",
                    "service_name": "polaris-server",
                    "service_version": "1.8.0",
                }
            )
        return _out

    def _logs_from_spans(spans):
        _rows = []
        for _i, _s in enumerate(spans):
            _ctx = dict(
                request_id=_s["request_id"], realm_id=_s["realm_id"], trace_id=_s["trace_id"], span_id=_s["span_id"],
                thread=f"executor-thread-{1 + _i % 12}", client_ip=_s["client_address"],
            )
            if "/tables/" in _s["url_path"] and _s["http_method"] == "GET" and _s["http_status"] == 200:
                _rows.append(dict(ts=_s["start"] + timedelta(microseconds=_s["duration_us"] // 2), level="INFO",
                                  logger="org.apa.ice.BaseMetastoreCatalog", http_method="", http_path="", http_status=0, size=0, **_ctx))
            if _s["http_status"] >= 500:
                _rows.append(dict(ts=_s["start"] + timedelta(microseconds=_s["duration_us"]), level="ERROR",
                                  logger="org.apa.pol.ser.exc.IcebergExceptionMapper", http_method="", http_path="", http_status=0, size=0, **_ctx))
            elif _s["http_status"] in (401, 403):
                _rows.append(dict(ts=_s["start"] + timedelta(microseconds=_s["duration_us"]), level="WARN",
                                  logger="org.apa.pol.ser.exc.IcebergExceptionMapper", http_method="", http_path="", http_status=0, size=0, **_ctx))
            _rows.append(dict(ts=_s["start"] + timedelta(microseconds=_s["duration_us"]), level="INFO", logger="io.qua.htt.access-log",
                              http_method=_s["http_method"], http_path=_s["url_path"], http_status=_s["http_status"],
                              size=0 if _s["http_status"] == 204 else 111 if _s["http_status"] >= 400 else 600 + 37 * (_i % 50), **_ctx))
        return _rows

    def _values(rows, fmt):
        return ",\n".join(fmt(r) for r in rows)

    _before = _existing()
    _created = []
    if not {"traces", "logs"} <= _before:
        with mo.status.spinner(title="Building stand-in observability tables…"):
            _now = datetime.now(timezone.utc)
            _spans = _jaeger_spans()
            _all_spans = _spans + _sample_spans(_now)
            execute("CREATE SCHEMA IF NOT EXISTS iceberg.observability")
            if "traces" not in _before:
                execute(
                    """CREATE TABLE IF NOT EXISTS iceberg.observability.traces (
                        trace_id VARCHAR, span_id VARCHAR, operation_name VARCHAR, start_time TIMESTAMP(3),
                        duration_us BIGINT, http_method VARCHAR, http_status INTEGER, url_path VARCHAR,
                        client_address VARCHAR, realm_id VARCHAR, request_id VARCHAR,
                        service_name VARCHAR, service_version VARCHAR)""",
                    "INSERT INTO iceberg.observability.traces VALUES\n"
                    + _values(
                        _all_spans,
                        lambda s: "('{}', '{}', '{}', TIMESTAMP '{}', {}, '{}', {}, '{}', '{}', '{}', '{}', '{}', '{}')".format(
                            _esc(s["trace_id"]), _esc(s["span_id"]), _esc(s["operation_name"]), _ts(s["start"]),
                            s["duration_us"], _esc(s["http_method"]), s["http_status"], _esc(s["url_path"]),
                            _esc(s["client_address"]), _esc(s["realm_id"]), _esc(s["request_id"]),
                            _esc(s["service_name"]), _esc(s["service_version"]),
                        ),
                    ),
                    f"COMMENT ON TABLE iceberg.observability.traces IS '{STANDIN_COMMENT}: {len(_spans)} Jaeger spans + {len(_all_spans) - len(_spans)} sample spans'",
                )
                _created.append("traces")
            if "logs" not in _before:
                _logs = _logs_from_spans(_all_spans)
                execute(
                    """CREATE TABLE IF NOT EXISTS iceberg.observability.logs (
                        log_timestamp TIMESTAMP(3), log_level VARCHAR, logger VARCHAR, request_id VARCHAR,
                        realm_id VARCHAR, trace_id VARCHAR, span_id VARCHAR, thread VARCHAR, client_ip VARCHAR,
                        http_method VARCHAR, http_path VARCHAR, http_status INTEGER, response_size INTEGER)""",
                    "INSERT INTO iceberg.observability.logs VALUES\n"
                    + _values(
                        _logs,
                        lambda r: "(TIMESTAMP '{}', '{}', '{}', '{}', '{}', '{}', '{}', '{}', '{}', '{}', '{}', {}, {})".format(
                            _ts(r["ts"]), r["level"], r["logger"], _esc(r["request_id"]), _esc(r["realm_id"]),
                            _esc(r["trace_id"]), _esc(r["span_id"]), r["thread"], _esc(r["client_ip"]),
                            _esc(r["http_method"]), _esc(r["http_path"]), r["http_status"], r["size"],
                        ),
                    ),
                    f"COMMENT ON TABLE iceberg.observability.logs IS '{STANDIN_COMMENT}: derived from traces, not real container logs'",
                )
                _created.append("logs")

    obs_status = sql(
        "SELECT table_name, comment FROM system.metadata.table_comments "
        "WHERE catalog_name = 'iceberg' AND schema_name = 'observability' AND table_name IN ('traces', 'logs')"
    )
    obs_status["rows"] = [int(sql(f"SELECT count(*) AS c FROM iceberg.observability.{t}")["c"].iloc[0]) for t in obs_status["table_name"]]
    obs_status["created_now"] = obs_status["table_name"].isin(_created)
    return (obs_status,)


@app.cell(hide_code=True)
def _(STANDIN_COMMENT, mo, obs_status):
    _rows = {r.table_name: r for r in obs_status.itertuples()}
    _standin = [t for t, r in _rows.items() if str(r.comment or "").startswith(STANDIN_COMMENT)]
    _tiles = mo.hstack(
        [
            mo.stat(
                _rows[t].rows if t in _rows else "missing",
                label=f"observability.{t}",
                caption=("stand-in" if t in _standin else "from ingest script") + (" · created now" if t in _rows and _rows[t].created_now else ""),
                bordered=True,
            )
            for t in ("traces", "logs")
        ],
        widths="equal",
    )
    if _standin:
        _note = mo.callout(
            mo.md(
                f"""
                **Stand-in data:** {", ".join(f"`observability.{t}`" for t in _standin)} {"was" if len(_standin) == 1 else "were"} built by this notebook.
                `traces` holds real spans from the Jaeger API plus a few labelled sample spans (`request_id` starting with `sample-`);
                `logs` is derived from those spans rather than parsed from the container.

                For the real data, run the ingest script from the repo root. It drops and reloads both tables:

                ```bash
                bash exercises/ingest-observability.sh
                ```

                (It uses `docker logs polaris`; on Podman, alias `docker=podman` or have `podman-docker` installed.)
                """
            ),
            kind="warn",
        )
    else:
        _note = mo.callout("Both tables came from `exercises/ingest-observability.sh`: real Jaeger spans and parsed Polaris logs.", kind="success")
    mo.vstack([_tiles, _note])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## The core difference

    > **Logging** = *what happened* (discrete events, one service at a time)
    > **Tracing** = *how a request flowed* (end-to-end journey across services)
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.ui.tabs(
        {
            "Side by side": mo.md(
                """
                | Aspect | Logging | Tracing |
                |--------|---------|---------|
                | **Unit** | Log line (event) | Span (timed operation) |
                | **Scope** | Single service | Cross-service request |
                | **Format** | Text/JSON with level, timestamp, message | Span tree with parent-child relationships |
                | **Storage** | ELK, Splunk, CloudWatch Logs | Jaeger, Grafana Tempo, Zipkin |
                | **Cardinality** | Every event | Sampled (typically 1-10% in production) |
                """
            ),
            "This stack": mo.mermaid(
                """
                flowchart LR
                    T["Trino / PyIceberg"] -->|REST| P["Polaris"]
                    P -->|stdout| L["Container logs"]
                    P -->|OTLP spans| J["Jaeger"]
                    L -->|ingest-observability.sh| OL[("iceberg.observability.logs")]
                    J -->|ingest-observability.sh| OT[("iceberg.observability.traces")]
                    OL --- Q["Trino SQL<br/>(this notebook)"]
                    OT --- Q
                """
            ),
        }
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Part 1 — Logging analysis

    Logs answer **"What happened?"** We query `iceberg.observability.logs`, parsed from
    `docker logs polaris` / `podman logs polaris`, for real-world logging use cases.

    ### Log level distribution
    """)
    return


@app.cell
def _(sql):
    df_log_levels = sql(
        "SELECT log_level, COUNT(*) AS cnt "
        "FROM iceberg.observability.logs "
        "GROUP BY log_level ORDER BY cnt DESC"
    )
    return (df_log_levels,)


@app.cell(hide_code=True)
def _(df_log_levels, mo):
    mo.hstack(
        [mo.stat(int(r.cnt), label=r.log_level, bordered=True) for r in df_log_levels.itertuples()],
        widths="equal",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### HTTP traffic from logs

    The access-log lines carry method, path and status. Which paths does Trino hit most?
    """)
    return


@app.cell
def _(sql):
    df_log_traffic = sql(
        "SELECT http_method, http_path, http_status, COUNT(*) AS cnt "
        "FROM iceberg.observability.logs "
        "WHERE http_status > 0 "
        "GROUP BY 1, 2, 3 ORDER BY cnt DESC LIMIT 15"
    )
    return (df_log_traffic,)


@app.cell(hide_code=True)
def _(df_log_traffic, show):
    show(df_log_traffic, page_size=15)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Use case: audit & compliance

    *"Who accessed the India or Germany sales data?"*

    In regulated industries (HIPAA, SOX, FedRAMP) you must prove who accessed what and when.
    Logs are the primary audit trail.
    """)
    return


@app.cell
def _(sql):
    df_audit = sql(
        "SELECT log_timestamp, request_id, realm_id, http_method, http_path, http_status "
        "FROM iceberg.observability.logs "
        "WHERE http_path LIKE '%ap_india%' OR http_path LIKE '%eu_germany%' "
        "ORDER BY log_timestamp"
    )
    return (df_audit,)


@app.cell(hide_code=True)
def _(df_audit, mo, show):
    mo.vstack(
        [
            mo.callout(
                mo.md(f"**{len(df_audit)} log entries** touched `ap_india` or `eu_germany`. Each one names the realm and request id."),
                kind="info" if len(df_audit) else "neutral",
            ),
            show(df_audit),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Use case: security alerting

    *"Are there failed authentication attempts or forbidden access?"*

    In production these feed a SIEM (Splunk, Elasticsearch) that detects brute-force attacks or
    unauthorized access patterns, e.g. *page security if there are more than 50 failed logins in a minute*.
    """)
    return


@app.cell
def _(sql):
    df_errors_log = sql(
        "SELECT http_status, http_path, COUNT(*) AS cnt "
        "FROM iceberg.observability.logs "
        "WHERE http_status >= 400 "
        "GROUP BY 1, 2 ORDER BY cnt DESC"
    )
    return (df_errors_log,)


@app.cell(hide_code=True)
def _(df_errors_log, mo, show):
    _by = lambda lo, hi: int(df_errors_log.loc[df_errors_log["http_status"].between(lo, hi), "cnt"].sum())
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(_by(401, 401), label="401 Unauthorized", caption="failed logins", bordered=True),
                    mo.stat(_by(403, 403), label="403 Forbidden", caption="missing grants", bordered=True),
                    mo.stat(_by(404, 404), label="404 Not Found", caption="usually harmless probes", bordered=True),
                    mo.stat(_by(500, 599), label="5xx", caption="server errors", bordered=True),
                ],
                widths="equal",
            ),
            show(df_errors_log),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Part 2 — Tracing analysis

    Traces answer **"How did a request flow?"** We query `iceberg.observability.traces`, flattened
    Jaeger spans, for latency diagnosis, SLA monitoring and error analysis.

    ### Trace overview: operations and latency stats
    """)
    return


@app.cell
def _(sql):
    df_trace_overview = sql(
        "SELECT operation_name, COUNT(*) AS cnt, "
        "ROUND(AVG(duration_us)) AS avg_us, "
        "MAX(duration_us) AS max_us, "
        "MIN(duration_us) AS min_us "
        "FROM iceberg.observability.traces "
        "GROUP BY 1 ORDER BY cnt DESC"
    )
    return (df_trace_overview,)


@app.cell(hide_code=True)
def _(df_trace_overview, show):
    show(df_trace_overview)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.vstack(
        [
            mo.md(
                """
                ### Use case: latency diagnosis

                *"Queries are slow. Where's the bottleneck?"*

                Without tracing you'd guess. With tracing you see exactly which operation takes the time:
                """
            ),
            mo.mermaid(
                """
                flowchart LR
                    T["Trino"] -->|"31 ms"| A["Polaris: OAuth token"]
                    T -->|"77 ms · slowest Polaris span"| M["Polaris: load table metadata"]
                    T -->|"400 ms · actual bottleneck"| S["S3: read Parquet"]
                    style S fill:#fdd,stroke:#c00
                """
            ),
        ]
    )
    return


@app.cell
def _(sql):
    df_slowest = sql(
        "SELECT operation_name, duration_us, url_path, http_status "
        "FROM iceberg.observability.traces "
        "ORDER BY duration_us DESC LIMIT 10"
    )
    return (df_slowest,)


@app.cell(hide_code=True)
def _(df_slowest, show):
    show(df_slowest)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Use case: SLA monitoring

    *"Are we meeting our latency targets?"*

    Your team promises "95% of requests under 100 ms". Percentiles tell you exactly where you stand
    per operation. A typical target table:

    | Operation | p50 | p95 | p99 |
    |-----------|-----|-----|-----|
    | `listTables` | 3ms | 12ms | 18ms |
    | `loadTable` | 45ms | 190ms | 340ms |
    | `oauth/tokens` | 4ms | 9ms | 31ms |

    Here are the real numbers from your stack:
    """)
    return


@app.cell
def _(sql):
    df_percentiles = sql(
        "SELECT operation_name, COUNT(*) AS cnt, "
        "CAST(ROUND(AVG(duration_us)) AS BIGINT) AS avg_us, "
        "CAST(approx_percentile(duration_us, 0.5) AS BIGINT) AS p50_us, "
        "CAST(approx_percentile(duration_us, 0.95) AS BIGINT) AS p95_us, "
        "CAST(approx_percentile(duration_us, 0.99) AS BIGINT) AS p99_us "
        "FROM iceberg.observability.traces "
        "GROUP BY 1 ORDER BY p95_us DESC"
    )
    return (df_percentiles,)


@app.cell(hide_code=True)
def _(mo):
    sla_ms = mo.ui.slider(5, 200, value=100, step=5, label="SLA target: p95 under (ms)", show_value=True)
    sla_ms
    return (sla_ms,)


@app.cell(hide_code=True)
def _(df_percentiles, mo, show, sla_ms):
    _df = df_percentiles.copy()
    _df["meets_sla"] = _df["p95_us"] <= sla_ms.value * 1000
    _miss = _df[~_df["meets_sla"]]
    mo.vstack(
        [
            mo.callout(
                mo.md(
                    f"**{len(_df) - len(_miss)} of {len(_df)} operations** meet a p95 target of {sla_ms.value} ms."
                    + (f" Breaching: {', '.join(f'`{o}`' for o in _miss['operation_name'].head(5))}" if len(_miss) else "")
                ),
                kind="success" if _miss.empty else "warn",
            ),
            show(_df),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Use case: error rate by endpoint

    *"Which endpoints are failing?"*

    404s on `/views/*` are normal: Trino checks whether a name is a view before falling back to a table.
    403s and 500s need investigation.
    """)
    return


@app.cell
def _(sql):
    df_errors_trace = sql(
        "SELECT url_path, http_status, COUNT(*) AS cnt "
        "FROM iceberg.observability.traces "
        "WHERE http_status >= 400 "
        "GROUP BY 1, 2 ORDER BY cnt DESC"
    )
    return (df_errors_trace,)


@app.cell(hide_code=True)
def _(df_errors_trace, show):
    show(df_errors_trace)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.vstack(
        [
            mo.md(
                """
                ---
                ## Part 3 — The power of correlation

                The real value is **linking logs and traces**. Polaris writes the same `trace_id`
                (and `request_id`) into both its log lines and its Jaeger spans.
                """
            ),
            mo.mermaid(
                """
                flowchart LR
                    S["Jaeger span<br/>GET /tables/products<br/>77 ms"] -->|"trace_id"| L["Polaris log<br/>INFO [req-42] Loaded table<br/>ap_india.products<br/>(3 snapshots, 12 files)"]
                """
            ),
            mo.md("Click a slow span in Jaeger → grep its trace id in the logs → see the full story."),
            mo.md("### Correlated view: traces + logs joined on `trace_id`"),
        ]
    )
    return


@app.cell
def _(sql):
    df_correlated = sql(
        "SELECT t.trace_id, t.operation_name, t.duration_us, "
        "l.log_timestamp, l.http_path, l.http_status "
        "FROM iceberg.observability.traces t "
        "JOIN iceberg.observability.logs l ON t.trace_id = l.trace_id "
        "ORDER BY t.duration_us DESC LIMIT 15"
    )
    return (df_correlated,)


@app.cell(hide_code=True)
def _(df_correlated, mo, show):
    mo.vstack(
        [
            show(df_correlated, page_size=15),
            mo.md("**Try it:** pick one of the slow traces to see every log line Polaris wrote for it."),
        ]
    )
    return


@app.cell(hide_code=True)
def _(df_correlated, mo):
    _ids = list(dict.fromkeys(df_correlated["trace_id"]))
    trace_picker = mo.ui.dropdown(_ids, value=_ids[0] if _ids else None, label="trace_id")
    trace_picker
    return (trace_picker,)


@app.cell(hide_code=True)
def _(mo, show, sql, trace_picker):
    mo.stop(trace_picker.value is None, mo.callout("No traces join to log lines yet.", kind="neutral"))
    _tid = trace_picker.value.replace("'", "")
    _span = sql(f"SELECT operation_name, start_time, duration_us, http_status, request_id FROM iceberg.observability.traces WHERE trace_id = '{_tid}'")
    _logs = sql(
        "SELECT log_timestamp, log_level, logger, request_id, thread, http_method, http_path, http_status "
        f"FROM iceberg.observability.logs WHERE trace_id = '{_tid}' ORDER BY log_timestamp"
    )
    mo.hstack(
        [
            mo.vstack([mo.md("**The span (tracing)**"), show(_span)]),
            mo.vstack([mo.md(f"**Its log lines (logging)** · `grep {_tid[:12]}…`"), show(_logs)]),
        ],
        widths=[1, 2],
        align="start",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Part 4 — Live Jaeger exploration

    The Iceberg tables are a snapshot. The Jaeger HTTP API shows what's happening **right now**.

    ### Services sending traces
    """)
    return


@app.cell
def _(JAEGER, jaeger_ok, pd, requests):
    df_services = (
        pd.DataFrame({"service": requests.get(f"{JAEGER}/api/services", timeout=10).json().get("data") or []})
        if jaeger_ok
        else pd.DataFrame({"service": []})
    )
    return (df_services,)


@app.cell(hide_code=True)
def _(df_services, jaeger_ok, mo, show):
    mo.stop(not jaeger_ok, mo.callout("Jaeger isn't reachable, so the live steps are skipped.", kind="warn"))
    show(df_services)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Recent traces from Jaeger (live)
    """)
    return


@app.cell
def _(JAEGER, datetime, jaeger_ok, pd, requests, timezone):
    _traces = (
        requests.get(f"{JAEGER}/api/traces", params={"service": "polaris-server", "limit": 5}, timeout=10).json().get("data") or []
        if jaeger_ok
        else []
    )
    _rows = []
    for _t in _traces:
        for _s in _t.get("spans", []):
            _tags = {tag["key"]: tag["value"] for tag in _s.get("tags", [])}
            _start = datetime.fromtimestamp(_s["startTime"] / 1_000_000, tz=timezone.utc)
            _rows.append(
                {
                    "trace_id": _s["traceID"][:16] + "...",
                    "operation": _s["operationName"],
                    "duration_us": _s["duration"],
                    "status": _tags.get("http.response.status_code", ""),
                    "url_path": _tags.get("url.path", ""),
                    "time": _start.strftime("%H:%M:%S.%f")[:-3],
                }
            )
    df_live_traces = pd.DataFrame(_rows)
    return (df_live_traces,)


@app.cell(hide_code=True)
def _(df_live_traces, mo, show):
    show(df_live_traces) if not df_live_traces.empty else mo.callout("No recent traces from `polaris-server`.", kind="neutral")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## When to use which

    | Scenario | Use |
    |----------|-----|
    | What error happened? | **Logs** |
    | Who did what and when? | **Logs** |
    | Why is this request slow? | **Tracing** |
    | Which service in the chain failed? | **Tracing** |
    | What's the normal latency for this operation? | **Tracing** |
    | Is this new deployment slower? | **Tracing** |
    | What happened at 3am that caused the alert? | **Both**: the trace ID in the logs links them |

    ---
    ## Wrap-up
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.accordion(
        {
            "Summary": mo.md(
                """
                In this lab you used observability data from your Polaris stack to:

                1. **Logging**: query parsed log entries for audit trails, security alerting and traffic analysis
                2. **Tracing**: analyze Jaeger spans for latency diagnosis, SLA percentiles and error rates
                3. **Correlation**: join traces with logs on `trace_id` to get the full picture
                4. **Live data**: pull real-time traces from the Jaeger API
                """
            ),
            "Try it yourself": mo.md(
                """
                - Open the **Jaeger UI**: [http://localhost:16686](http://localhost:16686) → service `polaris-server` → *Find Traces*
                - Re-run ingestion for fresh data: `bash exercises/ingest-observability.sh`
                - Run a Trino query, then re-ingest and re-run this notebook to see it appear in the traces table
                """
            ),
            "Challenge exercises": mo.md(
                """
                1. Find the trace with the highest total duration across all its spans
                2. Which namespace has the most table metadata loads (`loadTable`)?
                3. Calculate the ratio of OAuth token requests to actual data operations
                4. Write a query that identifies "bursty" traffic patterns (many requests within 1 second)
                """
            ),
            "Next lab": mo.md("**Lab 9 — Table Maintenance**: compaction, snapshot expiry and orphan-file cleanup on a real small-files problem."),
        },
        multiple=True,
    )
    return


if __name__ == "__main__":
    app.run()
