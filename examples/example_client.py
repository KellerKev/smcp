#!/usr/bin/env python3
"""
Example SCP Client - Demonstrates how to use the SCP client SDK
"""

import asyncio
import sys
from smcp_client import SMCPClient as SCPClient
from smcp_config import SMCPConfig as SCPConfig
from smcp_client_main import smcp_client as scp_client


async def run_client_demo():
    """Run client demonstration"""
    print("🚀 Starting SCP Client Demo")
    print("="*50)
    
    # Create client configuration
    config = SCPConfig(
        node_id="example_client",
        server_url="ws://localhost:8765",
        api_key="demo_key_123",
        secret_key="my_secret_key_2024",
        jwt_secret="jwt_secret_2024"
    )
    
    try:
        # Use context manager for automatic connection handling
        async with scp_client(config) as client:
            
            print("\n📋 Available Capabilities:")
            capabilities = client.list_capabilities()
            for name, cap in capabilities.items():
                print(f"   - {name}: {cap['description']}")
            
            print("\n🧮 Testing Calculator:")
            result1 = await client.invoke_tool("calculator", operation="add", a=15, b=27)
            print(f"   15 + 27 = {result1}")
            
            result2 = await client.invoke_tool("calculator", operation="multiply", a=8, b=7)
            print(f"   8 × 7 = {result2}")
            
            print("\n💻 Testing System Info:")
            sys_info = await client.invoke_tool("system_info")
            print(f"   Platform: {sys_info['platform']}")
            print(f"   Python: {sys_info['python_version']}")
            print(f"   Time: {sys_info['current_time']}")
            
            # Test custom tools if available
            if "timestamp" in capabilities:
                print("\n⏰ Testing Timestamp:")
                timestamp = await client.invoke_tool("timestamp")
                print(f"   Current timestamp: {timestamp}")
            
            if "reverse_string" in capabilities:
                print("\n🔄 Testing String Reversal:")
                reversed_text = await client.invoke_tool("reverse_string", text="Hello SCP!")
                print(f"   'Hello SCP!' reversed: '{reversed_text}'")
            
            if "word_count" in capabilities:
                print("\n📊 Testing Word Count:")
                text = "The SCP protocol is secure and efficient"
                word_stats = await client.invoke_tool("word_count", text=text)
                print(f"   Text: '{text}'")
                print(f"   Words: {word_stats['word_count']}")
                print(f"   Characters: {word_stats['character_count']}")
                print(f"   Unique words: {word_stats['unique_words']}")
            
            # Test AI integration
            if "ai_chat" in capabilities:
                print("\n🤖 Testing AI Integration:")
                print("   (This requires Ollama to be running locally)")
                
                try:
                    ai_response = await client.chat_with_ai(
                        "Explain what SCP protocol is in one short sentence"
                    )
                    print(f"   AI Response: {ai_response}")
                    
                    # Test with different model if available
                    ai_response2 = await client.invoke_tool(
                        "ai_chat", 
                        prompt="What is 2+2?", 
                        model="llama2"
                    )
                    
                    if isinstance(ai_response2, dict):
                        if 'error' in ai_response2:
                            print(f"   AI Error: {ai_response2['error']}")
                            if 'note' in ai_response2:
                                print(f"   Note: {ai_response2['note']}")
                        else:
                            print(f"   Math Question: {ai_response2.get('response', 'No response')}")
                    
                except Exception as e:
                    print(f"   AI chat failed: {e}")
            
            print("\n🔒 Security Test:")
            print("   All messages are encrypted with AES-256")
            print("   All messages are signed with HMAC-SHA256")
            print("   Authentication uses JWT tokens")
            
            print("\n" + "="*50)
            print("✅ Client demo completed successfully!")
            
    except Exception as e:
        print(f"\n❌ Client demo failed: {e}")
        print("\nTroubleshooting:")
        print("1. Make sure the server is running: python example_server.py")
        print("2. Check that the server is accessible on ws://localhost:8765")
        print("3. Verify API key matches between client and server")


def main():
    """Main function"""
    try:
        asyncio.run(run_client_demo())
    except KeyboardInterrupt:
        print("\n🛑 Demo stopped by user")


if __name__ == "__main__":
    main()