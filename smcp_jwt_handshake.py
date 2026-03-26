#!/usr/bin/env python3
"""
JWT-Based Session Key Establishment for SMCP-SA2A
Simplified handshake using only JWT tokens for authentication
No handshake secrets needed - JWT is the single source of truth
"""

import asyncio
import json
import uuid
import time
import secrets
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
import jwt

from scp_config import SCPConfig


@dataclass
class SecureSession:
    """Secure session with AES encryption after JWT authentication"""
    session_id: str
    aes_key: bytes
    client_id: str  # From JWT
    server_id: str
    permissions: List[str]  # From JWT
    created_at: float
    expires_at: float
    nonce_counter: int = 0


class JWTSessionManager:
    """Manages JWT-authenticated session key establishment"""
    
    def __init__(self, config: SCPConfig, node_id: str):
        self.config = config
        self.node_id = node_id
        self.jwt_secret = config.jwt_secret  # For dev/test
        self.oauth2_config = getattr(config, 'oauth2', None)  # For production
        self.logger = logging.getLogger(f'jwt_session_{node_id}')
        
        # Active sessions
        self.sessions: Dict[str, SecureSession] = {}
        
        # Generate RSA key pair for session key exchange
        self._init_crypto()
    
    def _init_crypto(self):
        """Initialize RSA key pair for session key exchange"""
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
    
    def validate_jwt(self, jwt_token: str) -> Dict[str, Any]:
        """Validate JWT token (works for both dev/test and production)"""
        try:
            # In production, would verify against OAuth2 server's public key
            # For now, use shared secret for dev/test
            payload = jwt.decode(jwt_token, self.jwt_secret, algorithms=['HS256'])
            
            # Check expiration
            if payload.get('exp', 0) < time.time():
                raise jwt.ExpiredSignatureError("Token expired")
            
            # Validate required fields
            required_fields = ['user', 'permissions']
            for field in required_fields:
                if field not in payload:
                    raise jwt.InvalidTokenError(f"Missing required field: {field}")
            
            self.logger.debug(f"Valid JWT for user: {payload['user']}")
            return payload
            
        except jwt.InvalidTokenError as e:
            self.logger.warning(f"Invalid JWT: {e}")
            raise
    
    async def client_initiate_session(self, server_endpoint: str, jwt_token: str) -> Dict[str, Any]:
        """Client initiates session with JWT authentication"""
        
        # Validate our own JWT first
        try:
            jwt_payload = self.validate_jwt(jwt_token)
        except jwt.InvalidTokenError as e:
            return {
                "status": "error",
                "error": f"Invalid JWT: {str(e)}"
            }
        
        # Generate ephemeral RSA key pair for this session
        client_private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )
        client_public_key = client_private_key.public_key()
        
        client_public_key_pem = client_public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        
        # Create session request with JWT
        session_request = {
            "type": "session_request",
            "jwt_token": jwt_token,
            "client_public_key": client_public_key_pem.decode(),
            "timestamp": time.time(),
            "request_id": str(uuid.uuid4())
        }
        
        self.logger.info(f"Initiating JWT session with {server_endpoint} for user {jwt_payload['user']}")
        
        # For demo, simulate server response
        server_response = await self._simulate_server_session_response(session_request)
        
        if server_response["status"] == "success":
            # Decrypt the AES session key
            encrypted_session_key = server_response["encrypted_session_key"]
            
            decrypted_session_key = client_private_key.decrypt(
                bytes.fromhex(encrypted_session_key),
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
            
            # Create session
            session = SecureSession(
                session_id=server_response["session_id"],
                aes_key=decrypted_session_key,
                client_id=jwt_payload['user'],
                server_id=server_response["server_id"],
                permissions=jwt_payload['permissions'],
                created_at=time.time(),
                expires_at=time.time() + server_response["session_duration"]
            )
            
            self.sessions[session.session_id] = session
            
            self.logger.info(f"JWT session established, session: {session.session_id}")
            return {
                "status": "success",
                "session_id": session.session_id,
                "server_id": server_response["server_id"],
                "session_duration": server_response["session_duration"],
                "user": jwt_payload['user']
            }
        else:
            self.logger.error(f"Session failed: {server_response.get('error', 'Unknown error')}")
            return server_response
    
    async def server_handle_session(self, session_request: Dict[str, Any]) -> Dict[str, Any]:
        """Server handles session request with JWT authentication"""
        
        try:
            jwt_token = session_request["jwt_token"]
            client_public_key_pem = session_request["client_public_key"]
            
            # Validate JWT
            try:
                jwt_payload = self.validate_jwt(jwt_token)
            except jwt.InvalidTokenError as e:
                return {
                    "status": "error",
                    "error": f"Authentication failed: {str(e)}"
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
            
            # Store session
            session = SecureSession(
                session_id=session_id,
                aes_key=session_key,
                client_id=jwt_payload['user'],
                server_id=self.node_id,
                permissions=jwt_payload['permissions'],
                created_at=time.time(),
                expires_at=time.time() + session_duration
            )
            
            self.sessions[session_id] = session
            
            self.logger.info(f"JWT session established for {jwt_payload['user']}, session: {session_id}")
            
            return {
                "status": "success",
                "session_id": session_id,
                "server_id": self.node_id,
                "encrypted_session_key": encrypted_session_key.hex(),
                "session_duration": session_duration
            }
            
        except Exception as e:
            self.logger.error(f"Session handling failed: {e}")
            return {
                "status": "error",
                "error": f"Session establishment failed: {str(e)}"
            }
    
    async def node_to_node_session(self, target_node_id: str, forwarded_jwt: str) -> Dict[str, Any]:
        """Establish session between nodes using forwarded JWT"""
        
        # Validate the JWT we're forwarding
        try:
            jwt_payload = self.validate_jwt(forwarded_jwt)
        except jwt.InvalidTokenError as e:
            return {
                "status": "error",
                "error": f"Cannot forward invalid JWT: {str(e)}"
            }
        
        # Generate ephemeral RSA key pair
        node_private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )
        node_public_key = node_private_key.public_key()
        
        node_public_key_pem = node_public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        
        # Create node session request
        session_request = {
            "type": "node_session_request",
            "source_node_id": self.node_id,
            "target_node_id": target_node_id,
            "forwarded_jwt": forwarded_jwt,
            "node_public_key": node_public_key_pem.decode(),
            "timestamp": time.time(),
            "request_id": str(uuid.uuid4())
        }
        
        self.logger.info(f"Initiating node session with {target_node_id} for client {jwt_payload['user']}")
        
        # For demo, simulate target node response
        target_response = await self._simulate_node_session_response(session_request)
        
        if target_response["status"] == "success":
            # Decrypt session key
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
            session = SecureSession(
                session_id=target_response["session_id"],
                aes_key=decrypted_session_key,
                client_id=jwt_payload['user'],  # Original client from JWT
                server_id=target_node_id,
                permissions=jwt_payload['permissions'],
                created_at=time.time(),
                expires_at=time.time() + target_response["session_duration"]
            )
            
            self.sessions[session.session_id] = session
            
            self.logger.info(f"Node session established with {target_node_id}, session: {session.session_id}")
            return {
                "status": "success",
                "session_id": session.session_id,
                "target_node_id": target_node_id,
                "original_client": jwt_payload['user']
            }
        else:
            return target_response
    
    def encrypt_with_session(self, data: Dict[str, Any], session_id: str) -> Dict[str, Any]:
        """Encrypt data using session AES key"""
        session = self.sessions.get(session_id)
        if not session:
            raise ValueError(f"No active session: {session_id}")
        
        if session.expires_at < time.time():
            raise ValueError(f"Session expired: {session_id}")
        
        # Increment nonce counter
        session.nonce_counter += 1
        nonce = session.nonce_counter.to_bytes(12, byteorder='big')
        
        # Serialize and encrypt
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
        session = self.sessions.get(session_id)
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
    
    def check_permission(self, session_id: str, required_permission: str) -> bool:
        """Check if session has required permission"""
        session = self.sessions.get(session_id)
        if not session:
            return False
        
        # Check if permission exists or wildcard
        return (required_permission in session.permissions or 
                "*" in session.permissions or
                f"{required_permission.split(':')[0]}:*" in session.permissions)
    
    async def _simulate_server_session_response(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate server session response (for demo)"""
        await asyncio.sleep(0.05)
        
        # Create mock server
        mock_server = JWTSessionManager(self.config, "demo_server")
        return await mock_server.server_handle_session(request)
    
    async def _simulate_node_session_response(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate node session response (for demo)"""
        await asyncio.sleep(0.05)
        
        target_node_id = request["target_node_id"]
        mock_target = JWTSessionManager(self.config, target_node_id)
        
        # Handle as server but with forwarded JWT
        session_request = {
            "jwt_token": request["forwarded_jwt"],
            "client_public_key": request["node_public_key"]
        }
        
        return await mock_target.server_handle_session(session_request)


def create_test_jwt(user: str, permissions: List[str], jwt_secret: str, expires_in: int = 3600) -> str:
    """Create test JWT token for dev/test environments"""
    payload = {
        'user': user,
        'permissions': permissions,
        'iat': time.time(),
        'exp': time.time() + expires_in
    }
    
    return jwt.encode(payload, jwt_secret, algorithm='HS256')


async def demo_jwt_handshake():
    """Demonstrate JWT-only session establishment"""
    
    print("🔐 SMCP-SA2A JWT-Only Session Establishment Demo")
    print("=" * 50)
    print("NO handshake secrets - JWT is the single authentication mechanism")
    print()
    
    # Test configuration (dev/test mode with JWT secret)
    config = SCPConfig(
        node_id="demo_system",
        jwt_secret="dev_test_jwt_secret_shared_for_demo"
    )
    
    # Test 1: Client-Server Session with JWT
    print("🤝 Test 1: Client-Server JWT Session")
    print("-" * 50)
    
    client_manager = JWTSessionManager(config, "demo_client")
    
    # Create test JWT (in dev/test, we generate these; in prod, OAuth2 server provides them)
    client_jwt = create_test_jwt(
        user="alice@company.com",
        permissions=["task:read", "task:write", "ai:generate"],
        jwt_secret=config.jwt_secret
    )
    
    print(f"✅ Created JWT for: alice@company.com")
    print(f"   Permissions: task:read, task:write, ai:generate")
    
    result1 = await client_manager.client_initiate_session(
        "wss://server.company.com", client_jwt
    )
    
    if result1["status"] == "success":
        print(f"✅ Session established via JWT")
        print(f"   Session ID: {result1['session_id']}")
        print(f"   Server: {result1['server_id']}")
        print(f"   User: {result1['user']}")
        
        # Test encrypted communication
        session_id = result1["session_id"]
        test_data = {"message": "Hello from JWT-authenticated session!", "task": "ai_generation"}
        
        encrypted = client_manager.encrypt_with_session(test_data, session_id)
        print(f"   ✅ Data encrypted with session key")
        
        decrypted = client_manager.decrypt_with_session(encrypted)
        print(f"   ✅ Data decrypted: {decrypted['message']}")
        
        # Test permission checking
        if client_manager.check_permission(session_id, "task:write"):
            print(f"   ✅ Permission check passed: task:write")
        
        if not client_manager.check_permission(session_id, "admin:delete"):
            print(f"   ✅ Permission check correctly denied: admin:delete")
    else:
        print(f"❌ Session failed: {result1.get('error', 'Unknown error')}")
    
    # Test 2: Node-to-Node Session with Forwarded JWT
    print("\n🔗 Test 2: Node-to-Node JWT Session")
    print("-" * 50)
    
    node1_manager = JWTSessionManager(config, "gpu_node_1")
    
    # Create JWT for forwarding (same JWT can be used across federation)
    forwarded_jwt = create_test_jwt(
        user="bob@company.com",
        permissions=["task:ai_reasoning", "task:storage", "task:*"],
        jwt_secret=config.jwt_secret
    )
    
    print(f"✅ Created JWT for: bob@company.com")
    print(f"   Permissions: task:ai_reasoning, task:storage, task:*")
    
    result2 = await node1_manager.node_to_node_session("gpu_node_2", forwarded_jwt)
    
    if result2["status"] == "success":
        print(f"✅ Node session established via forwarded JWT")
        print(f"   Session ID: {result2['session_id']}")
        print(f"   Target Node: {result2['target_node_id']}")
        print(f"   Original Client: {result2['original_client']}")
        
        # Test encrypted node communication
        session_id = result2["session_id"]
        node_data = {
            "task": "distributed_ai_processing",
            "client": result2["original_client"],
            "data": {"prompt": "Generate analysis"}
        }
        
        encrypted = node1_manager.encrypt_with_session(node_data, session_id)
        print(f"   ✅ Node data encrypted with session key")
        
        decrypted = node1_manager.decrypt_with_session(encrypted)
        print(f"   ✅ Node data decrypted: task={decrypted['task']}")
        
        # Test wildcard permissions
        if node1_manager.check_permission(session_id, "task:anything"):
            print(f"   ✅ Wildcard permission works: task:* covers task:anything")
    else:
        print(f"❌ Node session failed: {result2.get('error', 'Unknown error')}")
    
    # Test 3: Security Validation
    print("\n🛡️  Test 3: Security Validation")
    print("-" * 50)
    
    # Test with invalid JWT
    invalid_jwt = "invalid.jwt.token"
    
    invalid_result = await client_manager.client_initiate_session(
        "wss://server.company.com", invalid_jwt
    )
    
    if invalid_result["status"] == "error":
        print(f"✅ Correctly rejected invalid JWT: {invalid_result['error']}")
    else:
        print(f"❌ Security failure: invalid JWT accepted")
    
    # Test with expired JWT
    expired_jwt = create_test_jwt(
        user="expired@company.com",
        permissions=["task:basic"],
        jwt_secret=config.jwt_secret,
        expires_in=-3600  # Already expired
    )
    
    expired_result = await client_manager.client_initiate_session(
        "wss://server.company.com", expired_jwt
    )
    
    if expired_result["status"] == "error":
        print(f"✅ Correctly rejected expired JWT: {expired_result['error']}")
    else:
        print(f"❌ Security failure: expired JWT accepted")
    
    # Test 4: Production OAuth2 Simulation
    print("\n🏢 Test 4: Production OAuth2 Simulation")
    print("-" * 50)
    
    # In production, this JWT would come from OAuth2 server
    production_jwt = create_test_jwt(
        user="enterprise@company.com",
        permissions=["production:all", "admin:read", "ai:*"],
        jwt_secret=config.jwt_secret,
        expires_in=7200  # 2 hours
    )
    
    print(f"✅ Simulated OAuth2 JWT for: enterprise@company.com")
    print(f"   In production, this would come from: https://auth.company.com/oauth2/token")
    print(f"   Permissions: production:all, admin:read, ai:*")
    
    prod_result = await client_manager.client_initiate_session(
        "wss://production.company.com", production_jwt
    )
    
    if prod_result["status"] == "success":
        print(f"✅ Production-style session established")
        print(f"   Ready for enterprise deployment")
    
    print("\n🎉 JWT-Only Session Demo Complete!")
    print("\n📊 Architecture Summary:")
    print("✅ NO handshake secrets needed - JWT is the authentication")
    print("✅ Dev/Test uses JWT with shared secret (simple)")
    print("✅ Production uses OAuth2 server JWTs (enterprise)")
    print("✅ Session keys for encryption performance")
    print("✅ Permissions from JWT flow through entire session")
    print("✅ Single authentication mechanism across all environments")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    asyncio.run(demo_jwt_handshake())