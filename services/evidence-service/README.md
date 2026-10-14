# Evidence Layer health service

This is a local, health-only FastAPI application. It exposes exactly one
application route: `GET /healthz`, which returns HTTP `200` with the JSON body
`{"status":"ok"}`.

It does not expose MCP or customer operations, read a corpus, retrieve evidence,
authenticate users, resolve tenants, access a database, or call JEV, Decisions,
or another external provider. OpenAPI and interactive documentation routes are
disabled. Starting the process requires no secrets or customer data; `PORT` is
the only supported setting, and defaults to `8000` for local use.

A successful health response confirms only that this process can serve the
health route. It does not establish source authorization, tenant isolation,
provider-transfer authorization, or readiness for customer operations. The
existing source-read boundary remains deny-all and JEV transfer remains disabled.

## Local installation and startup

Use Python 3.12 or newer, from the repository root:

```bash
python -m pip install -e ".[dev,service]"
PYTHONPATH=services/evidence-service python -m evidence_service
```

The entry point binds to `0.0.0.0` and reads `PORT`. If it is unset, the local
default is `8000`. The equivalent Uvicorn command is:

```bash
PYTHONPATH=services/evidence-service python -m uvicorn evidence_service.app:app \
  --host 0.0.0.0 --port "${PORT:-8000}" --no-access-log
```

Check the response locally with Python's standard library:

```bash
python -c "from urllib.request import urlopen; print(urlopen('http://127.0.0.1:8000/healthz').read().decode())"
```

Expected body:

```json
{"status":"ok"}
```

No other environment variables are required. `.env.example` contains only the
non-secret `PORT` setting; do not add provider or database credentials for this
health-only process.

## Tests and container

Run the focused service tests and the full suite from the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider tests/test_evidence_service_health.py
PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider
```

Build the image with the repository root as its context:

```bash
docker build -f services/evidence-service/Dockerfile -t evidence-service:local .
```

The image runs as a non-root user and has a Python-standard-library health
check against its own `127.0.0.1:$PORT/healthz` endpoint.

## Railway status

Railway remains the documented target for a future persistent Python service.
This change does not configure automatic production deployment, create a
Railway project, or deploy the image. Any deployment requires separate review
and approval.
