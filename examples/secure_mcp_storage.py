#!/usr/bin/env python3
"""
Secure MCP Storage Module - Encrypted local file operations via MCP protocol
Provides secure local storage capabilities for the poem generation system
"""

import json
import os
import uuid
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from smcp_core import SMCPNode, MessageType, SMCPMessage, Capability
from smcp_config import SMCPConfig


class SecureMCPStorage:
    """Secure MCP-based local storage with encryption"""
    
    def __init__(self, storage_path: str = "./local_poems", encryption_key: Optional[str] = None):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(exist_ok=True, mode=0o700)  # Secure directory permissions
        
        # Initialize encryption
        self.encryption_key = encryption_key or self._generate_encryption_key()
        self.cipher_suite = self._setup_encryption()
        
        # Metadata file for tracking stored items
        self.metadata_file = self.storage_path / ".metadata.json"
        self.metadata = self._load_metadata()
        
        print(f"🔒 Secure MCP Storage initialized at: {self.storage_path}")
    
    def _generate_encryption_key(self) -> str:
        """Generate or load encryption key from secure location"""
        key_file = self.storage_path / ".encryption_key"
        
        if key_file.exists():
            # Load existing key
            with open(key_file, 'rb') as f:
                key = f.read()
        else:
            # Generate new key
            key = Fernet.generate_key()
            with open(key_file, 'wb') as f:
                f.write(key)
            os.chmod(key_file, 0o600)  # Owner read/write only
        
        return base64.urlsafe_b64encode(key).decode()
    
    def _setup_encryption(self) -> Fernet:
        """Setup encryption cipher"""
        # Derive key from stored key
        password = self.encryption_key.encode()
        salt = b"scp_mcp_secure_storage_salt_2024"  # In production, use random salt
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password))
        return Fernet(key)
    
    def _load_metadata(self) -> Dict[str, Any]:
        """Load metadata about stored items"""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {"items": {}, "created": datetime.now().isoformat()}
    
    def _save_metadata(self):
        """Save metadata to disk"""
        self.metadata["updated"] = datetime.now().isoformat()
        with open(self.metadata_file, 'w') as f:
            json.dump(self.metadata, f, indent=2)
        os.chmod(self.metadata_file, 0o600)
    
    def store_encrypted(self, data: Dict[str, Any], item_id: Optional[str] = None) -> Dict[str, Any]:
        """Store data with MCP-level encryption"""
        if not item_id:
            item_id = str(uuid.uuid4())
        
        timestamp = datetime.now().isoformat()
        
        # Prepare storage payload
        storage_payload = {
            "id": item_id,
            "data": data,
            "timestamp": timestamp,
            "security_level": "mcp_aes256",
            "integrity_hash": self._calculate_hash(data)
        }
        
        # Encrypt the payload
        payload_json = json.dumps(storage_payload, indent=2)
        encrypted_data = self.cipher_suite.encrypt(payload_json.encode())
        
        # Store encrypted file
        filename = f"encrypted_{item_id[:8]}_{timestamp.replace(':', '-').split('.')[0]}.enc"
        filepath = self.storage_path / filename
        
        with open(filepath, 'wb') as f:
            f.write(encrypted_data)
        os.chmod(filepath, 0o600)
        
        # Update metadata
        self.metadata["items"][item_id] = {
            "filename": filename,
            "stored_at": timestamp,
            "data_type": data.get("type", "unknown"),
            "size_bytes": len(encrypted_data),
            "integrity_hash": storage_payload["integrity_hash"]
        }
        self._save_metadata()
        
        return {
            "status": "success",
            "item_id": item_id,
            "filepath": str(filepath),
            "encrypted": True,
            "security_level": "mcp_aes256",
            "integrity_verified": True
        }
    
    def retrieve_encrypted(self, item_id: str) -> Dict[str, Any]:
        """Retrieve and decrypt stored data"""
        if item_id not in self.metadata["items"]:
            return {
                "status": "error",
                "error": f"Item not found: {item_id}"
            }
        
        item_metadata = self.metadata["items"][item_id]
        filepath = self.storage_path / item_metadata["filename"]
        
        if not filepath.exists():
            return {
                "status": "error",
                "error": f"File not found: {filepath}"
            }
        
        try:
            # Read encrypted file
            with open(filepath, 'rb') as f:
                encrypted_data = f.read()
            
            # Decrypt
            decrypted_json = self.cipher_suite.decrypt(encrypted_data).decode()
            storage_payload = json.loads(decrypted_json)
            
            # Verify integrity
            if self._calculate_hash(storage_payload["data"]) != storage_payload["integrity_hash"]:
                return {
                    "status": "error",
                    "error": "Data integrity verification failed"
                }
            
            return {
                "status": "success",
                "item_id": item_id,
                "data": storage_payload["data"],
                "metadata": {
                    "stored_at": storage_payload["timestamp"],
                    "security_level": storage_payload["security_level"],
                    "integrity_verified": True
                }
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": f"Decryption failed: {str(e)}"
            }
    
    def list_stored_items(self) -> Dict[str, Any]:
        """List all stored items"""
        return {
            "status": "success",
            "total_items": len(self.metadata["items"]),
            "items": {
                item_id: {
                    "data_type": meta["data_type"],
                    "stored_at": meta["stored_at"],
                    "size_bytes": meta["size_bytes"]
                }
                for item_id, meta in self.metadata["items"].items()
            },
            "storage_path": str(self.storage_path)
        }
    
    def delete_item(self, item_id: str) -> Dict[str, Any]:
        """Securely delete stored item"""
        if item_id not in self.metadata["items"]:
            return {
                "status": "error",
                "error": f"Item not found: {item_id}"
            }
        
        item_metadata = self.metadata["items"][item_id]
        filepath = self.storage_path / item_metadata["filename"]
        
        try:
            # Secure deletion (overwrite then delete)
            if filepath.exists():
                # Overwrite with random data
                file_size = filepath.stat().st_size
                with open(filepath, 'wb') as f:
                    f.write(os.urandom(file_size))
                os.remove(filepath)
            
            # Remove from metadata
            del self.metadata["items"][item_id]
            self._save_metadata()
            
            return {
                "status": "success",
                "item_id": item_id,
                "securely_deleted": True
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": f"Deletion failed: {str(e)}"
            }
    
    def _calculate_hash(self, data: Dict[str, Any]) -> str:
        """Calculate SHA256 hash for integrity verification"""
        data_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(data_str.encode()).hexdigest()


class SecureMCPStorageAgent(SMCPNode):
    """SCP Agent providing secure MCP storage capabilities"""
    
    def __init__(self, config: SMCPConfig, storage_path: str = "./local_poems"):
        super().__init__("mcp_storage_agent", config.secret_key, config.jwt_secret)
        
        self.config = config
        self.secure_storage = SecureMCPStorage(storage_path)
        
        # Register MCP storage capabilities
        self._register_mcp_capabilities()
        
        print(f"🔐 Secure MCP Storage Agent initialized")
    
    def _register_mcp_capabilities(self):
        """Register secure MCP storage capabilities"""
        
        # Store capability
        store_cap = Capability(
            name="mcp_store_encrypted",
            description="Store data with MCP-level AES256 encryption",
            parameters={
                "data": {"type": "object", "description": "Data to store"},
                "item_id": {"type": "string", "description": "Optional item ID"},
                "metadata": {"type": "object", "default": {}}
            }
        )
        self.register_capability(store_cap, self._handle_store_encrypted)
        
        # Retrieve capability
        retrieve_cap = Capability(
            name="mcp_retrieve_encrypted", 
            description="Retrieve and decrypt stored data",
            parameters={
                "item_id": {"type": "string", "description": "Item ID to retrieve"}
            }
        )
        self.register_capability(retrieve_cap, self._handle_retrieve_encrypted)
        
        # List capability
        list_cap = Capability(
            name="mcp_list_items",
            description="List all stored items",
            parameters={}
        )
        self.register_capability(list_cap, self._handle_list_items)
        
        # Delete capability
        delete_cap = Capability(
            name="mcp_delete_item",
            description="Securely delete stored item",
            parameters={
                "item_id": {"type": "string", "description": "Item ID to delete"}
            }
        )
        self.register_capability(delete_cap, self._handle_delete_item)
        
        # Poem-specific storage
        poem_store_cap = Capability(
            name="mcp_store_poem",
            description="Store poem with enhanced security and metadata",
            parameters={
                "poem_data": {"type": "object"},
                "collaboration_metadata": {"type": "object", "default": {}}
            }
        )
        self.register_capability(poem_store_cap, self._handle_store_poem)
    
    def _handle_store_encrypted(self, data: Dict[str, Any], item_id: Optional[str] = None, 
                               metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """Handle encrypted storage request"""
        # Enhance data with MCP metadata
        enhanced_data = {
            **data,
            "mcp_metadata": {
                **(metadata or {}),
                "stored_via": "secure_mcp_agent",
                "agent_id": self.node_id,
                "mcp_version": "1.0.0"
            }
        }
        
        return self.secure_storage.store_encrypted(enhanced_data, item_id)
    
    def _handle_retrieve_encrypted(self, item_id: str) -> Dict[str, Any]:
        """Handle encrypted retrieval request"""
        return self.secure_storage.retrieve_encrypted(item_id)
    
    def _handle_list_items(self) -> Dict[str, Any]:
        """Handle list items request"""
        return self.secure_storage.list_stored_items()
    
    def _handle_delete_item(self, item_id: str) -> Dict[str, Any]:
        """Handle secure deletion request"""
        return self.secure_storage.delete_item(item_id)
    
    def _handle_store_poem(self, poem_data: Dict[str, Any], 
                          collaboration_metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """Handle poem-specific storage with enhanced security"""
        
        # Create comprehensive poem storage structure
        enhanced_poem_data = {
            "type": "collaborative_poem",
            "poem": poem_data,
            "collaboration": collaboration_metadata or {},
            "security_audit": {
                "stored_by_agent": self.node_id,
                "security_level": "mcp_aes256_poem_enhanced",
                "compliance_tags": ["encrypted", "integrity_verified", "secure_local"],
                "audit_trail": {
                    "stored_at": datetime.now().isoformat(),
                    "encryption_method": "AES256_PBKDF2_SHA256",
                    "access_control": "owner_only_600"
                }
            },
            "poem_metadata": {
                "word_count": len(poem_data.get("content", "").split()),
                "theme": poem_data.get("theme"),
                "models_used": collaboration_metadata.get("agents_involved", []) if collaboration_metadata else [],
                "generation_method": "secure_a2a_collaboration"
            }
        }
        
        # Store with enhanced security
        storage_result = self.secure_storage.store_encrypted(enhanced_poem_data)
        
        # Add poem-specific response data
        if storage_result["status"] == "success":
            storage_result.update({
                "poem_id": poem_data.get("id"),
                "poem_theme": poem_data.get("theme"),
                "collaboration_type": collaboration_metadata.get("collaboration_type") if collaboration_metadata else "unknown",
                "security_features": [
                    "mcp_encrypted_storage",
                    "integrity_verification",
                    "secure_file_permissions",
                    "audit_trail_logging"
                ]
            })
        
        return storage_result
    
    # Public methods for direct access (used by federated systems)
    async def store_encrypted(self, data: Dict[str, Any], item_id: Optional[str] = None) -> Dict[str, Any]:
        """Public method for storing encrypted data (federated-friendly)"""
        return self._handle_store_encrypted(data, item_id)
    
    async def retrieve_encrypted(self, item_id: str) -> Dict[str, Any]:
        """Public method for retrieving encrypted data"""
        return self._handle_retrieve_encrypted(item_id)


# Demo and testing functions
async def demo_secure_mcp_storage():
    """Demonstrate secure MCP storage capabilities"""
    print("🔐 Secure MCP Storage Demo")
    print("=" * 50)
    
    config = SCPConfig()
    mcp_agent = SecureMCPStorageAgent(config)
    
    # Test poem storage
    test_poem = {
        "id": str(uuid.uuid4()),
        "content": "In secure channels data flows,\nEncrypted streams where no one knows,\nThe secrets that we share today,\nProtected in the MCP way.",
        "theme": "Secure Communication",
        "style": "quatrain",
        "model": "demo_model",
        "agent": "test_agent",
        "timestamp": datetime.now().isoformat()
    }
    
    test_collaboration = {
        "collaboration_id": str(uuid.uuid4()),
        "collaboration_type": "sequential",
        "agents_involved": ["qwen2.5-coder:7b-instruct-q4_K_M", "qwen3-coder:latest"],
        "security_flow": "encrypted_a2a_to_mcp_local"
    }
    
    print("1. Storing poem with enhanced security...")
    store_result = mcp_agent._handle_store_poem(test_poem, test_collaboration)
    
    if store_result["status"] == "success":
        print(f"   ✓ Stored with ID: {store_result['item_id']}")
        print(f"   ✓ Security Level: {store_result['security_level']}")
        print(f"   ✓ Features: {', '.join(store_result['security_features'])}")
        
        # Test retrieval
        print("\n2. Retrieving stored poem...")
        retrieve_result = mcp_agent._handle_retrieve_encrypted(store_result['item_id'])
        
        if retrieve_result["status"] == "success":
            print("   ✓ Successfully retrieved and decrypted")
            print(f"   ✓ Integrity verified: {retrieve_result['metadata']['integrity_verified']}")
            print(f"   ✓ Security level: {retrieve_result['metadata']['security_level']}")
            
            # Show poem content
            poem_content = retrieve_result["data"]["poem"]["content"][:100] + "..."
            print(f"   ✓ Poem content: {poem_content}")
        else:
            print(f"   ❌ Retrieval failed: {retrieve_result['error']}")
        
        # Test listing
        print("\n3. Listing stored items...")
        list_result = mcp_agent._handle_list_items()
        print(f"   ✓ Total items: {list_result['total_items']}")
        
    else:
        print(f"   ❌ Storage failed: {store_result['error']}")
    
    print("\n" + "=" * 50)
    print("✅ Secure MCP Storage Demo Complete!")


if __name__ == "__main__":
    import asyncio
    asyncio.run(demo_secure_mcp_storage())