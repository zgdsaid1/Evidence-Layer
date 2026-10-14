"""Run the health-only FastAPI app with Uvicorn."""

from __future__ import annotations

import os
from collections.abc import Mapping


def configured_port(environment: Mapping[str, str] | None = None) -> int:
    """Return a validated PORT value, defaulting to the local port 8000."""
    values = os.environ if environment is None else environment
    raw_port = values.get("PORT", "8000")
    if not isinstance(raw_port, str) or not raw_port.isascii() or not raw_port.isdecimal():
        raise SystemExit("PORT must be an integer between 1 and 65535")
    port = int(raw_port)
    if not 1 <= port <= 65535:
        raise SystemExit("PORT must be an integer between 1 and 65535")
    return port


def main() -> None:
    import uvicorn

    uvicorn.run(
        "evidence_service.app:app",
        host="0.0.0.0",
        port=configured_port(),
        access_log=False,
    )


if __name__ == "__main__":
    main()
