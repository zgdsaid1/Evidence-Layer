FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Build context is the repository root, e.g.:
#   docker build -f services/evidence-service/Dockerfile .
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# Placeholder only: there is no server yet. Replace with a real entry point
# once an MCP/HTTP service with a health endpoint and auth model exists.
CMD ["python", "-c", "import sys; print('evidence-service placeholder: no server implemented', file=sys.stderr); sys.exit(1)"]
