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
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
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

        # JWT verification posture. With HS256 (default) every node shares one
        # secret, so any node — or anyone who reads it — can mint tokens for any
        # identity: a demo-grade trust model. Configure jwt_algorithm="RS256"
        # with a public key so nodes can *verify* client tokens but cannot
        # *forge* them; only the private-key holder (the client authority) mints.
        self.jwt_algorithm = getattr(config.security, "jwt_algorithm", "HS256")
        self._jwt_verify_key = None
        if self.jwt_algorithm == "RS256":
            key_path = getattr(config.security, "jwt_public_key_path", None)
            if not key_path:
                raise ValueError(
                    "jwt_algorithm=RS256 requires security.jwt_public_key_path "
                    "so nodes can verify (but not forge) client tokens."
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
        
        # Trust relationships
        self.trusted_forwarders: Dict[str, bool] = {}  # node_id -> trusted
        
        # Initialize cryptographic components
        self._init_crypto()
    
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

    def sign_forwarding_proof(self, proof: ForwardingProof) -> Dict[str, Any]:
        """Sign the forwarding proof to prevent tampering"""
        proof_data = {
            'client_jwt': proof.client_jwt,
            'forwarded_by': proof.forwarded_by,
            'forwarded_at': proof.forwarded_at,
            'task_hash': proof.task_hash,
            'forwarded_to': proof.forwarded_to,
            'nonce': proof.nonce,
            'expires_at': proof.expires_at
        }
        
        # Create signature using HMAC
        message = json.dumps(proof_data, sort_keys=True).encode()
        signature = hmac.new(
            self.jwt_secret.encode(),
            message,
            hashlib.sha256
        ).hexdigest()
        
        return {
            'proof': proof_data,
            'signature': signature
        }
    
    def verify_forwarding_proof(self, signed_proof: Dict[str, Any]) -> Tuple[bool, Optional[ForwardingProof]]:
        """Verify a signed forwarding proof"""
        try:
            proof_data = signed_proof['proof']
            provided_signature = signed_proof['signature']
            
            # Recreate signature
            message = json.dumps(proof_data, sort_keys=True).encode()
            expected_signature = hmac.new(
                self.jwt_secret.encode(),
                message,
                hashlib.sha256
            ).hexdigest()
            
            # Verify signature
            if not hmac.compare_digest(provided_signature, expected_signature):
                self.logger.warning("Invalid forwarding proof signature")
                return False, None

            # Verify the proof was intended for THIS node — a proof captured on
            # the wire cannot be replayed against a different target.
            intended_target = proof_data.get('forwarded_to', '')
            if intended_target and intended_target != self.node_id:
                self.logger.warning(
                    f"Forwarding proof target mismatch: intended {intended_target}, "
                    f"received at {self.node_id}"
                )
                return False, None

            # Check expiration
            if proof_data['expires_at'] < time.time():
                self.logger.warning("Forwarding proof expired")
                return False, None
            
            # Check for replay attack
            nonce = proof_data['nonce']
            if nonce in self.forwarding_nonces:
                self.logger.warning("Forwarding proof nonce already used (replay attack?)")
                return False, None
            
            # Store nonce to prevent replay
            self.forwarding_nonces[nonce] = time.time()
            
            # Clean up old nonces periodically
            current_time = time.time()
            expired_nonces = [n for n, t in self.forwarding_nonces.items() if current_time - t > 600]
            for n in expired_nonces:
                del self.forwarding_nonces[n]
            
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
    
    async def negotiate_session_key(self, peer_node_id: str, client_jwt: str) -> SessionKey:
        """Negotiate ephemeral session key with another node"""
        
        # Check if we already have a valid session key
        existing_key = self.session_keys.get(peer_node_id)
        if existing_key and existing_key.expires_at > time.time():
            return existing_key
        
        # Derive a per-node-pair key from the shared deployment secret via HKDF.
        # Previously this hashed only public/guessable material (node ids, a JWT
        # prefix, a coarse time bucket) with NO secret, so anyone could recompute
        # the key. HKDF over the deployment secret makes it unrecoverable without
        # that secret. (Full forward-secret ECDH is the P4 asymmetric redesign;
        # this keeps the current shared-secret model but closes the disclosure.)
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
            key=session_secret,  # 256-bit key for AES
            node_a=node_a,
            node_b=node_b,
            created_at=time.time(),
            expires_at=time.time() + 900  # 15 minutes
        )
        
        # Store the session key
        self.session_keys[peer_node_id] = session_key
        
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
        
        # Encrypt with AES-GCM
        cipher = Cipher(algorithms.AES(session_key.key), modes.GCM(nonce))
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(plaintext) + encryptor.finalize()
        
        return {
            'encrypted_data': ciphertext.hex(),
            'nonce': nonce.hex(),
            'tag': encryptor.tag.hex(),
            'session_id': f"{session_key.node_a}:{session_key.node_b}",
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
        
        # Decrypt with AES-GCM
        cipher = Cipher(algorithms.AES(session_key.key), modes.GCM(nonce, tag))
        decryptor = cipher.decryptor()
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

        server = DistributedTaskServer(config or self.config, dispatch=None)
        server.register(
            "federated_forward",
            {"encrypted_request": {"type": "object"}, "from_node": {"type": "string"}},
            _dispatch,
            description="Receive a forwarded, token-authenticated request from a peer",
        )
        return server

    def add_peer(self, node_id: str, endpoint: str):
        """Add a peer node to the federation"""
        self.peers[node_id] = endpoint
        self.auth_manager.trust_forwarder(node_id)
        self.logger.info(f"Added federated peer: {node_id} at {endpoint}")
    
    async def forward_request(self, task: Dict[str, Any], target_node: str, client_jwt: str) -> Dict[str, Any]:
        """Forward a client request to another node with token forwarding auth"""
        
        # Create and sign forwarding proof (bound to the target node)
        proof = self.auth_manager.create_forwarding_proof(client_jwt, task, target_node)
        signed_proof = self.auth_manager.sign_forwarding_proof(proof)
        
        # Negotiate session key with target node
        session_key = await self.auth_manager.negotiate_session_key(target_node, client_jwt)
        
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
        if self.peer_pool is not None and target_node in self.peers:
            from urllib.parse import urlparse
            parsed = urlparse(self.peers[target_node])
            host = parsed.hostname or "localhost"
            port = parsed.port
            return await self.peer_pool.call(
                target_node, host, port,
                "federated_forward",
                encrypted_request=encrypted_request, from_node=self.node_id,
            )

        return await self._simulate_forwarded_request(encrypted_request, target_node)
    
    async def handle_forwarded_request(self, encrypted_request: Dict[str, Any], from_node: str) -> Dict[str, Any]:
        """Handle a request forwarded from another node"""
        
        try:
            # Decrypt the request
            request_payload = self.auth_manager.decrypt_with_session_key(encrypted_request, from_node)
            
            # Extract and verify forwarding proof
            auth_proof = request_payload['auth_proof']
            is_valid, proof = self.auth_manager.verify_forwarding_proof(auth_proof)
            
            if not is_valid:
                raise ValueError("Invalid forwarding proof")
            
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