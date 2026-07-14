#!/usr/bin/env python3
"""
Example SCP Server - Demonstrates how to set up and run an SCP server
"""

import asyncio
import sys
from datetime import datetime

from _demo_support import demo_config
from smcp_server import SMCPServer as SCPServer


def main():
    """Main server function"""
    print("🚀 Starting SCP Example Server")
    print("="*50)

    # Strong, per-machine demo secrets (shared with example_client via the cached
    # examples/.demo_secrets.json). Loopback demo, so ws:// is permitted.
    config = demo_config("example_server")

    # Create server
    server = SCPServer(config)

    # Register custom tools. register_tool takes (name, description, parameters,
    # handler) and wires the handler into the node's capabilities.
    def get_timestamp() -> str:
        return datetime.now().isoformat()

    def reverse_string(text: str) -> str:
        return text[::-1]

    def word_count(text: str) -> dict:
        words = text.split()
        return {
            "word_count": len(words),
            "character_count": len(text),
            "unique_words": len(set(words))
        }

    server.register_tool("timestamp", "Get current timestamp", {}, get_timestamp)
    server.register_tool(
        "reverse_string", "Reverse a string",
        {"text": {"type": "string", "description": "String to reverse"}},
        reverse_string,
    )
    server.register_tool(
        "word_count", "Count words in text",
        {"text": {"type": "string", "description": "Text to analyze"}},
        word_count,
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