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

from evidence_layer.mcp.tools import retrieve_evidence

mcp = MCPServer("Evidence Layer")


@mcp.tool(name="retrieve_evidence")
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


def main() -> None:
    """Run the MCP stdio server, routing logs to stderr only."""
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
