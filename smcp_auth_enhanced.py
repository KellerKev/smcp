#!/usr/bin/env python3
"""
Enhanced SCP Authentication System
Supports both simple API key auth (backward compatible) and enterprise OAuth2 with key exchange
"""

import asyncio
import json
import jwt
import base64
import os
import time
from typing import Dict, Any, Optional, Union, Tuple
from dataclasses import dataclass
from enum import Enum
from cryptography.hazmat.primitives.asymmetric import rsa, ec
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption, PublicFormat
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.fernet import Fernet
import requests
import aiohttp
from urllib.parse import urljoin

from smcp_config import SMCPConfig, OAuth2Config, CryptoConfig


class AuthMode(Enum):
    SIMPLE = "simple"           # API key auth (backward compatible)
    BASIC = "basic"             # Standard JWT + HTTPS (production mode)
    ENCRYPTED = "encrypted"     # ECDH + full message encryption
    ENTERPRISE = "enterprise"   # OAuth2 + key exchange
    DEVELOPMENT = "development" # Simplified enterprise for testing


@dataclass
class AuthResult:
    """Authentication result"""
    success: bool
    token: Optional[str] = None
    session_key: Optional[bytes] = None
    error: Optional[str] = None
    expires_at: Optional[float] = None


@dataclass
class KeyExchangeResult:
    """Key exchange result"""
    success: bool
    shared_secret: Optional[bytes] = None
    public_key: Optional[bytes] = None
    error: Optional[str] = None


class EnhancedSMCPSecurity:
    """Enhanced security with backward compatibility"""
    
    def __init__(self, config: SMCPConfig):
        self.config = config
        self.mode = AuthMode(config.mode)
        
        # Initialize based on mode
        if self.mode == AuthMode.SIMPLE:
            self._init_simple_auth()
        elif self.mode == AuthMode.BASIC:
            self._init_basic_auth()
        elif self.mode == AuthMode.ENCRYPTED:
            self._init_encrypted_auth()
        elif self.mode in [AuthMode.ENTERPRISE, AuthMode.DEVELOPMENT]:
            self._init_enterprise_auth()
        
        # Key exchange support
        if config.crypto.key_exchange != "static":
            self._init_key_exchange()
        
        self.session_keys: Dict[str, bytes] = {}
    
    def _init_simple_auth(self):
        """Initialize simple API key authentication (backward compatible)"""
        self.jwt_secret = self.config.jwt_secret
        self.api_key = self.config.api_key
        
        # Simple encryption setup (existing)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'scp_salt_2024',
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(self.config.secret_key.encode()))
        self.cipher = Fernet(key)
    
    def _init_basic_auth(self):
        """Initialize basic JWT authentication (standard production mode)"""
        self.jwt_secret = self.config.jwt_secret
        self.api_key = self.config.api_key
        
        # Basic mode: JWT tokens in headers, relies on HTTPS for transport security
        # No additional message-level encryption
        self.cipher = None  # No message encryption in basic mode
    
    def _init_encrypted_auth(self):
        """Initialize encrypted authentication (ECDH + full message encryption)"""
        self.jwt_secret = self.config.jwt_secret
        self.api_key = self.config.api_key
        
        # Encrypted mode: JWT tokens inside encrypted messages
        # Set up basic cipher for fallback (will be enhanced by ECDH)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'scp_encrypted_salt_2024',
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(self.config.secret_key.encode()))
        self.cipher = Fernet(key)
    
    def _init_enterprise_auth(self):
        """Initialize enterprise OAuth2 authentication"""
        self.oauth2_config = self.config.oauth2
        
        if self.mode == AuthMode.DEVELOPMENT:
            # Simplified enterprise mode for testing
            self._setup_development_oauth2()
        else:
            # Full enterprise mode
            self._setup_production_oauth2()
    
    def _init_key_exchange(self):
        """Initialize key exchange capabilities"""
        if self.config.crypto.key_exchange == "ecdh":
            # Generate ECDH key pair
            self.private_key = ec.generate_private_key(ec.SECP256R1())
            self.public_key = self.private_key.public_key()
        elif self.config.crypto.key_exchange == "rsa":
            # Generate RSA key pair
            self.private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
            )
            self.public_key = self.private_key.public_key()
        
        # Store keys if paths provided
        if self.config.crypto.private_key_path:
            self._save_private_key(self.config.crypto.private_key_path)
        if self.config.crypto.certificate_path:
            self._save_public_key(self.config.crypto.certificate_path)
    
    def _setup_development_oauth2(self):
        """Setup simplified OAuth2 for development/testing"""
        # Generate local keys for development
        if not self.config.oauth2.local_public_key_path:
            # Create development keys
            dev_key_dir = "./dev_keys"
            os.makedirs(dev_key_dir, exist_ok=True)
            
            # Generate RSA key pair for JWT signing
            jwt_private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
            )
            jwt_public_key = jwt_private_key.public_key()
            
            # Save development keys
            private_pem = jwt_private_key.private_bytes(
                encoding=Encoding.PEM,
                format=PrivateFormat.PKCS8,
                encryption_algorithm=NoEncryption()
            )
            public_pem = jwt_public_key.public_bytes(
                encoding=Encoding.PEM,
                format=PublicFormat.SubjectPublicKeyInfo
            )
            
            with open(f"{dev_key_dir}/jwt_private.pem", "wb") as f:
                f.write(private_pem)
            with open(f"{dev_key_dir}/jwt_public.pem", "wb") as f:
                f.write(public_pem)
            
            self.jwt_private_key = jwt_private_key
            self.jwt_public_key = jwt_public_key
            
            print(f"🔧 Development OAuth2 keys generated in {dev_key_dir}/")
        else:
            # Load existing development keys
            with open(self.config.oauth2.local_public_key_path, "rb") as f:
                self.jwt_public_key = serialization.load_pem_public_key(f.read())
    
    def _setup_production_oauth2(self):
        """Setup production OAuth2 with JWKS"""
        self.oauth2_session = aiohttp.ClientSession()
        self.jwks_cache = {}
        self.jwks_cache_time = 0
    
    def _save_private_key(self, path: str):
        """Save private key to file"""
        pem = self.private_key.private_bytes(
            encoding=Encoding.PEM,
            format=PrivateFormat.PKCS8,
            encryption_algorithm=NoEncryption()
        )
        with open(path, "wb") as f:
            f.write(pem)
        os.chmod(path, 0o600)  # Secure permissions
    
    def _save_public_key(self, path: str):
        """Save public key to file"""
        pem = self.public_key.public_bytes(
            encoding=Encoding.PEM,
            format=PublicFormat.SubjectPublicKeyInfo
        )
        with open(path, "wb") as f:
            f.write(pem)
    
    async def authenticate(self, credentials: Dict[str, Any]) -> AuthResult:
        """Authenticate based on configured mode"""
        if self.mode == AuthMode.SIMPLE:
            return await self._authenticate_simple(credentials)
        elif self.mode in [AuthMode.ENTERPRISE, AuthMode.DEVELOPMENT]:
            return await self._authenticate_oauth2(credentials)
        else:
            return AuthResult(success=False, error=f"Unknown auth mode: {self.mode}")
    
    async def _authenticate_simple(self, credentials: Dict[str, Any]) -> AuthResult:
        """Simple API key authentication (backward compatible)"""
        api_key = credentials.get("api_key")
        
        if not api_key or api_key != self.api_key:
            return AuthResult(success=False, error="Invalid API key")
        
        # Generate JWT token
        payload = {
            "node_id": credentials.get("node_id", "unknown"),
            "permissions": ["read", "write", "invoke"],
            "iat": time.time(),
            "exp": time.time() + self.config.security.token_expiry
        }
        
        token = jwt.encode(payload, self.jwt_secret, algorithm="HS256")
        
        return AuthResult(
            success=True,
            token=token,
            expires_at=payload["exp"]
        )
    
    async def _authenticate_oauth2(self, credentials: Dict[str, Any]) -> AuthResult:
        """OAuth2 client credentials authentication"""
        if self.mode == AuthMode.DEVELOPMENT:
            return await self._authenticate_development_oauth2(credentials)
        else:
            return await self._authenticate_production_oauth2(credentials)
    
    async def _authenticate_development_oauth2(self, credentials: Dict[str, Any]) -> AuthResult:
        """Development OAuth2 using local keys"""
        # Simulate OAuth2 flow with local key validation
        token = credentials.get("access_token")
        
        if not token:
            # Generate development token
            payload = {
                "sub": credentials.get("client_id", "dev_client"),
                "aud": "scp_api",
                "iss": "scp_dev_auth",
                "scope": self.config.oauth2.scope,
                "iat": time.time(),
                "exp": time.time() + 3600  # 1 hour
            }
            
            token = jwt.encode(payload, self.jwt_private_key, algorithm="RS256")
            
            return AuthResult(
                success=True,
                token=token,
                expires_at=payload["exp"]
            )
        else:
            # Validate existing token
            try:
                payload = jwt.decode(token, self.jwt_public_key, algorithms=["RS256"])
                return AuthResult(
                    success=True,
                    token=token,
                    expires_at=payload.get("exp")
                )
            except jwt.InvalidTokenError as e:
                return AuthResult(success=False, error=f"Invalid token: {str(e)}")
    
    async def _authenticate_production_oauth2(self, credentials: Dict[str, Any]) -> AuthResult:
        """Production OAuth2 with external identity provider"""
        try:
            # Get access token using client credentials flow
            if not credentials.get("access_token"):
                token_response = await self._get_oauth2_token()
                if not token_response["success"]:
                    return AuthResult(success=False, error=token_response["error"])
                access_token = token_response["access_token"]
            else:
                access_token = credentials["access_token"]
            
            # Validate token with JWKS
            validation_result = await self._validate_jwt_token(access_token)
            
            if validation_result["success"]:
                return AuthResult(
                    success=True,
                    token=access_token,
                    expires_at=validation_result.get("expires_at")
                )
            else:
                return AuthResult(success=False, error=validation_result["error"])
                
        except Exception as e:
            return AuthResult(success=False, error=f"OAuth2 authentication failed: {str(e)}")
    
    async def _get_oauth2_token(self) -> Dict[str, Any]:
        """Get OAuth2 access token using client credentials"""
        try:
            data = {
                "grant_type": "client_credentials",
                "client_id": self.oauth2_config.client_id,
                "client_secret": self.oauth2_config.client_secret,
                "scope": self.oauth2_config.scope
            }
            
            async with self.oauth2_session.post(
                self.oauth2_config.token_url,
                data=data
            ) as response:
                if response.status == 200:
                    token_data = await response.json()
                    return {
                        "success": True,
                        "access_token": token_data["access_token"],
                        "expires_in": token_data.get("expires_in", 3600)
                    }
                else:
                    error_text = await response.text()
                    return {
                        "success": False,
                        "error": f"Token request failed: {response.status} - {error_text}"
                    }
        except Exception as e:
            return {"success": False, "error": f"Token request exception: {str(e)}"}
    
    async def _validate_jwt_token(self, token: str) -> Dict[str, Any]:
        """Validate JWT token using JWKS"""
        try:
            # Get JWKS
            jwks = await self._get_jwks()
            if not jwks["success"]:
                return {"success": False, "error": jwks["error"]}
            
            # Decode token header to get kid
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            
            # Find matching key in JWKS
            jwk = None
            for key in jwks["keys"]:
                if key.get("kid") == kid:
                    jwk = key
                    break
            
            if not jwk:
                return {"success": False, "error": f"Key ID {kid} not found in JWKS"}
            
            # Convert JWK to public key and validate
            public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
            payload = jwt.decode(token, public_key, algorithms=["RS256"])
            
            return {
                "success": True,
                "payload": payload,
                "expires_at": payload.get("exp")
            }
            
        except jwt.InvalidTokenError as e:
            return {"success": False, "error": f"Token validation failed: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"Validation exception: {str(e)}"}
    
    async def _get_jwks(self) -> Dict[str, Any]:
        """Get JWKS with caching"""
        current_time = time.time()
        
        # Check cache (5 minute TTL)
        if self.jwks_cache and (current_time - self.jwks_cache_time) < 300:
            return {"success": True, "keys": self.jwks_cache}
        
        try:
            async with self.oauth2_session.get(self.oauth2_config.jwks_url) as response:
                if response.status == 200:
                    jwks_data = await response.json()
                    self.jwks_cache = jwks_data["keys"]
                    self.jwks_cache_time = current_time
                    return {"success": True, "keys": self.jwks_cache}
                else:
                    return {"success": False, "error": f"JWKS request failed: {response.status}"}
        except Exception as e:
            return {"success": False, "error": f"JWKS request exception: {str(e)}"}
    
    async def perform_key_exchange(self, peer_public_key: bytes) -> KeyExchangeResult:
        """Perform key exchange with peer"""
        if self.config.crypto.key_exchange == "static":
            # No key exchange, use static keys
            return KeyExchangeResult(success=True, shared_secret=None)
        
        try:
            if self.config.crypto.key_exchange == "ecdh":
                # ECDH key exchange
                peer_key = serialization.load_pem_public_key(peer_public_key)
                shared_key = self.private_key.exchange(ec.ECDH(), peer_key)
                
                # Derive session key
                session_key = self._derive_session_key(shared_key)
                
                return KeyExchangeResult(
                    success=True,
                    shared_secret=session_key,
                    public_key=self.public_key.public_bytes(
                        encoding=Encoding.PEM,
                        format=PublicFormat.SubjectPublicKeyInfo
                    )
                )
            elif self.config.crypto.key_exchange == "rsa":
                # RSA key exchange (encrypt with peer's public key)
                session_key = os.urandom(32)  # 256-bit key
                
                peer_key = serialization.load_pem_public_key(peer_public_key)
                encrypted_key = peer_key.encrypt(
                    session_key,
                    padding.OAEP(
                        mgf=padding.MGF1(algorithm=hashes.SHA256()),
                        algorithm=hashes.SHA256(),
                        label=None
                    )
                )
                
                return KeyExchangeResult(
                    success=True,
                    shared_secret=session_key,
                    public_key=base64.b64encode(encrypted_key)
                )
            else:
                return KeyExchangeResult(
                    success=False,
                    error=f"Unsupported key exchange: {self.config.crypto.key_exchange}"
                )
                
        except Exception as e:
            return KeyExchangeResult(success=False, error=f"Key exchange failed: {str(e)}")
    
    def _derive_session_key(self, shared_secret: bytes) -> bytes:
        """Derive session key from shared secret"""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'scp_session_2024',
            iterations=100000,
        )
        return kdf.derive(shared_secret)
    
    def encrypt_with_session_key(self, data: str, session_id: str) -> str:
        """Encrypt data with session key"""
        if session_id in self.session_keys:
            # Use session key
            session_key = base64.urlsafe_b64encode(self.session_keys[session_id])
            cipher = Fernet(session_key)
            return cipher.encrypt(data.encode()).decode()
        else:
            # Fallback to static encryption
            return self.cipher.encrypt(data.encode()).decode()
    
    def decrypt_with_session_key(self, encrypted_data: str, session_id: str) -> str:
        """Decrypt data with session key"""
        if session_id in self.session_keys:
            # Use session key
            session_key = base64.urlsafe_b64encode(self.session_keys[session_id])
            cipher = Fernet(session_key)
            return cipher.decrypt(encrypted_data.encode()).decode()
        else:
            # Fallback to static decryption
            return self.cipher.decrypt(encrypted_data.encode()).decode()
    
    def register_session_key(self, session_id: str, key: bytes):
        """Register session key for Perfect Forward Secrecy"""
        self.session_keys[session_id] = key
    
    def cleanup_session(self, session_id: str):
        """Clean up session key (Perfect Forward Secrecy)"""
        if session_id in self.session_keys:
            # Overwrite key in memory
            self.session_keys[session_id] = b'\x00' * len(self.session_keys[session_id])
            del self.session_keys[session_id]
    
    async def close(self):
        """Clean up resources"""
        if hasattr(self, 'oauth2_session'):
            await self.oauth2_session.close()
        
        # Clear all session keys
        for session_id in list(self.session_keys.keys()):
            self.cleanup_session(session_id)


# Example usage and testing
async def demo_enhanced_auth():
    """Demonstrate enhanced authentication modes"""
    print("🔐 Enhanced SCP Authentication Demo")
    print("=" * 50)
    
    # Test 1: Simple mode (backward compatible)
    print("1. Testing Simple Mode (Backward Compatible)")
    simple_config = SCPConfig(mode="simple")
    simple_auth = EnhancedSCPSecurity(simple_config)
    
    result = await simple_auth.authenticate({
        "api_key": "demo_key_123",
        "node_id": "test_client"
    })
    
    if result.success:
        print(f"   ✓ Simple auth successful, token: {result.token[:50]}...")
    else:
        print(f"   ❌ Simple auth failed: {result.error}")
    
    # Test 2: Development OAuth2 mode
    print("\n2. Testing Development OAuth2 Mode")
    dev_config = SCPConfig(mode="development")
    dev_config.oauth2.enabled = True
    dev_auth = EnhancedSCPSecurity(dev_config)
    
    result = await dev_auth.authenticate({
        "client_id": "dev_client_123"
    })
    
    if result.success:
        print(f"   ✓ Development OAuth2 successful, token: {result.token[:50]}...")
    else:
        print(f"   ❌ Development OAuth2 failed: {result.error}")
    
    # Test 3: Key exchange
    print("\n3. Testing ECDH Key Exchange")
    crypto_config = SCPConfig(mode="development")
    crypto_config.crypto.key_exchange = "ecdh"
    crypto_auth = EnhancedSCPSecurity(crypto_config)
    
    # Simulate key exchange
    peer_auth = EnhancedSCPSecurity(crypto_config)
    
    # Exchange public keys
    client_public = crypto_auth.public_key.public_bytes(
        encoding=Encoding.PEM,
        format=PublicFormat.SubjectPublicKeyInfo
    )
    
    server_result = await peer_auth.perform_key_exchange(client_public)
    
    if server_result.success:
        print("   ✓ ECDH key exchange successful")
        print(f"   ✓ Shared secret: {len(server_result.shared_secret)} bytes")
    else:
        print(f"   ❌ Key exchange failed: {server_result.error}")
    
    # Cleanup
    await simple_auth.close()
    await dev_auth.close()
    await crypto_auth.close()
    await peer_auth.close()
    
    print("\n" + "=" * 50)
    print("✅ Enhanced Authentication Demo Complete!")


if __name__ == "__main__":
    asyncio.run(demo_enhanced_auth())