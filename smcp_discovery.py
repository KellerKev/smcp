#!/usr/bin/env python3
"""Pluggable node discovery for the distributed A2A layer.

Each provider resolves a set of peer nodes from some backend and returns a list
of plain dicts: ``{"node_id", "host", "port", "capabilities"}``. The distributed
registry (``smcp_distributed_a2a.DistributedNodeRegistry.discover_nodes``) picks
a provider by ``cluster.discovery_method`` and health-checks whatever it returns.

Providers:
- ``static``  — the configured ``cluster.nodes`` list (no external backend).
- ``dns``     — SRV records for a service domain (requires ``dnspython``).
- ``consul``  — Consul's HTTP health API (via aiohttp, no extra dependency).
- ``etcd``    — etcd v3 HTTP gateway range read (via aiohttp, no extra dependency).

Consul/etcd talk to their HTTP APIs directly, so unit tests can mock the HTTP
layer; real Consul/etcd remain integration-only.
"""
import base64
import json
import logging
from typing import Any, Dict, List

logger = logging.getLogger("smcp_discovery")


class DiscoveryProvider:
    """Interface: return a list of node dicts."""

    async def discover(self) -> List[Dict[str, Any]]:  # pragma: no cover - interface
        raise NotImplementedError


class StaticProvider(DiscoveryProvider):
    """Return the statically configured node list unchanged."""

    def __init__(self, nodes: List[Dict[str, Any]]):
        self._nodes = nodes or []

    async def discover(self) -> List[Dict[str, Any]]:
        return [
            {
                "node_id": n["node_id"],
                "host": n["host"],
                "port": n["port"],
                "capabilities": n.get("capabilities", []),
            }
            for n in self._nodes
        ]


class DNSProvider(DiscoveryProvider):
    """Resolve peers from DNS SRV records.

    ``service_name`` is a full SRV name, e.g. ``_smcp._tcp.example.com``. Each SRV
    target's hostname + port becomes a node; ``node_id`` defaults to the target
    hostname. ``capabilities`` (optional) is applied to every discovered node.
    """

    def __init__(self, service_name: str, capabilities: List[str] = None,
                 resolver=None):
        if not service_name:
            raise ValueError("dns discovery requires discovery_config.service_name")
        self.service_name = service_name
        self.capabilities = capabilities or []
        self._resolver = resolver  # injectable for tests

    def _resolve(self):
        if self._resolver is not None:
            return self._resolver(self.service_name, "SRV")
        try:
            import dns.resolver
        except ImportError as e:  # pragma: no cover - dep guard
            raise RuntimeError(
                "dns discovery requires the 'dnspython' package"
            ) from e
        return dns.resolver.resolve(self.service_name, "SRV")

    async def discover(self) -> List[Dict[str, Any]]:
        nodes = []
        for rec in self._resolve():
            host = str(getattr(rec, "target", "")).rstrip(".")
            try:
                port = int(getattr(rec, "port"))
            except (TypeError, ValueError):
                logger.warning("SRV record port is not an integer; skipping")
                continue
            if not host:
                continue
            nodes.append({
                "node_id": host,
                "host": host,
                "port": port,
                "capabilities": list(self.capabilities),
            })
        return nodes


class ConsulProvider(DiscoveryProvider):
    """Discover peers from Consul's health API.

    Queries ``GET {consul_url}/v1/health/service/{service_name}?passing=1`` and
    maps each healthy instance to a node.
    """

    def __init__(self, consul_url: str, service_name: str, capabilities: List[str] = None,
                 session_factory=None, allow_insecure: bool = False):
        if not consul_url or not service_name:
            raise ValueError("consul discovery requires consul_url and service_name")
        self.consul_url = consul_url.rstrip("/")
        self.service_name = service_name
        self.capabilities = capabilities or []
        self._session_factory = session_factory  # injectable for tests
        self.allow_insecure = allow_insecure

    async def discover(self) -> List[Dict[str, Any]]:
        url = f"{self.consul_url}/v1/health/service/{self.service_name}?passing=1"
        data = await _http_get_json(url, self._session_factory, self.allow_insecure)
        nodes = []
        for entry in data or []:
            svc = entry.get("Service", {})
            node = entry.get("Node", {})
            host = svc.get("Address") or node.get("Address")
            port = svc.get("Port")
            if not host or port is None:
                continue
            try:
                port = int(port)
            except (TypeError, ValueError):
                logger.warning("consul service port is not an integer; skipping")
                continue
            node_id = svc.get("ID") or svc.get("Service") or host
            caps = svc.get("Tags") or list(self.capabilities)
            nodes.append({
                "node_id": node_id,
                "host": host,
                "port": port,
                "capabilities": caps,
            })
        return nodes


class EtcdProvider(DiscoveryProvider):
    """Discover peers from an etcd v3 key prefix.

    Reads ``POST {etcd_url}/v3/kv/range`` over ``etcd_prefix``; each value is a
    JSON node document (``{"node_id","host","port","capabilities"}``).
    """

    def __init__(self, etcd_url: str, etcd_prefix: str, session_factory=None,
                 allow_insecure: bool = False):
        if not etcd_url or not etcd_prefix:
            raise ValueError("etcd discovery requires etcd_url and etcd_prefix")
        self.etcd_url = etcd_url.rstrip("/")
        self.etcd_prefix = etcd_prefix
        self._session_factory = session_factory  # injectable for tests
        self.allow_insecure = allow_insecure

    @staticmethod
    def _range_end(prefix: str) -> str:
        # etcd range_end for a prefix: increment the last byte.
        b = bytearray(prefix.encode())
        for i in range(len(b) - 1, -1, -1):
            if b[i] < 0xFF:
                b[i] += 1
                return base64.b64encode(bytes(b[: i + 1])).decode()
        return "\0"

    async def discover(self) -> List[Dict[str, Any]]:
        url = f"{self.etcd_url}/v3/kv/range"
        body = {
            "key": base64.b64encode(self.etcd_prefix.encode()).decode(),
            "range_end": self._range_end(self.etcd_prefix),
        }
        data = await _http_post_json(url, body, self._session_factory, self.allow_insecure)
        nodes = []
        for kv in (data or {}).get("kvs", []):
            raw = kv.get("value")
            if not raw:
                continue
            try:
                doc = json.loads(base64.b64decode(raw).decode())
            except (ValueError, json.JSONDecodeError):
                logger.warning("etcd value is not valid node JSON; skipping")
                continue
            if not doc.get("host") or doc.get("port") is None:
                continue
            try:
                port = int(doc["port"])
            except (TypeError, ValueError):
                logger.warning("etcd node port is not an integer; skipping")
                continue
            nodes.append({
                "node_id": doc.get("node_id") or doc["host"],
                "host": doc["host"],
                "port": port,
                "capabilities": doc.get("capabilities", []),
            })
        return nodes


_DISCOVERY_HTTP_TIMEOUT = 5  # seconds; a slow backend must not stall discovery


def _check_discovery_url(url: str, allow_insecure: bool):
    """Refuse plaintext discovery backends to non-loopback hosts (topology feeds
    are security-sensitive — a poisoned/MITM'd response controls routing), and
    reject non-http(s) schemes (SSRF hardening)."""
    from urllib.parse import urlparse
    from smcp_config import enforce_secure_url
    scheme = (urlparse(url).scheme or "").lower()
    if scheme not in ("http", "https"):
        raise ValueError(f"discovery url must be http(s): {url!r}")
    enforce_secure_url(url, allow_insecure=allow_insecure)


async def _http_get_json(url: str, session_factory=None, allow_insecure: bool = False):
    import aiohttp
    _check_discovery_url(url, allow_insecure)
    factory = session_factory or aiohttp.ClientSession
    timeout = aiohttp.ClientTimeout(total=_DISCOVERY_HTTP_TIMEOUT)
    try:
        async with factory() as session:
            async with session.get(url, timeout=timeout) as resp:
                return await resp.json()
    except TypeError:
        # Injected test sessions may not accept a timeout kwarg.
        async with factory() as session:
            async with session.get(url) as resp:
                return await resp.json()


async def _http_post_json(url: str, body: Dict[str, Any], session_factory=None,
                          allow_insecure: bool = False):
    import aiohttp
    _check_discovery_url(url, allow_insecure)
    factory = session_factory or aiohttp.ClientSession
    timeout = aiohttp.ClientTimeout(total=_DISCOVERY_HTTP_TIMEOUT)
    try:
        async with factory() as session:
            async with session.post(url, json=body, timeout=timeout) as resp:
                return await resp.json()
    except TypeError:
        async with factory() as session:
            async with session.post(url, json=body) as resp:
                return await resp.json()


def make_provider(discovery_method: str, nodes: List[Dict[str, Any]],
                  discovery_config: Dict[str, Any]) -> DiscoveryProvider:
    """Build the provider for a discovery method, or raise ValueError."""
    cfg = discovery_config or {}
    if discovery_method == "static":
        return StaticProvider(nodes)
    if discovery_method == "dns":
        return DNSProvider(cfg.get("service_name"), cfg.get("capabilities"))
    if discovery_method == "consul":
        return ConsulProvider(cfg.get("consul_url"), cfg.get("service_name"),
                              cfg.get("capabilities"),
                              allow_insecure=bool(cfg.get("allow_insecure", False)))
    if discovery_method == "etcd":
        return EtcdProvider(cfg.get("etcd_url"), cfg.get("etcd_prefix"),
                            allow_insecure=bool(cfg.get("allow_insecure", False)))
    raise ValueError(f"Unknown discovery_method: {discovery_method!r}")
