"""v3 SMCP crypto must match the malgra-tunnel reference vector byte-for-byte, or this client can no
longer talk to malgra. See crates/malgra-tunnel/src/protocol.rs (KellerKev/malgra)."""
import types
from smcp_core import SMCPSecurity


def test_v3_interop_vector_matches_reference():
    sec = SMCPSecurity("interop-secret-value-32-bytes-xx", "jwt", "interop-salt")
    msg = types.SimpleNamespace(id="fixedid", type=types.SimpleNamespace(value="auth"),
                                timestamp=1700000000.0, payload={"x": 1})
    assert sec.sign_message(msg) == "661c3041e7cc52690927113ca9bc39c08899613f94e7d770addecd349374f8ca"


if __name__ == "__main__":
    test_v3_interop_vector_matches_reference()
    print("smcp v3 interop vector OK")
