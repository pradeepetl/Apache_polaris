# On-Demand Services

`spark-jupyter` and `marimo` are not started by `docker compose up -d`. They sit behind Compose profiles so the core stack (Trino, Polaris, LocalStack, Postgres, Jaeger, Admin UI) uses less memory. Start them only when a lab needs them.

| Service | Profile | URL |
|---------|---------|-----|
| spark-jupyter | `spark` | http://localhost:8888?token=spark123 |
| marimo | `marimo` | http://localhost:2718 |

`podman compose` accepts the same commands as `docker compose`.

## Local

```bash
# Core stack only
docker compose up -d

# Start Spark Jupyter
docker compose --profile spark up -d

# Start Marimo
docker compose --profile marimo up -d

# Start both
docker compose --profile spark --profile marimo up -d

# Stop them to free memory (core stack keeps running)
docker compose stop spark-jupyter marimo

# Check what is running
docker ps --format "table {{.Names}}\t{{.Status}}"

# Tear everything down, including profiled services
docker compose --profile "*" down
```

## Codespaces / Dev Container

In the dev container, marimo starts with the core stack and port 2718 is forwarded automatically. Only `spark-jupyter` is on-demand.

The dev container sets `COMPOSE_PROJECT_NAME=polaris_devcontainer` and `COMPOSE_FILE=.devcontainer/docker-compose.yml`, so plain `docker compose` commands in the workspace terminal target the running stack:

```bash
docker compose --profile spark up -d spark-jupyter
docker compose stop spark-jupyter
```

If you get `container name "/jaeger" is already in use`, compose is reading the root `docker-compose.yml`. This happens in Codespaces created before this setting was added. Rebuild the container, or pass the settings explicitly:

```bash
docker compose -p polaris_devcontainer -f .devcontainer/docker-compose.yml --profile spark up -d spark-jupyter
```

Spark Jupyter is not forwarded automatically. After starting it, open the Ports tab, click **Forward a Port**, and enter `8888`.

## Notes

- The first start of a profile builds its image (`spark/`, `marimo/`), which takes a few minutes. Later starts are fast.
- Both services wait for `polaris-setup` and `localstack-setup` to finish. If the core stack is already up, they start right away.
- A plain `docker compose down` does not stop profiled containers that are running. Use `--profile "*"`.
- After changing `spark/Dockerfile` or `marimo/Dockerfile`, rebuild with `docker compose --profile spark up -d --build`.
