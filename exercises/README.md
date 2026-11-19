# Exercises — Trino + Polaris Lab

Hands-on labs organized by difficulty. Each level builds on the previous one.

| Level | Lab | Topic | Time |
|-------|-----|-------|------|
| 0 | [Lab 0 — Environment Setup](lab0-setup.md) | Verify services, open UIs, first query | 10 min |
| 1 | [Lab 1 — Exploring Catalogs](lab1-exploring-catalogs.md) | Navigate catalogs, schemas, tables | 15 min |
| 2 | [Lab 2 — Query Federation](lab2-query-federation.md) | JOIN across Postgres + Iceberg | 20 min |
| 3 | [Lab 3 — Access Control](lab3-access-control.md) | Roles, grants, test as restricted user | 25 min |
| 4 | [Lab 4 — Data Ingestion](lab4-data-ingestion.md) | dlt pipeline, Spark writes, multi-engine reads | 30 min |
| 5 | [Lab 5 — API Mastery](lab5-api-mastery.md) | Polaris REST API, create principals, full RBAC setup | 30 min |
| 6 | [Lab 6 — Privileges & RBAC Deep Dive](lab6-privileges-rbac-deep-dive.md) | Multi-team RBAC, fine-grained grants, privilege revocation | 35 min |
| 7 | [Lab 7 — Realms](lab7-realms.md) | Multi-tenant isolation, second realm, cross-realm testing | 30 min |
| 8 | [Lab 8 — Observability](lab8-observability.md) | Metrics, structured logging, request tracing | 25 min |
| 9 | [Lab 9 — Table Maintenance](lab9-table-maintenance.md) | Compaction, snapshot expiry, orphan removal, partition evolution | 30 min |
| 10 | [Lab 10 — Time Travel](lab10-time-travel.md) | Query historical states, compare versions, rollback snapshots | 25 min |
| 11 | [Lab 11 — Hidden Partitioning](lab11-partitioning.md) | Partition transforms, pruning, partition evolution | 30 min |
| 12 | [Lab 12 — Schema Evolution](lab12-schema-evolution.md) | Add/drop/rename columns, type promotion, backward compatibility | 25 min |
| 13 | [Lab 13 — COW vs MOR](lab13-cow-vs-mor.md) | Copy-on-Write vs Merge-on-Read write modes, performance comparison | 30 min |
| 14 | [Lab 14 — Row-Level Operations](lab14-row-level-ops.md) | UPDATE, DELETE, MERGE INTO (upsert), snapshot tracking | 30 min |
| 15 | [Lab 15 — Branching & Tagging](lab15-branching-tagging.md) | Named snapshots, table branches, safe experimentation | 30 min |

Also see: [Cheatsheet](cheatsheet.md) — quick reference for common commands and API calls.

## Prerequisites

- All services running: `docker compose up -d` (or `podman compose up -d`)
- Verify with: `docker ps` — you should see ~8 containers

## How to Connect to Trino CLI

```bash
# As admin (full access)
docker exec -e TRINO_PASSWORD=admin123 -it trino \
  trino --server https://localhost:8443 --user admin --password --insecure

# As analyst (read-only)
docker exec -e TRINO_PASSWORD=analyst123 -it trino \
  trino --server https://localhost:8443 --user analyst --password --insecure
```

## Service URLs

| Service | URL |
|---------|-----|
| Trino Web UI | http://localhost:8080 |
| Polaris Admin | http://localhost:3000 |
| Spark Jupyter | http://localhost:8888?token=spark123 |
| Marimo | http://localhost:2718 |
