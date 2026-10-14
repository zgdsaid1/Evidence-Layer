FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY services/evidence-service/evidence_service ./evidence_service
RUN python -m pip install --no-cache-dir '.[service]'

USER 10001:10001

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 CMD ["python", "-m", "evidence_service.healthcheck"]

CMD ["python", "-m", "evidence_service"]
