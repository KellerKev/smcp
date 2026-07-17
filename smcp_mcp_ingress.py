#!/usr/bin/env python3
"""Inbound MCP -> SMCP ingress.

Exposes an ``SMCPNode``'s native tools to standard MCP clients over MCP's
JSON-RPC 2.0 (`tools/list`, `tools/call`). Every MCP-originated call is funneled
through ``SMCPNode.authorize_and_invoke`` — the SAME enforcement point the native
SMCP transport uses — so an MCP client's `tools/call` is gated identically:
per-tool authorization, parameter validation, the consent gate, output filtering,
and audit. This makes SMCP <-> MCP interop bidirectional.

This module is transport-agnostic: ``handle_request`` takes a parsed JSON-RPC
object plus the caller's bearer token and returns a JSON-RPC response object. Wrap
it in an HTTP/stdio server to expose it on the wire.
"""
import json
import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("smcp_mcp_ingress")

# JSON-RPC error codes (subset) + an app code for authorization/tool failures.
_METHOD_NOT_FOUND = -32601
_INVALID_REQUEST = -32600
_TOOL_ERROR = -32000


class MCPIngress:
    """Adapt inbound MCP JSON-RPC to an SMCPNode, enforcing SMCP authorization."""

    def __init__(self, node: Any, token_resolver: Optional[Callable[[Optional[str]], Optional[str]]] = None):
        """``node`` is the SMCPNode whose tools are exposed. ``token_resolver``
        maps the inbound MCP bearer token to an SMCP session token (which carries
        the authorization scopes); the default treats the bearer AS the SMCP
        session token. Return None to present an unauthenticated call (only tools
        with auth_required=False will run)."""
        self.node = node
        self.token_resolver = token_resolver or (lambda bearer: bearer)

    def handle_request(self, request: Dict[str, Any], bearer: Optional[str] = None) -> Dict[str, Any]:
        """Handle one JSON-RPC request; return a JSON-RPC response object."""
        rid = request.get("id")
        method = request.get("method")
        if request.get("jsonrpc") != "2.0" or not method:
            return self._error(rid, _INVALID_REQUEST, "Invalid JSON-RPC request")

        token = None
        try:
            token = self.token_resolver(bearer)
        except Exception:
            token = None

        if method == "tools/list":
            return self._ok(rid, {"tools": self._list_tools()})

        if method == "tools/call":
            params = request.get("params") or {}
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if not name:
                return self._error(rid, _INVALID_REQUEST, "tools/call requires 'name'")
            ok, outcome = self.node.authorize_and_invoke(name, arguments, token)
            if not ok:
                # Surface the SMCP rejection as an MCP tool error.
                return self._error(rid, _TOOL_ERROR, str(outcome))
            return self._ok(rid, {
                "content": [{"type": "text", "text": self._as_text(outcome)}],
                "isError": False,
            })

        return self._error(rid, _METHOD_NOT_FOUND, f"Method not found: {method}")

    def _list_tools(self):
        tools = []
        for name, cap in getattr(self.node, "capabilities", {}).items():
            tools.append({
                "name": name,
                "description": cap.description,
                "inputSchema": {"type": "object", "properties": cap.parameters or {}},
            })
        return tools

    @staticmethod
    def _as_text(value: Any) -> str:
        if isinstance(value, str):
            return value
        try:
            return json.dumps(value)
        except (TypeError, ValueError):
            return str(value)

    @staticmethod
    def _ok(rid, result):
        return {"jsonrpc": "2.0", "id": rid, "result": result}

    @staticmethod
    def _error(rid, code, message):
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}
