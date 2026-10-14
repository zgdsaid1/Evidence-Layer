"""Health-only HTTP application, isolated from evidence and provider code."""

from fastapi import FastAPI


def create_app() -> FastAPI:
    """Create the health-only app without loading application integrations."""
    application = FastAPI(
        title="Evidence Layer health service",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @application.api_route(
        "/healthz", methods=["GET"], status_code=200, include_in_schema=False
    )
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
