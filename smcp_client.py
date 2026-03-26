#!/usr/bin/env python3
"""
SCP Client SDK - Easy-to-use client library for SCP protocol
"""

import asyncio
import json
import websockets
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager
import yaml
from dataclasses import dataclass

from smcp_core import SMCPNode, MessageType, SMCPMessage
from smcp_config import SMCPConfig


class SMCPClient:
    """High-level SCP client"""
    
    def __init__(self, config: SMCPConfig = None):
        self.config = config or SMCPConfig()
        self.node = SMCPNode(self.config.node_id, self.config.secret_key, self.config.jwt_secret)
        self.websocket = None
        self.auth_token = None
        self.capabilities = {}
        self.connected = False
    
    async def connect(self):
        """Connect to SCP server"""
        try:
            self.websocket = await websockets.connect(
                self.config.server_url,
                ping_interval=20,
                ping_timeout=10
            )
            
            await self._handshake()
            await self._authenticate()
            await self._discover_capabilities()
            
            self.connected = True
            print(f"✓ Connected to SCP server at {self.config.server_url}")
            
        except Exception as e:
            print(f"✗ Connection failed: {str(e)}")
            raise
    
    async def disconnect(self):
        """Disconnect from server"""
        if self.websocket:
            await self.websocket.close()
        self.connected = False
        print("✓ Disconnected from SCP server")
    
    async def _handshake(self):
        """Perform handshake"""
        message = self.node.create_message(MessageType.HANDSHAKE, {
            "client_id": self.config.node_id,
            "protocol_version": "1.0"
        }, encrypt=False)
        
        response = await self._send_message(message)
        if response["type"] != "handshake":
            raise Exception("Handshake failed")
        
        print(f"✓ Handshake complete")
    
    async def _authenticate(self):
        """Authenticate with server"""
        message = self.node.create_message(MessageType.AUTH, {
            "api_key": self.config.api_key
        })
        
        response = await self._send_message(message)
        
        # Decrypt response
        if response.get("encrypted") and "encrypted_data" in response.get("payload", {}):
            decrypted = self.node.security.decrypt_payload(response["payload"]["encrypted_data"])
        else:
            decrypted = response.get("payload", {})
        
        if decrypted.get("status") != "success":
            raise Exception("Authentication failed")
        
        self.auth_token = decrypted.get("token")
        print("✓ Authentication successful")
    
    async def _discover_capabilities(self):
        """Discover capabilities"""
        message = self.node.create_message(MessageType.CAPABILITY_DISCOVERY, {
            "token": self.auth_token
        })
        
        response = await self._send_message(message)
        
        # Decrypt response
        if response.get("encrypted") and "encrypted_data" in response.get("payload", {}):
            decrypted = self.node.security.decrypt_payload(response["payload"]["encrypted_data"])
        else:
            decrypted = response.get("payload", {})
        
        self.capabilities = decrypted.get("capabilities", {})
        print(f"✓ Discovered {len(self.capabilities)} capabilities")
    
    async def invoke_tool(self, tool_name: str, **parameters) -> Any:
        """Invoke a tool"""
        if not self.connected:
            raise Exception("Not connected to server")
        
        message = self.node.create_message(MessageType.TOOL_INVOKE, {
            "token": self.auth_token,
            "tool_name": tool_name,
            "parameters": parameters
        })
        
        response = await self._send_message(message)
        
        # Decrypt response
        if response.get("encrypted") and "encrypted_data" in response.get("payload", {}):
            decrypted = self.node.security.decrypt_payload(response["payload"]["encrypted_data"])
        else:
            decrypted = response.get("payload", {})
        
        if response["type"] == "error":
            raise Exception(f"Tool invocation failed: {decrypted.get('error')}")
        
        return decrypted.get("result")
    
    async def _send_message(self, message: SMCPMessage) -> Dict[str, Any]:
        """Send message and get response"""
        await self.websocket.send(json.dumps(message.to_dict()))
        response_data = await self.websocket.recv()
        return json.loads(response_data)
    
    def list_capabilities(self) -> Dict[str, Any]:
        """List available capabilities"""
        return self.capabilities
    
    async def chat_with_ai(self, prompt: str, model: str = "llama2") -> str:
        """Convenience method for AI chat"""
        try:
            result = await self.invoke_tool("ai_chat", prompt=prompt, model=model)
            if isinstance(result, dict):
                return result.get("response", str(result))
            return str(result)
        except Exception as e:
            return f"AI chat failed: {str(e)}"


@asynccontextmanager
async def scp_client(config: SMCPConfig = None):
    """Context manager for SCP client"""
    client = SMCPClient(config)
    try:
        await client.connect()
        yield client
    finally:
        await client.disconnect()


def scp_tool(name: str, description: str, parameters: Dict[str, Any]):
    """Decorator for tool registration"""
    def decorator(func):
        func._scp_tool = {
            "name": name,
            "description": description,
            "parameters": parameters
        }
        return func
    return decorator


# Example usage
async def example_usage():
    """Example client usage"""
    config = SCPConfig(
        node_id="example_client",
        server_url="ws://localhost:8765",
        api_key="demo_key_123"
    )
    
    async with scp_client(config) as client:
        # List capabilities
        capabilities = client.list_capabilities()
        print(f"Available tools: {list(capabilities.keys())}")
        
        # Use calculator
        result = await client.invoke_tool("calculator", operation="add", a=10, b=20)
        print(f"10 + 20 = {result}")
        
        # Chat with AI (if available)
        if "ai_chat" in capabilities:
            response = await client.chat_with_ai("What is 2+2?")
            print(f"AI says: {response}")


if __name__ == "__main__":
    asyncio.run(example_usage())