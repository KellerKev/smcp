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


from smcp_connector_base import QueryRequest, QueryType  # noqa: E402


def _query(c, sql, qtype=QueryType.SELECT):
    return asyncio.run(c.execute_query(
        QueryRequest(query_id="q", query_type=qtype, query=sql)))


def test_raw_query_file_read_blocked_by_default(tmp_path):
    # The critical sandbox-escape: raw execute_query must not reach host files
    # even though DuckDB's engine default for enable_external_access is True.
    secret = tmp_path / "secret.csv"
    secret.write_text("top,secret\n1,2\n")
    c = duck()
    asyncio.run(c.connect())
    r = _query(c, f"SELECT * FROM read_csv_auto('{secret}')")
    assert r.status == "error"
    assert "not permitted" in (r.error or "").lower()


def test_raw_query_copy_to_blocked_by_default(tmp_path):
    c = duck()
    asyncio.run(c.connect())
    out = tmp_path / "exfil.csv"
    r = _query(c, f"COPY (SELECT 1) TO '{out}'", QueryType.CUSTOM)
    assert r.status == "error"
    assert not out.exists()


def test_raw_query_httpfs_url_blocked_by_default():
    c = duck()
    asyncio.run(c.connect())
    r = _query(c, "SELECT * FROM read_csv_auto('https://evil.example.com/x.csv')")
    assert r.status == "error"


def test_normal_query_still_works():
    c = duck()
    asyncio.run(c.connect())
    r = _query(c, "SELECT 42 AS x")
    assert r.status == "success"
    assert r.data == [{"x": 42}]


def test_engine_external_access_flag_set_both_ways():
    # The flag must be explicitly present in the engine config regardless of
    # value (omitting it leaves DuckDB's insecure default of True in effect).
    off = duck()
    on = duck(enable_external_access=True)
    # Inspect by connecting and querying the effective engine setting.
    for c, expected in [(off, False), (on, True)]:
        asyncio.run(c.connect())
        val = c.connection.execute(
            "SELECT current_setting('enable_external_access')").fetchone()[0]
        assert bool(val) is expected, (expected, val)


def test_allow_raw_file_sql_opt_in(tmp_path):
    # Explicit opt-in permits raw file SQL.
    data = tmp_path / "d.csv"
    data.write_text("a,b\n1,2\n")
    c = duck(allow_raw_file_sql=True)
    asyncio.run(c.connect())
    r = _query(c, f"SELECT * FROM read_csv_auto('{data}')")
    assert r.status == "success"
    assert r.row_count == 1


# --------------------------------------------------------------------------- #
# Filesystem extension allowlist (must apply to read/delete/list, not just write)
# --------------------------------------------------------------------------- #
def test_read_disallowed_extension_blocked(tmp_path):
    base = tmp_path / "data"
    base.mkdir()
    (base / "creds.env").write_text("SECRET=1")
    c = fs(base)
    asyncio.run(c.connect())
    with pytest.raises(Exception) as exc:
        asyncio.run(c._read_file({"file_path": "creds.env"}))
    assert "extension not allowed" in str(exc.value).lower()


def test_delete_disallowed_extension_blocked(tmp_path):
    base = tmp_path / "data"
    base.mkdir()
    secret = base / "key.pem"
    secret.write_text("-----BEGIN-----")
    c = fs(base)
    asyncio.run(c.connect())
    with pytest.raises(Exception):
        asyncio.run(c._delete_file({"file_path": "key.pem"}))
    assert secret.exists()  # not deleted


def test_list_hides_disallowed_extensions(tmp_path):
    base = tmp_path / "data"
    base.mkdir()
    (base / "notes.txt").write_text("hi")
    (base / "creds.env").write_text("SECRET=1")
    c = fs(base)
    asyncio.run(c.connect())
    res = asyncio.run(c._list_files({"directory": "."}))
    names = {row["name"] for row in res["data"]}
    assert "notes.txt" in names
    assert "creds.env" not in names


def test_symlink_inside_base_pointing_outside_rejected(tmp_path):
    # Exercises the real containment branch (is_relative_to), not the ".." short
    # circuit: a symlink that lives inside base_path but resolves outside it.
    base = tmp_path / "data"
    base.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret")
    link = base / "escape.txt"
    try:
        link.symlink_to(outside / "secret.txt")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported on this platform")
    c = fs(base)
    asyncio.run(c.connect())
    with pytest.raises(Exception):
        asyncio.run(c._resolve_path("escape.txt"))


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
