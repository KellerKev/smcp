"""Tests that SMCPConfig.load()/merge_configs preserve every setting.

Regression guard for the bug where merge_configs copied only a handful of
security fields and none of oauth2/crypto/cluster, so a config file that
enabled TLS or OAuth2 was silently downgraded to plaintext / no-OAuth2.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smcp_config import SMCPConfig, SCPConfig


STRONG = dict(
    api_key="a_strong_unique_api_key_value_1234567",
    secret_key="a_strong_unique_secret_key_value_7890",
    jwt_secret="a_strong_unique_jwt_secret_value_abcd",
    kdf_salt="per_deploy_salt_value_efghij",
)


def _write(tmp_path, body):
    p = tmp_path / "cfg.toml"
    p.write_text(body)
    return str(p)


def test_scpconfig_alias_is_smcpconfig():
    assert SCPConfig is SMCPConfig


def test_load_preserves_tls_and_jwt_algorithm(tmp_path):
    cfg_file = _write(tmp_path, """
mode = "enterprise"
api_key = "a_strong_unique_api_key_value_1234567"
secret_key = "a_strong_unique_secret_key_value_7890"
jwt_secret = "a_strong_unique_jwt_secret_value_abcd"
kdf_salt = "per_deploy_salt_value_efghij"

[security]
tls_enabled = true
tls_cert_path = "/etc/ssl/cert.pem"
tls_key_path = "/etc/ssl/key.pem"
jwt_algorithm = "RS256"
allow_insecure_transit = false
""")
    c = SMCPConfig.load(cfg_file, use_env=False)
    assert c.security.tls_enabled is True
    assert c.security.tls_cert_path == "/etc/ssl/cert.pem"
    assert c.security.tls_key_path == "/etc/ssl/key.pem"
    assert c.security.jwt_algorithm == "RS256"


def test_load_preserves_oauth2_block(tmp_path):
    cfg_file = _write(tmp_path, """
mode = "enterprise"
api_key = "a_strong_unique_api_key_value_1234567"
secret_key = "a_strong_unique_secret_key_value_7890"
jwt_secret = "a_strong_unique_jwt_secret_value_abcd"
kdf_salt = "per_deploy_salt_value_efghij"

[oauth2]
enabled = true
audience = "scp_api"
issuer = "https://idp.example.com/"
jwks_url = "https://idp.example.com/.well-known/jwks.json"
""")
    c = SMCPConfig.load(cfg_file, use_env=False)
    assert c.oauth2.enabled is True
    assert c.oauth2.audience == "scp_api"
    assert c.oauth2.issuer == "https://idp.example.com/"
    assert c.oauth2.jwks_url.endswith("/jwks.json")
    assert c.mode == "enterprise"


def test_load_preserves_crypto_and_cluster(tmp_path):
    cfg_file = _write(tmp_path, """
api_key = "a_strong_unique_api_key_value_1234567"
secret_key = "a_strong_unique_secret_key_value_7890"
jwt_secret = "a_strong_unique_jwt_secret_value_abcd"
kdf_salt = "per_deploy_salt_value_efghij"

[crypto]
key_exchange = "ecdh"
perfect_forward_secrecy = true

[cluster]
enabled = true
simulate_distributed = true
""")
    c = SMCPConfig.load(cfg_file, use_env=False)
    assert c.crypto.key_exchange == "ecdh"
    assert c.crypto.perfect_forward_secrecy is True
    assert c.cluster.enabled is True
    assert c.cluster.simulate_distributed is True


def test_merge_does_not_clobber_base_with_defaults():
    base = SMCPConfig(**STRONG)
    base.security.tls_enabled = True
    base.oauth2.enabled = True
    # A fresh override (all defaults) must NOT reset base's non-default values.
    override = SMCPConfig()
    merged = SMCPConfig.merge_configs(base, override)
    assert merged.security.tls_enabled is True
    assert merged.oauth2.enabled is True
    assert merged.api_key == STRONG["api_key"]


def test_to_file_roundtrips_enterprise_blocks(tmp_path):
    c = SMCPConfig(mode="enterprise", **STRONG)
    c.security.tls_enabled = True
    c.oauth2.enabled = True
    c.oauth2.audience = "scp_api"
    c.crypto.key_exchange = "ecdh"
    out = tmp_path / "out.toml"
    c.to_file(str(out))
    c2 = SMCPConfig.from_file(str(out))
    assert c2.security.tls_enabled is True
    assert c2.oauth2.enabled is True
    assert c2.oauth2.audience == "scp_api"
    assert c2.crypto.key_exchange == "ecdh"
    assert c2.mode == "enterprise"
