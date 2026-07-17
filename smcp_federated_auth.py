#!/usr/bin/env python3
"""
Federated Authentication System for SMCP-SA2A
Implements token forwarding pattern for simplified cross-node authentication
"""

import asyncio
import json
import uuid
import time
import hashlib
import hmac
import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding
from cryptography.exceptions import InvalidSignature
import secrets
import jwt

# Canonical module names are smcp_config/smcp_core (the scp_* aliases never existed).
from smcp_config import SCPConfig
from smcp_core import SMCPMessage as SCPMessage, MessageType

# Federation-wide issuer/audience binding. Client JWTs must carry these claims
# so a token minted by the same signer for a *different* service cannot be
# replayed into the federation, and audit logs reflect a real, bound identity.
FEDERATION_ISSUER = "smcp-federation"
FEDERATION_AUDIENCE = "smcp-federation"


@dataclass
class ForwardingProof:
    """Proof that a server is forwarding a client's request"""
    client_jwt: str
    forwarded_by: str
    forwarded_at: float
    task_hash: str
    # The node this proof is intended for. Verified at the receiver so a proof
    # captured in transit cannot be replayed against a *different* node.
    forwarded_to: str = ""
    nonce: str = field(default_factory=lambda: str(uuid.uuid4()))
    expires_at: float = field(default_factory=lambda: time.time() + 300)  # 5 minutes


@dataclass
class SessionKey:
    """Ephemeral session key for encrypted communication between nodes"""
    key: bytes
    node_a: str
    node_b: str
    created_at: float
    expires_at: float
    nonce_counter: int = 0


class FederatedAuthManager:
    """Manages federated authentication using token forwarding pattern"""
    
    def __init__(self, config: SCPConfig, node_id: str):
        self.config = config
        self.node_id = node_id
        self.jwt_secret = config.jwt_secret
        self.logger = logging.getLogger(f'federated_auth_{node_id}')

        # Federation client-token verification posture. This is SEPARATE from the
        # transport JWT: it only chooses how *forwarded client tokens* are
        # verified, and never mints anything, so it doesn't affect the transport
        # server's ability to mint its own session tokens. Prefer the dedicated
        # federation_jwt_* settings; fall back to the transport jwt_* fields for
        # backward compatibility. With HS256 (default) every node shares one
        # secret; RS256 with the issuer's public key lets nodes *verify* client
        # tokens but not *forge* them.
        sec = config.security
        self.jwt_algorithm = (getattr(sec, "federation_jwt_algorithm", None)
                              or getattr(sec, "jwt_algorithm", "HS256"))
        self._jwt_verify_key = None
        if self.jwt_algorithm == "RS256":
            key_path = (getattr(sec, "federation_jwt_public_key_path", None)
                        or getattr(sec, "jwt_public_key_path", None))
            if not key_path:
                raise ValueError(
                    "RS256 federation verification requires "
                    "security.federation_jwt_public_key_path (or the legacy "
                    "security.jwt_public_key_path) so nodes can verify (but not "
                    "forge) client tokens."
                )
            with open(key_path, "rb") as f:
                self._jwt_verify_key = f.read()
            self.logger.info("Federated JWT verification: RS256 (verify-only, cannot forge)")
        else:
            self._jwt_verify_key = self.jwt_secret
            self.logger.warning(
                "Federated JWT verification: HS256 shared secret (demo-grade — "
                "any node holding the secret can forge identities). Use RS256 in "
                "multi-party deployments."
            )
        
        # Session key management
        self.session_keys: Dict[str, SessionKey] = {}  # peer_node_id -> SessionKey
        self.forwarding_nonces: Dict[str, float] = {}  # nonce -> timestamp (for replay prevention)
        # Replay-cache concurrency + growth bounds (handlers run in a thread pool).
        self._nonce_lock = threading.Lock()
        self._max_nonces = 100_000
        self._max_session_keys = 10_000

        # Trust relationships
        self.trusted_forwarders: Dict[str, bool] = {}  # node_id -> trusted

        # Per-node forwarding-proof signing (asymmetric). When this node has its
        # own private key, it signs proofs with RSA-PSS so no shared-secret holder
        # can forge them; peers verify against the signer's registered public key.
        # Without a private key, proofs fall back to the shared-secret HMAC scheme.
        self.proof_private_key = None
        self.peer_public_keys: Dict[str, Any] = {}  # node_id -> RSA public key object
        proof_key_path = getattr(config.security, "proof_signing_key_path", None)
        if proof_key_path:
            with open(proof_key_path, "rb") as f:
                self.proof_private_key = serialization.load_pem_private_key(f.read(), password=None)
            # A node trusts its own proofs; register its own public key.
            self.peer_public_keys[node_id] = self.proof_private_key.public_key()
            self.logger.info("Forwarding proofs: per-node RSA-PSS signing (asymmetric)")

        # Initialize cryptographic components
        self._init_crypto()

    def _store_session_key(self, peer_node_id: str, session_key: 'SessionKey'):
        """Store a session key, evicting the oldest when over the cap so a flood
        of distinct peer ids can't grow the table without bound."""
        self.session_keys[peer_node_id] = session_key
        if len(self.session_keys) > self._max_session_keys:
            oldest = sorted(self.session_keys, key=lambda k: self.session_keys[k].created_at)
            for k in oldest[:len(self.session_keys) - self._max_session_keys]:
                del self.session_keys[k]

    def register_peer_public_key(self, node_id: str, public_key_path: str = None,
                                 public_key_pem: bytes = None):
        """Register a peer's forwarding-proof public key so this node can verify
        proofs the peer signs. Provide a PEM path or PEM bytes."""
        if public_key_pem is None:
            if not public_key_path:
                raise ValueError("register_peer_public_key needs a path or PEM bytes")
            with open(public_key_path, "rb") as f:
                public_key_pem = f.read()
        self.peer_public_keys[node_id] = serialization.load_pem_public_key(public_key_pem)
    
    def _init_crypto(self):
        """Initialize cryptographic components"""
        # Generate ephemeral ECDH key pair for this session
        self.private_key = ec.generate_private_key(ec.SECP256R1())
        self.public_key = self.private_key.public_key()
        
        # Serialize public key for sharing
        self.public_key_bytes = self.public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint
        )
    
    def validate_client_jwt(self, jwt_token: str) -> Dict[str, Any]:
        """Validate a client JWT: signature (algorithm-pinned), expiry, and the
        federation issuer/audience binding. PyJWT enforces exp/iat/aud/iss via
        the decode options, so a token minted for another audience — or one that
        is expired — is rejected before we look at any claim."""
        try:
            payload = jwt.decode(
                jwt_token,
                self._jwt_verify_key,
                algorithms=[self.jwt_algorithm],
                audience=FEDERATION_AUDIENCE,
                issuer=FEDERATION_ISSUER,
                options={"require": ["exp", "iat", "aud", "iss"]},
            )

            # Application-level required claims (beyond the registered ones).
            required_fields = ['user', 'permissions']
            for field in required_fields:
                if field not in payload:
                    raise jwt.InvalidTokenError(f"Missing required field: {field}")

            self.logger.debug(f"Valid client JWT for user: {payload['user']}")
            return payload

        except jwt.InvalidTokenError as e:
            self.logger.warning(f"Invalid JWT token: {e}")
            raise
    
    def can_forward_for_client(self, client_jwt: str) -> bool:
        """Check if we can forward requests for this client"""
        try:
            payload = self.validate_client_jwt(client_jwt)
            
            # Check if client allows forwarding
            forwarding_allowed = payload.get('forwarding_allowed', [])
            if not forwarding_allowed:
                return False
            
            # Check if this node is in the allowed list
            for pattern in forwarding_allowed:
                if pattern.endswith('*'):
                    if self.node_id.startswith(pattern[:-1]):
                        return True
                elif pattern == self.node_id:
                    return True
            
            return False
            
        except jwt.InvalidTokenError:
            return False
    
    def create_forwarding_proof(self, client_jwt: str, task: Dict[str, Any],
                                target_node: str) -> ForwardingProof:
        """Create signed proof that we're forwarding a client request to
        target_node. The target is bound into the (signed) proof so it is only
        valid at that node."""
        if not self.can_forward_for_client(client_jwt):
            raise PermissionError(f"Node {self.node_id} cannot forward for this client")

        task_hash = hashlib.sha256(json.dumps(task, sort_keys=True).encode()).hexdigest()

        proof = ForwardingProof(
            client_jwt=client_jwt,
            forwarded_by=self.node_id,
            forwarded_at=time.time(),
            task_hash=task_hash,
            forwarded_to=target_node
        )

        return proof

    @staticmethod
    def _proof_message(proof_data: Dict[str, Any]) -> bytes:
        # Canonical form: sorted keys + compact separators (matches the v3 message
        # signature style and serde_json's compact output), so proofs are
        # signable/verifiable byte-identically across languages (Python ⇄ Rust).
        return json.dumps(proof_data, sort_keys=True, separators=(",", ":")).encode()

    def sign_forwarding_proof(self, proof: ForwardingProof) -> Dict[str, Any]:
        """Sign the forwarding proof to prevent tampering.

        When this node has its own private key, the proof is signed with RSA-PSS
        (``sig_alg="PS256"``) so no shared-secret holder can forge it — verifiers
        check it against this node's registered public key. Otherwise it falls
        back to the shared-secret HMAC scheme.
        """
        proof_data = {
            'client_jwt': proof.client_jwt,
            'forwarded_by': proof.forwarded_by,
            'forwarded_at': proof.forwarded_at,
            'task_hash': proof.task_hash,
            'forwarded_to': proof.forwarded_to,
            'nonce': proof.nonce,
            'expires_at': proof.expires_at
        }
        message = self._proof_message(proof_data)

        if self.proof_private_key is not None:
            signature = self.proof_private_key.sign(
                message,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                            salt_length=hashes.SHA256.digest_size),  # 32; standard PS256 (RFC 7518), cross-language interoperable
                hashes.SHA256(),
            ).hex()
            return {'proof': proof_data, 'signature': signature, 'sig_alg': 'PS256'}

        # Shared-secret HMAC fallback.
        signature = hmac.new(self.jwt_secret.encode(), message, hashlib.sha256).hexdigest()
        return {'proof': proof_data, 'signature': signature, 'sig_alg': 'HS256'}

    def verify_forwarding_proof(self, signed_proof: Dict[str, Any]) -> Tuple[bool, Optional[ForwardingProof]]:
        """Verify a signed forwarding proof"""
        try:
            proof_data = signed_proof['proof']
            provided_signature = signed_proof['signature']
            sig_alg = signed_proof.get('sig_alg', 'HS256')
            message = self._proof_message(proof_data)
            signer = proof_data.get('forwarded_by')

            # Strict asymmetric mode: a node configured with its own proof key
            # rejects ALL shared-secret (HMAC) proofs — once the federation is on
            # per-node keys, the forgeable HMAC path must not remain selectable.
            if self.proof_private_key is not None and sig_alg != 'PS256':
                self.logger.warning(
                    "Rejecting non-PS256 proof: this node runs per-node asymmetric "
                    "proofs and does not accept shared-secret (HMAC) proofs."
                )
                return False, None

            # Algorithm pinning: if the claimed signer has a registered public key,
            # its proofs MUST be PS256. Otherwise an insider holding the shared
            # jwt_secret could forge a proof by setting sig_alg='HS256' and HMAC-
            # signing it — downgrading past the per-node asymmetric guarantee.
            if signer in self.peer_public_keys and sig_alg != 'PS256':
                self.logger.warning(
                    f"Rejecting non-PS256 proof for signer {signer!r} with a "
                    f"registered public key (downgrade attempt)"
                )
                return False, None

            if sig_alg == 'PS256':
                # Asymmetric: verify against the signer's registered public key.
                pub = self.peer_public_keys.get(signer)
                if pub is None:
                    self.logger.warning(f"No registered proof public key for signer {signer!r}")
                    return False, None
                try:
                    pub.verify(
                        bytes.fromhex(provided_signature),
                        message,
                        padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                                    salt_length=padding.PSS.MAX_LENGTH),
                        hashes.SHA256(),
                    )
                except (InvalidSignature, ValueError):
                    self.logger.warning("Invalid forwarding proof signature (PS256)")
                    return False, None
            else:
                # Shared-secret HMAC.
                expected_signature = hmac.new(
                    self.jwt_secret.encode(), message, hashlib.sha256
                ).hexdigest()
                if not hmac.compare_digest(provided_signature, expected_signature):
                    self.logger.warning("Invalid forwarding proof signature")
                    return False, None

            # Verify the proof was intended for THIS node — a proof captured on
            # the wire cannot be replayed against a different target. Require a
            # non-empty target: an empty forwarded_to must not opt out of binding
            # (which would let one proof be accepted at every node until expiry).
            intended_target = proof_data.get('forwarded_to', '')
            if not intended_target or intended_target != self.node_id:
                self.logger.warning(
                    f"Forwarding proof target mismatch: intended {intended_target!r}, "
                    f"received at {self.node_id}"
                )
                return False, None

            # Check expiration
            if proof_data['expires_at'] < time.time():
                self.logger.warning("Forwarding proof expired")
                return False, None
            
            # Replay check + record, done atomically under a lock. Handlers run in
            # a thread pool (and via asyncio.run in worker threads), so a naive
            # check-then-store races: two concurrent submissions of the same proof
            # could both pass the membership test. The lock closes that TOCTOU.
            nonce = proof_data['nonce']
            current_time = time.time()
            with self._nonce_lock:
                if nonce in self.forwarding_nonces:
                    self.logger.warning("Forwarding proof nonce already used (replay attack?)")
                    return False, None
                # Prune expired nonces, then bound total size (evict oldest) so a
                # flood of unique nonces can't grow the cache without limit.
                expired = [n for n, t in self.forwarding_nonces.items() if current_time - t > 600]
                for n in expired:
                    del self.forwarding_nonces[n]
                if len(self.forwarding_nonces) >= self._max_nonces:
                    for n in sorted(self.forwarding_nonces, key=self.forwarding_nonces.get)[:len(self.forwarding_nonces) - self._max_nonces + 1]:
                        del self.forwarding_nonces[n]
                self.forwarding_nonces[nonce] = current_time
            
            # Create ForwardingProof object
            proof = ForwardingProof(
                client_jwt=proof_data['client_jwt'],
                forwarded_by=proof_data['forwarded_by'],
                forwarded_at=proof_data['forwarded_at'],
                task_hash=proof_data['task_hash'],
                forwarded_to=proof_data.get('forwarded_to', ''),
                nonce=proof_data['nonce'],
                expires_at=proof_data['expires_at']
            )
            
            return True, proof
            
        except (KeyError, json.JSONDecodeError) as e:
            self.logger.warning(f"Invalid forwarding proof format: {e}")
            return False, None
    
    def _pfs_enabled(self) -> bool:
        return bool(getattr(getattr(self.config, "crypto", None), "perfect_forward_secrecy", False))

    def _derive_ecdh_session(self, peer_node_id: str, ephemeral_private, peer_pub_bytes: bytes) -> SessionKey:
        """Derive a session key from an ECDH shared secret.

        The HKDF salt is bound to the exchange transcript (both ephemeral public
        keys, order-independent) so both peers derive the same 256-bit key from a
        single round-trip without needing any pre-shared salt, and the key is
        tied to this specific exchange. ``info`` binds the sorted node pair.
        """
        peer_pub = ec.EllipticCurvePublicKey.from_encoded_point(
            ec.SECP256R1(), peer_pub_bytes)
        shared = ephemeral_private.exchange(ec.ECDH(), peer_pub)
        my_pub_bytes = ephemeral_private.public_key().public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint)
        transcript = b"".join(sorted([my_pub_bytes, peer_pub_bytes]))
        salt = hashlib.sha256(transcript).digest()
        node_a = min(self.node_id, peer_node_id)
        node_b = max(self.node_id, peer_node_id)
        info = f"smcp-ecdh-session:{node_a}:{node_b}".encode()
        key = HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=info).derive(shared)
        return SessionKey(key=key, node_a=node_a, node_b=node_b,
                          created_at=time.time(), expires_at=time.time() + 900)

    def perform_ecdh_exchange(self, peer_node_id: str, peer_pub_hex: str) -> str:
        """Receiver side of the ECDH handshake: given the peer's ephemeral public
        key, generate our own ephemeral keypair, derive+store the session key, and
        return our ephemeral public key. The ephemeral private key is discarded
        after derivation (forward secrecy)."""
        ephemeral = ec.generate_private_key(ec.SECP256R1())
        my_pub_bytes = ephemeral.public_key().public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint)
        session_key = self._derive_ecdh_session(
            peer_node_id, ephemeral, bytes.fromhex(peer_pub_hex))
        self._store_session_key(peer_node_id, session_key)
        return my_pub_bytes.hex()

    async def initiate_ecdh(self, peer_node_id: str, exchange_fn) -> SessionKey:
        """Sender side of the ECDH handshake. ``exchange_fn(my_pub_hex)`` delivers
        our ephemeral public key to the peer and returns the peer's ephemeral
        public key (as hex). Works over any transport (real WS capability, or an
        in-process call)."""
        ephemeral = ec.generate_private_key(ec.SECP256R1())
        my_pub_bytes = ephemeral.public_key().public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint)
        peer_pub_hex = await exchange_fn(my_pub_bytes.hex())
        session_key = self._derive_ecdh_session(
            peer_node_id, ephemeral, bytes.fromhex(peer_pub_hex))
        self._store_session_key(peer_node_id, session_key)
        return session_key

    async def negotiate_session_key(self, peer_node_id: str, client_jwt: str,
                                    exchange_fn=None) -> SessionKey:
        """Negotiate an ephemeral session key with another node.

        With ``crypto.perfect_forward_secrecy`` enabled, performs a real ECDH
        handshake (per-session ephemeral keys, discarded after use) so a later
        compromise of long-term secrets can't decrypt past sessions. ``exchange_fn``
        carries our ephemeral public key to the peer and returns theirs; the
        caller supplies it (over the WS transport, or in-process for the demo).

        Without forward secrecy (default), derives a per-node-pair key from the
        shared deployment secret via HKDF — unrecoverable without that secret,
        but not forward-secret.
        """
        existing_key = self.session_keys.get(peer_node_id)
        if existing_key and existing_key.expires_at > time.time():
            return existing_key

        if self._pfs_enabled() and exchange_fn is not None:
            self.logger.debug(f"ECDH forward-secret negotiation with {peer_node_id}")
            return await self.initiate_ecdh(peer_node_id, exchange_fn)

        # Shared-secret HKDF fallback.
        node_a = min(self.node_id, peer_node_id)
        node_b = max(self.node_id, peer_node_id)
        secret = (getattr(self.config, "secret_key", "") or "").encode()
        if not secret:
            raise ValueError("secret_key must be set to negotiate a session key")
        salt = (getattr(self.config, "kdf_salt", "") or "malgra-tunnel-v3").encode()
        info = f"smcp-federated-session:{node_a}:{node_b}".encode()
        session_secret = HKDF(
            algorithm=hashes.SHA256(), length=32, salt=salt, info=info
        ).derive(secret)

        session_key = SessionKey(
            key=session_secret, node_a=node_a, node_b=node_b,
            created_at=time.time(), expires_at=time.time() + 900,
        )
        self._store_session_key(peer_node_id, session_key)
        self.logger.debug(f"Negotiated session key with {peer_node_id}")
        return session_key
    
    def encrypt_with_session_key(self, data: Dict[str, Any], session_key: SessionKey) -> Dict[str, Any]:
        """Encrypt data using session key.

        Uses a fresh random 96-bit nonce per message. The previous shared,
        per-writer counter (both peers starting at 0 under the same key) caused
        catastrophic AES-GCM nonce reuse; a random nonce removes that entirely.
        """
        nonce = secrets.token_bytes(12)

        # Serialize data
        plaintext = json.dumps(data).encode()

        # Bind the session identity into the GCM tag as AAD, so ciphertext can't
        # be lifted onto a different session (the session_id is authenticated, not
        # just carried alongside).
        session_id = f"{session_key.node_a}:{session_key.node_b}"
        aad = session_id.encode()

        cipher = Cipher(algorithms.AES(session_key.key), modes.GCM(nonce))
        encryptor = cipher.encryptor()
        encryptor.authenticate_additional_data(aad)
        ciphertext = encryptor.update(plaintext) + encryptor.finalize()

        return {
            'encrypted_data': ciphertext.hex(),
            'nonce': nonce.hex(),
            'tag': encryptor.tag.hex(),
            'session_id': session_id,
            'encrypted_at': time.time()
        }
    
    def decrypt_with_session_key(self, encrypted_data: Dict[str, Any], peer_node_id: str) -> Dict[str, Any]:
        """Decrypt data using session key"""
        
        session_key = self.session_keys.get(peer_node_id)
        if not session_key:
            raise ValueError(f"No session key found for {peer_node_id}")
        
        if session_key.expires_at < time.time():
            raise ValueError(f"Session key expired for {peer_node_id}")
        
        # Extract encrypted components
        ciphertext = bytes.fromhex(encrypted_data['encrypted_data'])
        nonce = bytes.fromhex(encrypted_data['nonce'])
        tag = bytes.fromhex(encrypted_data['tag'])

        # Re-derive and verify the session-id AAD. The claimed session_id must
        # match this session key's pair, so ciphertext bound to a different
        # session fails authentication rather than decrypting.
        expected_session_id = f"{session_key.node_a}:{session_key.node_b}"
        claimed = encrypted_data.get('session_id', expected_session_id)
        if claimed != expected_session_id:
            raise ValueError("session_id mismatch")

        cipher = Cipher(algorithms.AES(session_key.key), modes.GCM(nonce, tag))
        decryptor = cipher.decryptor()
        decryptor.authenticate_additional_data(expected_session_id.encode())
        plaintext = decryptor.update(ciphertext) + decryptor.finalize()

        return json.loads(plaintext.decode())
    
    def trust_forwarder(self, node_id: str):
        """Mark a node as trusted for forwarding"""
        self.trusted_forwarders[node_id] = True
        self.logger.info(f"Trusting forwarder: {node_id}")
    
    def is_trusted_forwarder(self, node_id: str) -> bool:
        """Check if a node is trusted for forwarding"""
        return self.trusted_forwarders.get(node_id, False)


class FederatedSCPNode:
    """SCP Node with federated authentication capabilities"""
    
    def __init__(self, config: SCPConfig, node_id: str):
        self.config = config
        self.node_id = node_id
        self.auth_manager = FederatedAuthManager(config, node_id)
        self.logger = logging.getLogger(f'federated_node_{node_id}')

        # Known peers in the federation
        self.peers: Dict[str, str] = {}  # node_id -> endpoint

        # Real cross-node transport (opt-in). When enabled, forward_request goes
        # over the authenticated SMCP WebSocket RPC instead of the in-process
        # DEMO_FEDERATION_NODES mock used by the demo/tests.
        self.peer_pool = None

    def enable_real_transport(self, transport_config: 'SCPConfig' = None):
        """Route forwarded requests over the real SMCP WebSocket transport.

        Reuses the same PeerConnectionPool as the distributed layer. Peers must
        run a forward server (see :meth:`make_forward_server`)."""
        from smcp_distributed_transport import PeerConnectionPool
        self.peer_pool = PeerConnectionPool(transport_config or self.config)

    def make_forward_server(self, config: 'SCPConfig' = None):
        """Build a server exposing the ``federated_forward`` capability so peers
        can deliver forwarded requests over the real transport."""
        from smcp_distributed_transport import DistributedTaskServer

        def _dispatch(encrypted_request, from_node):
            # handle_forwarded_request is async; run it to completion in this
            # worker thread (handlers are dispatched off the event loop).
            return asyncio.run(self.handle_forwarded_request(encrypted_request, from_node))

        def _key_exchange(peer_node, peer_pub_hex):
            # ECDH handshake (forward secrecy): derive+store a session key with the
            # peer and return our ephemeral public key.
            my_pub_hex = self.auth_manager.perform_ecdh_exchange(peer_node, peer_pub_hex)
            return {"peer_pub_hex": my_pub_hex}

        server = DistributedTaskServer(config or self.config, dispatch=None)
        server.register(
            "federated_forward",
            {"encrypted_request": {"type": "object"}, "from_node": {"type": "string"}},
            _dispatch,
            description="Receive a forwarded, token-authenticated request from a peer",
        )
        server.register(
            "federated_key_exchange",
            {"peer_node": {"type": "string"}, "peer_pub_hex": {"type": "string"}},
            _key_exchange,
            description="ECDH ephemeral key exchange for forward-secret sessions",
        )
        return server

    def add_peer(self, node_id: str, endpoint: str, proof_public_key_path: str = None):
        """Add a peer node to the federation.

        Pass ``proof_public_key_path`` to register the peer's forwarding-proof
        public key so this node can verify proofs the peer signs with its own
        private key (asymmetric mode). Without it, verification uses the shared
        secret."""
        self.peers[node_id] = endpoint
        self.auth_manager.trust_forwarder(node_id)
        if proof_public_key_path:
            self.auth_manager.register_peer_public_key(node_id, proof_public_key_path)
        self.logger.info(f"Added federated peer: {node_id} at {endpoint}")
    
    async def forward_request(self, task: Dict[str, Any], target_node: str, client_jwt: str) -> Dict[str, Any]:
        """Forward a client request to another node with token forwarding auth"""

        # Create and sign forwarding proof (bound to the target node)
        proof = self.auth_manager.create_forwarding_proof(client_jwt, task, target_node)
        signed_proof = self.auth_manager.sign_forwarding_proof(proof)

        # Decide transport up front so the ECDH key exchange (if forward secrecy
        # is enabled) uses the same channel as the request.
        use_real = self.peer_pool is not None and target_node in self.peers
        host = port = None
        if use_real:
            from urllib.parse import urlparse
            parsed = urlparse(self.peers[target_node])
            host = parsed.hostname or "localhost"
            port = parsed.port

        # Exchange function for forward-secret ECDH: carries our ephemeral public
        # key to the peer and returns theirs. No-op unless PFS is enabled.
        if use_real:
            async def exchange_fn(my_pub_hex):
                res = await self.peer_pool.call(
                    target_node, host, port, "federated_key_exchange",
                    peer_node=self.node_id, peer_pub_hex=my_pub_hex)
                return res["peer_pub_hex"]
        else:
            async def exchange_fn(my_pub_hex):
                mock = DEMO_FEDERATION_NODES.get(target_node)
                if not mock:
                    raise ValueError(f"Target node {target_node} not found")
                return mock.auth_manager.perform_ecdh_exchange(self.node_id, my_pub_hex)

        # Negotiate session key with target node (ECDH when PFS is enabled).
        session_key = await self.auth_manager.negotiate_session_key(
            target_node, client_jwt, exchange_fn=exchange_fn)

        # Create request payload
        request_payload = {
            'task': task,
            'auth_proof': signed_proof,
            'forwarding_metadata': {
                'original_client': self._extract_user_from_jwt(client_jwt),
                'forwarding_path': [self.node_id],
                'task_id': task.get('task_id', str(uuid.uuid4())),
                'timestamp': time.time()
            }
        }

        # Encrypt the request
        encrypted_request = self.auth_manager.encrypt_with_session_key(request_payload, session_key)

        self.logger.info(f"Forwarding request to {target_node} with client token auth")

        # Real transport when enabled and the peer endpoint is known; otherwise
        # fall back to the in-process DEMO_FEDERATION_NODES simulation.
        if use_real:
            return await self.peer_pool.call(
                target_node, host, port,
                "federated_forward",
                encrypted_request=encrypted_request, from_node=self.node_id,
            )

        return await self._simulate_forwarded_request(encrypted_request, target_node)
    
    async def handle_forwarded_request(self, encrypted_request: Dict[str, Any], from_node: str) -> Dict[str, Any]:
        """Handle a request forwarded from another node"""
        
        try:
            # Ensure a session key exists for the sender.
            if from_node not in self.auth_manager.session_keys:
                if self.auth_manager._pfs_enabled():
                    # Forward secrecy is required: the sender must have completed
                    # the ECDH key exchange (federated_key_exchange) first. Refuse
                    # to silently fall back to the deterministic long-term-secret
                    # key, which would strip forward secrecy.
                    raise ValueError(
                        "No forward-secret session established; ECDH key exchange "
                        "is required before forwarding when perfect_forward_secrecy "
                        "is enabled."
                    )
                # PFS off: derive the deterministic shared-secret key on demand
                # (both sides compute the same key, so no exchange is needed).
                await self.auth_manager.negotiate_session_key(from_node, "")

            # Decrypt the request
            request_payload = self.auth_manager.decrypt_with_session_key(encrypted_request, from_node)
            
            # Extract and verify forwarding proof
            auth_proof = request_payload['auth_proof']
            is_valid, proof = self.auth_manager.verify_forwarding_proof(auth_proof)
            
            if not is_valid:
                raise ValueError("Invalid forwarding proof")

            # The transport-level sender (from_node, which selected the session key)
            # must match the signature-verified proof signer. Otherwise an insider
            # could decouple transport identity from proof identity (arbitrary
            # session-key derivation, muddied audit attribution).
            if from_node != proof.forwarded_by:
                raise ValueError(
                    f"from_node {from_node!r} does not match proof.forwarded_by "
                    f"{proof.forwarded_by!r}"
                )

            # Validate the original client JWT
            client_payload = self.auth_manager.validate_client_jwt(proof.client_jwt)

            # Check if forwarding node is trusted
            if not self.auth_manager.is_trusted_forwarder(proof.forwarded_by):
                raise ValueError(f"Untrusted forwarder: {proof.forwarded_by}")
            
            # Extract task and process it
            task = request_payload['task']
            forwarding_metadata = request_payload['forwarding_metadata']
            
            self.logger.info(f"Processing forwarded request for client: {forwarding_metadata['original_client']}")
            
            # Process the task with client's permissions
            result = await self._process_task_with_client_auth(task, client_payload, forwarding_metadata)
            
            return {
                'status': 'success',
                'result': result,
                'processed_by': self.node_id,
                'processed_at': time.time(),
                'forwarding_chain': forwarding_metadata['forwarding_path'] + [self.node_id]
            }
            
        except Exception as e:
            self.logger.error(f"Failed to process forwarded request: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'processed_by': self.node_id,
                'processed_at': time.time()
            }
    
    def _extract_user_from_jwt(self, jwt_token: str) -> str:
        """Extract the user id from a client JWT, verifying its signature first.

        Only authenticated identities are surfaced (e.g. into forwarding
        metadata and audit logs). An unsigned, forged, or expired token yields
        'unknown' rather than trusting attacker-controlled claims — decoding
        with verify_signature disabled would let anyone spoof the logged
        client identity.
        """
        try:
            payload = self.auth_manager.validate_client_jwt(jwt_token)
            return payload.get('user', 'unknown')
        except Exception:
            return 'unknown'
    
    async def _simulate_forwarded_request(self, encrypted_request: Dict[str, Any], target_node: str) -> Dict[str, Any]:
        """Simulate forwarded request for prototype (replace with real network call)"""
        # Simulate network delay
        await asyncio.sleep(0.1)
        
        # Get the actual target node from global registry
        mock_target = DEMO_FEDERATION_NODES.get(target_node)
        if not mock_target:
            return {'status': 'error', 'error': f'Target node {target_node} not found'}
        
        mock_target.auth_manager.trust_forwarder(self.node_id)
        
        # Share session key with target node (simulate key exchange)
        if target_node in self.auth_manager.session_keys:
            session_key = self.auth_manager.session_keys[target_node]
            mock_target.auth_manager.session_keys[self.node_id] = session_key
        
        return await mock_target.handle_forwarded_request(encrypted_request, self.node_id)
    
    async def _process_task_with_client_auth(self, task: Dict[str, Any], client_payload: Dict[str, Any], metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Process task using client's authentication and permissions"""
        
        # Check client permissions for this task
        permissions = client_payload.get('permissions', [])
        task_type = task.get('type', 'unknown')
        
        required_permission = f"task:{task_type}"
        if required_permission not in permissions and 'task:*' not in permissions:
            raise PermissionError(f"Client lacks permission: {required_permission}")
        
        # Process the task (simulate different task types)
        if task_type == 'ai_reasoning':
            return await self._process_ai_task(task, client_payload)
        elif task_type == 'storage':
            return await self._process_storage_task(task, client_payload)
        else:
            return {
                'task_type': task_type,
                'processed_by': self.node_id,
                'client': client_payload['user'],
                'result': f"Task {task_type} completed successfully",
                'timestamp': time.time()
            }
    
    async def _process_ai_task(self, task: Dict[str, Any], client_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process AI reasoning task"""
        return {
            'ai_result': f"AI processing completed for {client_payload['user']}",
            'model_used': 'federated_ai_model',
            'confidence': 0.95,
            'processing_node': self.node_id
        }
    
    async def _process_storage_task(self, task: Dict[str, Any], client_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process storage task"""
        return {
            'storage_result': f"Data stored for {client_payload['user']}",
            'storage_id': str(uuid.uuid4()),
            'storage_node': self.node_id,
            'encrypted': True
        }


def create_test_jwt(user: str, permissions: List[str], forwarding_allowed: List[str] = None,
                    secret: str = "test_jwt_secret_for_federated_auth_demo") -> str:
    """Create a test JWT token for demonstration.

    Emits the federation issuer/audience binding so the token validates against
    validate_client_jwt. `secret` must match the verifying node's HS256 secret
    (config.jwt_secret); pass it explicitly rather than relying on a coincidence.
    """
    if forwarding_allowed is None:
        forwarding_allowed = ["*"]  # Allow forwarding to any node by default

    payload = {
        'user': user,
        'permissions': permissions,
        'forwarding_allowed': forwarding_allowed,
        'iss': FEDERATION_ISSUER,
        'aud': FEDERATION_AUDIENCE,
        'iat': time.time(),
        'exp': time.time() + 3600  # 1 hour expiration
    }

    return jwt.encode(payload, secret, algorithm='HS256')


def mint_client_jwt(user: str, permissions: List[str],
                    forwarding_allowed: List[str] = None,
                    private_key_path: str = None, private_key_pem: bytes = None,
                    ttl_seconds: int = 3600) -> str:
    """Mint a real RS256 federation client token from an issuer's private key.

    This is the production issuer counterpart to ``create_test_jwt`` (HS256,
    test-only). Only the holder of the RSA private key can mint; every node
    verifies with the corresponding public key (``jwt_public_key_path`` +
    ``jwt_algorithm="RS256"``) and *cannot forge* tokens. The token carries the
    federation issuer/audience binding so it validates against
    ``FederatedAuthManager.validate_client_jwt``.

    Provide the signing key as ``private_key_path`` (PEM file) or
    ``private_key_pem`` (PEM bytes/str).
    """
    if forwarding_allowed is None:
        forwarding_allowed = ["*"]

    if private_key_pem is None:
        if not private_key_path:
            raise ValueError("mint_client_jwt requires private_key_path or private_key_pem")
        with open(private_key_path, "rb") as f:
            private_key_pem = f.read()

    now = time.time()
    payload = {
        'user': user,
        'permissions': permissions,
        'forwarding_allowed': forwarding_allowed,
        'iss': FEDERATION_ISSUER,
        'aud': FEDERATION_AUDIENCE,
        'iat': now,
        'exp': now + ttl_seconds,
    }
    return jwt.encode(payload, private_key_pem, algorithm='RS256')


# Global federation registry for demo
DEMO_FEDERATION_NODES = {}

async def demo_federated_authentication():
    """Demonstrate the federated authentication pattern"""
    
    print("🔐 SMCP-SA2A Federated Authentication Demo")
    print("==========================================")
    
    # Create test configuration
    config = SCPConfig(
        node_id="demo_client",
        jwt_secret="test_jwt_secret_for_federated_auth_demo",
        secret_key="demo_secret_key_for_session_key_negotiation_0001",
        kdf_salt="demo_federation_kdf_salt_0001",
    )
    
    # Create federated nodes
    gpu_server_1 = FederatedSCPNode(config, "gpu_server_1")
    gpu_server_2 = FederatedSCPNode(config, "gpu_server_2")
    storage_server = FederatedSCPNode(config, "storage_server")
    
    # Register nodes in global registry for demo
    DEMO_FEDERATION_NODES["gpu_server_1"] = gpu_server_1
    DEMO_FEDERATION_NODES["gpu_server_2"] = gpu_server_2
    DEMO_FEDERATION_NODES["storage_server"] = storage_server
    
    # Set up federation relationships
    gpu_server_1.add_peer("gpu_server_2", "ws://localhost:8767")
    gpu_server_1.add_peer("storage_server", "ws://localhost:8768")
    gpu_server_2.add_peer("storage_server", "ws://localhost:8768")
    
    # Create test client JWT
    client_jwt = create_test_jwt(
        user="alice@company.com",
        permissions=["task:ai_reasoning", "task:storage", "task:*"],
        forwarding_allowed=["gpu_server_*", "storage_server"]
    )
    
    print(f"✅ Created client JWT for: alice@company.com")
    print(f"✅ Set up federation: gpu_server_1 → gpu_server_2 → storage_server")
    
    # Test 1: Direct forwarding
    print("\n🔄 Test 1: Direct Token Forwarding")
    print("-" * 40)
    
    task1 = {
        'task_id': 'test_ai_001',
        'type': 'ai_reasoning',
        'prompt': 'Analyze federated authentication benefits',
        'model': 'qwen3-coder'
    }
    
    result1 = await gpu_server_1.forward_request(task1, "gpu_server_2", client_jwt)
    print(f"✅ Direct forwarding result: {result1['status']}")
    print(f"   Processed by: {result1['processed_by']}")
    print(f"   Forwarding chain: {result1.get('forwarding_chain', [])}")
    
    # Test 2: Chain forwarding (gpu_server_1 → gpu_server_2 → storage_server)
    print("\n🔗 Test 2: Chain Token Forwarding")
    print("-" * 40)
    
    # First, gpu_server_1 forwards to gpu_server_2
    task2 = {
        'task_id': 'test_chain_001',
        'type': 'storage',
        'data': 'Federated authentication test data',
        'encryption': True
    }
    
    # Simulate gpu_server_2 then forwarding to storage_server
    result2 = await gpu_server_2.forward_request(task2, "storage_server", client_jwt)
    print(f"✅ Chain forwarding result: {result2['status']}")
    print(f"   Final processor: {result2['processed_by']}")
    print(f"   Forwarding chain: {result2.get('forwarding_chain', [])}")
    
    # Test 3: Demonstrate security features
    print("\n🛡️  Test 3: Security Validation")
    print("-" * 40)
    
    # Test with expired JWT
    try:
        expired_jwt = create_test_jwt(
            user="eve@malicious.com",
            permissions=["task:*"],
            forwarding_allowed=["*"]
        )
        # Manually set expiration in the past
        payload = jwt.decode(expired_jwt, options={"verify_signature": False})
        payload['exp'] = time.time() - 3600  # Expired 1 hour ago
        expired_jwt = jwt.encode(payload, config.jwt_secret, algorithm='HS256')
        
        result3 = await gpu_server_1.forward_request(task1, "gpu_server_2", expired_jwt)
        print(f"❌ Should have failed with expired token!")
    except jwt.ExpiredSignatureError:
        print(f"✅ Correctly rejected expired JWT")
    except Exception as e:
        print(f"✅ Correctly rejected invalid request: {type(e).__name__}")
    
    # Test 4: Permission validation
    print("\n🔒 Test 4: Permission Validation")
    print("-" * 40)
    
    # Test with limited permissions
    limited_jwt = create_test_jwt(
        user="bob@company.com",
        permissions=["task:ai_reasoning"],  # No storage permission
        forwarding_allowed=["gpu_server_*"]
    )
    
    result4 = await gpu_server_1.forward_request(task2, "gpu_server_2", limited_jwt)  # storage task
    if result4['status'] == 'error':
        print(f"✅ Correctly rejected unauthorized task: {result4['error']}")
    else:
        print(f"❌ Should have rejected unauthorized task!")
    
    print("\n🎉 Federated Authentication Demo Complete!")
    print("\nKey Benefits Demonstrated:")
    print("✅ Client identity preserved across federation")
    print("✅ Ephemeral session keys for encrypted communication")
    print("✅ Signed forwarding proofs prevent tampering")
    print("✅ Permission validation at each node")
    print("✅ Replay attack prevention with nonces")
    print("✅ Token expiration handling")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    asyncio.run(demo_federated_authentication())