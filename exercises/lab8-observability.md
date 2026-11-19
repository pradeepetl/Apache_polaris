# Lab 8 — Observability (Metrics, Logging & Tracing)

**Level:** 4 (Intermediate) | **Time:** 25 minutes

**Goal:** Explore Polaris's built-in observability stack. Read runtime metrics, inspect structured logs, and enable request tracing — all without adding extra infrastructure.

---

## Concepts

Polaris exposes three observability signals out of the box:

```
┌──────────────────────────────────────────────────────────┐
│                  Polaris Observability                    │
│                                                          │
│  ┌────────────┐   ┌────────────┐   ┌──────────────┐     │
│  │  Metrics   │   │  Logging   │   │   Tracing    │     │
│  │            │   │            │   │              │     │
│  │ Micrometer │   │  Quarkus   │   │ OpenTelemetry│     │
│  │ Prometheus │   │  + MDC     │   │  OTLP spans  │     │
│  │            │   │            │   │              │     │
│  │ :8182      │   │ stdout +   │   │ Disabled by  │     │
│  │ /q/metrics │   │ file       │   │ default      │     │
│  └────────────┘   └────────────┘   └──────────────┘     │
│                                                          │
│  No extra containers needed. curl + docker logs is       │
│  enough to explore all three.                            │
└──────────────────────────────────────────────────────────┘
```

| Signal | What it tells you | How to access it |
|--------|-------------------|------------------|
| **Metrics** | Request counts, latencies, JVM health, error rates | `curl http://localhost:8182/q/metrics` |
| **Logs** | Request-level detail with context (realm, requestId, traceId) | `docker logs polaris` |
| **Tracing** | Span-level view of individual requests across components | Enable via env var, send to OTLP collector |

---

## Part 1: Metrics

### Step 1: Access the Metrics Endpoint

Polaris publishes Prometheus-format metrics on its management port (8182):

```bash
curl -s http://localhost:8182/q/metrics
```

This returns a wall of text. Let's break it down.

### Step 2: Count the Metrics

```bash
curl -s http://localhost:8182/q/metrics | grep -c "^# TYPE"
```

**Question:** How many distinct metric types does Polaris expose?

### Step 3: Explore HTTP Request Metrics

Filter for HTTP server metrics:

```bash
curl -s http://localhost:8182/q/metrics | grep "http_server"
```

Look for these key metrics:
- `http_server_requests_seconds_count` — total request count
- `http_server_requests_seconds_sum` — total processing time
- `http_server_requests_seconds_max` — max latency

Each metric is tagged with labels like `method`, `uri`, `status`, and `outcome`:

```bash
curl -s http://localhost:8182/q/metrics | grep "http_server_requests_seconds_count"
```

**Question:** Which API endpoints have received the most requests? Which HTTP status codes do you see?

### Step 4: Check JVM and System Metrics

**JVM memory usage:**

```bash
curl -s http://localhost:8182/q/metrics | grep "jvm_memory_used_bytes"
```

**JVM garbage collection:**

```bash
curl -s http://localhost:8182/q/metrics | grep "jvm_gc"
```

**System CPU:**

```bash
curl -s http://localhost:8182/q/metrics | grep "system_cpu"
```

These metrics are what you'd scrape with Prometheus and visualize in Grafana in a production setup.

### Step 5: Generate Traffic and Watch Metrics Change

First, note the current request count:

```bash
curl -s http://localhost:8182/q/metrics | grep "http_server_requests_seconds_count"
```

Now generate some API traffic:

```bash
TOKEN=$(curl -s -X POST http://localhost:8181/api/catalog/v1/oauth/tokens \
  -d 'grant_type=client_credentials&client_id=root&client_secret=s3cr3t&scope=PRINCIPAL_ROLE:ALL' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

for i in $(seq 1 10); do
  curl -s http://localhost:8181/api/management/v1/catalogs \
    -H "Authorization: Bearer $TOKEN" \
    -H "Polaris-Realm: POLARIS" > /dev/null
done
echo "Sent 10 requests"
```

Check the metrics again:

```bash
curl -s http://localhost:8182/q/metrics | grep "http_server_requests_seconds_count"
```

The counts should have increased by at least 10.

---

## Part 2: Logging

### Step 6: View Polaris Logs

```bash
docker logs polaris --tail 50
```

Each log line contains structured context. Look for patterns like:

```
2026-09-25 10:30:15,123 INFO  [org.apa.pol] [requestId,POLARIS] [...] (executor-thread-1) ...
```

### Step 7: Understand the Log Format

Polaris uses this default log pattern:

```
%d{yyyy-MM-dd HH:mm:ss,SSS} %-5p [%c{3.}] [%X{requestId},%X{realmId}] [%X{traceId},%X{parentId},%X{spanId},%X{sampled}] (%t) %s%e%n
```

| Field | Meaning |
|-------|---------|
| `%d` | Timestamp |
| `%-5p` | Log level (INFO, DEBUG, WARN, ERROR) |
| `%c{3.}` | Logger name (shortened) |
| `%X{requestId}` | Client-provided request ID (MDC) |
| `%X{realmId}` | Which realm the request targeted |
| `%X{traceId}` | OpenTelemetry trace ID |
| `%X{spanId}` | OpenTelemetry span ID |
| `(%t)` | Thread name |
| `%s%e` | Log message + exception |

### Step 8: Filter Logs by Realm

If you completed Lab 7 (Realms), you have two realms. Filter logs by realm:

```bash
docker logs polaris 2>&1 | grep "POLARIS"
docker logs polaris 2>&1 | grep "TRAINING"
```

This is how you'd debug issues for a specific tenant in a multi-realm deployment.

### Step 9: Use the Polaris-Request-Id Header for Tracking

Make a request with a custom request ID:

```bash
curl -s http://localhost:8181/api/management/v1/catalogs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Polaris-Realm: POLARIS" \
  -H "Polaris-Request-Id: my-debug-request-001" > /dev/null
```

Now find it in the logs:

```bash
docker logs polaris 2>&1 | grep "my-debug-request-001"
```

**Key insight:** In production, attach a unique request ID to every API call. When something fails, you can trace the exact request through Polaris's logs without searching through thousands of entries.

### Step 10: Watch Logs in Real-Time

Open a second terminal and stream logs:

```bash
docker logs -f polaris
```

In your first terminal, make API calls and watch them appear in real-time. This is useful during demos to show the audience what Polaris does behind the scenes.

---

## Part 3: Tracing

### Step 11: Check Current Tracing Status

Your stack has tracing disabled by default:

```bash
grep "otel" docker-compose.yml
```

You should see:

```yaml
quarkus.otel.sdk.disabled: "true"
```

This means Polaris is not emitting OpenTelemetry spans.

### Step 12: Understand Trace Metadata

Even without a collector, Polaris attaches trace context to every request. When tracing is enabled, each request generates a **span** with:

| Attribute | Value |
|-----------|-------|
| `service.name` | `Apache Polaris Server (incubating)` |
| `service.version` | Current Polaris release |
| `polaris.realm` | The realm ID |
| `polaris.request.id` | Client-provided request ID |

### Step 13: Enable Tracing (Conceptual)

To enable tracing in a real deployment, you would:

1. Set `quarkus.otel.sdk.disabled=false` in the Polaris environment
2. Point to an OTLP collector:

```yaml
environment:
  quarkus.otel.sdk.disabled: "false"
  quarkus.otel.exporter.otlp.traces.endpoint: "http://jaeger:4317"
```

3. Add a Jaeger or Grafana Tempo container to receive spans

**Note:** We're not adding a collector to avoid infrastructure overhead. The key takeaway is understanding what data Polaris emits and how it connects to your observability stack.

### Step 14: Simulate Trace Correlation

Even without full tracing, you can simulate request correlation using the `Polaris-Request-Id` header.

Make three related API calls with a shared prefix:

```bash
curl -s http://localhost:8181/api/management/v1/catalogs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Polaris-Realm: POLARIS" \
  -H "Polaris-Request-Id: workflow-42-step-1" > /dev/null

curl -s http://localhost:8181/api/management/v1/principal-roles \
  -H "Authorization: Bearer $TOKEN" \
  -H "Polaris-Realm: POLARIS" \
  -H "Polaris-Request-Id: workflow-42-step-2" > /dev/null

curl -s http://localhost:8181/api/catalog/v1/polaris_warehouse/namespaces \
  -H "Authorization: Bearer $TOKEN" \
  -H "Polaris-Realm: POLARIS" \
  -H "Polaris-Request-Id: workflow-42-step-3" > /dev/null
```

Now trace the entire workflow in the logs:

```bash
docker logs polaris 2>&1 | grep "workflow-42"
```

You should see all three requests grouped together, each with a different step. This is a lightweight alternative to full distributed tracing.

---

## Summary: Production Observability Checklist

| Check | How |
|-------|-----|
| Metrics exposed? | `curl http://polaris:8182/q/metrics` returns Prometheus data |
| Request counts increasing? | Compare `http_server_requests_seconds_count` before and after traffic |
| Logs contain realm context? | `docker logs polaris \| grep "POLARIS"` shows realm-scoped entries |
| Request IDs flow through? | Send `Polaris-Request-Id` header, find it in logs |
| Tracing enabled? | `quarkus.otel.sdk.disabled=false` + collector configured |

---

## Exercises

1. **Find the busiest endpoint** — Use `grep` and `sort` on the metrics output to identify which API path has the highest request count. What does this tell you about how Trino and Polaris interact?

2. **Monitor a query** — Open `docker logs -f polaris` in one terminal, then run a Trino query (`SELECT * FROM iceberg.shop.orders LIMIT 5`) in another. How many Polaris API calls does a single Trino query generate?

3. **Error rate analysis** — Filter metrics for HTTP 4xx and 5xx status codes. Are there any errors? If so, what endpoints are failing?

   ```bash
   curl -s http://localhost:8182/q/metrics | grep 'status="[45]'
   ```

4. **Custom request tracking** — Write a script that makes 5 API calls, each with a sequentially numbered `Polaris-Request-Id` (e.g., `audit-001` through `audit-005`). Then extract all 5 from the logs and calculate the time between the first and last request.

5. **Challenge:** If you wanted to add Prometheus scraping without running a full Prometheus server, how could you use `curl` + `cron` (or a simple loop) to capture metrics snapshots over time? Write a one-liner that appends timestamped metrics to a file every 30 seconds.

**Congratulations!** You've explored Polaris's complete observability stack without adding any extra infrastructure.
