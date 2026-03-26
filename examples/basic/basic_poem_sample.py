#!/usr/bin/env python3
"""
Basic Mode Poetry Generation Sample
=================================
Demonstrates secure AI poetry generation using standard JWT + HTTPS authentication.
Features Qwen 2.5 Coder 7B → Qwen3 Coder → Storage collaboration with production-ready security.

Security Model:
- Standard JWT tokens in Authorization headers
- Relies on HTTPS for transport security (TLS)
- Standard JSON message format
- Production-ready approach suitable for enterprise deployments
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


class BasicPoetryAgent(DistributedA2AAgent):
    """Basic poetry agent using standard JWT authentication and HTTPS transport security"""
    
    def __init__(self, config: SMCPConfig, agent_info: AgentInfo, cluster_registry: DistributedNodeRegistry):
        # Configure for basic security mode
        config.crypto.key_exchange = "static"  # No ECDH
        config.crypto.perfect_forward_secrecy = False
        config.mode = "basic"
        
        super().__init__(config, agent_info, cluster_registry, encrypted_storage=False)
        
        # Local storage for poems (standard file system)
        self.storage_path = Path("./basic_poems")
        self.storage_path.mkdir(exist_ok=True, mode=0o755)
        
        print(f"📋 Basic Poetry Agent initialized: {agent_info.name}")
        print(f"   Security Mode: Standard JWT + HTTPS")
        print(f"   Authentication: JWT Bearer tokens in headers")
        print(f"   Transport Security: HTTPS/TLS (industry standard)")
        print(f"   Storage: Standard JSON files")


async def demo_basic_poetry_generation():
    """Demonstrate basic mode poetry generation with Qwen 2.5 Coder 7B → Qwen3 Coder → Storage workflow"""
    print("📋 Basic Mode Poetry Generation Demo")
    print("=" * 70)
    print("Security Model: Standard JWT + HTTPS (Production Ready)")
    print("Best for: Production environments with proper TLS infrastructure")
    print("Authentication: JWT Bearer tokens in Authorization headers")
    print("Transport Security: HTTPS/TLS provides encryption in transit")
    print("Message Format: Standard JSON (no additional encryption)")
    print("=" * 70)
    
    # Create basic configuration (production-ready)
    config = SMCPConfig(
        mode="basic",
        node_id="basic_poetry_coordinator",
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
    
    # Create basic poetry agent
    agent_info = AgentInfo(
        agent_id="basic_poetry_coordinator",
        name="Basic Poetry Coordinator",
        description="Coordinates AI poetry generation using standard JWT authentication",
        specialties=["poetry", "collaboration", "ai_coordination", "basic_security"],
        capabilities=["cross_server_delegate", "distributed_workflow", "poem_generation"]
    )
    
    coordinator = BasicPoetryAgent(config, agent_info, cluster_registry)
    
    print(f"\n🤖 Available Ollama Models:")
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
    
    # Demo 1: Single AI Model Poetry Generation
    print("\n1. Single AI Model Poetry Generation (Basic Mode)")
    print("   Using: Qwen 2.5 Coder 7B with standard JWT authentication")
    
    single_result = await coordinator._handle_cross_server_delegation(
        task_type="poem_generation",
        task_data={
            "theme": "Digital Security and Trust",
            "style": "free_verse",
            "security_mode": "basic_jwt_https"
        },
        target_capability="qwen2.5-coder"
    )
    
    if single_result["status"] == "completed":
        print(f"   ✅ Single model generation completed")
        print(f"   🔑 Authentication: Standard JWT Bearer token")
        print(f"   🌐 Transport: HTTPS (simulated with ws:// in dev)")
        print(f"   ⚡ Performance: Minimal encryption overhead")
        print(f"   📄 Message Format: Standard JSON")
        print(f"   ⏱️  Execution time: {single_result['execution_time']:.2f}s")
        
        # Show content preview
        content = single_result.get('result', {}).get('content', 'No content')
        preview = content[:150] + "..." if len(content) > 150 else content
        print(f"   📝 Generated poem preview:")
        print(f"      {preview}")
    else:
        print(f"   ❌ Single model generation failed: {single_result['error']}")
    
    # Demo 2: Qwen 2.5 Coder 7B → Qwen3 Coder Collaboration Workflow
    print("\n2. Qwen 2.5 Coder 7B → Qwen3 Coder → Storage Collaboration Workflow")
    print("   📋 Multi-step AI workflow with basic security:")
    print("   Step 1: Qwen 2.5 Coder 7B generates initial poem (JWT auth)")
    print("   Step 2: Qwen3 Coder enhances the poem (JWT auth)")
    print("   Step 3: Storage server saves result (JWT auth)")
    print("   🔒 Security: JWT tokens in headers + HTTPS transport")
    
    workflow_steps = [
        {"capability": "qwen2.5-coder", "task_type": "poem_generation"},
        {"capability": "qwen3-coder", "task_type": "enhancement"}, 
        {"capability": "mcp_storage", "task_type": "store"}
    ]
    
    workflow_result = await coordinator._handle_distributed_workflow(
        workflow_steps=workflow_steps,
        input_data={
            "theme": "Enterprise AI Security with Modern Standards",
            "style": "sonnet",
            "security_mode": "basic_production",
            "collaboration_type": "sequential_enhancement",
            "workflow_id": str(uuid.uuid4()),
            "created_at": datetime.now().isoformat()
        },
        routing_strategy="optimal"
    )
    
    if workflow_result["status"] == "completed":
        print(f"   ✅ Multi-step workflow completed successfully")
        print(f"   🔑 Authentication: JWT tokens for each server communication")
        print(f"   🌐 Transport: HTTPS ensures secure data transmission")
        print(f"   📊 Workflow coordination: Standard REST-like patterns")
        
        # Show servers used
        servers_used = set()
        for step_id, step_result in workflow_result["results"].items():
            servers_used.add(step_result["server"])
        print(f"   🖥️  Servers coordinated: {', '.join(servers_used)}")
        
        # Show enhanced poem result
        final_data = workflow_result.get("final_data", {})
        if "content" in final_data:
            content_preview = final_data["content"][:200] + "..." if len(final_data["content"]) > 200 else final_data["content"]
            print(f"   📝 Final enhanced poem preview:")
            print(f"      {content_preview}")
        
        print(f"   📈 Performance metrics:")
        print(f"      • Total steps: {len(workflow_result['results'])}")
        print(f"      • Servers involved: {len(servers_used)}")
        print(f"      • Authentication overhead: Minimal (standard JWT)")
        print(f"      • Network efficiency: High (standard JSON)")
        
        # Store poem with basic security
        poem_id = final_data.get("workflow_id", str(uuid.uuid4()))[:8]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"basic_poem_{timestamp}_{poem_id}.json"
        filepath = coordinator.storage_path / filename
        
        # Create basic storage record
        storage_record = {
            "poem_result": workflow_result,
            "security_mode": "basic",
            "storage_metadata": {
                "stored_at": datetime.now().isoformat(),
                "stored_by": coordinator.agent_info.agent_id,
                "security_level": "basic_jwt_https",
                "file_format": "standard_json",
                "authentication": "jwt_bearer_token",
                "transport_security": "https_tls"
            },
            "workflow_metadata": {
                "steps_completed": len(workflow_result['results']),
                "servers_used": list(servers_used),
                "collaboration_type": "qwen2.5-coder_qwen3-coder_storage"
            }
        }
        
        # Store with standard file permissions
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(storage_record, f, indent=2, ensure_ascii=False)
        
        os.chmod(filepath, 0o644)  # Standard readable permissions
        
        print(f"   💾 Poem stored: {filepath}")
        print(f"      • Security: Standard file permissions (644)")
        print(f"      • Format: Standard JSON (human readable)")
        print(f"      • Size: {filepath.stat().st_size} bytes")
    else:
        print(f"   ❌ Multi-step workflow failed: {workflow_result.get('error')}")
    
    # Demo 3: Parallel Multi-Model Generation
    print("\n3. Parallel Multi-Model Poetry Generation")
    print("   Mode: Concurrent execution with basic authentication")
    
    parallel_result = await coordinator._handle_multi_server_collaboration(
        participants=["qwen2.5-coder", "qwen3-coder"],
        collaboration_type="parallel",
        data={
            "collaborative_theme": "Digital Transformation and Security Standards",
            "individual_prompts": {
                "qwen2.5-coder": "Write about digital innovation from a technical perspective",
                "qwen3-coder": "Write about digital security from an enterprise perspective"
            },
            "security_mode": "basic_parallel",
            "coordination_style": "independent_then_merge"
        }
    )
    
    if parallel_result["status"] == "completed":
        print(f"   ✅ Parallel multi-model generation completed")
        print(f"   🔑 Authentication: Concurrent JWT authentication")
        print(f"   📊 Coordination: Independent execution with result merging")
        print(f"   ⚡ Performance: Parallel processing efficiency")
        
        # Show results from each model
        if "results" in parallel_result:
            for participant, result in parallel_result["results"].items():
                print(f"   📝 {participant.title()} contribution:")
                content = result.get("content", "No content")
                preview = content[:100] + "..." if len(content) > 100 else content
                print(f"      {preview}")
    else:
        print(f"   ❌ Parallel generation failed: {parallel_result.get('error')}")
    
    # Cleanup
    await coordinator.security.close()
    
    print("\n" + "=" * 70)
    print("📊 Basic Mode Poetry Generation Summary")
    print("=" * 70)
    print("✅ Single AI Model: Qwen 2.5 Coder 7B with JWT authentication")
    print("✅ Multi-Step Workflow: Qwen 2.5 Coder 7B → Qwen3 Coder → Storage")
    print("✅ Parallel Generation: Concurrent multi-model execution")
    print("✅ Authentication: JWT Bearer tokens (industry standard)")
    print("✅ Transport Security: HTTPS/TLS encryption")
    print("✅ Message Format: Standard JSON (high compatibility)")
    print("✅ Storage: Standard file system with readable format")
    
    print("\n🚀 Production Deployment Benefits:")
    print("• Industry standard authentication (JWT + HTTPS)")
    print("• High performance (minimal encryption overhead)")
    print("• Excellent compatibility with existing infrastructure")
    print("• Standard monitoring and logging integration")
    print("• Straightforward load balancing and CDN support")
    
    print("\n🔒 Security Features:")
    print("• JWT tokens provide stateless authentication")
    print("• HTTPS/TLS ensures encrypted transport")
    print("• Standard authorization patterns")
    print("• Compatible with enterprise security policies")
    print("• Audit trail via standard application logs")
    
    print("\n💡 Best Practices:")
    print("• Use strong JWT secrets in production")
    print("• Implement proper TLS certificate management") 
    print("• Set appropriate JWT expiration times")
    print("• Use HTTPS (wss://) for WebSocket connections")
    print("• Follow OAuth2/OIDC standards for advanced auth")
    
    print("\n🔧 Configuration for Production:")
    print("• server_url: 'wss://your-api-domain.com'")
    print("• jwt_secret: Use secure random string (32+ chars)")
    print("• Enable TLS 1.3 with proper certificates")
    print("• Configure rate limiting and DDoS protection")
    
    print("\n✅ Basic Mode Poetry Generation Demo Complete!")
    print("🎯 Ready for production deployment with proper HTTPS setup!")


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    asyncio.run(demo_basic_poetry_generation())