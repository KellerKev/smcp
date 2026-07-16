# SMCP Roadmap

What's implemented from the roadmap, and what remains a non-code caveat. See the
[README](README.md) for what the security core does.

## Recently completed

- **Per-node asymmetric forwarding proofs** — each node signs forwarding proofs
  with its own RSA private key (RSA-PSS); peers verify against the signer's
  registered public key. No shared-secret holder can forge a proof. Falls back to
  shared-secret HMAC when no per-node keys are configured
  (`security.proof_signing_key_path`).
- **Forward-secret ECDH session keys** — with `crypto.perfect_forward_secrecy`
  enabled, nodes run a real ephemeral ECDH handshake (per-session keypairs,
  discarded after use, key bound to the exchange transcript) instead of deriving
  from a shared secret. A later compromise of long-term secrets can't decrypt
  past sessions.
- **Pluggable discovery** — `discovery_method` selects a provider: `static`
  (config `cluster.nodes`), `dns` (SRV records, needs `dnspython`), `consul`
  (Consul health API), or `etcd` (etcd v3 range). Discovered nodes are merged and
  health-checked over the real transport. Config via `cluster.discovery_config`.

## Current limitations

- The integrations (CrewAI, MindsDB) and the OAuth2 flow are exercised against
  local / mock services, not a production identity provider. Consul/etcd
  discovery is unit-tested against mocked backends; wire it to real services in a
  deployment.
- There has been no external security audit.
- It isn't yet running in production.
