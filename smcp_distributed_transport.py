#!/usr/bin/env python3
"""Real WebSocket transport for the distributed A2A layer.

Nodes talk over SMCP's existing authenticated, signed, optionally-TLS WebSocket
RPC (``SMCPServer`` + ``SMCPClient``) instead of the unimplemented HTTP surface
(``/health``, ``/api/task``) the distributed layer used to reach for. A node:

- **receives** cross-node work by running an ``SMCPServer`` that exposes the
  ``distributed_task_execute`` capability (see ``DistributedTaskServer``), and
- **sends** work by opening an ``SMCPClient`` to a peer and invoking that
  capability (see ``PeerConnectionPool``).

The SMCP protocol already encrypts and signs every payload, so no separate
transit envelope is needed. This module is deliberately transport-only; task
routing/selection stays in ``smcp_distributed_a2a``.
"""
import asyncio
import copy
import logging
from typing import Any, Callable, Dict

from smcp_config import SMCPConfig
from smcp_client import SMCPClient
from smcp_server import SMCPServer
from smcp_core import Capability

logger = logging.getLogger("distributed_transport")

# The capability every node exposes to receive delegated tasks from peers.
DISTRIBUTED_TASK_TOOL = "distributed_task_execute"


def peer_server_url(host: str, port: int, tls_enabled: bool) -> str:
    """WebSocket URL for a peer, wss:// when TLS is enabled else ws://."""
    scheme = "wss" if tls_enabled else "ws"
    return f"{scheme}://{host}:{port}"


class PeerConnectionPool:
    """One reusable authenticated ``SMCPClient`` per peer node.

    Connections are created lazily on first use, cached by ``node_id``, and
    transparently re-established if a call fails on a stale connection. A
    per-node lock serialises concurrent calls to the same peer so a single
    websocket isn't used from two coroutines at once.
    """

    # A call/handshake that gets no response must not hold the per-node lock
    # forever; bound every peer RPC so a silent peer can't wedge the pool.
    _CALL_TIMEOUT = 30

    def __init__(self, base_config: SMCPConfig):
        self.base_config = base_config
        self._clients: Dict[str, SMCPClient] = {}
        self._locks: Dict[str, asyncio.Lock] = {}

    def _peer_config(self, host: str, port: int) -> SMCPConfig:
        cfg = copy.deepcopy(self.base_config)
        cfg.server_url = peer_server_url(host, port, cfg.security.tls_enabled)
        return cfg

    def _lock(self, node_id: str) -> asyncio.Lock:
        return self._locks.setdefault(node_id, asyncio.Lock())

    async def _get_client(self, node_id: str, host: str, port: int) -> SMCPClient:
        client = self._clients.get(node_id)
        if client is not None and getattr(client, "connected", False):
            return client
        cfg = self._peer_config(host, port)
        client = SMCPClient(cfg)
        try:
            await asyncio.wait_for(client.connect(), timeout=self._CALL_TIMEOUT)
        except Exception:
            # Don't leak a half-open client if connect fails/times out.
            try:
                await client.disconnect()
            except Exception:
                pass
            raise
        self._clients[node_id] = client
        return client

    async def call(self, node_id: str, host: str, port: int,
                   tool_name: str, **params) -> Any:
        """Invoke ``tool_name`` on a peer, reconnecting once on failure."""
        async with self._lock(node_id):
            try:
                client = await self._get_client(node_id, host, port)
                return await asyncio.wait_for(
                    client.invoke_tool(tool_name, **params), timeout=self._CALL_TIMEOUT)
            except Exception as first_err:
                logger.warning(
                    f"peer call to {node_id} failed ({first_err}); reconnecting"
                )
                await self._drop(node_id)
                client = await self._get_client(node_id, host, port)
                return await asyncio.wait_for(
                    client.invoke_tool(tool_name, **params), timeout=self._CALL_TIMEOUT)

    async def health(self, node_id: str, host: str, port: int) -> bool:
        """Return True if the peer accepts an authenticated handshake."""
        async with self._lock(node_id):
            try:
                await self._get_client(node_id, host, port)
                return True
            except Exception as e:
                logger.warning(f"health check failed for {node_id}: {e}")
                await self._drop(node_id)
                return False

    async def _drop(self, node_id: str) -> None:
        client = self._clients.pop(node_id, None)
        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                pass

    async def close_all(self) -> None:
        for node_id in list(self._clients):
            await self._drop(node_id)


class DistributedTaskServer:
    """Runs an ``SMCPServer`` exposing cross-node capabilities.

    By default it exposes ``distributed_task_execute`` wired to ``dispatch`` (a
    synchronous ``(task: dict) -> Any`` callable). Additional capabilities can be
    added with :meth:`register` before :meth:`start`. Handlers run inside the
    server's worker-thread dispatch (``smcp_server`` offloads handlers off the
    event loop), so blocking handlers are fine.

    Pass ``dispatch=None`` to start with no default capability (e.g. when you
    only want to :meth:`register` your own).
    """

    def __init__(self, config: SMCPConfig,
                 dispatch: Callable[[Dict[str, Any]], Any] = None):
        self.server = SMCPServer(config)
        self._dispatch = dispatch
        self._serve_task = None
        if dispatch is not None:
            self.register(
                DISTRIBUTED_TASK_TOOL,
                {"task": {"type": "object"}},
                self._handle,
                description="Execute a task delegated from another node",
            )

    def register(self, tool_name: str, param_schema: Dict[str, Any],
                 handler: Callable, description: str = None) -> None:
        """Expose an additional capability. Call before :meth:`start`."""
        self.server.node.register_capability(
            Capability(
                name=tool_name,
                description=description or f"Cross-node capability: {tool_name}",
                parameters=param_schema,
            ),
            handler,
        )

    def _handle(self, task: Dict[str, Any]) -> Any:
        return self._dispatch(task)

    async def start(self, host: str = "localhost", port: int = 8765):
        """Bind the listener in the background and return once it is accepting."""
        self._serve_task = asyncio.create_task(self.server.start(host=host, port=port))
        # Give websockets.serve a moment to bind before callers connect.
        await asyncio.sleep(0.4)
        return self._serve_task

    async def stop(self) -> None:
        if self._serve_task is not None:
            self._serve_task.cancel()
            try:
                await self._serve_task
            except (asyncio.CancelledError, Exception):
                pass
            self._serve_task = None
