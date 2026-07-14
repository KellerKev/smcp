#!/usr/bin/env python3
"""Shared helpers for the SMCP example scripts.

The examples are loopback demos, but SMCP now (correctly) refuses to run with
empty/weak/publicly-known secrets and refuses plaintext transport to non-loopback
hosts. This module gives every example a consistent, *strong*, per-machine set of
demo secrets so a server and a client started as separate processes can still
talk to each other — without committing any secret to the repo.

Secrets are generated once and cached in a gitignored file
(examples/.demo_secrets.json). Delete that file to rotate them. You can also
override any of them via the standard SCP_* environment variables.
"""

import json
import os
import secrets as _secrets
import sys
from pathlib import Path

# Make the repo root importable when an example is run directly.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from smcp_config import SMCPConfig  # noqa: E402

_SECRETS_FILE = Path(__file__).resolve().parent / ".demo_secrets.json"


def load_or_create_demo_secrets() -> dict:
    """Return a dict of strong demo secrets, generating and caching them once.

    Environment variables (SCP_API_KEY / SCP_SECRET_KEY / SCP_JWT_SECRET /
    SCP_KDF_SALT) take precedence so CI or a user can pin their own values.
    """
    if _SECRETS_FILE.exists():
        data = json.loads(_SECRETS_FILE.read_text())
    else:
        data = {
            "api_key": _secrets.token_urlsafe(32),
            "secret_key": _secrets.token_urlsafe(32),
            "jwt_secret": _secrets.token_urlsafe(32),
            "kdf_salt": _secrets.token_urlsafe(16),
        }
        _SECRETS_FILE.write_text(json.dumps(data, indent=2))
        try:
            os.chmod(_SECRETS_FILE, 0o600)
        except OSError:
            pass

    # Environment overrides win.
    return {
        "api_key": os.getenv("SCP_API_KEY", data["api_key"]),
        "secret_key": os.getenv("SCP_SECRET_KEY", data["secret_key"]),
        "jwt_secret": os.getenv("SCP_JWT_SECRET", data["jwt_secret"]),
        "kdf_salt": os.getenv("SCP_KDF_SALT", data["kdf_salt"]),
    }


def demo_config(node_id: str,
                server_url: str = "ws://localhost:8765",
                mode: str = "simple",
                port: int = 8765) -> SMCPConfig:
    """Build a valid SMCPConfig for a loopback example.

    Uses the shared demo secrets and allows plaintext ws:// because the target is
    loopback (production must use wss:// — see SecurityConfig.tls_enabled).
    """
    s = load_or_create_demo_secrets()
    cfg = SMCPConfig(
        node_id=node_id,
        server_url=server_url,
        api_key=s["api_key"],
        secret_key=s["secret_key"],
        jwt_secret=s["jwt_secret"],
        kdf_salt=s["kdf_salt"],
        mode=mode,
    )
    cfg.server.port = port
    # Loopback demo only: permit ws:// (never allowed to a remote host).
    cfg.security.allow_insecure_transit = True
    return cfg


def apply_demo_secrets(cfg: SMCPConfig, node_id: str | None = None) -> SMCPConfig:
    """Set strong shared demo secrets on an already-built SMCPConfig.

    Use this when an example needs to pass its own oauth2/crypto/cluster kwargs
    to SMCPConfig() and therefore can't use demo_config() directly.
    """
    s = load_or_create_demo_secrets()
    cfg.api_key = s["api_key"]
    cfg.secret_key = s["secret_key"]
    cfg.jwt_secret = s["jwt_secret"]
    cfg.kdf_salt = s["kdf_salt"]
    if node_id:
        cfg.node_id = node_id
    cfg.security.allow_insecure_transit = True  # loopback demo only
    return cfg


# Small, fast model for example/test runs; override with SMCP_DEMO_MODEL.
DEMO_MODEL = os.getenv("SMCP_DEMO_MODEL", "llama3.2:1b")
