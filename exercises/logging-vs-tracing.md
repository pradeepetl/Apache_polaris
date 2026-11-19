# Logging vs Tracing — Real-World Applications

**Companion to:** Lab 8 (Observability) | **Type:** Reference

---

## The Core Difference

```
Logging  = What happened (discrete events, one service at a time)
Tracing  = How a request flowed (end-to-end journey across services)
```

| Aspect | Logging | Tracing |
|--------|---------|---------|
| **Unit** | Log line (event) | Span (timed operation) |
| **Scope** | Single service | Cross-service request |
| **Format** | Text/JSON with level, timestamp, message | Span tree with parent-child relationships |
| **Storage** | ELK, Splunk, CloudWatch Logs | Jaeger, Grafana Tempo, Zipkin |
| **Cardinality** | Every event | Sampled (typically 1-10% in production) |

---

## Logging — Real-World Applications

### 1. Incident Response

A user reports "I can't query the India sales table." You check Trino logs:

```
ERROR Query failed: ICEBERG_CANNOT_OPEN_SPLIT:
  Failed to open Parquet file s3://warehouse/ap_india/sales/data-001.parquet
```

You now know the issue is a corrupt/missing Parquet file — not permissions, not network.

**In your stack:**
```bash
docker logs trino 2>&1 | grep "ERROR" | tail -20
docker logs polaris 2>&1 | grep "ap_india" | tail -20
```

### 2. Audit & Compliance

Financial regulations require proof of who accessed what data and when. Polaris logs every OAuth token request with the principal identity.

```bash
# Who accessed Germany sales data in March?
docker logs polaris 2>&1 | grep "eu_germany"
```

**Industries:** Healthcare (HIPAA), Finance (SOX), Government (FedRAMP)

### 3. Security Alerting

Set up a rule: if more than 50 failed logins in 1 minute, page the security team.

```bash
# Count 401 errors in last 100 log lines
docker logs polaris --tail 100 2>&1 | grep -c "401"
```

In production, logs feed into a SIEM (Splunk, Elasticsearch) that detects patterns humans would miss.

### 4. Debugging Application Logic

Your dlt-earthquakes pipeline ingested 0 rows. The log says:

```
WARN No records returned from USGS API for date range 2026-10-17 to 2026-10-18
```

Not a code bug — the API had no data. Without that log line, you'd spend hours debugging working code.

**In your stack:**
```bash
docker logs dlt-earthquakes 2>&1 | tail -30
```

---

## Tracing — Real-World Applications

### 1. Latency Diagnosis

A user says "queries are slow." You open Jaeger (http://localhost:16686) and find:

```
Trino ──► Polaris (OAuth)     31ms    ← token fetch is slow
       ──► Polaris (metadata)  77ms    ← loading table metadata from S3
       ──► S3 (read parquet)  400ms    ← actual bottleneck
```

Without tracing you'd guess. With tracing you see S3 read is 70% of total time — optimize there.

**In your stack:**
Open Jaeger → Service: `polaris-server` → Find Traces → Click any trace to see the span waterfall.

### 2. Cross-Service Failure Diagnosis

A query fails. The Trino log says "timeout." But timeout *where*?

```
Trino → Polaris → S3 (GetObject) ─── 30,000ms ─── TIMEOUT
```

Now you know: Polaris responded fine, but S3 (LocalStack) hung. Restart LocalStack, not Polaris.

**In your stack:**
```
Your services:  Browser → Trino → Polaris → LocalStack (S3)
                                ↓
                              Jaeger (collects spans)
```

### 3. Dependency Mapping

50 microservices. A new engineer asks "what happens when a user runs a query?"

Instead of reading docs, they open one trace in Jaeger:

```
Browser
  └─ Trino
       ├─ Polaris: POST /oauth/tokens          3ms
       ├─ Polaris: HEAD /namespaces/na_usa      5ms
       ├─ Polaris: GET /namespaces/na_usa/tables 7ms
       └─ S3: GET data-001.parquet            120ms
```

One picture, complete understanding.

### 4. SLA Monitoring

Your team promises "95% of queries complete under 2 seconds." Tracing backends aggregate:

| Operation | p50 | p95 | p99 |
|-----------|-----|-----|-----|
| `listTables` | 3ms | 12ms | 18ms |
| `loadTable` | 45ms | 190ms | 340ms |
| `oauth/tokens` | 4ms | 9ms | 31ms |

You know exactly which operation to optimize.

### 5. Canary Deployments

Deploy Polaris 1.9.0 to 5% of traffic. Traces show the new version's `loadTable` takes 200ms vs 77ms on 1.8.0. Catch the regression before rolling to 100%.

---

## Reading a Real Trace (From Your Stack)

This trace was exported from Jaeger on 2026-10-18. Here's how to read it:

### The Trace at a Glance

```
20 spans across ~15 seconds, all from Trino → Polaris
Single client: Trino (Apache-HttpClient/5.6.2, IP 10.89.1.147)
Single server: polaris-server v1.8.0
```

### Timeline

**Burst 1 (0–810ms) — Trino catalog discovery:**

```
 +0ms     GET /namespaces/na_canada/tables    2.6ms  200  ✓
 +3ms     GET /namespaces/na_canada/views     1.8ms  200  ✓
 +275ms   POST /oauth/tokens                  5.9ms  200  ✓ (re-auth)
 +283ms   HEAD /namespaces/na_usa             4.6ms  204  ✓ (exists?)
 +318ms   POST /oauth/tokens                  9.4ms  200  ✓ (re-auth)
 +330ms   GET /namespaces/na_usa/tables       7.2ms  200  ✓
 +339ms   GET /namespaces/na_usa/views        6.9ms  200  ✓
 +541ms   POST /oauth/tokens                  3.1ms  200  ✓ (re-auth)
 +545ms   HEAD /namespaces/north_america      2.3ms  204  ✓
 +570ms   POST /oauth/tokens                  4.9ms  200  ✓ (re-auth)
 +576ms   GET /namespaces/north_america/tables 1.9ms 200  ✓
 +579ms   GET /namespaces/north_america/views  1.8ms 200  ✓
 +800ms   POST /oauth/tokens                  3.7ms  200  ✓ (re-auth)
 +805ms   GET /namespaces/system/tables       3.1ms  404  ✗ (expected)
 +809ms   GET /namespaces/system/views        1.6ms  404  ✗ (expected)
```

This is what happens behind the scenes when you run `SHOW SCHEMAS` or load the Trino UI.

**15-second gap** — user thinking / typing a query

**Burst 2 (+15,000ms) — Query on ap_india.products:**

```
 +15.0s   POST /oauth/tokens                    31ms  200  ✓ (cold token)
 +15.0s   GET /ap_india/views/products           19ms  404  ✗ (not a view)
 +15.1s   POST /oauth/tokens                     6ms  200  ✓
 +15.1s   GET /ap_india/tables/products          77ms  200  ✓ (load metadata)
 +15.2s   POST /ap_india/tables/products/metrics  6ms  204  ✓ (report stats)
```

This is Trino executing `SELECT * FROM iceberg.ap_india.products`.

### Key Observations

| Observation | What it means |
|-------------|---------------|
| 7 OAuth token requests in 20 spans | Trino re-authenticates frequently; consider token caching |
| 404 on `/system/tables` | Harmless — Trino probes a non-existent namespace |
| 404 on `/views/products` | Normal — Trino checks view-first, then falls back to table |
| 77ms for `loadTable` | Slowest span — Polaris fetching Iceberg metadata from S3 |
| 31ms for OAuth (burst 2) | Token cache expired during the 15s gap; cold re-auth is slower |

---

## When to Use Which

| Scenario | Use |
|----------|-----|
| What error happened? | **Logs** |
| Who did what and when? | **Logs** |
| Why is this request slow? | **Tracing** |
| Which service in the chain failed? | **Tracing** |
| What's the normal latency for this operation? | **Tracing** |
| Is this new deployment slower? | **Tracing** |
| What happened at 3am that caused the alert? | **Both** — trace ID in logs links them |

---

## The Power of Correlation

The real value is linking logs and traces together. Polaris already includes `polaris.request.id` in both logs and spans.

```
  Jaeger (trace)                     Polaris logs
  ┌─────────────┐                   ┌──────────────────────────┐
  │ Span: GET   │   request.id      │ INFO [req-42] Loaded     │
  │ /tables/... │ ────────────────► │ table ap_india.products  │
  │ 77ms        │                   │ (3 snapshots, 12 files)  │
  └─────────────┘                   └──────────────────────────┘
```

Click a slow span in Jaeger → grep the request ID in logs → see the full story.

---

## Try It Yourself

1. **Open Jaeger:** http://localhost:16686
2. **Select service:** `polaris-server`
3. **Find traces** → Click any trace → Explore the span waterfall
4. **Copy a `polaris.request.id`** from a span's tags
5. **Grep it in logs:** `docker logs polaris 2>&1 | grep "<request-id>"`
6. **Export a trace:** Click the JSON button in Jaeger to download — that's how `traces-1792318756425.json` was created
