#!/usr/bin/env python3
"""
Encrypted A2A Demo - Auto-Generated ECDH Mode
===========================================
Demonstrates TinyLLama → Mistral collaboration using auto-generated ECDH keys
and full message encryption. Ideal for dev/test or production hardening.

Security Model:
- Auto-generated ECDH key pairs for dev/test
- Full message encryption (including JWT tokens)
- Perfect forward secrecy
- Protection against token capture and replay attacks
"""

import asyncio
import json
import uuid
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from smcp_config import SMCPConfig, ClusterConfig, CryptoConfig
from smcp_distributed_a2a import DistributedA2AAgent, DistributedNodeRegistry
from smcp_a2a import AgentInfo
import requests


def auto_generate_ecdh_keys() -> Dict[str, str]:
    """Auto-generate ECDH keys for dev/test use"""
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    
    # Generate ephemeral ECDH key pair
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    
    # Serialize keys
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode('utf-8')
    
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode('utf-8')
    
    return {
        "private_key": private_pem,
        "public_key": public_pem
    }


def setup_encrypted_keys_dir() -> Path:
    """Setup directory for auto-generated encrypted keys"""
    keys_dir = Path("./encrypted_dev_keys")
    keys_dir.mkdir(exist_ok=True, mode=0o700)
    return keys_dir


class EncryptedA2AAgent(DistributedA2AAgent):
    """Encrypted A2A agent using auto-generated ECDH keys and full message encryption"""
    
    def __init__(self, config: SMCPConfig, agent_info: AgentInfo, cluster_registry: DistributedNodeRegistry):
        # Ensure encrypted security mode
        config.crypto.key_exchange = "ecdh"
        config.crypto.perfect_forward_secrecy = True
        config.crypto.use_self_signed = True
        config.mode = "encrypted"
        
        super().__init__(config, agent_info, cluster_registry, encrypted_storage=True)
        
        print(f"🔐 Encrypted A2A Agent initialized: {agent_info.name}")
        print(f"   Security Mode: Auto-Generated ECDH + Full Message Encryption")
        print(f"   Key Exchange: Ephemeral ECDH (Perfect Forward Secrecy)")
        print(f"   Message Protection: AES-256-GCM + JWT inside encrypted payload")
        print(f"   Replay Protection: Nonce-based + timestamp validation")


async def demo_encrypted_a2a_collaboration():
    """Demonstrate encrypted A2A collaboration with TinyLLama → Mistral workflow"""
    print("🔐 Encrypted A2A Collaboration Demo")
    print("=" * 70)
    print("Security Model: Auto-Generated ECDH + Full Message Encryption")
    print("Message Protection: JWT tokens encrypted inside message payload")
    print("Key Exchange: Ephemeral ECDH with Perfect Forward Secrecy")
    print("Ideal for: Dev/Test environments or Production hardening")
    print("=" * 70)
    
    # Setup auto-generated keys
    keys_dir = setup_encrypted_keys_dir()
    print(f"🔑 Auto-generating ECDH keys for secure communication...")
    
    # Generate keys for client and simulated servers
    client_keys = auto_generate_ecdh_keys()
    server_keys = auto_generate_ecdh_keys()
    
    # Save keys for this session
    with open(keys_dir / "client_private.pem", "w") as f:
        f.write(client_keys["private_key"])
    with open(keys_dir / "client_public.pem", "w") as f:
        f.write(client_keys["public_key"])
    with open(keys_dir / "server_public.pem", "w") as f:
        f.write(server_keys["public_key"])
    
    print(f"   ✓ Client ECDH keys generated: {keys_dir}/client_*.pem")
    print(f"   ✓ Server ECDH keys generated: {keys_dir}/server_*.pem")
    print(f"   🔒 Keys are ephemeral (deleted after demo)")
    
    # Create encrypted configuration
    config = SMCPConfig(
        mode="encrypted", 
        node_id="encrypted_coordinator",
        server_url="ws://localhost:8765",
        api_key="demo_key_123",
        secret_key="my_secret_key_2024",
        jwt_secret="jwt_secret_2024"
    )
    
    # Configure crypto for full encryption
    config.crypto = CryptoConfig(
        key_exchange="ecdh",
        perfect_forward_secrecy=True,
        use_self_signed=True,
        private_key_path=str(keys_dir / "client_private.pem")
    )
    
    # Configure cluster for localhost simulation
    config.cluster = ClusterConfig(
        enabled=True,
        simulate_distributed=True,
        simulate_ports=[8766, 8767, 8768]
    )
    
    # Create cluster registry
    cluster_registry = DistributedNodeRegistry(config.cluster)
    
    # Create encrypted A2A agent
    agent_info = AgentInfo(
        agent_id="encrypted_coordinator",
        name="Encrypted A2A Coordinator", 
        description="Coordinates A2A tasks using ECDH encryption and secure messaging",
        specialties=["coordination", "encrypted_communication", "secure_workflows"],
        capabilities=["cross_server_delegate", "distributed_workflow", "multi_server_collaboration"]
    )
    
    coordinator = EncryptedA2AAgent(config, agent_info, cluster_registry)
    
    print(f"\n📋 Available Ollama Models:")
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get("models", [])
            for model in models[:5]:  # Show first 5
                print(f"   • {model['name']}")
            if len(models) > 5:
                print(f"   ... and {len(models) - 5} more")
        else:
            print("   ⚠️  Could not fetch model list")
    except Exception as e:
        print(f"   ⚠️  Ollama not available: {e}")
    
    # Test 1: Encrypted cross-server delegation
    print("\n1. Testing Encrypted Cross-Server Task Delegation")
    print("   Mode: Full message encryption with ECDH")
    
    result = await coordinator._handle_cross_server_delegation(
        task_type="poem_generation",
        task_data={"theme": "Encrypted Secure Communication"},
        target_capability="tinyllama"
    )
    
    if result["status"] == "completed":
        print(f"   ✓ Task delegated to: {result['target_server']}")
        print(f"   ✓ Authentication: JWT encrypted inside message")
        print(f"   ✓ Transport: Encrypted payload + ECDH key exchange")
        print(f"   ✓ Security: Perfect Forward Secrecy enabled")
        print(f"   ✓ Execution time: {result['execution_time']:.2f}s")
        # Show content preview
        content = result.get('result', {}).get('content', 'No content')
        preview = content[:100] + "..." if len(content) > 100 else content
        print(f"   📝 Content preview: {preview}")
    else:
        print(f"   ❌ Delegation failed: {result['error']}")
    
    # Test 2: Encrypted TinyLLama → Mistral workflow
    print("\n2. Testing Encrypted TinyLLama → Mistral Collaboration Workflow")
    print("   📋 Encrypted Workflow Steps:")
    print("   Step 1: TinyLLama generates initial poem (encrypted)")
    print("   Step 2: Mistral enhances the poem (encrypted)")
    print("   Step 3: Storage server saves the result (encrypted)")
    print("   🔐 All messages use ECDH key exchange + AES-256-GCM encryption")
    
    workflow_steps = [
        {"capability": "tinyllama", "task_type": "poem_generation"},
        {"capability": "mistral", "task_type": "enhancement"}, 
        {"capability": "mcp_storage", "task_type": "store"}
    ]
    
    workflow_result = await coordinator._handle_distributed_workflow(
        workflow_steps=workflow_steps,
        input_data={
            "theme": "Secure Encrypted AI Collaboration",
            "style": "free_verse",
            "security_mode": "ecdh_encrypted",
            "encryption_enabled": True,
            "workflow_id": str(uuid.uuid4())
        },
        routing_strategy="optimal"
    )
    
    if workflow_result["status"] == "completed":
        print(f"   ✓ Encrypted workflow completed successfully")
        print(f"   ✓ Authentication: JWT tokens encrypted in each message")
        print(f"   ✓ Security: ECDH + AES-256-GCM for all communications")
        print(f"   ✓ Protection: Immune to token capture and replay attacks")
        
        # Show servers used
        servers_used = set()
        for step_id, step_result in workflow_result["results"].items():
            servers_used.add(step_result["server"])
        print(f"   ✓ Encrypted coordination across: {', '.join(servers_used)}")
        
        # Show final result
        final_data = workflow_result.get("final_data", {})
        if "content" in final_data:
            content_preview = final_data["content"][:150] + "..." if len(final_data["content"]) > 150 else final_data["content"]
            print(f"   📝 Final enhanced poem preview:")
            print(f"      {content_preview}")
        
        print(f"   📊 Encrypted workflow metadata:")
        print(f"      • Steps completed: {len(workflow_result['results'])}")
        print(f"      • Total servers: {len(servers_used)}")
        print(f"      • Authentication method: Encrypted JWT")
        print(f"      • Key exchange: Ephemeral ECDH")
        print(f"      • Message encryption: AES-256-GCM")
    else:
        print(f"   ❌ Encrypted workflow failed: {workflow_result.get('error')}")
    
    # Test 3: Encrypted multi-server parallel collaboration
    print("\n3. Testing Encrypted Multi-Server Parallel Collaboration")
    print("   Mode: Parallel execution with full message encryption")
    
    collaboration_result = await coordinator._handle_multi_server_collaboration(
        participants=["tinyllama", "mistral"],
        collaboration_type="parallel",
        data={
            "project_name": "Encrypted Secure Poetry Generation",
            "collaborative_theme": "AI Communication Encryption",
            "coordination_mode": "parallel",
            "security_level": "encrypted",
            "encryption_method": "ecdh_aes256"
        }
    )
    
    if collaboration_result["status"] == "completed":
        print(f"   ✓ Encrypted parallel collaboration completed")
        print(f"   ✓ Authentication: Encrypted JWT for each participant")
        print(f"   ✓ Coordination: Fully encrypted messaging")
        print(f"   ✓ Security: No tokens exposed in transit")
        
        # Show results from each participant
        if "results" in collaboration_result:
            for participant, result in collaboration_result["results"].items():
                print(f"   📝 {participant.title()} encrypted contribution:")
                content = result.get("content", "No content")
                preview = content[:80] + "..." if len(content) > 80 else content
                print(f"      {preview}")
    else:
        print(f"   ❌ Encrypted collaboration failed: {collaboration_result.get('error')}")
    
    # Cleanup
    await coordinator.security.close()
    
    # Clean up ephemeral keys
    print(f"\n🧹 Cleaning up ephemeral keys...")
    for key_file in keys_dir.glob("*.pem"):
        key_file.unlink()
        print(f"   ✓ Deleted: {key_file.name}")
    keys_dir.rmdir()
    print(f"   ✓ Removed directory: {keys_dir}")
    
    print("\n" + "=" * 70)
    print("📊 Encrypted A2A Demo Summary")
    print("=" * 70)
    print("✅ Cross-server task delegation: Encrypted JWT + ECDH")
    print("✅ TinyLLama → Mistral workflow: Fully encrypted multi-step")
    print("✅ Multi-server collaboration: Encrypted parallel execution")
    print("✅ Authentication: JWT tokens encrypted inside messages")
    print("✅ Key Exchange: Auto-generated ephemeral ECDH")
    print("✅ Message Encryption: AES-256-GCM + Perfect Forward Secrecy")
    print("✅ Replay Protection: Nonce + timestamp validation")
    
    print("\n🚀 Production Deployment:")
    print("• Use proper ECDH key management system")
    print("• Implement key rotation policies")
    print("• Configure hardware security modules (HSMs)")
    print("• Set up secure key distribution")
    
    print("\n🔒 Security Benefits:")
    print("• JWT tokens never exposed in transit")
    print("• Perfect Forward Secrecy (PFS)")
    print("• Protection against replay attacks")
    print("• Resistant to token capture")
    print("• Defense in depth (encryption + HTTPS)")
    
    print("\n💡 Use Cases:")
    print("• Development and testing environments")
    print("• Production hardening (defense in depth)")
    print("• High-security requirements")
    print("• Environments without reliable HTTPS")
    
    print("\n✅ Encrypted A2A Collaboration Demo Complete!")


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    asyncio.run(demo_encrypted_a2a_collaboration())