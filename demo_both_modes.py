#!/usr/bin/env python3
"""
Demo script to show both encrypted and plain storage modes
"""

import asyncio
import logging
from smcp_distributed_a2a import demo_distributed_a2a

async def run_both_demos():
    print("🚀 Running Distributed A2A Demo in BOTH modes")
    print("=" * 80)
    
    # First run: Encrypted storage
    print("\n" + "🔐" * 20 + " ENCRYPTED STORAGE MODE " + "🔐" * 20)
    await demo_distributed_a2a(encrypted_storage=True)
    
    print("\n" + "⏱️" * 80)
    print("Waiting 3 seconds before next demo...")
    await asyncio.sleep(3)
    
    # Second run: Plain storage  
    print("\n" + "📄" * 20 + " PLAIN STORAGE MODE " + "📄" * 20)
    await demo_distributed_a2a(encrypted_storage=False)
    
    print("\n" + "🎯" * 80)
    print("📊 COMPARISON SUMMARY:")
    print("🔐 Encrypted Mode: A2A transit encrypted + MCP encrypted file storage")
    print("📄 Plain Mode: A2A transit encrypted + Standard JSON file storage")
    print("✅ Both modes provide secure A2A communication in transit!")
    print("✅ Choose encrypted storage for maximum security compliance")
    print("✅ Choose plain storage for easier debugging and file inspection")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_both_demos())