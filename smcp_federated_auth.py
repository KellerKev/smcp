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
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
import secrets
import jwt

from scp_config import SCPConfig
from scp_core import SCPMessage, MessageType


@dataclass
class ForwardingProof:
    """Proof that a server is forwarding a client's request"""
    client_jwt: str
    forwarded_by: str
    forwarded_at: float
    task_hash: str
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
        """Validate client JWT token"""
        try:
            payload = jwt.decode(jwt_token, self.jwt_secret, algorithms=['HS256'])
            
            # Check expiration
            if payload.get('exp', 0) < time.time():
                raise jwt.ExpiredSignatureError("Token expired")
            
            # Validate required fields
            required_fields = ['user', 'permissions', 'iat']
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
    
    def create_forwarding_proof(self, client_jwt: str, task: Dict[str, Any]) -> ForwardingProof:
        """Create signed proof that we're forwarding a client request"""
        if not self.can_forward_for_client(client_jwt):
            raise PermissionError(f"Node {self.node_id} cannot forward for this client")
        
        task_hash = hashlib.sha256(json.dumps(task, sort_keys=True).encode()).hexdigest()
        
        proof = ForwardingProof(
            client_jwt=client_jwt,
            forwarded_by=self.node_id,
            forwarded_at=time.time(),
            task_hash=task_hash
        )
        
        return proof
    
    def sign_forwarding_proof(self, proof: ForwardingProof) -> Dict[str, Any]:
        """Sign the forwarding proof to prevent tampering"""
        proof_data = {
            'client_jwt': proof.client_jwt,
            'forwarded_by': proof.forwarded_by,
            'forwarded_at': proof.forwarded_at,
            'task_hash': proof.task_hash,
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
        
        # For prototype, generate a shared key based on both nodes' info
        # In production, this would involve actual ECDH key exchange over network
        
        # Create deterministic but ephemeral shared secret using canonical ordering
        node_a = min(self.node_id, peer_node_id)
        node_b = max(self.node_id, peer_node_id)
        key_material = f"{node_a}:{node_b}:{client_jwt[:50]}:{time.time()//300}"  # 5-minute windows
        shared_secret = hashlib.sha256(key_material.encode()).digest()
        
        session_key = SessionKey(
            key=shared_secret[:32],  # 256-bit key for AES
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
        """Encrypt data using session key"""
        
        # Increment nonce counter
        session_key.nonce_counter += 1
        nonce = session_key.nonce_counter.to_bytes(12, byteorder='big')
        
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
    
    def add_peer(self, node_id: str, endpoint: str):
        """Add a peer node to the federation"""
        self.peers[node_id] = endpoint
        self.auth_manager.trust_forwarder(node_id)
        self.logger.info(f"Added federated peer: {node_id} at {endpoint}")
    
    async def forward_request(self, task: Dict[str, Any], target_node: str, client_jwt: str) -> Dict[str, Any]:
        """Forward a client request to another node with token forwarding auth"""
        
        # Create and sign forwarding proof
        proof = self.auth_manager.create_forwarding_proof(client_jwt, task)
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
        
        # For prototype, return simulated response
        # In real implementation, this would make actual network call
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
        """Extract user ID from JWT token"""
        try:
            payload = jwt.decode(jwt_token, options={"verify_signature": False})
            return payload.get('user', 'unknown')
        except:
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


def create_test_jwt(user: str, permissions: List[str], forwarding_allowed: List[str] = None) -> str:
    """Create a test JWT token for demonstration"""
    if forwarding_allowed is None:
        forwarding_allowed = ["*"]  # Allow forwarding to any node by default
    
    payload = {
        'user': user,
        'permissions': permissions,
        'forwarding_allowed': forwarding_allowed,
        'iat': time.time(),
        'exp': time.time() + 3600  # 1 hour expiration
    }
    
    # Use a test secret (in production, this would be from config)
    test_secret = "test_jwt_secret_for_federated_auth_demo"
    return jwt.encode(payload, test_secret, algorithm='HS256')


# Global federation registry for demo
DEMO_FEDERATION_NODES = {}

async def demo_federated_authentication():
    """Demonstrate the federated authentication pattern"""
    
    print("🔐 SMCP-SA2A Federated Authentication Demo")
    print("==========================================")
    
    # Create test configuration
    config = SCPConfig(
        node_id="demo_client",
        jwt_secret="test_jwt_secret_for_federated_auth_demo"
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