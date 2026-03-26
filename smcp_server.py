#!/usr/bin/env python3
"""
SCP Server - WebSocket server with tool registration
"""

import asyncio
import json
import logging
import websockets
from typing import Dict, Any, Callable
import platform
import requests
from datetime import datetime

from smcp_core import SMCPNode, MessageType, SMCPMessage, Capability
from smcp_config import SMCPConfig


class SMCPServer:
    """SCP WebSocket Server"""
    
    def __init__(self, config: SMCPConfig = None):
        self.config = config or SMCPConfig(node_id="scp_server")
        self.node = SMCPNode(
            self.config.node_id, 
            self.config.secret_key, 
            self.config.jwt_secret
        )
        self.connections = {}
        self.running = False
        
        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger('scp_server')
        
        # Register built-in tools
        self._register_builtin_tools()
    
    def _register_builtin_tools(self):
        """Register built-in tools"""
        # Calculator tool
        calc_capability = Capability(
            name="calculator",
            description="Basic calculator operations",
            parameters={
                "operation": {"type": "string", "enum": ["add", "subtract", "multiply", "divide"]},
                "a": {"type": "number"},
                "b": {"type": "number"}
            }
        )
        self.node.register_capability(calc_capability, self._calculator_handler)
        
        # System info tool
        sysinfo_capability = Capability(
            name="system_info",
            description="Get system information",
            parameters={}
        )
        self.node.register_capability(sysinfo_capability, self._system_info_handler)
        
        # AI chat tool (Ollama integration)
        ai_capability = Capability(
            name="ai_chat",
            description="Chat with local AI model via Ollama",
            parameters={
                "prompt": {"type": "string", "description": "Message to send to AI"},
                "model": {"type": "string", "default": "llama2", "description": "AI model to use"}
            }
        )
        self.node.register_capability(ai_capability, self._ai_chat_handler)
    
    def _calculator_handler(self, operation: str, a: float, b: float) -> float:
        """Calculator tool handler"""
        if operation == "add":
            return a + b
        elif operation == "subtract":
            return a - b
        elif operation == "multiply":
            return a * b
        elif operation == "divide":
            return a / b if b != 0 else 0
        else:
            raise ValueError(f"Unknown operation: {operation}")
    
    def _system_info_handler(self) -> Dict[str, Any]:
        """System info tool handler"""
        import os
        return {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "current_time": datetime.now().isoformat(),
            "working_directory": os.getcwd(),
            "node_id": self.node.node_id
        }
    
    def _ai_chat_handler(self, prompt: str, model: str = "llama2") -> Dict[str, Any]:
        """AI chat tool handler using Ollama"""
        try:
            response = requests.post(
                'http://localhost:11434/api/generate',
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False
                },
                timeout=30
            )
            
            if response.status_code == 200:
                ai_response = response.json().get("response", "No response")
                return {
                    "response": ai_response,
                    "model": model,
                    "prompt_length": len(prompt)
                }
            else:
                return {
                    "error": f"AI service error: {response.status_code}",
                    "model": model
                }
        except requests.exceptions.RequestException as e:
            return {
                "error": f"Failed to connect to Ollama: {str(e)}",
                "model": model,
                "note": "Make sure Ollama is running on localhost:11434"
            }
    
    def register_tool(self, name: str, description: str, parameters: Dict[str, Any], handler: Callable):
        """Register a custom tool"""
        capability = Capability(name=name, description=description, parameters=parameters)
        self.node.register_capability(capability, handler)
        self.logger.info(f"✓ Registered tool: {name}")
    
    async def handle_client(self, websocket):
        """Handle client connection"""
        client_addr = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
        self.connections[client_addr] = websocket
        self.logger.info(f"✓ Client connected: {client_addr}")
        
        try:
            async for raw_message in websocket:
                try:
                    # Parse message
                    message_data = json.loads(raw_message)
                    message = SMCPMessage.from_dict(message_data)
                    
                    # Process message
                    response = self.node.process_message(message)
                    
                    # Send response
                    if response:
                        await websocket.send(json.dumps(response.to_dict()))
                        
                except json.JSONDecodeError:
                    self.logger.error("Invalid JSON received")
                except Exception as e:
                    self.logger.error(f"Message processing error: {e}")
                    error_response = {
                        "type": "error",
                        "payload": {"error": "Message processing failed"},
                        "timestamp": datetime.now().timestamp()
                    }
                    await websocket.send(json.dumps(error_response))
        
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            self.logger.error(f"Connection error: {e}")
        finally:
            if client_addr in self.connections:
                del self.connections[client_addr]
            self.logger.info(f"✗ Client disconnected: {client_addr}")
    
    async def start(self, host: str = "localhost", port: int = 8765):
        """Start the server"""
        self.running = True
        self.logger.info(f"🚀 SCP Server starting on {host}:{port}")
        self.logger.info(f"📋 Registered {len(self.node.capabilities)} capabilities:")
        
        for name, cap in self.node.capabilities.items():
            self.logger.info(f"   - {name}: {cap.description}")
        
        start_server = websockets.serve(
            self.handle_client,
            host,
            port,
            ping_interval=20,
            ping_timeout=10
        )
        
        self.logger.info(f"✓ Server ready - waiting for connections...")
        await start_server
        
        # Keep running
        try:
            await asyncio.Future()  # Run forever
        except KeyboardInterrupt:
            self.logger.info("🛑 Server shutdown requested")
        finally:
            self.running = False
    
    def stop(self):
        """Stop the server"""
        self.running = False


# Decorator for easy tool registration
def tool(name: str, description: str, parameters: Dict[str, Any] = None):
    """Decorator to register server tools"""
    def decorator(func):
        func._scp_tool = {
            "name": name,
            "description": description,
            "parameters": parameters or {}
        }
        return func
    return decorator


# Example usage
async def example_server():
    """Example server with custom tools"""
    server = SCPServer()
    
    # Register custom tool
    @tool("greet", "Greet a user", {"name": {"type": "string"}})
    def greet_user(name: str) -> Dict[str, str]:
        return {
            "greeting": f"Hello, {name}!",
            "timestamp": datetime.now().isoformat()
        }
    
    # Register the decorated function
    tool_info = greet_user._scp_tool
    server.register_tool(
        tool_info["name"],
        tool_info["description"],
        tool_info["parameters"],
        greet_user
    )
    
    # Start server
    await server.start()


if __name__ == "__main__":
    try:
        asyncio.run(example_server())
    except KeyboardInterrupt:
        print("\n✓ Server stopped")