import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium", app_title="Lab 8 — Observability")


@app.cell(hide_code=True)
def _():
    import os
    import re
    import time

    import marimo as mo
    import pandas as pd
    import requests

    POLARIS = f"http://{os.environ.get('POLARIS_HOST', 'localhost')}:8181"
    POLARIS_MGMT = f"http://{os.environ.get('POLARIS_HOST', 'localhost')}:8182"
    JAEGER = f"http://{os.environ.get('JAEGER_HOST', 'localhost')}:16686"
    REALM = "POLARIS"
    return JAEGER, POLARIS, POLARIS_MGMT, REALM, mo, pd, re, requests, time


@app.cell(hide_code=True)
def _(JAEGER, POLARIS, POLARIS_MGMT, REALM, pd, re, requests, time):
    _LINE = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{(.*?)\})?\s+(\S+)")
    _LABEL = re.compile(r'(\w+)="((?:[^"\\]|\\.)*)"')

    def fetch_metrics():
        """Raw Prometheus text from the Polaris management port."""
        return requests.get(f"{POLARIS_MGMT}/q/metrics", timeout=10).text

    def parse_metrics(raw):
        """Parse Prometheus text into one row per sample: metric, labels..., value."""
        rows = []
        for line in raw.splitlines():
            if not line or line.startswith("#"):
                continue
            m = _LINE.match(line)
            if not m:
                continue
            name, labels, value = m.groups()
            try:
                value = float(value)
            except ValueError:
                continue
            row = {"metric": name, **dict(_LABEL.findall(labels or ""))}
            row["value"] = value
            rows.append(row)
        return pd.DataFrame(rows)

    def total_requests(raw):
        df = parse_metrics(raw)
        return float(df.loc[df["metric"] == "http_server_requests_seconds_count", "value"].sum())

    def get_token():
        resp = requests.post(
            f"{POLARIS}/api/catalog/v1/oauth/tokens",
            headers={"Polaris-Realm": REALM},
            data={
                "grant_type": "client_credentials",
                "client_id": "root",
                "client_secret": "s3cr3t",
                "scope": "PRINCIPAL_ROLE:ALL",
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    def find_spans(request_id, wait=8.0):
        """Look up Jaeger spans tagged with a Polaris request id (Jaeger ingests asynchronously)."""
        deadline = time.time() + wait
        while True:
            resp = requests.get(
                f"{JAEGER}/api/traces",
                params={
                    "service": "polaris-server",
                    "tags": '{"polaris.request.id":"%s"}' % request_id,
                    "lookback": "1h",
                    "limit": 20,
                },
                timeout=10,
            )
            rows = []
            for trace in resp.json().get("data") or []:
                for span in trace.get("spans", []):
                    tags = {t["key"]: t["value"] for t in span.get("tags", [])}
                    rows.append(
                        {
                            "request_id": tags.get("polaris.request.id", ""),
                            "trace_id": span["traceID"],
                            "operation": span["operationName"],
                            "duration_ms": round(span["duration"] / 1000, 2),
                            "status": tags.get("http.response.status_code", ""),
                            "realm": tags.get("polaris.realm.id", ""),
                            "url_path": tags.get("url.path", ""),
                        }
                    )
            if rows or time.time() > deadline:
                return pd.DataFrame(rows)
            time.sleep(1)

    return fetch_metrics, find_spans, get_token, parse_metrics, total_requests


@app.cell(hide_code=True)
def _(mo):
    mo.sidebar([mo.md("### Lab 8\n**Observability**"), mo.outline()])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.vstack(
        [
            mo.md(
                """
                # Lab 8 — Observability (Metrics, Logging & Tracing)

                **Level:** 4 (Intermediate) &nbsp;|&nbsp; **Time:** 25 minutes

                **Goal:** Explore Polaris's built-in observability stack. Read runtime metrics, inspect
                structured logs, and follow requests through traces, using nothing but HTTP calls and
                `podman logs` / `docker logs`.
                """
            ),
            mo.callout(
                mo.md(
                    """
                    **What you'll do**

                    1. Read and parse the Prometheus metrics Polaris exposes on port 8182
                    2. Break down HTTP request counts, JVM memory and CPU, then generate traffic and watch the counters move
                    3. Understand the Polaris log format and tag requests with your own request id
                    4. Find those same requests as spans in Jaeger and correlate a multi-step workflow
                    """
                ),
                kind="info",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(JAEGER, POLARIS_MGMT, mo, requests):
    def _get(url):
        try:
            return requests.get(url, timeout=5)
        except requests.RequestException:
            return None

    _health = _get(f"{POLARIS_MGMT}/q/health")
    _polaris_ok = _health is not None and _health.ok
    mo.stop(
        not _polaris_ok,
        mo.callout(
            mo.md(
                f"""
                **Polaris isn't reachable** at `{POLARIS_MGMT}/q/health`.

                Start the stack with `podman compose --profile marimo up -d`
                (or `docker compose --profile marimo up -d`), then re-run this cell.
                """
            ),
            kind="danger",
        ),
    )
    _svc = _get(f"{JAEGER}/api/services")
    jaeger_services = (_svc.json().get("data") or []) if (_svc is not None and _svc.ok) else None
    _checks = {c["name"]: c["status"] for c in _health.json().get("checks", [])}

    mo.hstack(
        [
            mo.stat(_health.json().get("status", "?"), label="Polaris health", caption="/q/health on :8182", bordered=True),
            mo.stat(len(_checks), label="Health checks", caption=", ".join(f"{k}: {v}" for k, v in _checks.items())[:60], bordered=True),
            mo.stat(
                "Up" if jaeger_services is not None else "Down",
                label="Jaeger",
                caption=f"{len(jaeger_services)} service(s) reporting" if jaeger_services is not None else "tracing steps will be skipped",
                bordered=True,
            ),
        ],
        widths="equal",
    )
    return (jaeger_services,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Concepts

    Polaris exposes three observability signals out of the box. Metrics and logs need no extra containers;
    this stack also runs **Jaeger** to collect traces.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.mermaid(
        """
        flowchart LR
            C["Clients<br/>Trino · PyIceberg · curl"] -->|REST :8181| P["Polaris"]
            P -->|"Micrometer<br/>:8182/q/metrics"| M["Metrics<br/>(Prometheus format)"]
            P -->|"Quarkus logging + MDC<br/>stdout"| L["Logs<br/>podman logs polaris"]
            P -->|"OpenTelemetry<br/>OTLP :4317"| J["Traces<br/>Jaeger :16686"]
        """
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    | Signal | What it tells you | How to access it |
    |--------|-------------------|------------------|
    | **Metrics** | Request counts, latencies, JVM health, error rates | `curl http://localhost:8182/q/metrics` |
    | **Logs** | Request-level detail with context (realm, requestId, traceId) | `podman logs polaris` / `docker logs polaris` |
    | **Tracing** | Span-level view of individual requests across components | OpenTelemetry → OTLP collector (Jaeger here) |
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Part 1 — Metrics

    ## Step 1 — Fetch the raw metrics

    Polaris publishes Prometheus-format metrics on its **management port (8182)**, the same text
    `curl -s http://localhost:8182/q/metrics` returns. It's a wall of text, so we'll break it down.
    """)
    return


@app.cell
def _(fetch_metrics, parse_metrics):
    metrics_raw = fetch_metrics()
    metrics_df = parse_metrics(metrics_raw)
    return metrics_df, metrics_raw


@app.cell(hide_code=True)
def _(metrics_df, metrics_raw, mo):
    _lines = metrics_raw.strip().split("\n")
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(len(_lines), label="Lines", caption="raw response", bordered=True),
                    mo.stat(len(metrics_df), label="Samples", caption="lines with a value", bordered=True),
                    mo.stat(metrics_df["metric"].nunique(), label="Series names", bordered=True),
                ],
                widths="equal",
            ),
            mo.md("**First 20 lines** of the raw response:"),
            mo.plain_text("\n".join(_lines[:20])),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Try it: grep the metrics

    The labs usually pipe the endpoint into `grep`. Type a pattern to do the same here
    (try `http_server`, `jvm_gc`, `system_cpu` or `status="4`).
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    metric_grep = mo.ui.text(value="http_server_requests_seconds_count", label="grep", full_width=True)
    metric_grep
    return (metric_grep,)


@app.cell(hide_code=True)
def _(metric_grep, metrics_raw, mo):
    _hits = [l for l in metrics_raw.split("\n") if metric_grep.value and metric_grep.value in l]
    mo.vstack(
        [
            mo.md(f"`curl -s http://localhost:8182/q/metrics | grep '{metric_grep.value}'` → **{len(_hits)} lines**"),
            mo.plain_text("\n".join(_hits[:40]) + ("\n…" if len(_hits) > 40 else "")),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Step 2 — Count the metric types

    Each metric family is announced by a `# TYPE <name> <kind>` line
    (`curl -s http://localhost:8182/q/metrics | grep -c "^# TYPE"`).

    **Question:** How many distinct metric types does Polaris expose?
    """)
    return


@app.cell
def _(metrics_raw, pd):
    type_lines = [l for l in metrics_raw.split("\n") if l.startswith("# TYPE")]
    metric_types = pd.DataFrame([l.split()[2:4] for l in type_lines], columns=["metric", "kind"])
    return metric_types, type_lines


@app.cell(hide_code=True)
def _(metric_types, mo, type_lines):
    _kinds = metric_types["kind"].value_counts()
    mo.vstack(
        [
            mo.hstack(
                [mo.stat(len(type_lines), label="Distinct metric types", bordered=True)]
                + [mo.stat(int(n), label=k, bordered=True) for k, n in _kinds.items()],
                widths="equal",
            ),
            mo.ui.table(metric_types, selection=None, show_column_summaries=False, page_size=10),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Step 3 — HTTP request metrics

    The key HTTP server metrics:

    - `http_server_requests_seconds_count` — total request count
    - `http_server_requests_seconds_sum` — total processing time
    - `http_server_requests_seconds_max` — max latency

    Each sample is tagged with `method`, `uri`, `status` and `outcome` labels, so one metric name
    becomes one row per endpoint and status code.
    """)
    return


@app.cell
def _(metrics_df):
    _http = metrics_df[metrics_df["metric"].str.startswith("http_server_requests_seconds")]
    http_requests = (
        _http.pivot_table(index=["method", "uri", "status", "outcome"], columns="metric", values="value", aggfunc="sum")
        .rename(
            columns={
                "http_server_requests_seconds_count": "count",
                "http_server_requests_seconds_sum": "total_s",
                "http_server_requests_seconds_max": "max_s",
            }
        )
        .reset_index()
        .sort_values("count", ascending=False)
    )
    http_requests["avg_ms"] = (1000 * http_requests["total_s"] / http_requests["count"]).round(2)
    http_requests = http_requests[["method", "uri", "status", "outcome", "count", "avg_ms", "max_s"]]
    return (http_requests,)


@app.cell(hide_code=True)
def _(http_requests, mo):
    _errors = http_requests[http_requests["status"].str.match(r"[45]")]
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(len(http_requests), label="Endpoint × status series", bordered=True),
                    mo.stat(int(http_requests["count"].sum()), label="Requests served", bordered=True),
                    mo.stat(int(_errors["count"].sum()), label="4xx / 5xx responses", bordered=True),
                ],
                widths="equal",
            ),
            mo.ui.table(http_requests, selection=None, show_column_summaries=False, page_size=15),
            mo.callout(
                mo.md(
                    "**Question:** Which API endpoints have received the most requests? Which HTTP status codes do you see? "
                    "What does the top of this table tell you about how Trino and Polaris interact?"
                ),
                kind="neutral",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Step 4 — JVM and system metrics

    JVM memory (`jvm_memory_used_bytes`), garbage collection (`jvm_gc_*`) and CPU (`system_cpu_*`).
    These are what you'd scrape with Prometheus and chart in Grafana in a production setup.
    """)
    return


@app.cell
def _(metrics_df):
    jvm_memory = metrics_df[metrics_df["metric"] == "jvm_memory_used_bytes"][["area", "id", "value"]].copy()
    jvm_memory["used_mb"] = (jvm_memory.pop("value") / 1024 / 1024).round(1)
    jvm_memory = jvm_memory.sort_values("used_mb", ascending=False)

    jvm_gc = metrics_df[metrics_df["metric"].str.startswith("jvm_gc")][["metric", "value"]]
    system_cpu = metrics_df[metrics_df["metric"].str.contains("cpu")][["metric", "value"]]
    return jvm_gc, jvm_memory, system_cpu


@app.cell(hide_code=True)
def _(jvm_gc, jvm_memory, mo, system_cpu):
    def _cpu(name):
        _v = system_cpu.loc[system_cpu["metric"] == name, "value"]
        return float(_v.iloc[0]) if len(_v) else 0.0

    _heap = jvm_memory.loc[jvm_memory["area"] == "heap", "used_mb"].sum()
    _nonheap = jvm_memory.loc[jvm_memory["area"] == "nonheap", "used_mb"].sum()
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(f"{_heap:.0f} MB", label="Heap used", bordered=True),
                    mo.stat(f"{_nonheap:.0f} MB", label="Non-heap used", bordered=True),
                    mo.stat(f"{_cpu('system_cpu_usage') * 100:.1f}%", label="System CPU", bordered=True),
                    mo.stat(f"{_cpu('system_cpu_count'):.0f}", label="CPU count", bordered=True),
                ],
                widths="equal",
            ),
            mo.ui.tabs(
                {
                    "JVM memory": mo.ui.table(jvm_memory, selection=None, show_column_summaries=False),
                    "JVM GC": mo.ui.table(jvm_gc, selection=None, show_column_summaries=False),
                    "CPU": mo.ui.table(system_cpu, selection=None, show_column_summaries=False),
                }
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Step 5 — Generate traffic and watch the metrics change

    Read the total `http_server_requests_seconds_count`, send 10 `GET /api/management/v1/catalogs`
    calls, then read it again. The count should rise by at least 10 (plus the token request).
    """)
    return


@app.cell
def _(POLARIS, REALM, fetch_metrics, get_token, requests, time, total_requests):
    count_before = total_requests(fetch_metrics())

    auth = {"Authorization": f"Bearer {get_token()}", "Polaris-Realm": REALM}
    for _ in range(10):
        requests.get(f"{POLARIS}/api/management/v1/catalogs", headers=auth, timeout=10)

    time.sleep(1)
    count_after = total_requests(fetch_metrics())
    return auth, count_after, count_before


@app.cell(hide_code=True)
def _(count_after, count_before, mo):
    _delta = count_after - count_before
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(f"{count_before:.0f}", label="Request count before", bordered=True),
                    mo.stat(f"{count_after:.0f}", label="Request count after", bordered=True),
                    mo.stat(f"+{_delta:.0f}", label="Difference", caption="10 catalog calls + 1 token", bordered=True),
                ],
                widths="equal",
            ),
            mo.callout(
                mo.md(f"Sent 10 requests; the counters rose by **{_delta:.0f}**. Other clients (Trino, other labs) may add a few more."),
                kind="success" if _delta >= 10 else "warn",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Part 2 — Logging

    ## Step 6 — View the Polaris logs

    Polaris logs to stdout with structured context: realm id, request id and trace id.
    Run this in your **terminal** (the marimo container has no access to the container runtime):

    ```bash
    podman logs polaris --tail 50      # or: docker logs polaris --tail 50
    ```

    Each line looks like this (the `io.qua.htt.access-log` lines are the HTTP access log):

    ```
    2026-11-05 06:56:21,471 INFO  [io.qua.htt.access-log] [my-debug-request-001,POLARIS] [b69a9039138c8d10b22f584473f39e37,,9136992b416a319d,true] (executor-thread-3) 192.168.127.1 - root [05/Nov/2026:06:56:21 +0000] "GET /api/management/v1/catalogs HTTP/1.1" 200 600
    ```

    ## Step 7 — Understand the log format

    ```
    %d{yyyy-MM-dd HH:mm:ss,SSS} %-5p [%c{3.}] [%X{requestId},%X{realmId}] [%X{traceId},%X{parentId},%X{spanId},%X{sampled}] (%t) %s%e%n
    ```

    | Field | Meaning |
    |-------|---------|
    | `%d` | Timestamp |
    | `%-5p` | Log level (INFO, DEBUG, WARN, ERROR) |
    | `%c{3.}` | Logger name (shortened) |
    | `%X{requestId}` | Request ID (MDC), taken from the client's request-id header or generated |
    | `%X{realmId}` | Which realm the request targeted |
    | `%X{traceId}` | OpenTelemetry trace ID |
    | `%X{spanId}` | OpenTelemetry span ID |
    | `(%t)` | Thread name |
    | `%s%e` | Log message + exception |

    ## Step 8 — Filter logs by realm

    This stack has two realms (`POLARIS` and `TRAINING`, see Lab 7). Filter by realm:

    ```bash
    podman logs polaris 2>&1 | grep "POLARIS"
    podman logs polaris 2>&1 | grep "TRAINING"
    ```

    This is how you'd debug issues for a specific tenant in a multi-realm deployment.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Step 9 — Tag a request with your own request id

    Send a request with a custom request id, then find it in the logs. **Key insight:** in production,
    attach a unique request id to every API call. When something fails, you can find the exact request in
    Polaris's logs without searching through thousands of entries.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.callout(
        mo.md(
            "**Header name:** older Polaris docs (and earlier versions of this lab) use `Polaris-Request-Id`. "
            "Polaris 1.8, which this stack runs, reads **`X-Request-ID`** instead (configurable with "
            "`polaris.log.request-id-header-name`) and echoes it back in the response. A `Polaris-Request-Id` header "
            "is silently ignored, and Polaris generates its own id. The cells below send both, so you can see which one Polaris uses."
        ),
        kind="warn",
    )
    return


@app.cell
def _(POLARIS, auth, requests):
    DEBUG_REQUEST_ID = "marimo-debug-001"
    debug_resp = requests.get(
        f"{POLARIS}/api/management/v1/catalogs",
        headers={**auth, "X-Request-ID": DEBUG_REQUEST_ID, "Polaris-Request-Id": DEBUG_REQUEST_ID},
        timeout=10,
    )
    return DEBUG_REQUEST_ID, debug_resp


@app.cell(hide_code=True)
def _(DEBUG_REQUEST_ID, debug_resp, mo):
    _echo = debug_resp.headers.get("X-Request-ID", "(none)")
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(debug_resp.status_code, label="HTTP status", bordered=True),
                    mo.stat(_echo, label="X-Request-ID echoed", caption="response header", bordered=True),
                ],
                widths="equal",
            ),
            mo.callout(
                mo.md(
                    f"""
                    Request sent with request id **`{DEBUG_REQUEST_ID}`**. Now find it in the logs:

                    ```bash
                    podman logs polaris 2>&1 | grep "{DEBUG_REQUEST_ID}"     # or docker logs …
                    ```
                    """
                ),
                kind="success" if _echo == DEBUG_REQUEST_ID else "warn",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Step 10 — Watch logs in real time

    Open a second terminal and stream the logs:

    ```bash
    podman logs -f polaris      # or: docker logs -f polaris
    ```

    Then re-run any cell in this notebook and watch the requests appear. This is a good way to show
    an audience what Polaris does behind the scenes during a demo.

    ---
    ## Part 3 — Tracing

    ## Step 11 — Check the tracing status

    Polaris ships with OpenTelemetry **disabled** by default (`quarkus.otel.sdk.disabled: "true"`).
    This lab stack turns it on in `docker-compose.yml` and sends spans to the Jaeger container:

    ```yaml
    polaris:
      environment:
        QUARKUS_OTEL_SDK_DISABLED: "false"
        QUARKUS_OTEL_EXPORTER_OTLP_TRACES_ENDPOINT: "http://jaeger:4317"
    jaeger:
      image: jaegertracing/all-in-one:latest   # UI on :16686, OTLP gRPC on :4317
    ```

    Check it with `grep -i otel docker-compose.yml`. To enable tracing in your own deployment:

    1. Set `quarkus.otel.sdk.disabled=false` in the Polaris environment
    2. Point `quarkus.otel.exporter.otlp.traces.endpoint` at an OTLP collector
    3. Run a Jaeger or Grafana Tempo container to receive the spans
    """)
    return


@app.cell(hide_code=True)
def _(JAEGER, jaeger_services, mo):
    mo.callout(
        mo.md(
            f"Tracing is **enabled**. Jaeger at `{JAEGER}` is receiving spans from: "
            + ", ".join(f"`{s}`" for s in jaeger_services)
            + f". Open the UI at [http://localhost:16686](http://localhost:16686)."
        )
        if jaeger_services
        else mo.md(
            "Jaeger isn't reachable or has no services yet, so Polaris isn't exporting spans. "
            "Check `podman ps` for the `jaeger` container."
        ),
        kind="success" if jaeger_services else "warn",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Step 12 — Trace metadata

    Each Polaris request becomes a **span** with these attributes:

    | Attribute | Value |
    |-----------|-------|
    | `service.name` | `polaris-server` (Jaeger service name) |
    | `service.version` | Current Polaris release |
    | `polaris.realm.id` | The realm ID |
    | `polaris.request.id` | The request id, the same value that appears in the logs |
    | `http.request.method`, `url.path`, `http.response.status_code` | The HTTP call itself |

    The request id is the bridge between the two signals. Here is the span for the request from Step 9:
    """)
    return


@app.cell
def _(DEBUG_REQUEST_ID, debug_resp, find_spans, jaeger_services):
    debug_spans = find_spans(DEBUG_REQUEST_ID) if jaeger_services is not None and debug_resp.ok else None
    return (debug_spans,)


@app.cell(hide_code=True)
def _(DEBUG_REQUEST_ID, debug_spans, mo):
    if debug_spans is None:
        _out = mo.callout("Jaeger is not reachable, so there are no spans to show.", kind="warn")
    elif debug_spans.empty:
        _out = mo.callout(mo.md(f"No span tagged `{DEBUG_REQUEST_ID}` yet. Jaeger may still be ingesting; re-run this cell."), kind="warn")
    else:
        _out = mo.vstack(
            [
                mo.callout(
                    mo.md(
                        f"Found **{len(debug_spans)} span(s)** tagged `polaris.request.id = {DEBUG_REQUEST_ID}` "
                        "(one per run of Step 9 in the last hour). Copy a `trace_id` and search for it in "
                        "the logs or the Jaeger UI."
                    ),
                    kind="success",
                ),
                mo.ui.table(debug_spans, selection=None, show_column_summaries=False),
            ]
        )
    _out
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Step 13 — Correlate a multi-step workflow

    Even without a tracing backend, a shared request-id prefix lets you group related calls.
    Make three related API calls tagged `workflow-99-step-1` … `step-3`:
    """)
    return


@app.cell
def _(POLARIS, auth, pd, requests):
    workflow_steps = [
        ("workflow-99-step-1", f"{POLARIS}/api/management/v1/catalogs"),
        ("workflow-99-step-2", f"{POLARIS}/api/management/v1/principal-roles"),
        ("workflow-99-step-3", f"{POLARIS}/api/catalog/v1/polaris_warehouse/namespaces"),
    ]
    _rows = []
    for _req_id, _url in workflow_steps:
        _r = requests.get(_url, headers={**auth, "X-Request-ID": _req_id, "Polaris-Request-Id": _req_id}, timeout=10)
        _rows.append({"request_id": _req_id, "endpoint": _url.removeprefix(POLARIS), "status": _r.status_code})
    workflow_results = pd.DataFrame(_rows)
    return workflow_results, workflow_steps


@app.cell(hide_code=True)
def _(find_spans, jaeger_services, mo, pd, workflow_results, workflow_steps):
    _spans = (
        pd.concat([find_spans(_rid) for _rid, _ in workflow_steps], ignore_index=True)
        if jaeger_services is not None
        else pd.DataFrame()
    )
    if not _spans.empty:
        _spans = _spans.drop_duplicates("request_id", keep="first")
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.vstack([mo.md("**Requests sent**"), mo.ui.table(workflow_results, selection=None, show_column_summaries=False)]),
                    mo.vstack(
                        [
                            mo.md("**Matching spans in Jaeger** (latest per step)"),
                            mo.ui.table(_spans[["request_id", "operation", "duration_ms", "status"]], selection=None, show_column_summaries=False)
                            if not _spans.empty
                            else mo.md("_No spans found yet; re-run this cell._"),
                        ]
                    ),
                ],
                widths="equal",
                align="start",
            ),
            mo.md(
                """
                Trace the whole workflow in the logs:

                ```bash
                podman logs polaris 2>&1 | grep "workflow-99"      # or docker logs …
                ```

                You'll see all three requests grouped together, each with a different step. This is a
                lightweight alternative to full distributed tracing, and with OpenTelemetry enabled you also get
                each step's timing in Jaeger.
                """
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
            "Production observability checklist": mo.md(
                """
                | Check | How |
                |-------|-----|
                | Metrics exposed? | `curl http://localhost:8182/q/metrics` returns Prometheus data |
                | Request counts increasing? | Compare `http_server_requests_seconds_count` before and after traffic |
                | Logs contain realm context? | `podman logs polaris \\| grep "POLARIS"` shows realm-scoped entries |
                | Request IDs flow through? | Send an `X-Request-ID` header and find it in the logs and in Jaeger |
                | Tracing enabled? | `quarkus.otel.sdk.disabled=false` + collector configured |
                """
            ),
            "Key takeaways": mo.md(
                """
                1. Metrics, logs and traces need no code changes in Polaris, only configuration
                2. `:8182/q/metrics` speaks Prometheus; labels (`uri`, `status`, `outcome`) make per-endpoint analysis easy
                3. Every log line carries the request id, realm and trace id via MDC
                4. A client-supplied request id appears in the logs **and** as the `polaris.request.id` span tag, linking the two
                5. Tracing shows *where time goes*; logs show *what happened*. Lab 9 (Logging vs Tracing) goes deeper.
                """
            ),
            "Exercises": mo.md(
                """
                1. **Find the busiest endpoint** — Parse the metrics and sort by request count (or use `grep` and `sort`
                   on the raw output). Which API path gets the most traffic? What does this tell you about how Trino and Polaris interact?
                2. **Monitor a query** — Stream `podman logs -f polaris` in a terminal, then run a Trino query
                   (`SELECT * FROM iceberg.shop.orders LIMIT 5`, as in Lab 1). How many Polaris API calls does a single Trino query generate?
                3. **Error rate analysis** — Filter metrics for HTTP 4xx and 5xx (`curl -s http://localhost:8182/q/metrics | grep 'status="[45]'`,
                   or type `status="4` in the grep box above). Are there any errors? If so, which endpoints are failing?
                4. **Custom request tracking** — Make 5 API calls with sequential request ids (`audit-001` through `audit-005`).
                   Find all 5 in the logs and calculate the time between the first and last request.
                5. **Challenge:** Write a function that fetches metrics, parses the Prometheus format, and returns a dictionary of
                   `{metric_name: value}` for all HTTP request counts. Then capture metrics snapshots over time without a Prometheus
                   server: write a `curl` + `cron` (or loop) one-liner that appends timestamped metrics to a file every 30 seconds.
                """
            ),
            "Next lab": mo.md(
                "**Lab 9 — Logging vs Tracing** loads these logs and Jaeger spans into Iceberg tables and analyzes them with SQL. "
                "**Lab 9 — Table Maintenance** covers compaction, snapshot expiry and orphan-file cleanup."
            ),
        },
        multiple=True,
    )
    return


if __name__ == "__main__":
    app.run()
