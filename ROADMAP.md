# SMCP Roadmap

What's implemented and what remains. See the [README](README.md) for what the
security core does and [docs/SMCP_PROTOCOL.md](docs/SMCP_PROTOCOL.md) /
[docs/SMCP_A2A_SPEC.md](docs/SMCP_A2A_SPEC.md) for the wire + A2A specs.

## Recently completed

- **Federated crypto correctness** — forwarding-proof verification is
  algorithm-pinned (no PS256→HS256 downgrade); a node on per-node keys rejects
  all shared-secret proofs; forward secrecy is enforced when enabled (no silent
  static-key fallback); session payloads bind the session id as GCM AAD.
- **Authorization** — the distributed dispatch authorizes the inner `task_type`
  against an allowlist (no capability-bypass pivot); per-tool scopes can be
  issued via a permission policy; forwarding proofs require a non-empty target
  and `from_node == forwarded_by`.
- **Discovery hardening** — Consul/etcd fetches enforce TLS + timeouts, malformed
  responses are skipped (no discovery DoS), and discovery cannot repoint a
  statically-trusted node; routing prefers trusted nodes.
- **Capability shadowing defense** — silent capability overwrite is refused; the
  bridge/registry prefer the first-registered / statically-trusted provider.
- **LLM-safety + audit hooks** — pluggable consent gate, tool-output filter, and
  a structured audit event stream on the invoke path.
- **Interoperability** — protocol version negotiation, a published wire spec + A2A
  spec, and language-agnostic conformance vectors (`tests/conformance_vectors.json`).
- (Earlier) per-node asymmetric proofs, forward-secret ECDH, pluggable discovery,
  RS256 issuer + keygen.

## Remaining / not addressed

- **Bridged MCP calls don't inherit the full SMCP protocol.** The bridge applies
  TLS + a bearer token and now refuses capability shadowing, but bridged calls do
  not carry SMCP per-message encryption/signing or per-tool JWT authz. Full parity
  (wrapping the bridge in the security + audit layer) is future work.
- **Prompt injection / tool poisoning** — SMCP provides the consent/output-filter
  hooks but ships no built-in defense; policy is the operator's responsibility.
- **Tool/manifest provenance & attestation** — capability signing/pinning is not
  implemented.
- **Session-key rotation without PFS** — the non-PFS static key does not rotate;
  use `perfect_forward_secrecy` for long-lived, high-volume links.

## Current limitations

- Integrations (CrewAI, MindsDB) and the OAuth2 flow are exercised against
  local/mock services; Consul/etcd discovery is unit-tested against mocked
  backends. No external security audit; not yet running in production.
