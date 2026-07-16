"""Tests for the federated auth hardening.

Covers the previously-untested module: audience/issuer binding on client JWTs,
forwarding-proof signing/verification, target-node binding (a proof for node A
must not verify at node B), replay prevention, and tamper detection.
"""
import sys
import time
from pathlib import Path

import jwt
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smcp_config import SMCPConfig
from smcp_federated_auth import (
    FederatedAuthManager,
    create_test_jwt,
    mint_client_jwt,
    FEDERATION_ISSUER,
    FEDERATION_AUDIENCE,
)

SECRET = "federation_shared_secret_for_tests_0001"


def _config():
    return SMCPConfig(
        node_id="node",
        jwt_secret=SECRET,
        secret_key="test_secret_key_for_session_negotiation_00",
        kdf_salt="test_kdf_salt_00",
    )


def _mgr(node_id="node_a"):
    return FederatedAuthManager(_config(), node_id)


def _jwt(**over):
    kw = dict(user="alice@corp", permissions=["task:*"],
              forwarding_allowed=["*"], secret=SECRET)
    kw.update(over)
    return create_test_jwt(**kw)


# --------------------------------------------------------------------------- #
# Client JWT validation
# --------------------------------------------------------------------------- #
def test_valid_client_jwt_accepted():
    payload = _mgr().validate_client_jwt(_jwt())
    assert payload["user"] == "alice@corp"


def test_jwt_wrong_audience_rejected():
    bad = jwt.encode(
        {"user": "e", "permissions": ["task:*"], "iss": FEDERATION_ISSUER,
         "aud": "some-other-service", "iat": time.time(), "exp": time.time() + 60},
        SECRET, algorithm="HS256")
    with pytest.raises(jwt.InvalidTokenError):
        _mgr().validate_client_jwt(bad)


def test_jwt_wrong_issuer_rejected():
    bad = jwt.encode(
        {"user": "e", "permissions": ["task:*"], "iss": "evil-issuer",
         "aud": FEDERATION_AUDIENCE, "iat": time.time(), "exp": time.time() + 60},
        SECRET, algorithm="HS256")
    with pytest.raises(jwt.InvalidTokenError):
        _mgr().validate_client_jwt(bad)


def test_jwt_missing_aud_iss_rejected():
    bad = jwt.encode(
        {"user": "e", "permissions": ["task:*"],
         "iat": time.time(), "exp": time.time() + 60},
        SECRET, algorithm="HS256")
    with pytest.raises(jwt.InvalidTokenError):
        _mgr().validate_client_jwt(bad)


def test_jwt_wrong_secret_rejected():
    bad = _jwt(secret="a_different_secret_a_compromised_node_has")
    with pytest.raises(jwt.InvalidTokenError):
        _mgr().validate_client_jwt(bad)


def test_expired_jwt_rejected():
    bad = jwt.encode(
        {"user": "e", "permissions": ["task:*"], "iss": FEDERATION_ISSUER,
         "aud": FEDERATION_AUDIENCE, "iat": time.time() - 120, "exp": time.time() - 60},
        SECRET, algorithm="HS256")
    with pytest.raises(jwt.ExpiredSignatureError):
        _mgr().validate_client_jwt(bad)


# --------------------------------------------------------------------------- #
# Forwarding proofs
# --------------------------------------------------------------------------- #
def test_forwarding_proof_roundtrip():
    m = _mgr("node_a")
    proof = m.create_forwarding_proof(_jwt(), {"type": "ai_reasoning"}, "node_b")
    signed = m.sign_forwarding_proof(proof)
    # The intended target verifies it.
    receiver = FederatedAuthManager(_config(), "node_b")
    ok, out = receiver.verify_forwarding_proof(signed)
    assert ok and out.forwarded_to == "node_b"


def test_forwarding_proof_target_binding():
    # A proof minted for node_b must NOT verify at node_c (replay to a
    # different node), even though both share the secret.
    m = _mgr("node_a")
    proof = m.create_forwarding_proof(_jwt(), {"type": "ai_reasoning"}, "node_b")
    signed = m.sign_forwarding_proof(proof)
    wrong_target = FederatedAuthManager(_config(), "node_c")
    ok, out = wrong_target.verify_forwarding_proof(signed)
    assert not ok


def test_forwarding_proof_tamper_rejected():
    m = _mgr("node_a")
    proof = m.create_forwarding_proof(_jwt(), {"type": "ai_reasoning"}, "node_b")
    signed = m.sign_forwarding_proof(proof)
    signed["proof"]["forwarded_by"] = "attacker_node"  # tamper without re-signing
    receiver = FederatedAuthManager(_config(), "node_b")
    ok, _ = receiver.verify_forwarding_proof(signed)
    assert not ok


def test_forwarding_proof_replay_rejected():
    m = _mgr("node_a")
    proof = m.create_forwarding_proof(_jwt(), {"type": "ai_reasoning"}, "node_b")
    signed = m.sign_forwarding_proof(proof)
    receiver = FederatedAuthManager(_config(), "node_b")
    ok1, _ = receiver.verify_forwarding_proof(signed)
    ok2, _ = receiver.verify_forwarding_proof(signed)  # same nonce again
    assert ok1 and not ok2


# --------------------------------------------------------------------------- #
# RS256 verify-only posture
# --------------------------------------------------------------------------- #
def test_rs256_requires_public_key():
    cfg = _config()
    cfg.security.jwt_algorithm = "RS256"
    cfg.security.jwt_public_key_path = None
    with pytest.raises(ValueError):
        FederatedAuthManager(cfg, "node_a")


# --------------------------------------------------------------------------- #
# RS256 real issuer: mint with private key, verify with public key
# --------------------------------------------------------------------------- #
def _rsa_keypair(tmp_path):
    from tools.generate_jwt_keys import generate_rsa_keypair
    priv, pub = generate_rsa_keypair(2048)
    priv_path = tmp_path / "priv.pem"
    pub_path = tmp_path / "pub.pem"
    priv_path.write_bytes(priv)
    pub_path.write_bytes(pub)
    return priv_path, pub_path


def _rs256_config(pub_path):
    cfg = _config()
    cfg.security.jwt_algorithm = "RS256"
    cfg.security.jwt_public_key_path = str(pub_path)
    return cfg


def test_rs256_minted_token_verifies(tmp_path):
    priv_path, pub_path = _rsa_keypair(tmp_path)
    mgr = FederatedAuthManager(_rs256_config(pub_path), "verifier")
    token = mint_client_jwt("alice@corp", ["task:*"], private_key_path=str(priv_path))
    payload = mgr.validate_client_jwt(token)
    assert payload["user"] == "alice@corp"


def test_federation_rs256_via_dedicated_fields(tmp_path):
    # RS256 federation verification via federation_jwt_* fields, which do NOT
    # touch the transport JWT — so the transport can still mint session tokens.
    priv_path, pub_path = _rsa_keypair(tmp_path)
    cfg = _config()
    cfg.security.federation_jwt_algorithm = "RS256"
    cfg.security.federation_jwt_public_key_path = str(pub_path)
    # Transport JWT stays the default HS256 (mints session tokens fine).
    assert cfg.security.jwt_algorithm == "HS256"
    mgr = FederatedAuthManager(cfg, "verifier")
    token = mint_client_jwt("bob@corp", ["task:*"], private_key_path=str(priv_path))
    assert mgr.validate_client_jwt(token)["user"] == "bob@corp"


def test_rs256_federation_token_with_hs256_transport_end_to_end(tmp_path):
    # The previously-broken combination: RS256-issued client tokens verified by
    # peers, while the transport server mints its own HS256 session tokens.
    from smcp_federated_auth import FederatedSCPNode
    import secrets as _secrets

    issuer_priv, issuer_pub = _rsa_keypair(tmp_path)  # federation issuer key
    a_priv, a_pub = _proof_keypair(tmp_path, "nodeA")
    b_priv, b_pub = _proof_keypair(tmp_path, "nodeB")
    api = "cfg_" + _secrets.token_urlsafe(24)
    shared = dict(api_key=api, jwt_secret=SECRET,
                  secret_key=_secrets.token_urlsafe(32),
                  kdf_salt=_secrets.token_urlsafe(16))

    def cfg(proof_key):
        c = SMCPConfig(node_id="n", **shared)
        c.security.allow_insecure_transit = True
        c.security.federation_jwt_algorithm = "RS256"           # verify client tokens
        c.security.federation_jwt_public_key_path = str(issuer_pub)
        c.security.proof_signing_key_path = str(proof_key)
        # transport jwt_algorithm stays HS256 -> session tokens mint fine
        return c

    async def main():
        A = FederatedSCPNode(cfg(a_priv), "nodeA")
        B = FederatedSCPNode(cfg(b_priv), "nodeB")
        serverB = B.make_forward_server(cfg(b_priv))
        await serverB.start(host="localhost", port=8843)
        A.enable_real_transport(cfg(a_priv))
        A.add_peer("nodeB", "ws://localhost:8843", proof_public_key_path=str(b_pub))
        B.add_peer("nodeA", "ws://localhost:8844", proof_public_key_path=str(a_pub))
        token = mint_client_jwt("alice@corp", ["task:*"], ["node*"],
                                private_key_path=str(issuer_priv))
        try:
            r = await A.forward_request({"task_id": "t", "type": "ai_reasoning"}, "nodeB", token)
            assert r["status"] == "success", r
        finally:
            await serverB.stop()
            await A.peer_pool.close_all()

    asyncio.run(main())


def test_rs256_rejects_hs256_forgery(tmp_path):
    # Under RS256 pinning, an HS256-signed token (the shared-secret forgery a
    # compromised node might attempt) must be rejected.
    priv_path, pub_path = _rsa_keypair(tmp_path)
    mgr = FederatedAuthManager(_rs256_config(pub_path), "verifier")
    forged = jwt.encode(
        {"user": "eve", "permissions": ["task:*"], "iss": FEDERATION_ISSUER,
         "aud": FEDERATION_AUDIENCE, "iat": time.time(), "exp": time.time() + 60},
        "guessed-secret-that-is-long-enough-to-avoid-warnings", algorithm="HS256")
    with pytest.raises(jwt.InvalidTokenError):
        mgr.validate_client_jwt(forged)


def test_rs256_verifier_cannot_mint(tmp_path):
    # A verify-only node holds only the public key; minting requires the private
    # key, so mint_client_jwt with the public key must fail.
    _priv_path, pub_path = _rsa_keypair(tmp_path)
    with pytest.raises(Exception):
        mint_client_jwt("mallory", ["task:*"], private_key_path=str(pub_path))


def test_mint_requires_a_key():
    with pytest.raises(ValueError):
        mint_client_jwt("bob", ["task:*"])


# --------------------------------------------------------------------------- #
# Per-node asymmetric forwarding proofs
# --------------------------------------------------------------------------- #
from smcp_federated_auth import ForwardingProof  # noqa: E402


def _proof_keypair(tmp_path, name):
    from tools.generate_jwt_keys import generate_rsa_keypair
    priv, pub = generate_rsa_keypair(2048)
    d = tmp_path / name
    d.mkdir()
    (d / "priv.pem").write_bytes(priv)
    (d / "pub.pem").write_bytes(pub)
    return d / "priv.pem", d / "pub.pem"


def _proof_config(priv_path=None):
    cfg = _config()
    if priv_path:
        cfg.security.proof_signing_key_path = str(priv_path)
    return cfg


def _proof(signer, target="nodeB"):
    return ForwardingProof(client_jwt="x", forwarded_by=signer, forwarded_at=0.0,
                           task_hash="h", forwarded_to=target)


def test_asymmetric_proof_verifies_with_registered_key(tmp_path):
    a_priv, a_pub = _proof_keypair(tmp_path, "A")
    A = FederatedAuthManager(_proof_config(a_priv), "nodeA")
    B = FederatedAuthManager(_proof_config(), "nodeB")
    B.register_peer_public_key("nodeA", str(a_pub))
    signed = A.sign_forwarding_proof(_proof("nodeA"))
    assert signed["sig_alg"] == "PS256"
    ok, _ = B.verify_forwarding_proof(signed)
    assert ok


def test_asymmetric_proof_forgery_rejected(tmp_path):
    # Attacker signs with a DIFFERENT key but claims forwarded_by=nodeA.
    a_priv, a_pub = _proof_keypair(tmp_path, "A")
    c_priv, _c_pub = _proof_keypair(tmp_path, "C")
    B = FederatedAuthManager(_proof_config(), "nodeB")
    B.register_peer_public_key("nodeA", str(a_pub))
    attacker = FederatedAuthManager(_proof_config(c_priv), "attacker")
    forged = attacker.sign_forwarding_proof(_proof("nodeA"))  # claims to be nodeA
    ok, _ = B.verify_forwarding_proof(forged)
    assert not ok


def test_asymmetric_proof_unknown_signer_rejected(tmp_path):
    a_priv, _a_pub = _proof_keypair(tmp_path, "A")
    A = FederatedAuthManager(_proof_config(a_priv), "nodeA")
    B = FederatedAuthManager(_proof_config(), "nodeB")  # no key registered for anyone
    signed = A.sign_forwarding_proof(_proof("nodeA"))
    ok, _ = B.verify_forwarding_proof(signed)
    assert not ok


def test_hmac_fallback_when_no_proof_keys():
    # Without proof keys, proofs use the shared-secret HMAC and still verify.
    A = FederatedAuthManager(_proof_config(), "nodeA")
    B = FederatedAuthManager(_proof_config(), "nodeB")  # same jwt_secret via _config()
    signed = A.sign_forwarding_proof(_proof("nodeA", target=""))
    assert signed["sig_alg"] == "HS256"
    ok, _ = B.verify_forwarding_proof(signed)
    assert ok


# --------------------------------------------------------------------------- #
# Forward-secret ECDH session keys
# --------------------------------------------------------------------------- #
import asyncio  # noqa: E402


def _pfs_config():
    cfg = _config()
    cfg.crypto.perfect_forward_secrecy = True
    return cfg


def test_ecdh_exchange_derives_matching_keys():
    A = FederatedAuthManager(_pfs_config(), "nodeA")
    B = FederatedAuthManager(_pfs_config(), "nodeB")

    async def ex(my_pub_hex):
        return B.perform_ecdh_exchange("nodeA", my_pub_hex)

    ka = asyncio.run(A.negotiate_session_key("nodeB", "jwt", exchange_fn=ex))
    kb = B.session_keys["nodeA"]
    assert ka.key == kb.key and len(ka.key) == 32


def test_ecdh_forward_secrecy_new_key_per_session():
    A = FederatedAuthManager(_pfs_config(), "nodeA")
    B = FederatedAuthManager(_pfs_config(), "nodeB")

    async def ex(my_pub_hex):
        return B.perform_ecdh_exchange("nodeA", my_pub_hex)

    k1 = asyncio.run(A.negotiate_session_key("nodeB", "jwt", exchange_fn=ex))
    A.session_keys.clear(); B.session_keys.clear()
    k2 = asyncio.run(A.negotiate_session_key("nodeB", "jwt", exchange_fn=ex))
    assert k1.key != k2.key  # ephemeral keys discarded => fresh key each session


def test_ecdh_encrypt_decrypt_roundtrip():
    A = FederatedAuthManager(_pfs_config(), "nodeA")
    B = FederatedAuthManager(_pfs_config(), "nodeB")

    async def ex(my_pub_hex):
        return B.perform_ecdh_exchange("nodeA", my_pub_hex)

    ka = asyncio.run(A.negotiate_session_key("nodeB", "jwt", exchange_fn=ex))
    enc = A.encrypt_with_session_key({"msg": "secret"}, ka)
    assert B.decrypt_with_session_key(enc, "nodeA") == {"msg": "secret"}


def test_no_pfs_uses_shared_secret_hkdf():
    # With PFS off, both sides derive the same key from the shared secret (no
    # exchange needed) — preserves the previous behaviour.
    A = FederatedAuthManager(_config(), "nodeA")
    B = FederatedAuthManager(_config(), "nodeB")
    ka = asyncio.run(A.negotiate_session_key("nodeB", "jwt"))
    kb = asyncio.run(B.negotiate_session_key("nodeA", "jwt"))
    assert ka.key == kb.key


# --------------------------------------------------------------------------- #
# End-to-end: real WS transport + forward-secret ECDH + per-node asymmetric proof
# --------------------------------------------------------------------------- #
def test_federated_forward_pfs_asymmetric_over_real_socket(tmp_path):
    from smcp_federated_auth import FederatedSCPNode
    import secrets as _secrets

    api = "cfg_" + _secrets.token_urlsafe(24)
    shared = dict(api_key=api, jwt_secret=SECRET,
                  secret_key=_secrets.token_urlsafe(32),
                  kdf_salt=_secrets.token_urlsafe(16))
    a_priv, a_pub = _proof_keypair(tmp_path, "nodeA")
    b_priv, b_pub = _proof_keypair(tmp_path, "nodeB")

    def cfg(proof_key):
        c = SMCPConfig(node_id="n", **shared)
        c.security.allow_insecure_transit = True
        c.security.proof_signing_key_path = str(proof_key)
        c.crypto.perfect_forward_secrecy = True
        return c

    async def main():
        A = FederatedSCPNode(cfg(a_priv), "nodeA")
        B = FederatedSCPNode(cfg(b_priv), "nodeB")
        serverB = B.make_forward_server(cfg(b_priv))
        await serverB.start(host="localhost", port=8841)
        A.enable_real_transport(cfg(a_priv))
        A.add_peer("nodeB", "ws://localhost:8841", proof_public_key_path=str(b_pub))
        B.add_peer("nodeA", "ws://localhost:8842", proof_public_key_path=str(a_pub))
        tok = create_test_jwt("alice@corp", ["task:*"], ["node*"], secret=SECRET)
        try:
            r = await A.forward_request({"task_id": "t", "type": "ai_reasoning"}, "nodeB", tok)
            assert r["status"] == "success", r
            assert r["processed_by"] == "nodeB"
            # A real ECDH session key was established on both ends.
            assert "nodeB" in A.auth_manager.session_keys
            assert "nodeA" in B.auth_manager.session_keys
        finally:
            await serverB.stop()
            await A.peer_pool.close_all()

    asyncio.run(main())
