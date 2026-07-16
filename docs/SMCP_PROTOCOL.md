# SMCP Wire Protocol (v3.0)

This is the normative specification for the SMCP transport protocol, sufficient
to implement an interoperable client or server in any language. The Python
reference is `smcp_core.py`; a Rust reference lives in malgra-tunnel
(`src/protocol.rs`). Conformance test vectors are in `tests/conformance_vectors.json`.

Protocol version: **3.0**. Peers exchange `protocol_version` in the handshake; a
mismatched **major** version is rejected (see §6).

## 1. Message envelope

Every message is a JSON object with exactly these fields:

```json
{
  "id": "<uuid4 string>",
  "type": "handshake|auth|capability_discovery|tool_invoke|tool_response|error|heartbeat",
  "timestamp": <float, unix seconds>,
  "payload": { ... },
  "encrypted": <bool>,
  "signature": "<hex string | null>"
}
```

- `id` — unique per message (UUIDv4). Also the replay key (§5).
- `type` — one of the MessageType values above.
- `timestamp` — unix seconds as a JSON number (see §4 for its canonical string form).
- `payload` — object; when `encrypted` is true it is `{"encrypted_data": "<token>"}` (§3).
- `encrypted` — whether `payload` carries ciphertext.
- `signature` — lowercase hex HMAC over the canonical signing input (§4), or null.

## 2. Key schedule (v3)

All symmetric keys derive from a per-deployment `secret_key` and `kdf_salt`,
shared by peers in the same trust domain:

```
salt      = kdf_salt bytes, or the constant b"malgra-tunnel-v3" if unset
master    = PBKDF2-HMAC-SHA256(secret_key, salt, iterations=600000, dklen=32)
cipher_key= HKDF-SHA256(master, salt=None, info=b"malgra-tunnel-v3-cipher", L=32)
mac_key   = HKDF-SHA256(master, salt=None, info=b"malgra-tunnel-v3-mac",    L=32)
```

The raw `secret_key` is never used directly as a key. `cipher_key` feeds the
payload cipher (§3); `mac_key` keys the message signature (§4).

## 3. Payload encryption

Payload encryption uses **Fernet** (AES-128-CBC + HMAC-SHA256, the standard
`cryptography` Fernet construction) with the key `base64url(cipher_key)`:

```
encrypted_data = Fernet(base64url(cipher_key)).encrypt(utf8(json(payload)))
```

Decryption MAY enforce a TTL (the receiver rejects Fernet tokens older than the
replay window, §5). When `encrypted` is true and `payload` is non-empty, `payload`
MUST be exactly `{"encrypted_data": "<fernet token>"}`. The `encrypted` flag MUST
agree with the presence of `encrypted_data` (a mismatch is rejected).

## 4. Message signature

The signature is `hex(HMAC-SHA256(mac_key, signing_input))` where the signing
input is the concatenation, in order, of:

```
signing_input = id ++ type ++ ts_str ++ canonical(payload)
```

- `id` — the message id string.
- `type` — the message type string value.
- `ts_str` — the timestamp rendered so integer seconds become `"<n>.0"`
  (e.g. `1700000000` → `"1700000000.0"`); non-integers use the shortest
  round-tripping decimal. This matches the Rust f64 serialization.
- `canonical(payload)` — JSON of the payload with **sorted keys** and compact
  separators (`","` and `":"`), matching serde_json's compact form.

Signatures are compared in constant time. Note the `encrypted` boolean is NOT
part of the signing input; receivers instead require it to agree with the
payload shape (§3).

**Reference vector:** `HMAC` with `mac_key` derived from
secret=`interop-secret-value-32-bytes-xx`, jwt=`jwt`, salt=`interop-salt`, over a
message `id="fixedid"`, `type="auth"`, `timestamp=1700000000.0`, `payload={"x":1}`
yields signature
`661c3041e7cc52690927113ca9bc39c08899613f94e7d770addecd349374f8ca`.

## 5. Replay & freshness

Receivers keep a window (default 300s). A message is accepted only if
`|now - timestamp| <= window` and its `id` has not been seen before within the
window; ids are recorded and pruned as they age. Encrypted payloads additionally
carry a Fernet TTL as defence in depth.

## 6. Session state machine

```
HANDSHAKE  -> mutual auth: client sends {client_id, protocol_version, nonce};
              server verifies major version, echoes client_nonce in a signed reply.
AUTH       -> client sends {api_key[, client_id]}; server constant-time compares,
              mints a session JWT (§7) with least-privilege scopes, returns {token}.
CAPABILITY_DISCOVERY -> client sends {token}; server returns advertised capabilities.
TOOL_INVOKE -> client sends {token, tool_name, parameters}; server checks scope,
              validates parameters against the capability schema, dispatches,
              returns {tool_name, result, status}.
HEARTBEAT  -> liveness.
ERROR      -> {request_id, error, timestamp}; a signed message like any other.
```

Version negotiation: the handshake compares the major component of
`protocol_version`. A different major (e.g. `4.x`) is refused with an ERROR.

## 7. Session tokens (JWT)

On AUTH the server mints a JWT bound to `iss="smcp"`, `aud="smcp"`, with `exp`
(1h) and `iat`. Two algorithms:

- **HS256** (default): signed and verified with the shared `jwt_secret`.
- **RS256** (recommended for multi-party): the server holds the private key and
  mints; clients verify with the public key and cannot forge. `exp`/`iat` are
  required; `iss`/`aud` are enforced.

Authorization scopes: `tool:<name>` authorizes a specific tool; `tool_invoke`
authorizes any tool; `discovery` authorizes capability discovery. Capabilities
with `auth_required=false` may be called without a token.

## 8. Transport

Messages are framed one-per-WebSocket-message (JSON text). TLS (`wss://`) is
required to non-loopback hosts unless an explicit insecure-transit opt-in is set
for a loopback target. Servers enforce a max message size and per-IP rate limits.

## 9. Interoperability notes

SMCP is a standalone secure agent protocol, not JSON-RPC/MCP on the wire. It
interoperates with MCP through the bridge (`smcp_mcp_bridge.py`), which adapts
SMCP tool invocations to external MCP servers over their native transport. To
implement a conformant peer, reproduce §2–§7 exactly and check against the
vectors in `tests/conformance_vectors.json`.
