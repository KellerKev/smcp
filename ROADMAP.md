# SMCP Roadmap

What's deferred and what to treat as not-yet-production. See the
[README](README.md) for what the security core already does.

## Deferred / planned

- **Pluggable discovery** — Consul / etcd / DNS. Today discovery is static and
  config-driven only (`cluster.nodes`); the other methods raise
  `NotImplementedError`.
- **Forward-secret ECDH session keys** — session keys are derived from a shared
  secret via HKDF today; ephemeral ECDH for per-session forward secrecy is
  planned.
- **Per-node asymmetric forwarding proofs** — forwarding proofs are currently
  signed with the shared secret; per-node keypairs (each node signs proofs with
  its own private key) are planned.

## Current limitations

- The integrations (CrewAI, MindsDB) and the OAuth2 flow are exercised against
  local / mock services, not a production identity provider.
- There has been no external security audit.
- It isn't yet running in production.
