"""Security regression tests for the SMCP hardening work.

Each test pins one of the fixes from the production-security remediation so a
future change can't silently reintroduce a hole. Pure-Python; no network or
ollama required.
"""
import json
import secrets
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smcp_config import SMCPConfig, enforce_secure_url
from smcp_core import SMCPNode, SMCPSecurity, SMCPMessage, Capability, MessageType


def strong():
    return secrets.token_urlsafe(32)


def good_config(**over):
    kw = dict(api_key=strong(), secret_key=strong(), jwt_secret=strong(),
              kdf_salt=secrets.token_urlsafe(16))
    kw.update(over)
    return SMCPConfig(**kw)


# --------------------------------------------------------------------------- #
# validate()
# --------------------------------------------------------------------------- #
def test_empty_config_is_rejected():
    assert SMCPConfig().validate() != []


def test_strong_config_passes():
    assert good_config().validate() == []


@pytest.mark.parametrize("field,value", [
    ("api_key", "demo_key_123"),
    ("secret_key", "default_secret_key"),
    ("jwt_secret", "default_jwt_secret"),
    ("secret_key", "my_secret_key_2024"),
])
def test_known_published_secrets_rejected(field, value):
    issues = good_config(**{field: value}).validate()
    assert any(field in i for i in issues)


@pytest.mark.parametrize("field", ["secret_key", "jwt_secret"])
def test_short_secrets_rejected(field):
    issues = good_config(**{field: "tooshort"}).validate()
    assert any("too short" in i for i in issues)


def test_placeholder_prefixes_rejected():
    issues = good_config(api_key="CHANGE_ME_please", secret_key="your_secret_here_xxx").validate()
    assert any("api_key" in i for i in issues)
    assert any("secret_key" in i for i in issues)


def test_kdf_salt_required():
    issues = good_config(kdf_salt="").validate()
    assert any("kdf_salt" in i for i in issues)


def test_merge_configs_preserves_kdf_salt_and_mode():
    override = SMCPConfig()
    override.kdf_salt = "salt-preserved-1234"
    override.mode = "encrypted"
    merged = SMCPConfig.merge_configs(SMCPConfig(), override)
    assert merged.kdf_salt == "salt-preserved-1234"
    assert merged.mode == "encrypted"


# --------------------------------------------------------------------------- #
# auth backdoor removal + per-tool authorization
# --------------------------------------------------------------------------- #
def make_pair():
    sk, js, salt = strong(), strong(), secrets.token_urlsafe(16)
    api = "cfg_" + strong()
    server = SMCPNode("srv", sk, js, salt, api_key=api)
    client = SMCPNode("cli", sk, js, salt)  # shares channel secret in this model
    return server, client, api


def _decrypt(node, resp):
    if resp.encrypted and "encrypted_data" in resp.payload:
        return node.security.decrypt_payload(resp.payload["encrypted_data"])
    return resp.payload


def test_demo_key_backdoor_is_gone():
    server, client, _api = make_pair()
    msg = client.create_message(MessageType.AUTH, {"api_key": "demo_key_123"})
    resp = server.process_message(msg)
    assert resp.type == MessageType.ERROR


def test_configured_api_key_authenticates():
    server, client, api = make_pair()
    msg = client.create_message(MessageType.AUTH, {"api_key": api, "client_id": "c1"})
    resp = server.process_message(msg)
    assert _decrypt(server, resp).get("status") == "success"


def test_replay_is_rejected():
    server, client, api = make_pair()
    msg = client.create_message(MessageType.AUTH, {"api_key": api})
    wire = json.dumps(msg.to_dict())
    first = server.process_message(SMCPMessage.from_dict(json.loads(wire)))
    assert first.type == MessageType.AUTH
    replay = server.process_message(SMCPMessage.from_dict(json.loads(wire)))
    assert replay.type == MessageType.ERROR


def test_stale_message_is_rejected():
    server, client, api = make_pair()
    msg = client.create_message(MessageType.AUTH, {"api_key": api})
    msg.timestamp -= 10_000
    msg.signature = client.security.sign_message(msg)
    resp = server.process_message(msg)
    assert resp.type == MessageType.ERROR


def _authed_token(server, client, api):
    msg = client.create_message(MessageType.AUTH, {"api_key": api, "client_id": "c1"})
    return _decrypt(server, server.process_message(msg))["token"]


def _invoke(server, client, token, params):
    m = client.create_message(MessageType.TOOL_INVOKE,
                              {"token": token, "tool_name": "calc", "parameters": params})
    return _decrypt(server, server.process_message(m))


def register_calc(server):
    server.register_capability(
        Capability("calc", "calc", {
            "operation": {"type": "string", "enum": ["add", "sub"]},
            "a": {"type": "number"}, "b": {"type": "number"},
        }),
        lambda operation, a, b: a + b if operation == "add" else a - b,
    )


def test_parameter_validation_rejects_bad_input():
    server, client, api = make_pair()
    register_calc(server)
    token = _authed_token(server, client, api)
    assert _invoke(server, client, token, {"operation": "add", "a": 2, "b": 3})["result"] == 5
    assert "error" in _invoke(server, client, token, {"operation": "mul", "a": 2, "b": 3})
    assert "error" in _invoke(server, client, token, {"operation": "add", "a": "x", "b": 3})
    assert "error" in _invoke(server, client, token, {"operation": "add", "a": 2, "b": 3, "evil": 1})


def test_missing_param_allowed_without_required_list():
    """Schemas here don't encode required-ness; a param absent from the call is
    passed through to the handler (which supplies its own default), not rejected."""
    server, client, api = make_pair()
    server.register_capability(
        Capability("greet", "greet", {"name": {"type": "string"}}),
        lambda name="world": {"hi": name},
    )
    token = server.security.generate_jwt("c", ["tool_invoke"])
    m = client.create_message(MessageType.TOOL_INVOKE,
                              {"token": token, "tool_name": "greet", "parameters": {}})
    assert _decrypt(server, server.process_message(m))["result"] == {"hi": "world"}


def test_explicit_required_list_enforced():
    server, client, api = make_pair()
    server.register_capability(
        Capability("need", "need", {"x": {"type": "string"}, "required": ["x"]}),
        lambda x: {"got": x},
    )
    token = server.security.generate_jwt("c", ["tool_invoke"])
    m = client.create_message(MessageType.TOOL_INVOKE,
                              {"token": token, "tool_name": "need", "parameters": {}})
    assert "error" in _decrypt(server, server.process_message(m))


def test_per_tool_scope_enforced():
    server, client, api = make_pair()
    register_calc(server)
    good = server.security.generate_jwt("c", ["tool:calc"])
    bad = server.security.generate_jwt("c", ["tool:other"])
    assert _invoke(server, client, good, {"operation": "add", "a": 1, "b": 1})["result"] == 2
    assert "error" in _invoke(server, client, bad, {"operation": "add", "a": 1, "b": 1})


# --------------------------------------------------------------------------- #
# JWT hardening (aud/iss/exp) + asymmetric mode
# --------------------------------------------------------------------------- #
def test_jwt_rejects_wrong_issuer_audience():
    import jwt as pyjwt
    import time
    sec = SMCPSecurity(strong(), strong(), secrets.token_urlsafe(16))
    forged = pyjwt.encode({"client_id": "x", "permissions": ["tool_invoke"],
                           "iss": "evil", "aud": "evil",
                           "exp": time.time() + 60, "iat": time.time()},
                          sec.jwt_secret, algorithm="HS256")
    assert sec.verify_jwt(forged) is None


def test_rs256_client_cannot_mint_tokens():
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    d = Path(tempfile.mkdtemp())
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pk, pub = d / "jwt_private.pem", d / "jwt_public.pem"
    pk.write_bytes(priv.private_bytes(serialization.Encoding.PEM,
                   serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    pub.write_bytes(priv.public_key().public_bytes(serialization.Encoding.PEM,
                    serialization.PublicFormat.SubjectPublicKeyInfo))
    server = SMCPSecurity(strong(), strong(), secrets.token_urlsafe(16),
                          jwt_algorithm="RS256", jwt_private_key_path=str(pk),
                          jwt_public_key_path=str(pub))
    client = SMCPSecurity(strong(), strong(), secrets.token_urlsafe(16),
                          jwt_algorithm="RS256", jwt_public_key_path=str(pub))
    tok = server.generate_jwt("c", ["tool_invoke"])
    assert client.verify_jwt(tok) is not None
    with pytest.raises(ValueError):
        client.generate_jwt("evil", ["tool_invoke", "admin"])


# --------------------------------------------------------------------------- #
# TLS enforcement
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("url,allow,ok", [
    ("wss://host:1", False, True),
    ("https://host:1", False, True),
    ("ws://localhost:1", True, True),
    ("ws://localhost:1", False, False),
    ("ws://remote:1", True, False),
    ("http://evil.com", True, False),
])
def test_enforce_secure_url(url, allow, ok):
    if ok:
        enforce_secure_url(url, allow_insecure=allow)
    else:
        with pytest.raises(ValueError):
            enforce_secure_url(url, allow_insecure=allow)


# --------------------------------------------------------------------------- #
# server refuses insecure config at construction
# --------------------------------------------------------------------------- #
def test_server_refuses_insecure_config():
    from smcp_server import SMCPServer
    with pytest.raises(ValueError):
        SMCPServer(SMCPConfig(node_id="s"))


def test_v3_interop_vector_unchanged():
    import types
    sec = SMCPSecurity("interop-secret-value-32-bytes-xx", "jwt", "interop-salt")
    msg = types.SimpleNamespace(id="fixedid", type=types.SimpleNamespace(value="auth"),
                                timestamp=1700000000.0, payload={"x": 1})
    assert sec.sign_message(msg) == "661c3041e7cc52690927113ca9bc39c08899613f94e7d770addecd349374f8ca"


# --------------------------------------------------------------------------- #
# encrypted-flag tamper detection (flag isn't in the HMAC, but the payload is)
# --------------------------------------------------------------------------- #
def test_flipping_encrypted_flag_to_false_is_rejected():
    server, client, api = make_pair()
    # A real encrypted message carries {"encrypted_data": ...} in its payload.
    msg = client.create_message(MessageType.AUTH, {"api_key": api})
    assert msg.encrypted and "encrypted_data" in msg.payload
    # Attacker flips only the (unsigned) flag; the signed payload still shows
    # ciphertext, so the mismatch must be caught.
    msg.encrypted = False
    resp = server.process_message(msg)
    assert resp.type == MessageType.ERROR


def test_flipping_encrypted_flag_to_true_is_rejected():
    server, client, api = make_pair()
    msg = client.create_message(MessageType.AUTH, {"api_key": api}, encrypt=False)
    assert not msg.encrypted and "encrypted_data" not in msg.payload
    msg.encrypted = True  # claim encryption over a plaintext (signed) payload
    resp = server.process_message(msg)
    assert resp.type == MessageType.ERROR
