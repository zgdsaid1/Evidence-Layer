"""Container health probe using only the Python standard library."""

from __future__ import annotations

import http.client
import os


def is_healthy() -> bool:
    raw_port = os.environ.get("PORT", "8000")
    try:
        port = int(raw_port)
        if not 1 <= port <= 65535:
            return False
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        try:
            connection.request("GET", "/healthz")
            response = connection.getresponse()
            return response.status == 200 and response.read() == b'{"status":"ok"}'
        finally:
            connection.close()
    except (OSError, ValueError):
        return False


if __name__ == "__main__":
    raise SystemExit(0 if is_healthy() else 1)
