#!/usr/bin/env python3
"""Malgra guardrail plugin for SMCP.

Wires SMCP's pluggable security hooks (`consent_hook`, `output_filter`) to the
malgra policy engine so tool INPUTS and (untrusted) tool OUTPUTS are checked for
prompt injection, tool poisoning, and policy violations — the LLM-layer threats
SMCP's transport security deliberately doesn't cover.

Two decision sources:
- **malgra policy-server** `POST /evaluate {prompt, context} ->
  {allowed, violated_rule, reason, severity}` (the decoupled decision API).
- **local fast-path regex** mirroring malgra's untrusted-span injection patterns,
  used as a pre-filter and as a safe degraded mode when malgra is unreachable.

Wire it up:
    guard = MalgraGuard("https://malgra-policy:8900", fail_closed=True)
    node.consent_hook = guard.consent_hook
    node.output_filter = guard.output_filter

The hooks run in the node's worker-thread dispatch, so synchronous HTTP is fine.
"""
import json
import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger("smcp_malgra_guard")

# Fast-path mirror of malgra's untrusted-span injection library
# (malgra-rs/src/lib.rs untrusted_span_injection). Deliberately broad — these
# run against UNTRUSTED content (tool outputs / args), where imperative
# instructions are a strong injection signal.
_INJECTION_PATTERNS = [
    r"(?i)ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts?|context)",
    r"(?i)disregard\s+(the\s+)?(system|previous|above)",
    r"(?i)reveal|print|repeat\s+.{0,30}(system\s+prompt|instructions)",
    r"(?i)(exfiltrate|send|post|upload)\s+.{0,40}?(to\s+)?https?://",
    r"(?i)<\|im_start\|>|<\|system\|>|\[/?(INST|SYS)\]",
    r"(?i)override\s+(the\s+)?(policy|guardrails?|safety)",
    r"(?i)you\s+are\s+now\b|new\s+instructions?:|do\s+anything\s+now|\bDAN\b",
]
_INJECTION_RE = [re.compile(p) for p in _INJECTION_PATTERNS]


class MalgraBlocked(Exception):
    """Raised by output_filter to block a tool result flagged as unsafe."""


class MalgraGuard:
    def __init__(self, policy_url: str, auth_token: Optional[str] = None,
                 fail_closed: bool = True, timeout: float = 5.0,
                 allow_insecure: bool = False, session=None):
        """``policy_url`` is the malgra policy-server base URL. ``fail_closed``
        (default True) denies when malgra is unreachable AND the local regex did
        not already decide. ``session`` is an injectable requests-like session
        for tests. Plaintext to a non-loopback host is refused unless
        ``allow_insecure``."""
        from smcp_config import enforce_secure_url
        enforce_secure_url(policy_url, allow_insecure=allow_insecure)
        self.policy_url = policy_url.rstrip("/")
        self.auth_token = auth_token
        self.fail_closed = fail_closed
        self.timeout = timeout
        self._session = session

    # -- decision helpers ---------------------------------------------------- #
    @staticmethod
    def _has_injection(text: str) -> bool:
        return any(rx.search(text) for rx in _INJECTION_RE)

    def _evaluate(self, prompt: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Call malgra /evaluate. Returns the decision dict, or raises on error."""
        sess = self._session
        if sess is None:
            import requests
            sess = requests
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        resp = sess.post(f"{self.policy_url}/evaluate",
                         json={"prompt": prompt, "context": context},
                         headers=headers, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def _decide(self, text: str, context: Dict[str, Any]) -> bool:
        """Return True if allowed. Local regex is a hard block; then malgra;
        then fail_closed on malgra error."""
        if self._has_injection(text):
            logger.warning("malgra guard: local injection pattern matched; blocking")
            return False
        try:
            decision = self._evaluate(text, context)
        except Exception as e:
            logger.warning(f"malgra guard: policy server unreachable ({e}); "
                           f"{'denying (fail-closed)' if self.fail_closed else 'allowing'}")
            return not self.fail_closed
        return bool(decision.get("allowed", False))

    # -- SMCP hooks ---------------------------------------------------------- #
    def consent_hook(self, tool_name: str, parameters: Dict[str, Any],
                     client_id: Optional[str]) -> bool:
        """Gate a tool INVOCATION (tool + args) through malgra policy."""
        text = f"tool={tool_name} args={json.dumps(parameters, sort_keys=True, default=str)}"
        return self._decide(text, {"stage": "tool_invoke", "tool": tool_name,
                                    "client_id": client_id})

    def output_filter(self, tool_name: str, result: Any) -> Any:
        """Scan a tool RESULT (untrusted) for injected instructions; block on hit.

        Raises MalgraBlocked so the SMCP pipeline returns an error instead of
        handing a poisoned result back to the caller/LLM."""
        text = result if isinstance(result, str) else json.dumps(result, default=str)
        if not self._decide(text, {"stage": "tool_output", "tool": tool_name}):
            raise MalgraBlocked(f"tool output from {tool_name!r} blocked by malgra policy")
        return result
