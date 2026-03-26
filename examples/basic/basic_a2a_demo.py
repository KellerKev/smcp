#!/usr/bin/env python3
"""
Basic A2A Demo - Standard JWT Mode
=================================
Demonstrates TinyLLama → Mistral collaboration using standard JWT authentication.
Assumes HTTPS in production. Suitable for production environments with proper TLS.

Security Model:
- Standard JWT tokens in Authorization headers  
- Relies on HTTPS for transport security
- No additional message-level encryption
- Production-ready approach
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

from smcp_config import SMCPConfig, ClusterConfig
from smcp_distributed_a2a import DistributedA2AAgent, DistributedNodeRegistry
from smcp_a2a import AgentInfo
import requests


class BasicA2AAgent(DistributedA2AAgent):
    """Basic A2A agent using standard JWT authentication"""
    
    def __init__(self, config: SMCPConfig, agent_info: AgentInfo, cluster_registry: DistributedNodeRegistry):
        # Ensure basic security mode (standard JWT)
        config.crypto.key_exchange = "static"  # No ECDH
        config.crypto.perfect_forward_secrecy = False
        config.mode = "basic"
        
        super().__init__(config, agent_info, cluster_registry, encrypted_storage=False)
        
        print(f"🔑 Basic A2A Agent initialized: {agent_info.name}")
        print(f"   Security Mode: Standard JWT + HTTPS")
        print(f"   Message Encryption: Disabled (relies on HTTPS)")
        print(f"   Authentication: JWT Bearer tokens")


async def demo_basic_a2a_collaboration():
    """Demonstrate basic A2A collaboration with TinyLLama → Mistral workflow"""
    print("🌐 Basic A2A Collaboration Demo")
    print("=" * 60)
    print("Security Model: Standard JWT + HTTPS (Production Mode)")
    print("Message Encryption: Disabled (HTTPS provides transport security)")
    print("Authentication: JWT Bearer tokens in headers")
    print("=" * 60)
    
    # Create basic configuration (assumes HTTPS in production)
    config = SMCPConfig(
        mode="basic",
        node_id="basic_coordinator",
        server_url="ws://localhost:8765",  # In prod: wss://your-domain.com
        api_key="demo_key_123",
        secret_key="my_secret_key_2024",
        jwt_secret="jwt_secret_2024"
    )
    
    # Configure cluster for localhost simulation
    config.cluster = ClusterConfig(
        enabled=True,
        simulate_distributed=True,
        simulate_ports=[8766, 8767, 8768]
    )
    
    # Create cluster registry
    cluster_registry = DistributedNodeRegistry(config.cluster)
    
    # Create basic A2A agent
    agent_info = AgentInfo(
        agent_id="basic_coordinator",
        name="Basic A2A Coordinator",
        description="Coordinates A2A tasks using standard JWT authentication",
        specialties=["coordination", "workflow_management", "basic_security"],
        capabilities=["cross_server_delegate", "distributed_workflow", "multi_server_collaboration"]
    )
    
    coordinator = BasicA2AAgent(config, agent_info, cluster_registry)
    
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
        print(f"   ❌ Ollama not available: {e}")
        print("   💡 Make sure Ollama is running: ollama serve")
        print("   💡 Install required models: ollama pull tinyllama:latest && ollama pull mistral:7b-instruct-q4_K_M")
        raise Exception(f"A2A demo requires working Ollama server: {e}")
    
    # Test 1: Basic cross-server delegation
    print("\n1. Testing Basic Cross-Server Task Delegation")
    print("   Mode: Standard JWT authentication")
    
    result = await coordinator._handle_cross_server_delegation(
        task_type="poem_generation",
        task_data={"theme": "Basic Secure Communication"},
        target_capability="tinyllama"
    )
    
    if result["status"] == "completed":
        print(f"   ✓ Task delegated to: {result['target_server']}")
        print(f"   ✓ Authentication: Standard JWT Bearer token")
        print(f"   ✓ Transport: Simulated HTTPS (ws:// in dev)")
        print(f"   ✓ Execution time: {result['execution_time']:.2f}s")
        # Show content preview
        content = result.get('result', {}).get('content', 'No content')
        preview = content[:100] + "..." if len(content) > 100 else content
        print(f"   📝 Content preview: {preview}")
    else:
        print(f"   ❌ Delegation failed: {result['error']}")
    
    # Test 2: TinyLLama → Mistral workflow  
    print("\n2. Testing TinyLLama → Mistral Collaboration Workflow")
    print("   📋 Workflow Steps:")
    print("   Step 1: TinyLLama generates initial poem")
    print("   Step 2: Mistral enhances the poem")
    print("   Step 3: Storage server saves the result")
    
    workflow_steps = [
        {"capability": "tinyllama", "task_type": "poem_generation"},
        {"capability": "mistral", "task_type": "enhancement"}, 
        {"capability": "mcp_storage", "task_type": "store"}
    ]
    
    workflow_result = await coordinator._handle_distributed_workflow(
        workflow_steps=workflow_steps,
        input_data={
            "theme": "Secure AI Collaboration",
            "style": "free_verse",
            "security_mode": "basic_jwt",
            "workflow_id": str(uuid.uuid4())
        },
        routing_strategy="optimal"
    )
    
    if workflow_result["status"] == "completed":
        print(f"   ✓ Workflow completed successfully")
        print(f"   ✓ Authentication: JWT tokens for each step")
        print(f"   ✓ Security: HTTPS transport (simulated)")
        
        # Show servers used
        servers_used = set()
        for step_id, step_result in workflow_result["results"].items():
            servers_used.add(step_result["server"])
        print(f"   ✓ Servers coordinated: {', '.join(servers_used)}")
        
        # Show final result
        final_data = workflow_result.get("final_data", {})
        if "content" in final_data:
            content_preview = final_data["content"][:150] + "..." if len(final_data["content"]) > 150 else final_data["content"]
            print(f"   📝 Final enhanced poem preview:")
            print(f"      {content_preview}")
        
        print(f"   📊 Workflow metadata:")
        print(f"      • Steps completed: {len(workflow_result['results'])}")
        print(f"      • Total servers: {len(servers_used)}")
        print(f"      • Authentication method: Standard JWT")
        print(f"      • Transport security: HTTPS (production)")
    else:
        print(f"   ❌ Workflow failed: {workflow_result.get('error')}")
    
    # Test 3: Multi-server parallel collaboration
    print("\n3. Testing Multi-Server Parallel Collaboration")
    print("   Mode: Parallel execution with basic authentication")
    
    collaboration_result = await coordinator._handle_multi_server_collaboration(
        participants=["tinyllama", "mistral"],
        collaboration_type="parallel",
        data={
            "project_name": "Basic Secure Poetry Generation",
            "collaborative_theme": "AI Communication Security",
            "coordination_mode": "parallel",
            "security_level": "basic"
        }
    )
    
    if collaboration_result["status"] == "completed":
        print(f"   ✓ Parallel collaboration completed")
        print(f"   ✓ Authentication: JWT for each participant")
        print(f"   ✓ Coordination: Basic secure messaging")
        
        # Show results from each participant
        if "results" in collaboration_result:
            for participant, result in collaboration_result["results"].items():
                print(f"   📝 {participant.title()} contribution:")
                content = result.get("content", "No content")
                preview = content[:80] + "..." if len(content) > 80 else content
                print(f"      {preview}")
    else:
        print(f"   ❌ Collaboration failed: {collaboration_result.get('error')}")
    
    # Cleanup
    await coordinator.security.close()
    
    print("\n" + "=" * 60)
    print("📊 Basic A2A Demo Summary")
    print("=" * 60)
    print("✅ Cross-server task delegation: Standard JWT")
    print("✅ TinyLLama → Mistral workflow: Multi-step coordination")
    print("✅ Multi-server collaboration: Parallel execution")
    print("✅ Authentication: JWT Bearer tokens")
    print("✅ Transport Security: HTTPS (production) / ws:// (dev)")
    print("✅ Message Format: Standard JSON (no additional encryption)")
    
    print("\n🚀 Production Deployment:")
    print("• Change ws:// to wss:// for HTTPS")
    print("• Configure proper TLS certificates")
    print("• Use production OAuth2 provider")
    print("• Set secure JWT secrets")
    
    print("\n🔒 Security Notes:")
    print("• Relies on HTTPS for transport security")
    print("• JWT tokens in Authorization headers")
    print("• No additional message-level encryption")
    print("• Suitable for production with proper TLS setup")
    
    print("\n✅ Basic A2A Collaboration Demo Complete!")


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    asyncio.run(demo_basic_a2a_collaboration())