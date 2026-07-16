"""Validate the implementation against the published conformance vectors.

The vectors in conformance_vectors.json are the language-agnostic contract an
external implementer tests against (see docs/SMCP_PROTOCOL.md). This test proves
the Python reference reproduces them; a Rust/other implementation runs the same
checks against the same file.
"""
import json
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smcp_core import SMCPSecurity, PROTOCOL_VERSION

VECTORS = json.loads((Path(__file__).parent / "conformance_vectors.json").read_text())


def _sec():
    ks = VECTORS["key_schedule"]
    return SMCPSecurity(ks["secret_key"], "jwt", ks["kdf_salt"])


def test_protocol_version_matches():
    assert VECTORS["protocol_version"] == PROTOCOL_VERSION


def test_key_schedule_mac_key():
    assert _sec().mac_key.hex() == VECTORS["key_schedule"]["mac_key_hex"]


def test_signature_vectors():
    sec = _sec()
    for case in VECTORS["signatures"]:
        msg = types.SimpleNamespace(
            id=case["id"],
            type=types.SimpleNamespace(value=case["type"]),
            timestamp=case["timestamp"],
            payload=case["payload"],
        )
        assert sec.sign_message(msg) == case["signature"], case["id"]
