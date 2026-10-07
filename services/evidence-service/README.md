# services/evidence-service

Placeholder for the future Python MCP/HTTP service that Railway will host.

**Not a server.** There is no MCP implementation, no FastAPI/HTTP service, and
no health endpoint. The Dockerfile only installs the `evidence_layer` package
and its `CMD` prints a message and exits non-zero. **Do not deploy this
placeholder as a production service.**

## Railway (later)

- Planned build context / Root Directory: the repository root.
- Planned Dockerfile path: `services/evidence-service/Dockerfile`.
- Reason: the Dockerfile copies `pyproject.toml`, `README.md`, and `src/`,
  which live at the repository root.
- Railway is not configured and nothing is deployed.
- Deploy only after the service has a health endpoint and an auth model.

## Environment

`.env.example` lists variable names only. Never commit a `.env` file or values;
see [docs/ENVIRONMENT_AND_SECRETS.md](../../docs/ENVIRONMENT_AND_SECRETS.md).
