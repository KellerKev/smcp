#!/usr/bin/env python3
"""
SCP Core - Secure Context Protocol Implementation
A secure, simplified alternative to MCP with native encryption and authentication
"""

import asyncio
import json
import uuid
import time
import hashlib
import hmac
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from enum import Enum
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
import base64
import jwt
from datetime import datetime, timedelta, timezone


# Wire protocol version. The MAJOR component must match between peers — a
# different major means incompatible framing/crypto and the handshake is refused.
PROTOCOL_VERSION = "3.0"


def _protocol_major(version: str) -> str:
    return str(version or "").split(".", 1)[0]


class MessageType(Enum):
    HANDSHAKE = "handshake"
    AUTH = "auth"
    CAPABILITY_DISCOVERY = "capability_discovery"
    TOOL_INVOKE = "tool_invoke"
    TOOL_RESPONSE = "tool_response"
    ERROR = "error"
    HEARTBEAT = "heartbeat"


@dataclass
class SMCPMessage:
    """Core SCP message structure"""
    id: str
    type: MessageType
    timestamp: float
    payload: Dict[str, Any]
    encrypted: bool = False
    signature: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "timestamp": self.timestamp,
            "payload": self.payload,
            "encrypted": self.encrypted,
            "signature": self.signature
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SMCPMessage':
        return cls(
            id=data["id"],
            type=MessageType(data["type"]),
            timestamp=data["timestamp"],
            payload=data["payload"],
            encrypted=data.get("encrypted", False),
            signature=data.get("signature")
        )


@dataclass
class Capability:
    """Tool capability definition"""
    name: str
    description: str
    parameters: Dict[str, Any]
    auth_required: bool = True


class SMCPSecurity:
    """Handles encryption and authentication"""
    
    def __init__(self, secret_key: str, jwt_secret: str, kdf_salt: str = "",
                 jwt_algorithm: str = "HS256",
                 jwt_private_key_path: Optional[str] = None,
                 jwt_public_key_path: Optional[str] = None):
        self.secret_key = secret_key.encode()
        self.jwt_secret = jwt_secret
        self.kdf_salt = kdf_salt
        self._setup_keys()
        self._setup_jwt(jwt_algorithm, jwt_private_key_path, jwt_public_key_path)

    def _setup_jwt(self, algorithm, private_key_path, public_key_path):
        """Configure JWT signing/verification.

        HS256 (default): a shared symmetric secret — every holder can BOTH mint and
        verify tokens, so it cannot establish per-node identity. Kept for
        backward-compatible single-trust-domain use.

        RS256: asymmetric. The server loads a PRIVATE key and can mint tokens;
        clients load only the PUBLIC key and can verify but NOT forge them. This
        is the production-recommended mode: a client can no longer escalate its
        own permissions by minting a token, because it doesn't hold the signer.
        """
        self.jwt_algorithm = algorithm
        self.jwt_signing_key = None      # private key (server) or shared secret
        self.jwt_verify_key = None       # public key (client/server) or shared secret
        if algorithm == "HS256":
            self.jwt_signing_key = self.jwt_secret
            self.jwt_verify_key = self.jwt_secret
            return
        if algorithm not in ("RS256", "ES256", "EdDSA"):
            raise ValueError(f"Unsupported jwt_algorithm: {algorithm}")
        from cryptography.hazmat.primitives import serialization as _ser
        if private_key_path:
            with open(private_key_path, "rb") as f:
                self.jwt_signing_key = _ser.load_pem_private_key(f.read(), password=None)
        if public_key_path:
            with open(public_key_path, "rb") as f:
                self.jwt_verify_key = _ser.load_pem_public_key(f.read())
        elif self.jwt_signing_key is not None:
            # Derive the public verify key from the private key when only the
            # private key was provided (server that both signs and verifies).
            self.jwt_verify_key = self.jwt_signing_key.public_key()
        if self.jwt_signing_key is None and self.jwt_verify_key is None:
            raise ValueError(
                f"{algorithm} requires jwt_private_key_path (to sign) and/or "
                f"jwt_public_key_path (to verify)"
            )

    def _setup_keys(self):
        """v3 key derivation (matches malgra-tunnel/src/protocol.rs + docs/SMCP_PROTOCOL.md):
        master = PBKDF2-HMAC-SHA256(secret, kdf_salt, 600k) -> HKDF splits an independent Fernet
        cipher key and an HMAC key. The raw secret is never used as a key (v2's flaw)."""
        salt = self.kdf_salt.encode() if self.kdf_salt else b"malgra-tunnel-v3"
        master = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=600_000).derive(self.secret_key)
        cipher_key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"malgra-tunnel-v3-cipher").derive(master)
        self.mac_key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"malgra-tunnel-v3-mac").derive(master)
        self.cipher = Fernet(base64.urlsafe_b64encode(cipher_key))

    def encrypt_payload(self, payload: Dict[str, Any]) -> str:
        """Encrypt message payload"""
        json_payload = json.dumps(payload).encode()
        return self.cipher.encrypt(json_payload).decode()

    def decrypt_payload(self, encrypted_payload: str, ttl: Optional[int] = None) -> Dict[str, Any]:
        """Decrypt message payload. When ttl is given, Fernet rejects tokens
        older than ttl seconds (defence-in-depth against replay of stale data)."""
        decrypted = self.cipher.decrypt(encrypted_payload.encode(), ttl=ttl)
        return json.loads(decrypted.decode())

    @staticmethod
    def _canonical(payload) -> str:
        """Canonical JSON of the wire payload: sorted keys, compact separators (matches serde_json)."""
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _ts_str(ts) -> str:
        """Integer seconds render as '<n>.0' to match the Rust f64 serialization."""
        f = float(ts)
        return f"{int(f)}.0" if f.is_integer() else str(f)

    def sign_message(self, message: SMCPMessage) -> str:
        """v3 payload-bound HMAC signature over id + type + ts + canonical(payload), keyed by mac_key."""
        msg_data = f"{message.id}{message.type.value}{self._ts_str(message.timestamp)}{self._canonical(message.payload)}"
        return hmac.new(
            self.mac_key,
            msg_data.encode(),
            hashlib.sha256
        ).hexdigest()
    
    def verify_signature(self, message: SMCPMessage) -> bool:
        """Verify message signature"""
        if not message.signature:
            return False
        expected = self.sign_message(message)
        return hmac.compare_digest(expected, message.signature)
    
    # Issuer/audience bind a token to this protocol, so a token minted for some
    # other purpose under the same signing key is not accepted here.
    JWT_ISSUER = "smcp"
    JWT_AUDIENCE = "smcp"

    def generate_jwt(self, client_id: str, permissions: List[str]) -> str:
        """Generate a JWT. Requires a signing key; in RS256 mode a client that
        holds only the public key cannot mint tokens (raises)."""
        if self.jwt_signing_key is None:
            raise ValueError(
                "This node has no JWT signing key (verify-only). It cannot mint "
                "tokens; only the server holding the private key can."
            )
        now = datetime.now(timezone.utc)
        payload = {
            "client_id": client_id,
            "permissions": permissions,
            "iss": self.JWT_ISSUER,
            "aud": self.JWT_AUDIENCE,
            "exp": now + timedelta(hours=1),
            "iat": now,
        }
        return jwt.encode(payload, self.jwt_signing_key, algorithm=self.jwt_algorithm)

    def verify_jwt(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify JWT token, enforcing algorithm, expiry, issuer and audience."""
        if self.jwt_verify_key is None:
            return None
        try:
            return jwt.decode(
                token, self.jwt_verify_key, algorithms=[self.jwt_algorithm],
                audience=self.JWT_AUDIENCE, issuer=self.JWT_ISSUER,
                options={"require": ["exp", "iat"]},
            )
        except jwt.InvalidTokenError:
            return None


class SMCPNode:
    """Core SCP node that can act as client or server"""
    
    def __init__(self, node_id: str, secret_key: str = "", jwt_secret: str = "",
                 kdf_salt: str = "", api_key: str = "", jwt_algorithm: str = "HS256",
                 jwt_private_key_path: Optional[str] = None,
                 jwt_public_key_path: Optional[str] = None):
        # No insecure built-in defaults: empty secrets are caught by
        # SMCPConfig.validate() at startup, and _handle_auth fails closed when
        # api_key is unset. Never ship guessable "default_*" credentials.
        self.node_id = node_id
        self.api_key = api_key
        self.security = SMCPSecurity(
            secret_key, jwt_secret, kdf_salt,
            jwt_algorithm=jwt_algorithm,
            jwt_private_key_path=jwt_private_key_path,
            jwt_public_key_path=jwt_public_key_path,
        )
        self.capabilities: Dict[str, Capability] = {}
        self.tool_handlers: Dict[str, Callable] = {}
        self.auth_tokens: Dict[str, Dict[str, Any]] = {}
        # Optional least-privilege authorization policy. A dict {client_id: [scopes]}
        # or a callable (client_id) -> [scopes]. When set and it returns scopes for
        # a client, those are granted instead of the broad default; scopes are
        # `tool:<name>` (a specific tool) and/or `tool_invoke`/`discovery`. Left
        # None, every authenticated client gets the broad default (back-compat).
        self.permission_policy = None
        # Optional pluggable safety/observability hooks (all default off, so no
        # behaviour change unless configured):
        #   consent_hook(tool_name, parameters, client_id) -> bool
        #       return False to deny an invocation (human-in-the-loop / policy gate).
        #   output_filter(tool_name, result) -> result
        #       transform/redact/taint a tool result before it is returned.
        #   audit_hook(event: dict) -> None
        #       receive structured audit events (auth, invoke, denial, error).
        self.consent_hook = None
        self.output_filter = None
        self.audit_hook = None
        # Replay protection: accept a message only once and only within a freshness
        # window. Maps message id -> timestamp; pruned as it grows.
        self.replay_window_seconds = 300
        self._seen_message_ids: Dict[str, float] = {}
        
    def register_capability(self, capability: Capability, handler: Callable, override: bool = False):
        """Register a tool capability.

        Refuses to silently overwrite an existing capability of the same name
        (tool shadowing): a later registration replacing a legitimate tool is a
        classic MCP shadowing vector. Pass ``override=True`` to intentionally
        replace one.
        """
        if capability.name in self.capabilities and not override:
            raise ValueError(
                f"Capability {capability.name!r} is already registered; refusing to "
                f"shadow it. Pass override=True to replace intentionally."
            )
        self.capabilities[capability.name] = capability
        self.tool_handlers[capability.name] = handler
    
    def create_message(self, msg_type: MessageType, payload: Dict[str, Any], encrypt: bool = True) -> SMCPMessage:
        """Create a new SCP message"""
        message = SMCPMessage(
            id=str(uuid.uuid4()),
            type=msg_type,
            timestamp=float(int(time.time())),  # integer seconds so the signed ts renders as "<n>.0"
            payload=payload,
            encrypted=encrypt
        )
        
        if encrypt and payload:
            message.payload = {"encrypted_data": self.security.encrypt_payload(payload)}
        
        message.signature = self.security.sign_message(message)
        return message
    
    def _check_and_record_replay(self, message: SMCPMessage) -> bool:
        """Return True if the message is fresh and unseen; record it. Reject stale
        or duplicate messages (replay protection)."""
        now = time.time()
        # Freshness: timestamp must be within +/- the replay window.
        if abs(now - float(message.timestamp)) > self.replay_window_seconds:
            return False
        # Uniqueness: reject a message id we've already accepted.
        if message.id in self._seen_message_ids:
            return False
        # Prune expired ids opportunistically, then record this one.
        if len(self._seen_message_ids) > 10000:
            cutoff = now - self.replay_window_seconds
            self._seen_message_ids = {
                mid: ts for mid, ts in self._seen_message_ids.items() if ts >= cutoff
            }
        self._seen_message_ids[message.id] = now
        return True

    def process_message(self, message: SMCPMessage) -> Optional[SMCPMessage]:
        """Process incoming message"""
        if not self.security.verify_signature(message):
            return self.create_error_response(message.id, "Invalid signature")

        # Reject stale or replayed messages before doing any further work.
        if not self._check_and_record_replay(message):
            return self.create_error_response(message.id, "Stale or replayed message rejected")

        # The `encrypted` boolean is not itself covered by the HMAC (the v3
        # signature — fixed for cross-language interop — spans id/type/ts/payload
        # only). The payload IS signed, though, so require the flag to agree with
        # the signed payload shape: an attacker flipping only the flag is caught
        # here because it no longer matches the (tamper-proof) presence of
        # "encrypted_data". An encrypted message with an empty payload carries no
        # ciphertext, so that case is allowed.
        payload = message.payload if isinstance(message.payload, dict) else {}
        has_ciphertext = "encrypted_data" in payload
        if has_ciphertext and not message.encrypted:
            return self.create_error_response(
                message.id, "Encrypted flag does not match payload"
            )
        if message.encrypted and payload and not has_ciphertext:
            return self.create_error_response(
                message.id, "Encrypted flag does not match payload"
            )

        if message.encrypted and "encrypted_data" in message.payload:
            try:
                message.payload = self.security.decrypt_payload(
                    message.payload["encrypted_data"], ttl=self.replay_window_seconds
                )
            except Exception:
                self._log_internal_error("decrypt_payload")
                return self.create_error_response(message.id, "Decryption failed")
        
        if message.type == MessageType.HANDSHAKE:
            return self._handle_handshake(message)
        elif message.type == MessageType.AUTH:
            return self._handle_auth(message)
        elif message.type == MessageType.CAPABILITY_DISCOVERY:
            return self._handle_capability_discovery(message)
        elif message.type == MessageType.TOOL_INVOKE:
            return self._handle_tool_invoke(message)
        elif message.type == MessageType.HEARTBEAT:
            return self._handle_heartbeat(message)
        
        return self.create_error_response(message.id, "Unknown message type")
    
    def _handle_handshake(self, message: SMCPMessage) -> SMCPMessage:
        """Handle handshake. Mutual auth: echo the client's nonce so it can confirm we hold the
        shared secret and are answering THIS handshake (not a replay).

        Version negotiation: the client advertises its protocol_version; a
        mismatched MAJOR version means incompatible framing/crypto, so the
        handshake is refused rather than proceeding into undefined behaviour.
        """
        client_version = (message.payload or {}).get("protocol_version", PROTOCOL_VERSION)
        if _protocol_major(client_version) != _protocol_major(PROTOCOL_VERSION):
            return self.create_error_response(
                message.id,
                f"Incompatible protocol version {client_version!r}; this node speaks "
                f"{PROTOCOL_VERSION}",
            )
        return self.create_message(MessageType.HANDSHAKE, {
            "node_id": self.node_id,
            "protocol_version": PROTOCOL_VERSION,
            "capabilities_count": len(self.capabilities),
            "encryption_enabled": True,
            "client_nonce": (message.payload or {}).get("nonce", "")
        })
    
    def _handle_auth(self, message: SMCPMessage) -> SMCPMessage:
        """Handle authentication against the configured API key.

        The key is compared in constant time. There is deliberately no hardcoded
        fallback credential: a node with no ``api_key`` set cannot authenticate
        anyone (fail closed). The client id is taken from the caller but the
        granted permissions are least-privilege and fixed here, not caller-chosen.
        """
        api_key = message.payload.get("api_key") or ""
        expected = self.api_key or ""
        if not expected or not hmac.compare_digest(str(api_key), str(expected)):
            return self.create_error_response(message.id, "Authentication failed")

        client_id = str(message.payload.get("client_id", "client"))
        permissions = self._grant_permissions(client_id)
        token = self.security.generate_jwt(client_id, permissions)
        self._emit_audit({"event": "auth", "client_id": client_id, "permissions": permissions})
        self.auth_tokens[token] = {
            "client_id": client_id,
            "permissions": permissions,
            "expires": time.time() + 3600
        }
        return self.create_message(MessageType.AUTH, {
            "status": "success",
            "token": token,
            "expires_in": 3600
        })
    
    def _grant_permissions(self, client_id: str) -> List[str]:
        """Resolve the scopes to grant a client at auth time.

        Consults `permission_policy` (dict or callable) for least-privilege,
        per-client `tool:<name>` scoping. Falls back to the broad
        `["tool_invoke","discovery"]` default when no policy applies, preserving
        backward-compatible behaviour.
        """
        policy = getattr(self, "permission_policy", None)
        if policy is not None:
            perms = policy(client_id) if callable(policy) else policy.get(client_id)
            if perms:
                return list(perms)
        return ["tool_invoke", "discovery"]

    def _handle_capability_discovery(self, message: SMCPMessage) -> SMCPMessage:
        """Handle capability discovery"""
        if not self._is_authorized(message.payload.get("token"), "discovery"):
            return self.create_error_response(message.id, "Unauthorized")
        
        capabilities_data = {
            cap_name: {
                "name": cap.name,
                "description": cap.description,
                "parameters": cap.parameters,
                "auth_required": cap.auth_required
            }
            for cap_name, cap in self.capabilities.items()
        }
        
        return self.create_message(MessageType.CAPABILITY_DISCOVERY, {
            "capabilities": capabilities_data
        })
    
    def _handle_tool_invoke(self, message: SMCPMessage) -> SMCPMessage:
        """Handle tool invocation with per-tool authorization + parameter validation."""
        tool_name = message.payload.get("tool_name")
        parameters = message.payload.get("parameters", {})

        if tool_name not in self.tool_handlers:
            return self.create_error_response(message.id, f"Tool '{tool_name}' not found")

        capability = self.capabilities.get(tool_name)
        # Per-tool authorization: a token must carry either the tool-specific
        # scope `tool:<name>` or the broad `tool_invoke` scope. Tools that opt out
        # (auth_required=False) may be called without a token.
        if capability is None or capability.auth_required:
            token = message.payload.get("token")
            if not (self._is_authorized(token, f"tool:{tool_name}")
                    or self._is_authorized(token, "tool_invoke")):
                self._emit_audit({"event": "authz_denied", "tool": tool_name,
                                  "client_id": self._client_id_for(token)})
                return self.create_error_response(message.id, "Unauthorized")

        # Validate parameters against the declared capability schema before dispatch.
        if capability is not None:
            error = self._validate_parameters(parameters, capability.parameters)
            if error:
                return self.create_error_response(message.id, f"Invalid parameters: {error}")

        client_id = self._client_id_for(message.payload.get("token"))

        # Consent / policy gate (human-in-the-loop). Denials are audited.
        if self.consent_hook is not None:
            try:
                allowed = self.consent_hook(tool_name, parameters, client_id)
            except Exception:
                allowed = False
            if not allowed:
                self._emit_audit({"event": "invoke_denied", "tool": tool_name,
                                  "client_id": client_id})
                return self.create_error_response(message.id, "Tool invocation denied by policy")

        try:
            result = self.tool_handlers[tool_name](**parameters)
            # Optional output filtering (redaction / tainting) before returning.
            if self.output_filter is not None:
                result = self.output_filter(tool_name, result)
            self._emit_audit({"event": "invoke", "tool": tool_name,
                              "client_id": client_id, "status": "success"})
            return self.create_message(MessageType.TOOL_RESPONSE, {
                "tool_name": tool_name,
                "result": result,
                "status": "success"
            })
        except TypeError as e:
            # Argument-shape mismatch is a client error; keep it specific.
            return self.create_error_response(message.id, f"Invalid parameters: {str(e)}")
        except Exception:
            # Do not leak internal exception detail to the caller.
            self._log_internal_error(tool_name)
            self._emit_audit({"event": "invoke", "tool": tool_name,
                              "client_id": client_id, "status": "error"})
            return self.create_error_response(message.id, "Tool execution failed")

    def _emit_audit(self, event: Dict[str, Any]) -> None:
        """Emit a structured audit event to the configured hook (best-effort)."""
        hook = getattr(self, "audit_hook", None)
        if hook is None:
            return
        try:
            event.setdefault("ts", time.time())
            event.setdefault("node_id", self.node_id)
            hook(event)
        except Exception:
            self._log_internal_error("audit_hook")

    def _client_id_for(self, token: Optional[str]) -> Optional[str]:
        """Best-effort client identity from a session token (for audit/consent)."""
        if not token:
            return None
        payload = self.security.verify_jwt(token)
        return (payload or {}).get("client_id")

    @staticmethod
    def _validate_parameters(parameters: Dict[str, Any], schema: Dict[str, Any]) -> Optional[str]:
        """Lightweight validation of caller parameters against a capability schema.

        Rejects unexpected keys and checks declared JSON types / enum membership
        on the parameters that ARE supplied. Required-ness is only enforced when
        the schema declares it explicitly via a top-level ``required`` list
        (JSON-Schema style); absence of a ``default`` is NOT treated as required,
        because these capability schemas don't follow that convention and the
        handlers supply their own defaults. Returns an error string, or None.
        """
        if not isinstance(parameters, dict):
            return "parameters must be an object"

        # Support an optional JSON-Schema-style {"required": [...]} declaration.
        required = schema.get("required") if isinstance(schema, dict) else None
        prop_schema = {k: v for k, v in schema.items() if k != "required"} \
            if isinstance(required, list) else schema

        allowed = set(prop_schema.keys())
        extra = set(parameters.keys()) - allowed
        if extra:
            return f"unexpected parameter(s): {', '.join(sorted(extra))}"

        if isinstance(required, list):
            missing = [r for r in required if r not in parameters]
            if missing:
                return f"missing required parameter(s): {', '.join(missing)}"

        _JSON_TYPES = {
            "string": str, "number": (int, float), "integer": int,
            "boolean": bool, "object": dict, "array": list,
        }
        for name, value in parameters.items():
            spec = prop_schema.get(name)
            if not isinstance(spec, dict):
                continue
            declared = spec.get("type")
            py_type = _JSON_TYPES.get(declared)
            # bool is a subclass of int; guard against accepting True as a number
            if py_type and (not isinstance(value, py_type)
                            or (declared in ("number", "integer") and isinstance(value, bool))):
                return f"parameter '{name}' must be of type {declared}"
            enum = spec.get("enum")
            if enum is not None and value not in enum:
                return f"parameter '{name}' must be one of {enum}"
        return None

    def _log_internal_error(self, context: str) -> None:
        """Hook for logging internal errors without exposing them to callers."""
        import logging, traceback
        logging.getLogger("smcp_core").error(
            "Internal error handling '%s': %s", context, traceback.format_exc()
        )
    
    def _handle_heartbeat(self, message: SMCPMessage) -> SMCPMessage:
        """Handle heartbeat"""
        return self.create_message(MessageType.HEARTBEAT, {
            "status": "alive",
            "timestamp": time.time()
        })
    
    def _is_authorized(self, token: str, permission: str) -> bool:
        """Check authorization"""
        if not token:
            return False
        payload = self.security.verify_jwt(token)
        return payload and permission in payload.get("permissions", [])
    
    def create_error_response(self, request_id: str, error_message: str) -> SMCPMessage:
        """Create error response"""
        return self.create_message(MessageType.ERROR, {
            "request_id": request_id,
            "error": error_message,
            "timestamp": time.time()
        })