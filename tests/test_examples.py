"""End-to-end smoke tests for the example scripts and the live server/client.

These start a real SMCP server on loopback and drive it with a real client, so
they exercise handshake, auth, replay protection, and tool invocation together.
The ollama-backed test is skipped automatically when ollama or the demo model is
unavailable.
"""
import asyncio
import os
import socket
import sys
import urllib.request
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "examples"))

from _demo_support import demo_config, DEMO_MODEL
from smcp_server import SMCPServer
from smcp_client import scp_client


def _free_port():
    s = socket.socket()
    s.bind(("localhost", 0))
    port = s.getsockname()[1]
    s.close()
    return port


async def _run_server(server, host, port):
    await server.start(host=host, port=port)


@pytest.mark.asyncio
async def test_server_client_end_to_end():
    port = _free_port()
    scfg = demo_config("test_server", port=port)
    ccfg = demo_config("test_client", server_url=f"ws://localhost:{port}")

    server = SMCPServer(scfg)
    server.register_tool("echo", "echo", {"message": {"type": "string"}},
                         lambda message: {"echo": message})

    task = asyncio.create_task(_run_server(server, "localhost", port))
    try:
        await asyncio.sleep(0.5)
        async with scp_client(ccfg) as client:
            caps = client.list_capabilities()
            assert "calculator" in caps and "echo" in caps
            assert await client.invoke_tool("calculator", operation="add", a=15, b=27) == 42
            assert await client.invoke_tool("echo", message="hi") == {"echo": "hi"}
    finally:
        task.cancel()


def _ollama_up():
    url = os.getenv("SMCP_OLLAMA_URL", "http://localhost:11434")
    try:
        with urllib.request.urlopen(f"{url}/api/tags", timeout=2) as r:
            body = r.read().decode()
        return DEMO_MODEL.split(":")[0] in body
    except Exception:
        return False


@pytest.mark.asyncio
@pytest.mark.skipif(not _ollama_up(), reason="ollama or demo model not available")
async def test_ai_chat_via_ollama():
    port = _free_port()
    scfg = demo_config("test_server_ai", port=port)
    ccfg = demo_config("test_client_ai", server_url=f"ws://localhost:{port}")
    server = SMCPServer(scfg)
    task = asyncio.create_task(_run_server(server, "localhost", port))
    try:
        await asyncio.sleep(0.5)
        async with scp_client(ccfg) as client:
            result = await client.invoke_tool(
                "ai_chat", prompt="Reply with the single word: pong", model=DEMO_MODEL)
            assert isinstance(result, dict)
            assert "response" in result and result["response"]
    finally:
        task.cancel()
