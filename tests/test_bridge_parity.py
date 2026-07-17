"""Bridge security parity (outbound) + inbound MCP ingress.

Outbound: bridged MCP tools are registered as namespaced native capabilities and
flow through the SMCP security pipeline (authz, consent, output filter, audit).
Inbound: MCP JSON-RPC tools/call is gated identically via authorize_and_invoke.
"""
import secrets
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smcp_core import SMCPNode, MessageType, Capability
from smcp_mcp_bridge import MCPBridge, MCPServerConfig, MCPServerType
from smcp_mcp_ingress import MCPIngress


def _node(node_id="srv", api="cfg_abc123defabc123defabc12"):
    sk, js, salt = secrets.token_urlsafe(32), secrets.token_urlsafe(32), secrets.token_urlsafe(16)
    return SMCPNode(node_id, sk, js, salt, api_key=api), api


def _cfg(server_id="weather"):
    return MCPServerConfig(server_id=server_id, server_type=MCPServerType.CUSTOM,
                           name=f"{server_id} MCP", url="wss://example")


# --------------------------------------------------------------------------- #
# Outbound bridge parity
# --------------------------------------------------------------------------- #
def test_bridged_capability_is_namespaced():
    node, _ = _node()
    bridge = MCPBridge(node=node)
    bridge._register_bridged_capabilities(_cfg("weather"), ["get_weather"])
    assert "mcp:weather:get_weather" in node.capabilities
    # Not registered under the bare foreign name (can't shadow a native tool).
    assert "get_weather" not in node.capabilities


def test_bridged_invoke_flows_through_pipeline():
    node, api = _node()
    bridge = MCPBridge(node=node)
    bridge.servers["weather"] = _cfg("weather")
    bridge._register_bridged_capabilities(_cfg("weather"), ["get_weather"])

    async def fake_send(server_id, request):
        return {"result": {"temp": 72}}
    bridge._send_request_with_retry = fake_send

    events = []
    node.audit_hook = events.append
    node.output_filter = lambda tool, res: {**res, "filtered": True}

    tok = node.security.generate_jwt("c1", ["tool:mcp:weather:get_weather"])
    ok, out = node.authorize_and_invoke("mcp:weather:get_weather", {"task": {"q": "NYC"}}, tok)
    assert ok
    assert out.get("filtered") is True  # output filter applied to bridged result
    kinds = [e["event"] for e in events]
    assert "invoke" in kinds  # native audit
    assert any(e.get("bridged") for e in events)  # bridge provenance audit


def test_bridged_invoke_requires_scope():
    node, _ = _node()
    bridge = MCPBridge(node=node)
    bridge.servers["weather"] = _cfg("weather")
    bridge._register_bridged_capabilities(_cfg("weather"), ["get_weather"])
    # A token scoped to a different tool cannot call the bridged one.
    tok = node.security.generate_jwt("c1", ["tool:something_else"])
    ok, out = node.authorize_and_invoke("mcp:weather:get_weather", {"task": {}}, tok)
    assert not ok and out == "Unauthorized"


def test_bridged_invoke_consent_denied():
    node, _ = _node()
    bridge = MCPBridge(node=node)
    bridge.servers["weather"] = _cfg("weather")
    bridge._register_bridged_capabilities(_cfg("weather"), ["get_weather"])
    bridge._send_request_with_retry = lambda s, r: {"result": {}}
    node.consent_hook = lambda tool, params, cid: not tool.startswith("mcp:")
    tok = node.security.generate_jwt("c1", ["tool_invoke"])
    ok, out = node.authorize_and_invoke("mcp:weather:get_weather", {"task": {}}, tok)
    assert not ok and "denied" in out.lower()


# --------------------------------------------------------------------------- #
# Inbound MCP ingress
# --------------------------------------------------------------------------- #
def _ingress_node():
    node, _ = _node()
    node.register_capability(Capability("greet", "greets", {"name": {"type": "string"}}),
                             lambda name: {"hi": name})
    return node


def test_ingress_tools_list():
    ing = MCPIngress(_ingress_node())
    resp = ing.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = [t["name"] for t in resp["result"]["tools"]]
    assert "greet" in names


def test_ingress_call_without_token_rejected():
    ing = MCPIngress(_ingress_node())
    resp = ing.handle_request(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "greet", "arguments": {"name": "x"}}}, bearer=None)
    assert "error" in resp


def test_ingress_call_with_scoped_token():
    node = _ingress_node()
    ing = MCPIngress(node)
    tok = node.security.generate_jwt("c1", ["tool:greet"])
    resp = ing.handle_request(
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "greet", "arguments": {"name": "x"}}}, bearer=tok)
    assert "result" in resp
    assert resp["result"]["content"][0]["text"] == '{"hi": "x"}'


def test_ingress_unknown_method():
    ing = MCPIngress(_ingress_node())
    resp = ing.handle_request({"jsonrpc": "2.0", "id": 4, "method": "bogus/thing"})
    assert resp["error"]["code"] == -32601


def test_ingress_gating_matches_native():
    # An inbound call and a native call with the same scope get the same verdict.
    node = _ingress_node()
    ing = MCPIngress(node)
    node.consent_hook = lambda tool, params, cid: False  # deny everything
    tok = node.security.generate_jwt("c1", ["tool:greet"])
    resp = ing.handle_request(
        {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
         "params": {"name": "greet", "arguments": {"name": "x"}}}, bearer=tok)
    assert "error" in resp  # consent denial applies to MCP-originated calls too
