#!/usr/bin/env python3
"""
Example SCP Server - Demonstrates how to set up and run an SCP server
"""

import asyncio
import sys
from datetime import datetime
from scp_server import SCPServer, tool
from scp_client import SCPConfig


def main():
    """Main server function"""
    print("🚀 Starting SCP Example Server")
    print("="*50)
    
    # Create server configuration
    config = SCPConfig(
        node_id="example_server",
        server_url="ws://localhost:8765",
        api_key="demo_key_123",
        secret_key="my_secret_key_2024",
        jwt_secret="jwt_secret_2024"
    )
    
    # Create server
    server = SCPServer(config)
    
    # Register custom tools
    @tool("timestamp", "Get current timestamp", {})
    def get_timestamp() -> str:
        return datetime.now().isoformat()
    
    @tool("reverse_string", "Reverse a string", {
        "text": {"type": "string", "description": "String to reverse"}
    })
    def reverse_string(text: str) -> str:
        return text[::-1]
    
    @tool("word_count", "Count words in text", {
        "text": {"type": "string", "description": "Text to analyze"}
    })
    def word_count(text: str) -> dict:
        words = text.split()
        return {
            "word_count": len(words),
            "character_count": len(text),
            "unique_words": len(set(words))
        }
    
    # Register the tools
    for func in [get_timestamp, reverse_string, word_count]:
        if hasattr(func, '_scp_tool'):
            tool_info = func._scp_tool
            server.register_tool(
                tool_info["name"],
                tool_info["description"],
                tool_info["parameters"],
                func
            )
    
    print("\n📋 Server Features:")
    print("   ✓ Built-in calculator")
    print("   ✓ System information")
    print("   ✓ AI chat (Ollama integration)")
    print("   ✓ Custom timestamp tool")
    print("   ✓ String reversal tool")
    print("   ✓ Word count analyzer")
    
    print(f"\n🔐 Authentication:")
    print(f"   API Key: {config.api_key}")
    print(f"   Encryption: AES-256")
    print(f"   Signatures: HMAC-SHA256")
    
    print(f"\n🌐 Connection:")
    print(f"   Server URL: {config.server_url}")
    print(f"   Node ID: {config.node_id}")
    
    print("\n📖 Usage:")
    print("   1. Keep this server running")
    print("   2. Run: python example_client.py")
    print("   3. Or connect with your own SCP client")
    
    print("\n" + "="*50)
    print("🟢 Server is ready! Press Ctrl+C to stop.")
    
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except Exception as e:
        print(f"\n❌ Server error: {e}")


if __name__ == "__main__":
    main()