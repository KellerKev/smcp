# Malgra guardrail integration

SMCP secures the transport, identity, and authorization of tool calls. It does
**not** ship a built-in defense against LLM-layer threats — prompt injection, tool
poisoning, malicious tool descriptions, PII leakage. [Malgra](https://github.com/KellerKev/malgra)
does exactly that (span-provenance injection detection, TOFU tool-pinning, a PII
gate, and a policy engine), and it already speaks SMCP. This doc describes the two
ways to combine them.

## Shape 1 — Malgra as an SMCP guard plugin (embedded)

The SMCP node stays in control and calls malgra for a policy decision on tool
inputs and outputs, via SMCP's pluggable hooks. Malgra is an opt-in backend.

```python
from smcp_malgra_guard import MalgraGuard

guard = MalgraGuard("https://malgra-policy:8900", fail_closed=True)
node.consent_hook = guard.consent_hook   # gate tool INVOCATIONS (tool + args)
node.output_filter = guard.output_filter  # scan tool OUTPUTS (untrusted) for injection
```

- `consent_hook` sends the tool + arguments to malgra's `POST /evaluate`; a
  `block` verdict denies the invocation (audited as `invoke_denied`).
- `output_filter` scans the tool result for injected instructions / PII and
  blocks a poisoned result before it reaches the caller/LLM. It also runs a local
  fast-path regex mirror of malgra's injection library, so an obvious injection is
  caught even if malgra is momentarily unreachable.
- **Fail mode:** `fail_closed=True` (default) denies when malgra is unreachable
  and the local regex didn't already decide; `fail_closed=False` allows clean
  input in a degraded mode. Choose per risk tolerance.
- **Coverage:** because bridged MCP tools are now native node capabilities
  (see [bridge parity](#)), the same hooks guard **foreign MCP tool output** too —
  the highest-value target, since foreign output is the untrusted-span source.

This works in any topology (embedded node, distributed A2A, behind the ingress).

## Shape 2 — Malgra fronts SMCP (gateway)

Agents speak SMCP to malgra-rs's built-in SMCP server (`[smcp] enabled=true`,
default `ws://0.0.0.0:8767`), which applies its full governance pipeline
(span-provenance, policy, tool-definition pinning, PII) and then forwards to the
SMCP node/tool backend. Governance is centralized in malgra; SMCP nodes sit
behind it.

- Use when you want one governance choke point for a fleet, or malgra's richer
  in-process pipeline (`McpGateway::call`, `enforce_spans`) rather than the
  decoupled `/evaluate` decision.
- Interop requires malgra's handshake to accept SMCP's version negotiation —
  malgra now compares the MAJOR protocol version (see the malgra protocol sync),
  so an SMCP `3.x` client interoperates.
- **Validation:** run `malgra-rs` with the SMCP server enabled, point an
  `SMCPClient` at `ws://localhost:8767`, and complete
  handshake → auth (api_key → JWT) → capability_discovery → tool_invoke. The core
  wire protocol is byte-identical (shared v3 tunnel + interop vector).

## What each blocks

| Threat | Shape 1 (plugin) | Shape 2 (malgra fronts) |
|---|---|---|
| Prompt injection in tool output | ✅ output_filter + local regex | ✅ span-provenance |
| Malicious tool invocation / args | ✅ consent_hook `/evaluate` | ✅ policy on tools/call |
| Tool poisoning / definition drift | (policy-dependent) | ✅ TOFU pinning |
| PII leakage | (policy-dependent) | ✅ PII gate |
| Per-tool authorization, audit | ✅ native SMCP | ✅ native SMCP + malgra receipts |

## Recommendation

Start with **Shape 1** — it's a few lines, works everywhere, and (via bridge
parity) covers foreign MCP output. Add **Shape 2** when you want centralized
governance or malgra's deeper in-process guardrails. They compose: a node behind
malgra can still run the plugin for defense in depth.
