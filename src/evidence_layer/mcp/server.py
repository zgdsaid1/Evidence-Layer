"""MCP stdio server exposing the local ``retrieve_evidence`` tool.

This module wires the transport-free adapter from
``evidence_layer.mcp.tools`` into an MCP stdio server using the official
``mcp`` SDK (``MCPServer``). It exposes exactly one read-only tool,
``retrieve_evidence``, and performs no network, HTTP, auth, database, or
deployment work.
"""

from __future__ import annotations

import logging
import sys

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from evidence_layer.mcp.tools import retrieve_evidence

logger = logging.getLogger(__name__)

mcp = MCPServer("Evidence Layer")


@mcp.tool(
    name="retrieve_evidence",
    annotations=ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        open_world_hint=False,
        # No idempotency claim is made here.
    ),
)
def retrieve_evidence_tool(
    query: str,
    top_k: int = 5,
    budget_words: int = 500,
) -> dict:
    """Retrieve ranked, budgeted local evidence for a query.

    Searches the local corpus using the existing lexical retrieval adapter and
    returns a JSON-safe result. Invalid input and internal failures are
    returned as safe error structures; no exception text, paths, or secrets
    are exposed.
    """
    try:
        return retrieve_evidence(query, top_k, budget_words)
    except Exception:
        return {"error": {"code": "internal_error", "message": "retrieve_evidence failed"}}


def _configure_logging() -> None:
    """Route all application and library logs to stderr only.

    stdout is reserved exclusively for newline-delimited JSON-RPC, so no log
    handler may target stdout.
    """
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)


def main() -> None:
    """Run the MCP stdio server, routing logs to stderr only."""
    _configure_logging()
    logger.info("starting evidence layer MCP stdio server")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
