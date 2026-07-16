"""Discovery provider tests.

DNS uses an injected resolver; Consul/etcd use an injected aiohttp-style session
factory — so every provider is unit-tested against a mocked backend without any
real DNS/Consul/etcd running. Real backends remain integration-only.
"""
import asyncio
import base64
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smcp_discovery import (
    StaticProvider, DNSProvider, ConsulProvider, EtcdProvider, make_provider,
)


# --- fake aiohttp session -------------------------------------------------- #
class _FakeResp:
    def __init__(self, payload):
        self._p = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def json(self):
        return self._p


class _FakeSession:
    def __init__(self, payload):
        self._p = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def get(self, url):
        return _FakeResp(self._p)

    def post(self, url, json=None):
        return _FakeResp(self._p)


def _factory(payload):
    return lambda: _FakeSession(payload)


# --- static ---------------------------------------------------------------- #
def test_static_provider():
    p = StaticProvider([{"node_id": "n1", "host": "h", "port": 9, "capabilities": ["x"]}])
    nodes = asyncio.run(p.discover())
    assert nodes == [{"node_id": "n1", "host": "h", "port": 9, "capabilities": ["x"]}]


# --- dns ------------------------------------------------------------------- #
def test_dns_provider_with_injected_resolver():
    def resolver(name, rtype):
        assert rtype == "SRV"
        return [
            SimpleNamespace(target="gpu1.example.com.", port=8766),
            SimpleNamespace(target="gpu2.example.com.", port=8767),
        ]
    p = DNSProvider("_smcp._tcp.example.com", capabilities=["ai"], resolver=resolver)
    nodes = asyncio.run(p.discover())
    assert {n["host"] for n in nodes} == {"gpu1.example.com", "gpu2.example.com"}
    assert nodes[0]["port"] == 8766
    assert nodes[0]["capabilities"] == ["ai"]


def test_dns_requires_service_name():
    with pytest.raises(ValueError):
        DNSProvider("")


# --- consul ---------------------------------------------------------------- #
def test_consul_provider_with_mocked_http():
    payload = [
        {"Node": {"Address": "10.0.0.1"},
         "Service": {"ID": "smcp-1", "Service": "smcp", "Address": "10.0.0.1",
                     "Port": 8765, "Tags": ["ai"]}},
        {"Node": {"Address": "10.0.0.2"},
         "Service": {"ID": "smcp-2", "Service": "smcp", "Port": 8766}},
    ]
    p = ConsulProvider("http://consul:8500", "smcp", session_factory=_factory(payload))
    nodes = asyncio.run(p.discover())
    assert nodes[0] == {"node_id": "smcp-1", "host": "10.0.0.1", "port": 8765, "capabilities": ["ai"]}
    # second entry falls back to Node.Address for host
    assert nodes[1]["host"] == "10.0.0.2" and nodes[1]["port"] == 8766


def test_consul_requires_url_and_service():
    with pytest.raises(ValueError):
        ConsulProvider("", "svc")


# --- etcd ------------------------------------------------------------------ #
def test_etcd_provider_with_mocked_http():
    def kv(doc):
        return {"value": base64.b64encode(json.dumps(doc).encode()).decode()}
    payload = {"kvs": [
        kv({"node_id": "gpu_1", "host": "10.0.0.3", "port": 8765, "capabilities": ["ai"]}),
        kv({"node_id": "store", "host": "10.0.0.4", "port": 8768}),
    ]}
    p = EtcdProvider("http://etcd:2379", "/smcp/nodes/", session_factory=_factory(payload))
    nodes = asyncio.run(p.discover())
    assert {n["node_id"] for n in nodes} == {"gpu_1", "store"}
    assert nodes[0]["capabilities"] == ["ai"]


def test_etcd_range_end_prefix():
    # range_end increments the last byte of the prefix.
    end = EtcdProvider._range_end("/smcp/nodes/")
    assert base64.b64decode(end) == b"/smcp/nodes0"  # '/' (0x2f) -> '0' (0x30)


# --- dispatcher ------------------------------------------------------------ #
def test_make_provider_dispatch():
    assert isinstance(make_provider("static", [], {}), StaticProvider)
    assert isinstance(make_provider("dns", [], {"service_name": "s"}), DNSProvider)
    assert isinstance(make_provider("consul", [], {"consul_url": "u", "service_name": "s"}), ConsulProvider)
    assert isinstance(make_provider("etcd", [], {"etcd_url": "u", "etcd_prefix": "/p/"}), EtcdProvider)
    with pytest.raises(ValueError):
        make_provider("bogus", [], {})


# --- registry integration -------------------------------------------------- #
def test_discover_nodes_merges_and_healthchecks(monkeypatch):
    from smcp_config import ClusterConfig
    from smcp_distributed_a2a import DistributedNodeRegistry, NodeStatus

    reg = DistributedNodeRegistry(ClusterConfig(
        simulate_distributed=False,
        discovery_method="dns",
        discovery_config={"service_name": "_smcp._tcp.example.com"},
    ))
    # Inject discovery results by patching the provider factory.
    import smcp_distributed_a2a as mod

    class _P:
        async def discover(self):
            return [{"node_id": "disc1", "host": "localhost", "port": 65001, "capabilities": []}]

    monkeypatch.setattr("smcp_discovery.make_provider", lambda *a, **k: _P())

    async def main():
        await reg.discover_nodes()
        assert "disc1" in reg.nodes
        # No server on that port -> health check marks it ERROR (real probe).
        assert reg.nodes["disc1"].status == NodeStatus.ERROR

    # Give the registry a real pool so health_check does a real probe.
    from smcp_distributed_transport import PeerConnectionPool
    from smcp_config import SMCPConfig
    import secrets
    c = SMCPConfig(node_id="x", api_key="cfg_" + secrets.token_urlsafe(24),
                   secret_key=secrets.token_urlsafe(32), jwt_secret=secrets.token_urlsafe(32),
                   kdf_salt=secrets.token_urlsafe(16))
    c.security.allow_insecure_transit = True
    reg.peer_pool = PeerConnectionPool(c)
    asyncio.run(main())
