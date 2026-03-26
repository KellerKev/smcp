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
import base64
import jwt
from datetime import datetime, timedelta


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
    
    def __init__(self, secret_key: str, jwt_secret: str):
        self.secret_key = secret_key.encode()
        self.jwt_secret = jwt_secret
        self._setup_encryption()
    
    def _setup_encryption(self):
        """Setup AES encryption"""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'scp_salt_2024',
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(self.secret_key))
        self.cipher = Fernet(key)
    
    def encrypt_payload(self, payload: Dict[str, Any]) -> str:
        """Encrypt message payload"""
        json_payload = json.dumps(payload).encode()
        return self.cipher.encrypt(json_payload).decode()
    
    def decrypt_payload(self, encrypted_payload: str) -> Dict[str, Any]:
        """Decrypt message payload"""
        decrypted = self.cipher.decrypt(encrypted_payload.encode())
        return json.loads(decrypted.decode())
    
    def sign_message(self, message: SMCPMessage) -> str:
        """Create HMAC signature"""
        msg_data = f"{message.id}{message.type.value}{message.timestamp}"
        return hmac.new(
            self.secret_key,
            msg_data.encode(),
            hashlib.sha256
        ).hexdigest()
    
    def verify_signature(self, message: SMCPMessage) -> bool:
        """Verify message signature"""
        if not message.signature:
            return False
        expected = self.sign_message(message)
        return hmac.compare_digest(expected, message.signature)
    
    def generate_jwt(self, client_id: str, permissions: List[str]) -> str:
        """Generate JWT token"""
        payload = {
            "client_id": client_id,
            "permissions": permissions,
            "exp": datetime.utcnow() + timedelta(hours=1),
            "iat": datetime.utcnow()
        }
        return jwt.encode(payload, self.jwt_secret, algorithm="HS256")
    
    def verify_jwt(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify JWT token"""
        try:
            return jwt.decode(token, self.jwt_secret, algorithms=["HS256"])
        except jwt.InvalidTokenError:
            return None


class SMCPNode:
    """Core SCP node that can act as client or server"""
    
    def __init__(self, node_id: str, secret_key: str = "default_secret", jwt_secret: str = "default_jwt"):
        self.node_id = node_id
        self.security = SMCPSecurity(secret_key, jwt_secret)
        self.capabilities: Dict[str, Capability] = {}
        self.tool_handlers: Dict[str, Callable] = {}
        self.auth_tokens: Dict[str, Dict[str, Any]] = {}
        
    def register_capability(self, capability: Capability, handler: Callable):
        """Register a tool capability"""
        self.capabilities[capability.name] = capability
        self.tool_handlers[capability.name] = handler
    
    def create_message(self, msg_type: MessageType, payload: Dict[str, Any], encrypt: bool = True) -> SMCPMessage:
        """Create a new SCP message"""
        message = SMCPMessage(
            id=str(uuid.uuid4()),
            type=msg_type,
            timestamp=time.time(),
            payload=payload,
            encrypted=encrypt
        )
        
        if encrypt and payload:
            message.payload = {"encrypted_data": self.security.encrypt_payload(payload)}
        
        message.signature = self.security.sign_message(message)
        return message
    
    def process_message(self, message: SMCPMessage) -> Optional[SMCPMessage]:
        """Process incoming message"""
        if not self.security.verify_signature(message):
            return self.create_error_response(message.id, "Invalid signature")
        
        if message.encrypted and "encrypted_data" in message.payload:
            try:
                message.payload = self.security.decrypt_payload(message.payload["encrypted_data"])
            except Exception as e:
                return self.create_error_response(message.id, f"Decryption failed: {str(e)}")
        
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
        """Handle handshake"""
        return self.create_message(MessageType.HANDSHAKE, {
            "node_id": self.node_id,
            "protocol_version": "1.0",
            "capabilities_count": len(self.capabilities),
            "encryption_enabled": True
        })
    
    def _handle_auth(self, message: SMCPMessage) -> SMCPMessage:
        """Handle authentication"""
        api_key = message.payload.get("api_key")
        if api_key == "demo_key_123":  # Simple demo auth
            token = self.security.generate_jwt("demo_client", ["tool_invoke", "discovery"])
            self.auth_tokens[token] = {
                "client_id": "demo_client",
                "permissions": ["tool_invoke", "discovery"],
                "expires": time.time() + 3600
            }
            return self.create_message(MessageType.AUTH, {
                "status": "success",
                "token": token,
                "expires_in": 3600
            })
        return self.create_error_response(message.id, "Authentication failed")
    
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
        """Handle tool invocation"""
        if not self._is_authorized(message.payload.get("token"), "tool_invoke"):
            return self.create_error_response(message.id, "Unauthorized")
        
        tool_name = message.payload.get("tool_name")
        parameters = message.payload.get("parameters", {})
        
        if tool_name not in self.tool_handlers:
            return self.create_error_response(message.id, f"Tool '{tool_name}' not found")
        
        try:
            result = self.tool_handlers[tool_name](**parameters)
            return self.create_message(MessageType.TOOL_RESPONSE, {
                "tool_name": tool_name,
                "result": result,
                "status": "success"
            })
        except Exception as e:
            return self.create_error_response(message.id, f"Tool execution failed: {str(e)}")
    
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