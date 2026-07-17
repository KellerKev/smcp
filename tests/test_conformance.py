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


# --------------------------------------------------------------------------- #
# Federation vectors — the same file the Rust (malgra) side verifies against.
# --------------------------------------------------------------------------- #
FED = json.loads((Path(__file__).parent / "federation_conformance_vectors.json").read_text())


def test_federation_proof_hmac_vector():
    import hmac as _hmac, hashlib
    canonical = FED["proof_canonical_message"]
    secret = FED["proof_hmac"]["secret"]
    sig = _hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
    assert sig == FED["proof_hmac"]["signature"]


def test_federation_ecdh_vector():
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    import hashlib
    e = FED["ecdh"]
    a = ec.derive_private_key(int(e["priv_a_scalar_hex"], 16), ec.SECP256R1())
    b = ec.derive_private_key(int(e["priv_b_scalar_hex"], 16), ec.SECP256R1())
    pa = bytes.fromhex(e["pub_a_x962_hex"])
    pb = bytes.fromhex(e["pub_b_x962_hex"])
    shared = a.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), pb))
    salt = hashlib.sha256(b"".join(sorted([pa, pb]))).digest()
    na, nb = sorted([e["node_a"], e["node_b"]])
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=salt,
               info=f"smcp-ecdh-session:{na}:{nb}".encode()).derive(shared)
    assert key.hex() == e["session_key_hex"]


def test_federation_ps256_verify_vector():
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.exceptions import InvalidSignature
    p = FED["ps256"]
    pub = serialization.load_pem_public_key(p["public_key_pem"].encode())
    try:
        pub.verify(bytes.fromhex(p["signature_hex"]), p["canonical"].encode(),
                   padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                               salt_length=hashes.SHA256.digest_size),
                   hashes.SHA256())
    except InvalidSignature:
        assert False, "PS256 conformance signature failed to verify"
