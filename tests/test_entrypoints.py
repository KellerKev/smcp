"""Guards that every module imports and both CLIs resolve their config class.

Regression for the SCPConfig NameError that made `python smcp_server_main.py`
and `python smcp_client_main.py` crash on startup, plus the misspelled
`scp_config` / `scp_federated_auth` imports.
"""
import importlib
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "connectors"))

MODULES = [
    "smcp_core", "smcp_config", "smcp_server", "smcp_client",
    "smcp_server_main", "smcp_client_main", "smcp_auth_enhanced",
    "smcp_federated_auth", "smcp_mcp_bridge", "smcp_distributed_a2a",
    "smcp_a2a", "smcp_a2a_server", "smcp_jwt_handshake",
    "smcp_simplified_handshake", "smcp_federated_ollama_demo",
    "smcp_duckdb_connector", "smcp_filesystem_connector",
]


@pytest.mark.parametrize("mod", MODULES)
def test_module_imports(mod):
    importlib.import_module(mod)


def test_entry_points_reference_resolvable_config():
    # SCPConfig must be importable (the alias) from both entry modules.
    import smcp_server_main
    import smcp_client_main
    assert getattr(smcp_server_main, "SCPConfig", None) is not None
    assert getattr(smcp_client_main, "SCPConfig", None) is not None


def test_server_cli_validate_only_runs():
    # The server CLI must reach validation instead of dying on NameError.
    r = subprocess.run(
        [sys.executable, str(ROOT / "smcp_server_main.py"), "--validate-only"],
        capture_output=True, text=True, cwd=str(ROOT), timeout=60,
    )
    combined = r.stdout + r.stderr
    assert "NameError" not in combined, combined
    assert "SCPConfig" not in combined or "not defined" not in combined
