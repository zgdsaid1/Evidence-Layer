"""Subprocess integration tests for the MCP stdio server (``retrieve_evidence``).

The wire tests launch ``python -m evidence_layer.mcp`` as a subprocess and speak
newline-delimited JSON-RPC over stdin/stdout. The corpus/internal-failure error
mapping is exercised at the unit level (a subprocess cannot be monkeypatched).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"

MODULE = "evidence_layer.mcp"
INITIALIZE_PARAMS = {
    "protocolVersion": "2025-11-25",
    "capabilities": {},
    "clientInfo": {"name": "test-client", "version": "0.1.0"},
}

def _start():
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(SRC) + (os.pathsep + existing if existing else "")
    return subprocess.Popen(
        [sys.executable, "-m", MODULE],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env,
    )


def _write(proc, payload):
    proc.stdin.write(json.dumps(payload) + "\n")
    proc.stdin.flush()


def _read(proc):
    line = proc.stdout.readline()
    assert line != "", "server closed stdout unexpectedly"
    message = json.loads(line)  # stdout must be JSON-RPC only
    assert message.get("jsonrpc") == "2.0"
    return message


def _initialize(proc):
    _write(
        proc,
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": INITIALIZE_PARAMS},
    )
    return _read(proc)


def _notify_initialized(proc):
    _write(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})


def _request(proc, msg_id, method, params):
    _write(proc, {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params})
    return _read(proc)


def _call_tool(proc, msg_id, arguments):
    return _request(
        proc, msg_id, "tools/call", {"name": "retrieve_evidence", "arguments": arguments}
    )


def _tool_text(response):
    content = response["result"]["content"]
    assert len(content) == 1
    return json.loads(content[0]["text"])


def _shutdown(proc):
    if proc.poll() is None:
        proc.stdin.close()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.terminate()
            proc.wait(timeout=5)


@pytest.fixture
def server():
    proc = _start()
    try:
        yield proc
    finally:
        _shutdown(proc)


def test_initialize_succeeds(server):
    response = _initialize(server)
    assert response["id"] == 1
    result = response["result"]
    assert result["protocolVersion"] == "2025-11-25"
    assert result["serverInfo"]["name"] == "Evidence Layer"
    assert "tools" in result["capabilities"]


def test_notifications_initialized_and_tools_list(server):
    _initialize(server)
    _notify_initialized(server)
    response = _request(server, 2, "tools/list", {})
    tools = response["result"]["tools"]
    assert [tool["name"] for tool in tools] == ["retrieve_evidence"]


def test_tools_call_fails_closed_without_classified_source(server):
    _initialize(server)
    _notify_initialized(server)
    response = _call_tool(server, 3, {"query": "btree index"})
    data = _tool_text(response)
    assert data == {
        "error": {
            "code": "source_unavailable",
            "message": "local source is unavailable",
        }
    }


def test_tools_call_invalid_argument_returns_adapter_error(server):
    _initialize(server)
    _notify_initialized(server)
    response = _call_tool(server, 4, {"query": ""})
    data = _tool_text(response)
    assert data == {
        "error": {"code": "invalid_argument", "message": "query must be a non-empty string"}
    }
    # The tool returned normally with a safe error dict, not a protocol error.
    assert response["result"].get("isError") is not True


def test_stdout_is_json_rpc_only(server):
    _initialize(server)
    _notify_initialized(server)
    _request(server, 2, "tools/list", {})
    _call_tool(server, 3, {"query": "btree index"})
    server.stdin.close()
    try:
        server.wait(timeout=5)
    except subprocess.TimeoutExpired:
        server.terminate()
        server.wait(timeout=5)
    assert server.stdout.read() == ""


def test_stderr_has_no_protocol_output(server):
    _initialize(server)
    _notify_initialized(server)
    _request(server, 2, "tools/list", {})
    _shutdown(server)
    assert '"jsonrpc"' not in server.stderr.read()


def test_tool_advertises_read_only_and_closed_world_annotations(server):
    _initialize(server)
    _notify_initialized(server)
    response = _request(server, 2, "tools/list", {})
    tools = response["result"]["tools"]
    assert [tool["name"] for tool in tools] == ["retrieve_evidence"]
    annotations = tools[0]["annotations"]
    assert annotations["readOnlyHint"] is True
    assert annotations["destructiveHint"] is False
    assert annotations["openWorldHint"] is False
    assert "idempotentHint" not in annotations


def test_logging_configured_to_stderr():
    import logging

    import evidence_layer.mcp.server as server_mod

    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level

    try:
        server_mod._configure_logging()
        stderr_handlers = [
            handler
            for handler in root.handlers
            if isinstance(handler, logging.StreamHandler)
            and getattr(handler, "stream", None) is sys.stderr
        ]
        assert stderr_handlers
    finally:
        for handler in list(root.handlers):
            root.removeHandler(handler)
        for handler in original_handlers:
            root.addHandler(handler)
        root.setLevel(original_level)


def test_startup_log_goes_to_stderr_not_stdout(server):
    _initialize(server)
    _notify_initialized(server)
    _request(server, 2, "tools/list", {})
    _shutdown(server)
    assert "starting evidence layer MCP stdio server" in server.stderr.read()


def test_source_denial_is_returned_as_tool_result(monkeypatch):
    import evidence_layer.mcp.server as server_mod

    monkeypatch.setattr(
        server_mod,
        "retrieve_evidence",
        lambda *a, **k: {
            "error": {"code": "source_unavailable", "message": "local source is unavailable"}
        },
    )
    result = server_mod.retrieve_evidence_tool("btree index")
    assert result == {
        "error": {"code": "source_unavailable", "message": "local source is unavailable"}
    }


def test_internal_failure_returns_safe_generic_error(monkeypatch):
    import evidence_layer.mcp.server as server_mod

    def boom(*a, **k):
        raise RuntimeError("SECRET sk-999999 /home/secret/token")

    monkeypatch.setattr(server_mod, "retrieve_evidence", boom)
    result = server_mod.retrieve_evidence_tool("btree index")
    assert result == {
        "error": {"code": "internal_error", "message": "retrieve_evidence failed"}
    }
