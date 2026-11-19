# GitHub Codespaces — Setup Guide

Step-by-step instructions to run the Trino + Polaris lab in GitHub Codespaces.

## Prerequisites

- A GitHub account (free tier works — 60 core-hours/month)
- This repo pushed to a GitHub repository

## Step 1: Create the Codespace

1. Go to your GitHub repository
2. Click the green **Code** button
3. Switch to the **Codespaces** tab
4. Click **Create codespace on main**
5. **Important:** Select **8-core / 32 GB RAM** machine type
   - Click the `...` menu next to "Create codespace" to choose machine type
   - The lab runs ~9 containers (Trino, Marimo and Spark are memory-hungry); 4-core/16GB can run out of memory

## Step 2: Wait for Build (~3-5 minutes)

**You do NOT need to run `docker compose up` manually.** Codespaces detects the `devcontainer.json` and automatically starts all services for you.

What happens behind the scenes:
1. Codespaces reads `.devcontainer/devcontainer.json`
2. Runs `docker compose up` on `.devcontainer/docker-compose.yml` automatically
3. Builds the dlt and Marimo images (Spark is built the first time you start its profile)
4. Runs init jobs (PostgreSQL seed data, Polaris catalog setup, LocalStack S3 bucket, dlt earthquake ingestion)
5. Opens VS Code in the browser with everything running

You'll see build logs in the terminal. Wait until you see:
```
=== Trino Polaris Lab ===
Waiting for services...
Ready!
```

## Step 3: Verify Services Are Running

Open the **Terminal** in VS Code (it's already connected to the workspace container) and run:

```bash
docker ps --format "table {{.Names}}\t{{.Status}}"
```

Expected:
```
NAMES              STATUS
trino              Up (about a minute ago)
postgres           Up (healthy)
polaris            Up (healthy)
localstack         Up (healthy)
polaris-admin      Up
marimo             Up
```

`spark-jupyter` is on-demand and not started by default. Start it from the terminal when needed. The dev container points `docker compose` at this stack, so no `-f` flag is needed:
```bash
docker compose --profile spark up -d spark-jupyter
```

`polaris-setup`, `localstack-setup`, and `dlt-earthquakes` will show as **Exited (0)** — that's normal, they are one-shot init containers.

If any service failed, check logs:
```bash
docker logs <container-name>
```

## Step 4: Access the Web UIs

Go to the **Ports** tab in the bottom panel of VS Code. You'll see forwarded ports:

| Port | Label | How to Open |
|------|-------|-------------|
| 8080 | Trino UI | Click the globe icon or "Open in Browser" |
| 3000 | Polaris Admin | Click to open, login with `root` / `s3cr3t` / `POLARIS` |
| 16686 | Jaeger Tracing | Click to open |
| 2718 | Marimo | Click to open |

Spark Jupyter (8888) is on-demand. After starting it, click **Forward a Port** and enter `8888` (token is `spark123`).

If the Ports tab is empty, click **Forward a Port** and enter the port number (e.g. `2718`).

> Codespaces generates unique URLs like `https://xyz-8080.app.github.dev`. These replace `localhost:PORT`.

## Step 5: Run Your First Query

In the VS Code terminal:

```bash
docker exec -e TRINO_PASSWORD=admin123 trino \
  trino --server https://localhost:8443 --user admin --password --insecure \
  --execute "SHOW CATALOGS"
```

Expected output:
```
  Catalog
-----------
 iceberg
 memory
 postgres
 system
 tpcds
 tpch
```

Try a data query:
```bash
docker exec -e TRINO_PASSWORD=admin123 trino \
  trino --server https://localhost:8443 --user admin --password --insecure \
  --execute "SELECT name, country FROM postgres.public.customers LIMIT 5"
```

## Step 6: Populate Iceberg Tables

The Iceberg shop tables (orders, order_items) need to be created after Polaris starts. Run:

```bash
docker exec -e TRINO_PASSWORD=admin123 -it trino \
  trino --server https://localhost:8443 --user admin --password --insecure
```

Then paste the Iceberg table creation SQL from `sample-queries.sql` (Section 2).

Verify earthquake data from the dlt pipeline:
```sql
SELECT count(*) FROM iceberg.earthquakes.events;
SELECT magnitude, place FROM iceberg.earthquakes.events ORDER BY magnitude DESC LIMIT 5;
```

## Step 7: Start the Labs

Open the `exercises/` folder in the file explorer. Start with:
- [Lab 0 — Environment Setup](../exercises/lab0-setup.md) — verify everything works
- Then progress through Labs 1-5

Also keep the [Cheatsheet](../exercises/cheatsheet.md) open for quick reference.

---

## Useful Commands

```bash
# Interactive Trino CLI
docker exec -e TRINO_PASSWORD=admin123 -it trino \
  trino --server https://localhost:8443 --user admin --password --insecure

# Re-run earthquake ingestion
docker restart dlt-earthquakes
docker logs -f dlt-earthquakes

# Check S3 contents
docker exec localstack awslocal s3 ls s3://warehouse/ --recursive --human-readable

# Polaris health
curl -s http://localhost:8182/q/health

# Restart a service
docker restart trino
```

## Troubleshooting

**Polaris Admin won't load**
- Wait 1-2 minutes after Codespace starts — Polaris needs time to become healthy
- Check: `docker logs polaris` for errors

**Trino queries fail with "catalog not found"**
- Verify Polaris is healthy: `curl -s http://localhost:8182/q/health`
- Check Trino logs: `docker logs trino | tail -20`

**Spark Jupyter can't connect**
- Forward port `8888` in the Ports tab and use the Codespaces URL
- Token is `spark123`

**dlt-earthquakes failed**
- Check: `docker logs dlt-earthquakes`
- Re-run: `docker restart dlt-earthquakes`

**Running out of Codespaces hours**
- Free tier: 60 core-hours/month (= 7.5 hours at 8-core)
- Stop the Codespace when not in use: Codespaces tab > `...` > Stop
- Stopped Codespaces don't count against hours

**Services slow or OOM-killed**
- Ensure you selected an 8-core/32GB machine
- Check: `docker stats` to see memory usage per container

---

## Cleanup

When done with the lab:
1. **Stop** the Codespace (preserves state, pauses billing): Codespaces tab > Stop
2. **Delete** the Codespace (frees resources): Codespaces tab > Delete

Data does NOT persist between Codespace deletions. Each new Codespace starts fresh.
