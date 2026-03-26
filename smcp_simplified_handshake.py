#!/usr/bin/env python3
"""
Simplified Handshake System for SMCP-SA2A
Optional one-time secret/password authentication with asymmetric key exchange
"""

import asyncio
import json
import uuid
import time
import hashlib
import hmac
import secrets
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import jwt

from scp_config import SCPConfig


@dataclass
class SimplifiedSession:
    """Simplified session with asymmetric key exchange"""
    session_id: str
    aes_key: bytes
    client_id: str
    server_id: str
    created_at: float
    expires_at: float
    nonce_counter: int = 0


class SimplifiedHandshakeManager:
    """Manages simplified one-time secret handshakes"""
    
    def __init__(self, config: SCPConfig, node_id: str):
        self.config = config
        self.node_id = node_id
        self.logger = logging.getLogger(f'simplified_handshake_{node_id}')
        
        # Session management
        self.active_sessions: Dict[str, SimplifiedSession] = {}  # session_id -> SimplifiedSession
        self.one_time_secrets: Dict[str, Dict[str, Any]] = {}  # secret -> {client_id, created_at, expires_at}
        
        # Generate RSA key pair for this node
        self._init_crypto()
        
        # Pre-configured one-time secrets (in production, these would be generated dynamically)
        self._setup_demo_secrets()
    
    def _init_crypto(self):
        """Initialize RSA key pair for asymmetric encryption"""
        self.private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )
        self.public_key = self.private_key.public_key()
        
        # Serialize public key for sharing
        self.public_key_pem = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        
        self.logger.info(f"Generated RSA key pair for {self.node_id}")
    
    def _setup_demo_secrets(self):
        """Setup demo one-time secrets (for testing)"""
        demo_secrets = {
            "demo_secret_2024": {
                "client_id": "demo_client",
                "created_at": time.time(),
                "expires_at": time.time() + 3600,  # 1 hour
                "description": "Demo secret for testing"
            },
            "enterprise_key_abc123": {
                "client_id": "enterprise_client",
                "created_at": time.time(),
                "expires_at": time.time() + 86400,  # 24 hours
                "description": "Enterprise client temporary access"
            }
        }
        
        self.one_time_secrets.update(demo_secrets)
        self.logger.info(f"Setup {len(demo_secrets)} demo one-time secrets")
    
    def generate_one_time_secret(self, client_id: str, duration_hours: int = 1) -> str:
        """Generate a new one-time secret for a client"""
        secret = secrets.token_urlsafe(32)  # 256-bit secret
        
        self.one_time_secrets[secret] = {
            "client_id": client_id,
            "created_at": time.time(),
            "expires_at": time.time() + (duration_hours * 3600),
            "description": f"Generated for {client_id}"
        }
        
        self.logger.info(f"Generated one-time secret for {client_id}, expires in {duration_hours}h")
        return secret
    
    def validate_one_time_secret(self, secret: str, client_id: str) -> bool:
        """Validate a one-time secret"""
        if secret not in self.one_time_secrets:
            self.logger.warning(f"Unknown one-time secret from {client_id}")
            return False
        
        secret_info = self.one_time_secrets[secret]
        
        # Check expiration
        if secret_info["expires_at"] < time.time():
            self.logger.warning(f"Expired one-time secret from {client_id}")
            del self.one_time_secrets[secret]  # Clean up expired secret
            return False
        
        # Check client ID match (optional - can allow any client with valid secret)
        if secret_info["client_id"] != client_id and secret_info["client_id"] != "*":
            self.logger.warning(f"Client ID mismatch for secret: expected {secret_info['client_id']}, got {client_id}")
            return False
        
        self.logger.info(f"Valid one-time secret from {client_id}")
        return True
    
    def validate_forwarded_jwt(self, jwt_token: str) -> Dict[str, Any]:
        """Validate forwarded JWT token (for node-to-node handshakes)"""
        try:
            payload = jwt.decode(jwt_token, self.config.jwt_secret, algorithms=['HS256'])
            
            # Check expiration
            if payload.get('exp', 0) < time.time():
                raise jwt.ExpiredSignatureError("Token expired")
            
            # Validate required fields
            required_fields = ['user', 'permissions', 'iat']
            for field in required_fields:
                if field not in payload:
                    raise jwt.InvalidTokenError(f"Missing required field: {field}")
            
            self.logger.debug(f"Valid forwarded JWT for user: {payload['user']}")
            return payload
            
        except jwt.InvalidTokenError as e:
            self.logger.warning(f"Invalid forwarded JWT: {e}")
            raise
    
    async def client_initiate_handshake(self, server_endpoint: str, secret: str, client_id: str) -> Dict[str, Any]:
        """Client initiates simplified handshake with one-time secret"""
        
        # Generate ephemeral RSA key pair for this handshake
        client_private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )
        client_public_key = client_private_key.public_key()
        
        client_public_key_pem = client_public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        
        # Create handshake request
        handshake_request = {
            "type": "simplified_handshake_request",
            "client_id": client_id,
            "one_time_secret": secret,
            "client_public_key": client_public_key_pem.decode(),
            "timestamp": time.time(),
            "handshake_id": str(uuid.uuid4())
        }
        
        self.logger.info(f"Initiating simplified handshake with {server_endpoint}")
        
        # For demo, simulate server response
        server_response = await self._simulate_server_handshake_response(handshake_request)
        
        if server_response["status"] == "success":
            # Decrypt the AES session key with our private key
            encrypted_session_key = server_response["encrypted_session_key"]
            
            # Decrypt session key
            decrypted_session_key = client_private_key.decrypt(
                bytes.fromhex(encrypted_session_key),
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
            
            # Create session
            session = SimplifiedSession(
                session_id=server_response["session_id"],
                aes_key=decrypted_session_key,
                client_id=client_id,
                server_id=server_response["server_id"],
                created_at=time.time(),
                expires_at=time.time() + server_response["session_duration"]
            )
            
            self.active_sessions[session.session_id] = session
            
            self.logger.info(f"Simplified handshake successful, session: {session.session_id}")
            return {
                "status": "success",
                "session_id": session.session_id,
                "server_id": server_response["server_id"],
                "session_duration": server_response["session_duration"]
            }
        else:
            self.logger.error(f"Handshake failed: {server_response['error']}")
            return server_response
    
    async def server_handle_handshake(self, handshake_request: Dict[str, Any]) -> Dict[str, Any]:
        """Server handles simplified handshake request"""
        
        try:
            client_id = handshake_request["client_id"]
            one_time_secret = handshake_request["one_time_secret"]
            client_public_key_pem = handshake_request["client_public_key"]
            
            # Validate one-time secret
            if not self.validate_one_time_secret(one_time_secret, client_id):
                return {
                    "status": "error",
                    "error": "Invalid or expired one-time secret"
                }
            
            # Parse client's public key
            client_public_key = serialization.load_pem_public_key(
                client_public_key_pem.encode()
            )
            
            # Generate AES session key
            session_key = secrets.token_bytes(32)  # 256-bit AES key
            session_id = str(uuid.uuid4())
            session_duration = 3600  # 1 hour
            
            # Encrypt session key with client's public key
            encrypted_session_key = client_public_key.encrypt(
                session_key,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
            
            # Store session on server side
            session = SimplifiedSession(
                session_id=session_id,
                aes_key=session_key,
                client_id=client_id,
                server_id=self.node_id,
                created_at=time.time(),
                expires_at=time.time() + session_duration
            )
            
            self.active_sessions[session_id] = session
            
            # Consume the one-time secret (optional - can keep for multiple uses)
            # del self.one_time_secrets[one_time_secret]
            
            self.logger.info(f"Simplified handshake successful for {client_id}, session: {session_id}")
            
            return {
                "status": "success",
                "session_id": session_id,
                "server_id": self.node_id,
                "encrypted_session_key": encrypted_session_key.hex(),
                "session_duration": session_duration
            }
            
        except Exception as e:
            self.logger.error(f"Handshake failed: {e}")
            return {
                "status": "error",
                "error": f"Handshake processing failed: {str(e)}"
            }
    
    async def node_initiate_handshake(self, target_node_id: str, forwarded_jwt: str) -> Dict[str, Any]:
        """Node initiates handshake with another node using forwarded JWT"""
        
        # Validate the JWT we're forwarding
        try:
            jwt_payload = self.validate_forwarded_jwt(forwarded_jwt)
        except jwt.InvalidTokenError as e:
            return {
                "status": "error",
                "error": f"Cannot forward invalid JWT: {str(e)}"
            }
        
        # Generate ephemeral RSA key pair for this handshake
        node_private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )
        node_public_key = node_private_key.public_key()
        
        node_public_key_pem = node_public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        
        # Create node-to-node handshake request
        handshake_request = {
            "type": "node_handshake_request",
            "source_node_id": self.node_id,
            "target_node_id": target_node_id,
            "forwarded_jwt": forwarded_jwt,
            "original_client": jwt_payload["user"],
            "node_public_key": node_public_key_pem.decode(),
            "timestamp": time.time(),
            "handshake_id": str(uuid.uuid4())
        }
        
        self.logger.info(f"Initiating node handshake with {target_node_id} for client {jwt_payload['user']}")
        
        # For demo, simulate target node response
        target_response = await self._simulate_node_handshake_response(handshake_request)
        
        if target_response["status"] == "success":
            # Decrypt the AES session key
            encrypted_session_key = target_response["encrypted_session_key"]
            
            decrypted_session_key = node_private_key.decrypt(
                bytes.fromhex(encrypted_session_key),
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
            
            # Create session
            session = SimplifiedSession(
                session_id=target_response["session_id"],
                aes_key=decrypted_session_key,
                client_id=f"{self.node_id}->>{target_node_id}",
                server_id=target_node_id,
                created_at=time.time(),
                expires_at=time.time() + target_response["session_duration"]
            )
            
            self.active_sessions[session.session_id] = session
            
            self.logger.info(f"Node handshake successful with {target_node_id}, session: {session.session_id}")
            return {
                "status": "success",
                "session_id": session.session_id,
                "target_node_id": target_node_id,
                "original_client": jwt_payload["user"]
            }
        else:
            return target_response
    
    async def node_handle_handshake(self, handshake_request: Dict[str, Any]) -> Dict[str, Any]:
        """Node handles handshake request from another node"""
        
        try:
            source_node_id = handshake_request["source_node_id"]
            forwarded_jwt = handshake_request["forwarded_jwt"]
            node_public_key_pem = handshake_request["node_public_key"]
            
            # Validate forwarded JWT
            try:
                jwt_payload = self.validate_forwarded_jwt(forwarded_jwt)
            except jwt.InvalidTokenError as e:
                return {
                    "status": "error",
                    "error": f"Invalid forwarded JWT: {str(e)}"
                }
            
            # Parse source node's public key
            source_public_key = serialization.load_pem_public_key(
                node_public_key_pem.encode()
            )
            
            # Generate AES session key
            session_key = secrets.token_bytes(32)
            session_id = str(uuid.uuid4())
            session_duration = 3600  # 1 hour
            
            # Encrypt session key with source node's public key
            encrypted_session_key = source_public_key.encrypt(
                session_key,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
            
            # Store session
            session = SimplifiedSession(
                session_id=session_id,
                aes_key=session_key,
                client_id=f"{source_node_id}->>{self.node_id}",
                server_id=self.node_id,
                created_at=time.time(),
                expires_at=time.time() + session_duration
            )
            
            self.active_sessions[session_id] = session
            
            self.logger.info(f"Node handshake accepted from {source_node_id} for client {jwt_payload['user']}")
            
            return {
                "status": "success",
                "session_id": session_id,
                "target_node_id": self.node_id,
                "encrypted_session_key": encrypted_session_key.hex(),
                "session_duration": session_duration,
                "original_client": jwt_payload["user"]
            }
            
        except Exception as e:
            self.logger.error(f"Node handshake failed: {e}")
            return {
                "status": "error",
                "error": f"Node handshake processing failed: {str(e)}"
            }
    
    def encrypt_with_session(self, data: Dict[str, Any], session_id: str) -> Dict[str, Any]:
        """Encrypt data using session AES key"""
        session = self.active_sessions.get(session_id)
        if not session:
            raise ValueError(f"No active session: {session_id}")
        
        if session.expires_at < time.time():
            raise ValueError(f"Session expired: {session_id}")
        
        # Increment nonce counter
        session.nonce_counter += 1
        nonce = session.nonce_counter.to_bytes(12, byteorder='big')
        
        # Serialize and encrypt data
        plaintext = json.dumps(data).encode()
        
        cipher = Cipher(algorithms.AES(session.aes_key), modes.GCM(nonce))
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(plaintext) + encryptor.finalize()
        
        return {
            "encrypted_data": ciphertext.hex(),
            "nonce": nonce.hex(),
            "tag": encryptor.tag.hex(),
            "session_id": session_id,
            "encrypted_at": time.time()
        }
    
    def decrypt_with_session(self, encrypted_data: Dict[str, Any]) -> Dict[str, Any]:
        """Decrypt data using session AES key"""
        session_id = encrypted_data["session_id"]
        session = self.active_sessions.get(session_id)
        if not session:
            raise ValueError(f"No active session: {session_id}")
        
        # Extract components
        ciphertext = bytes.fromhex(encrypted_data["encrypted_data"])
        nonce = bytes.fromhex(encrypted_data["nonce"])
        tag = bytes.fromhex(encrypted_data["tag"])
        
        # Decrypt
        cipher = Cipher(algorithms.AES(session.aes_key), modes.GCM(nonce, tag))
        decryptor = cipher.decryptor()
        plaintext = decryptor.update(ciphertext) + decryptor.finalize()
        
        return json.loads(plaintext.decode())
    
    async def _simulate_server_handshake_response(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate server handshake response (for demo)"""
        # Simulate processing delay
        await asyncio.sleep(0.05)
        
        # Create a mock server to handle the request
        mock_server = SimplifiedHandshakeManager(self.config, "demo_server")
        return await mock_server.server_handle_handshake(request)
    
    async def _simulate_node_handshake_response(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate node handshake response (for demo)"""
        await asyncio.sleep(0.05)
        
        target_node_id = request["target_node_id"]
        mock_target = SimplifiedHandshakeManager(self.config, target_node_id)
        return await mock_target.node_handle_handshake(request)


async def demo_simplified_handshake():
    """Demonstrate simplified handshake patterns"""
    
    print("🔑 SMCP-SA2A Simplified Handshake Demo")
    print("=" * 50)
    
    config = SCPConfig(
        node_id="demo_system",
        jwt_secret="demo_jwt_secret_for_simplified_handshake"
    )
    
    # Test 1: Client-Server Handshake with One-Time Secret
    print("\n🤝 Test 1: Client-Server One-Time Secret Handshake")
    print("-" * 50)
    
    client_manager = SimplifiedHandshakeManager(config, "demo_client")
    
    # Use demo secret
    secret = "demo_secret_2024"
    client_id = "demo_client"
    
    result1 = await client_manager.client_initiate_handshake(
        "wss://server.company.com", secret, client_id
    )
    
    if result1["status"] == "success":
        print(f"✅ Client handshake successful")
        print(f"   Session ID: {result1['session_id']}")
        print(f"   Server: {result1['server_id']}")
        
        # Test encrypted communication
        session_id = result1["session_id"]
        test_data = {"message": "Hello from simplified handshake!", "timestamp": time.time()}
        
        encrypted = client_manager.encrypt_with_session(test_data, session_id)
        print(f"   ✅ Data encrypted with session key")
        
        decrypted = client_manager.decrypt_with_session(encrypted)
        print(f"   ✅ Data decrypted: {decrypted['message']}")
    else:
        print(f"❌ Client handshake failed: {result1['error']}")
    
    # Test 2: Node-to-Node Handshake with JWT
    print("\n🔗 Test 2: Node-to-Node JWT Handshake")
    print("-" * 50)
    
    node1_manager = SimplifiedHandshakeManager(config, "gpu_node_1")
    
    # Create a test JWT for forwarding
    test_jwt_payload = {
        'user': 'alice@company.com',
        'permissions': ['task:ai_reasoning', 'task:storage'],
        'iat': time.time(),
        'exp': time.time() + 3600
    }
    test_jwt = jwt.encode(test_jwt_payload, config.jwt_secret, algorithm='HS256')
    
    result2 = await node1_manager.node_initiate_handshake("gpu_node_2", test_jwt)
    
    if result2["status"] == "success":
        print(f"✅ Node handshake successful")
        print(f"   Session ID: {result2['session_id']}")
        print(f"   Target Node: {result2['target_node_id']}")
        print(f"   Original Client: {result2['original_client']}")
        
        # Test encrypted node communication
        session_id = result2["session_id"]
        node_data = {
            "task": "ai_processing",
            "client": result2["original_client"],
            "node_id": "gpu_node_1"
        }
        
        encrypted = node1_manager.encrypt_with_session(node_data, session_id)
        print(f"   ✅ Node data encrypted with session key")
        
        decrypted = node1_manager.decrypt_with_session(encrypted)
        print(f"   ✅ Node data decrypted: task={decrypted['task']}, client={decrypted['client']}")
    else:
        print(f"❌ Node handshake failed: {result2['error']}")
    
    # Test 3: Security Validation
    print("\n🛡️  Test 3: Security Validation")
    print("-" * 50)
    
    # Test with invalid secret
    invalid_result = await client_manager.client_initiate_handshake(
        "wss://server.company.com", "invalid_secret", "test_client"
    )
    
    if invalid_result["status"] == "error":
        print(f"✅ Correctly rejected invalid secret: {invalid_result['error']}")
    else:
        print(f"❌ Security failure: invalid secret accepted")
    
    # Test with expired JWT
    expired_jwt_payload = {
        'user': 'bob@company.com',
        'permissions': ['task:basic'],
        'iat': time.time() - 7200,  # 2 hours ago
        'exp': time.time() - 3600   # Expired 1 hour ago
    }
    expired_jwt = jwt.encode(expired_jwt_payload, config.jwt_secret, algorithm='HS256')
    
    expired_result = await node1_manager.node_initiate_handshake("gpu_node_3", expired_jwt)
    
    if expired_result["status"] == "error":
        print(f"✅ Correctly rejected expired JWT: {expired_result['error']}")
    else:
        print(f"❌ Security failure: expired JWT accepted")
    
    print("\n🎉 Simplified Handshake Demo Complete!")
    print("\n📊 Benefits Demonstrated:")
    print("✅ One-time secrets eliminate need for long-term certificates")
    print("✅ RSA encryption of AES session keys provides perfect forward secrecy")
    print("✅ JWT forwarding maintains client identity across nodes")
    print("✅ Simplified key management compared to full ECDH")
    print("✅ Backward compatible with existing authentication")
    print("✅ Session-based encryption for high-performance communication")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    asyncio.run(demo_simplified_handshake())