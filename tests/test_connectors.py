"""Connector hardening tests: DuckDB SQL/path injection and filesystem traversal."""
import asyncio
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "connectors"))

duckdb = pytest.importorskip("duckdb")

from smcp_connector_base import ConnectorConfig, ConnectorType
from smcp_duckdb_connector import DuckDBConnector, _IDENTIFIER_RE


def duck(**params):
    base = {"database_path": ":memory:"}
    base.update(params)
    return DuckDBConnector(ConnectorConfig(
        name="d", connector_type=ConnectorType.DATABASE, connection_params=base))


def test_external_access_defaults_off():
    assert duck().enable_external_access is False


def test_identifier_regex():
    assert _IDENTIFIER_RE.match("users")
    assert not _IDENTIFIER_RE.match("users; DROP TABLE x")
    assert not _IDENTIFIER_RE.match("read_csv_auto('/etc/passwd')")


def test_malicious_identifier_rejected():
    c = duck()
    asyncio.run(c.connect())
    r = asyncio.run(c.create_table_from_file("t; DROP TABLE x; --", "data.csv"))
    assert r.status == "error"
    assert "identifier" in (r.error or "").lower()


def test_file_access_blocked_when_disabled():
    c = duck()
    asyncio.run(c.connect())
    r = asyncio.run(c.create_table_from_file("goodtable", "/etc/passwd"))
    assert r.status == "error"
    assert "disabled" in (r.error or "").lower()


def test_path_outside_data_dir_rejected():
    c = duck(enable_external_access=True, data_dir="/tmp")
    asyncio.run(c.connect())
    r = asyncio.run(c.create_table_from_file("goodtable", "/etc/passwd"))
    assert r.status == "error"
    assert "outside" in (r.error or "").lower()


# --------------------------------------------------------------------------- #
# Filesystem connector
# --------------------------------------------------------------------------- #
from smcp_filesystem_connector import FilesystemConnector  # noqa: E402


def fs(base, **params):
    p = {"base_path": str(base)}
    p.update(params)
    return FilesystemConnector(ConnectorConfig(
        name="fs", connector_type=ConnectorType.FILE, connection_params=p))


def test_sibling_prefix_not_treated_as_inside(tmp_path):
    base = tmp_path / "data"
    base.mkdir()
    (tmp_path / "data-evil").mkdir()
    c = fs(base)
    asyncio.run(c.connect())
    # ".." is rejected outright; also verify a sibling-prefix path can't escape.
    with pytest.raises(Exception):
        asyncio.run(c._resolve_path("../data-evil/secret.txt"))


def test_write_size_cap(tmp_path):
    base = tmp_path / "data"
    base.mkdir()
    c = fs(base, max_file_size=100)
    asyncio.run(c.connect())
    with pytest.raises(Exception) as exc:
        asyncio.run(c._write_file({"file_path": "big.txt", "content": "x" * 500}))
    assert "too large" in str(exc.value).lower()
    # A small write within the cap must still succeed.
    ok = asyncio.run(c._write_file({"file_path": "small.txt", "content": "hello"}))
    assert (base / "small.txt").exists()
