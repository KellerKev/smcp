# SMCP Agent-to-Agent (A2A) Spec

How SMCP nodes discover each other, delegate tasks, and forward client-authorized
requests across a federation. Builds on the wire protocol
([SMCP_PROTOCOL.md](SMCP_PROTOCOL.md)). References: `smcp_a2a.py`,
`smcp_distributed_a2a.py`, `smcp_distributed_transport.py`,
`smcp_federated_auth.py`, `smcp_discovery.py`.

## 1. Agents & capabilities

An agent is an SMCP node with an `AgentInfo` (id, name, specialties,
capabilities) and registered capability handlers. Capability names are unique
per node: registering a name that already exists is refused unless an explicit
override is requested (anti-shadowing). Capabilities are advertised via
`capability_discovery`.

## 2. Cross-node transport

Nodes talk over the authenticated SMCP WebSocket RPC — a node runs a receiving
server exposing the `distributed_task_execute` capability and calls peers with an
`SMCPClient` pool (`PeerConnectionPool`). Every cross-node RPC:

- is authenticated (the caller holds a session token for the capability),
- is encrypted + signed by the wire protocol,
- has a bounded timeout so a silent peer cannot wedge the caller.

### `distributed_task_execute`
Params: `{"task": {"task_id", "task_type", "task_data"}}`. The receiver
authorizes the **inner** `task_type` against an allowlist (default: the node's
application handlers, excluding control-plane capabilities such as
`cross_server_delegate`, `distributed_workflow`, `federated_forward`,
`federated_key_exchange`). A task_type outside the allowlist is refused — a
caller authorized only for `distributed_task_execute` cannot pivot to arbitrary
handlers.

## 3. Discovery

`discovery_method` selects a provider (`smcp_discovery.py`):

- `static` — the configured `cluster.nodes`.
- `dns` — SRV records for `discovery_config.service_name` (requires dnspython).
- `consul` — Consul health API (`/v1/health/service/<name>?passing=1`).
- `etcd` — etcd v3 range read over `discovery_config.etcd_prefix`; values are
  node JSON documents.

Discovery backends are security-sensitive: Consul/etcd fetches enforce TLS to
non-loopback hosts and a request timeout, malformed entries are skipped (never
crash discovery), and **discovery may add nodes but must not repoint a
statically-configured (trusted) node's host/port**. Routing prefers trusted
(static) nodes over discovered ones for a given capability, so a poisoned backend
cannot shadow a trusted provider.

## 4. Federated token forwarding

A node forwards a client's request to a peer while proving the client authorized
it. Message flow (`federated_forward` capability):

1. The forwarder builds a **forwarding proof** bound to `{client_jwt,
   forwarded_by, forwarded_to (the target node), task_hash, nonce, expires_at}`.
2. It signs the proof (see §5), encrypts the request under a session key (§6),
   and calls the target's `federated_forward` with `{encrypted_request, from_node}`.
3. The receiver derives/looks up the session key, decrypts, verifies the proof,
   checks `from_node == proof.forwarded_by`, validates the client JWT, checks the
   forwarder is trusted, then executes with the client's permissions.

Client tokens carry the federation `iss`/`aud` binding and a `forwarding_allowed`
list; verification is algorithm-pinned. Multi-party federations SHOULD verify
client tokens with **RS256** (issuer holds the private key, peers hold the public
key) via `security.federation_jwt_*` — this is independent of the transport JWT,
so a verify-only node still mints its own session tokens.

## 5. Forwarding proofs

Two schemes, selected by the signer's configuration:

- **PS256 (per-node asymmetric, recommended):** the signer signs the canonical
  proof JSON with its own RSA private key (RSA-PSS, SHA-256); verifiers check
  against the signer's registered public key. No shared-secret holder can forge.
- **HS256 (shared-secret HMAC, demo/single-domain):** HMAC over the canonical
  proof JSON keyed by `jwt_secret`.

Security rules (normative):
- The verifier MUST NOT let the message pick a weaker scheme: if the claimed
  `forwarded_by` has a registered public key, the proof MUST be PS256.
- A node configured with its own proof key MUST reject all HMAC proofs.
- `forwarded_to` MUST be non-empty and equal the receiver's node id (target
  binding; an empty target does not opt out).
- Each `nonce` is single-use within a bounded, size-capped, lock-guarded replay
  cache; `expires_at` bounds validity.

## 6. Session keys

- **Forward-secret (recommended, `crypto.perfect_forward_secrecy=true`):** an
  ephemeral ECDH exchange (`federated_key_exchange`, P-256) per session; the key
  is HKDF-derived with a salt bound to the exchange transcript (both ephemeral
  public keys), and ephemeral private keys are discarded. Under PFS a
  `federated_forward` with no established ECDH session is refused (no silent
  fallback to a long-term key).
- **Shared-secret (default):** an HKDF key over `secret_key` bound to the sorted
  node pair; deterministic on both sides, but not forward-secret.

Session payloads use AES-256-GCM with a fresh random 96-bit nonce and the
`session_id` (node pair) bound as GCM AAD, so ciphertext cannot be lifted onto a
different session.

## 7. Trust model summary

Transport session tokens authenticate client↔server within a node. Federated
client tokens authenticate the end user's identity across the federation
(RS256 recommended). Forwarding proofs authenticate the forwarding node
(per-node RSA recommended). Discovery establishes *reachability*, not trust —
static configuration is authoritative.
