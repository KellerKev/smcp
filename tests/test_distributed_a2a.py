"""Real multi-node A2A over the SMCP WebSocket transport.

These tests stand up actual SMCPServers on loopback ports and drive cross-node
calls over real sockets (no in-process DEMO_FEDERATION_NODES mock, no simulated
node registry). They also lock in the sync/async correctness fixes.
"""
import asyncio
import secrets
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from smcp_config import SMCPConfig, ClusterConfig
from smcp_core import Capability
from smcp_a2a import SMCPAgent, AgentInfo, AgentRegistry, Task
from smcp_distributed_a2a import DistributedA2AAgent, DistributedNodeRegistry, DistributedNode, NodeStatus
from smcp_distributed_transport import (
    PeerConnectionPool, DistributedTaskServer, DISTRIBUTED_TASK_TOOL, peer_server_url,
)

SK, JS, SALT = secrets.token_urlsafe(32), secrets.token_urlsafe(32), secrets.token_urlsafe(16)
API = "cfg_" + secrets.token_urlsafe(24)


def cfg(node_id, port=None):
    c = SMCPConfig(node_id=node_id, api_key=API, secret_key=SK, jwt_secret=JS, kdf_salt=SALT,
                   server_url=f"ws://localhost:{port or 8765}")
    c.security.allow_insecure_transit = True  # loopback plaintext for tests
    return c


def agent_info(node_id):
    return AgentInfo(agent_id=node_id, name=node_id, description="test",
                     specialties=["echo"], capabilities=["echo"])


# --------------------------------------------------------------------------- #
# Transport primitive: real socket round-trip
# --------------------------------------------------------------------------- #
def test_peer_pool_roundtrip_over_real_socket():
    async def main():
        def dispatch(task):
            td = task.get("task_data", {})
            return {"sum": td.get("a", 0) + td.get("b", 0), "by": "nodeB"}
        server = DistributedTaskServer(cfg("nodeB", 8821), dispatch)
        await server.start(host="localhost", port=8821)
        pool = PeerConnectionPool(cfg("nodeA"))
        try:
            result = await pool.call("nodeB", "localhost", 8821, DISTRIBUTED_TASK_TOOL,
                                     task={"task_type": "add", "task_data": {"a": 20, "b": 22}})
            assert result == {"sum": 42, "by": "nodeB"}
        finally:
            await pool.close_all()
            await server.stop()
    asyncio.run(main())


def test_peer_pool_health_live_and_dead():
    async def main():
        server = DistributedTaskServer(cfg("nodeB", 8822), lambda task: {"ok": True})
        await server.start(host="localhost", port=8822)
        pool = PeerConnectionPool(cfg("nodeA"))
        try:
            assert await pool.health("nodeB", "localhost", 8822) is True
            assert await pool.health("ghost", "localhost", 9) is False
        finally:
            await pool.close_all()
            await server.stop()
    asyncio.run(main())


def test_peer_url_scheme():
    assert peer_server_url("h", 1, False) == "ws://h:1"
    assert peer_server_url("h", 1, True) == "wss://h:1"


# --------------------------------------------------------------------------- #
# Registry health + discovery over the real transport
# --------------------------------------------------------------------------- #
def test_registry_health_check_real(monkeypatch):
    async def main():
        server = DistributedTaskServer(cfg("nodeB", 8823), lambda task: {"ok": True})
        await server.start(host="localhost", port=8823)
        reg = DistributedNodeRegistry(ClusterConfig(
            simulate_distributed=False,
            nodes=[{"node_id": "nodeB", "host": "localhost", "port": 8823},
                   {"node_id": "dead", "host": "localhost", "port": 9}],
        ))
        reg.peer_pool = PeerConnectionPool(cfg("nodeA"))
        try:
            await reg.discover_nodes()
            assert reg.nodes["nodeB"].status == NodeStatus.ONLINE
            assert reg.nodes["dead"].status == NodeStatus.ERROR
        finally:
            await reg.peer_pool.close_all()
            await server.stop()
    asyncio.run(main())


def test_unknown_discovery_method_raises():
    async def main():
        reg = DistributedNodeRegistry(ClusterConfig(simulate_distributed=False,
                                                    discovery_method="bogus"))
        with pytest.raises(ValueError):
            await reg.discover_nodes()
    asyncio.run(main())


def test_consul_discovery_without_config_raises():
    # Consul is implemented now, but requires consul_url + service_name.
    async def main():
        reg = DistributedNodeRegistry(ClusterConfig(simulate_distributed=False,
                                                    discovery_method="consul"))
        with pytest.raises(ValueError):
            await reg.discover_nodes()
    asyncio.run(main())


# --------------------------------------------------------------------------- #
# Real dispatch (A4) — no fabricated output, no TypeError
# --------------------------------------------------------------------------- #
def test_execute_task_dispatches_to_real_handler():
    a = SMCPAgent(cfg("solo"), agent_info("solo"), AgentRegistry())
    a.register_capability(
        Capability(name="echo", description="", parameters={"msg": {"type": "string"}}),
        lambda msg: {"echoed": msg},
    )
    result = a._execute_task(Task(task_id="t1", type="echo", description="", input_data={"msg": "hi"}),
                             a.agent_info)
    assert result == {"echoed": "hi"}


# --------------------------------------------------------------------------- #
# P1a: distributed dispatch authorizes the inner task_type
# --------------------------------------------------------------------------- #
def _dist_agent(node_id, port):
    reg = DistributedNodeRegistry(ClusterConfig(simulate_distributed=False))
    a = DistributedA2AAgent(cfg(node_id, port), agent_info(node_id), reg, encrypted_storage=False)
    a.register_capability(
        Capability(name="echo", description="", parameters={"msg": {"type": "string"}}),
        lambda msg: {"echoed": msg})
    return a


def test_distributed_dispatch_allows_app_handler():
    a = _dist_agent("n1", 8861)
    assert a._distributed_dispatch({"task_type": "echo", "task_data": {"msg": "hi"}}) == {"echoed": "hi"}


def test_distributed_dispatch_blocks_control_plane():
    # A peer authorized only for distributed_task_execute must not be able to
    # invoke control-plane capabilities (lateral movement).
    a = _dist_agent("n1", 8862)
    for cap in ("cross_server_delegate", "distributed_workflow", "multi_server_collaboration"):
        r = a._distributed_dispatch({"task_type": cap, "task_data": {}})
        assert r.get("status") == "error", cap


def test_distributed_dispatch_respects_explicit_allowlist():
    a = _dist_agent("n1", 8863)
    a.remote_task_allowlist = set()  # nothing remotely invocable
    r = a._distributed_dispatch({"task_type": "echo", "task_data": {"msg": "x"}})
    assert r.get("status") == "error"


def test_execute_task_no_handler_is_honest():
    a = SMCPAgent(cfg("solo"), agent_info("solo"), AgentRegistry())
    result = a._execute_task(Task(task_id="t1", type="unknown", description="", input_data={}),
                             a.agent_info)
    assert result["status"] == "no_handler"
    # No fabricated analysis/research fields.
    assert "analysis_result" not in result and "research_findings" not in result


# --------------------------------------------------------------------------- #
# Full DistributedA2AAgent: real cross-node execution over sockets
# --------------------------------------------------------------------------- #
def test_distributed_agent_cross_node_real():
    async def main():
        # Node B receives and executes for real.
        regB = DistributedNodeRegistry(ClusterConfig(simulate_distributed=False))
        agentB = DistributedA2AAgent(cfg("nodeB", 8824), agent_info("nodeB"), regB,
                                     encrypted_storage=False)
        agentB.register_capability(
            Capability(name="echo", description="", parameters={"msg": {"type": "string"}}),
            lambda msg: {"echoed": msg, "on": "nodeB"},
        )
        serverB = agentB.make_task_server(cfg("nodeB", 8824))
        await serverB.start(host="localhost", port=8824)

        # Node A sends to B over a real socket.
        regA = DistributedNodeRegistry(ClusterConfig(
            simulate_distributed=False,
            nodes=[{"node_id": "nodeB", "host": "localhost", "port": 8824, "capabilities": ["echo"]}],
        ))
        agentA = DistributedA2AAgent(cfg("nodeA", 8825), agent_info("nodeA"), regA,
                                     encrypted_storage=False)
        target = regA.nodes["nodeB"]
        try:
            result = await agentA._real_cross_server_request(
                target, {"task_id": "x", "task_type": "echo", "task_data": {"msg": "ping"}})
            assert result == {"echoed": "ping", "on": "nodeB"}
        finally:
            await agentA.peer_pool.close_all()
            await serverB.stop()
    asyncio.run(main())
