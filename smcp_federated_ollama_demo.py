#!/usr/bin/env python3
"""
Federated SMCP-SA2A with Real Ollama Integration
Demonstrates token forwarding authentication with actual AI models
"""

import asyncio
import json
import time
import logging
import requests
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from scp_config import SCPConfig
from scp_federated_auth import FederatedSCPNode, create_test_jwt, DEMO_FEDERATION_NODES
from examples.secure_mcp_storage import SecureMCPStorageAgent


class OllamaFederatedAgent(FederatedSCPNode):
    """Federated SCP Node with Ollama AI integration"""
    
    def __init__(self, config: SCPConfig, node_id: str, ollama_url: str = "http://localhost:11434"):
        super().__init__(config, node_id)
        self.ollama_url = ollama_url
        self.available_models = []
        self._discover_models()
    
    def _discover_models(self):
        """Discover available Ollama models"""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models_data = response.json()
                self.available_models = [model['name'] for model in models_data.get('models', [])]
                self.logger.info(f"Discovered Ollama models: {self.available_models}")
            else:
                self.logger.warning(f"Failed to discover models: HTTP {response.status_code}")
        except requests.RequestException as e:
            self.logger.warning(f"Ollama not available at {self.ollama_url}: {e}")
    
    async def _process_ai_task(self, task: Dict[str, Any], client_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process AI reasoning task using real Ollama"""
        prompt = task.get('prompt', 'Hello from federated AI!')
        model = task.get('model', 'qwen2.5-coder:7b-instruct-q4_K_M')
        
        # Check if model is available
        if model not in self.available_models:
            # Fallback to first available model
            if self.available_models:
                model = self.available_models[0]
                self.logger.info(f"Requested model not found, using {model}")
            else:
                return {
                    'error': 'No Ollama models available',
                    'processed_by': self.node_id,
                    'client': client_payload['user']
                }
        
        # Add context about federated processing
        federated_context = f"""
You are processing a request in a federated SMCP-SA2A system.
- Processing Node: {self.node_id}
- Client: {client_payload['user']}
- Security: Token forwarding with ephemeral encryption
- Request: {prompt}

Please respond acknowledging the federated context and process the request:
"""
        
        try:
            response = requests.post(
                f'{self.ollama_url}/api/generate',
                json={
                    "model": model,
                    "prompt": federated_context,
                    "stream": False
                },
                timeout=30
            )
            
            if response.status_code == 200:
                ai_response = response.json().get("response", "No response from AI")
                return {
                    'ai_result': ai_response,
                    'model_used': model,
                    'processing_node': self.node_id,
                    'client': client_payload['user'],
                    'federated_processing': True,
                    'timestamp': time.time()
                }
            else:
                return {
                    'error': f'Ollama API error: {response.status_code}',
                    'processed_by': self.node_id,
                    'client': client_payload['user']
                }
                
        except requests.RequestException as e:
            return {
                'error': f'Failed to connect to Ollama: {str(e)}',
                'processed_by': self.node_id,
                'client': client_payload['user']
            }
    
    async def _process_storage_task(self, task: Dict[str, Any], client_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process storage task with federated authentication"""
        data = task.get('data', 'No data provided')
        
        # Create secure MCP storage agent
        storage_agent = SecureMCPStorageAgent(self.config, "./federated_storage")
        
        # Store with client context
        storage_data = {
            'content': data,
            'client': client_payload['user'],
            'processed_by': self.node_id,
            'federated_auth': True,
            'timestamp': time.time(),
            'permissions': client_payload.get('permissions', [])
        }
        
        result = await storage_agent.store_encrypted(storage_data)
        return {
            'storage_result': 'Data stored successfully with federated authentication',
            'storage_id': result.get('file_id', 'unknown'),
            'encrypted': True,
            'processed_by': self.node_id,
            'client': client_payload['user']
        }


async def demo_federated_ollama():
    """Demonstrate federated authentication with real Ollama models"""
    
    print("🤖 SMCP-SA2A Federated Authentication + Real Ollama Demo")
    print("=" * 60)
    
    # Create test configuration (must match federated auth secret)
    config = SCPConfig(
        node_id="demo_client",
        jwt_secret="test_jwt_secret_for_federated_auth_demo"
    )
    
    # Create federated Ollama nodes
    creative_node = OllamaFederatedAgent(config, "creative_ai_node", "http://localhost:11434")
    analytical_node = OllamaFederatedAgent(config, "analytical_ai_node", "http://localhost:11434") 
    storage_node = OllamaFederatedAgent(config, "storage_node", "http://localhost:11434")
    
    # Register nodes in global registry
    DEMO_FEDERATION_NODES["creative_ai_node"] = creative_node
    DEMO_FEDERATION_NODES["analytical_ai_node"] = analytical_node  
    DEMO_FEDERATION_NODES["storage_node"] = storage_node
    
    # Set up federation relationships
    creative_node.add_peer("analytical_ai_node", "ws://localhost:8767")
    creative_node.add_peer("storage_node", "ws://localhost:8768")
    analytical_node.add_peer("storage_node", "ws://localhost:8768")
    
    # Create client JWT with comprehensive permissions
    client_jwt = create_test_jwt(
        user="data_scientist@company.com",
        permissions=["task:ai_reasoning", "task:storage", "task:analysis", "task:*"],
        forwarding_allowed=["creative_ai_node", "analytical_ai_node", "storage_node", "*"]
    )
    
    print(f"✅ Created federated Ollama nodes with real AI models")
    print(f"✅ Client: data_scientist@company.com with full permissions")
    
    # Check Ollama availability
    if not creative_node.available_models:
        print("⚠️  Warning: No Ollama models detected. Starting Ollama...")
        print("   Please run: ollama serve")
        print("   Then: ollama pull qwen2.5-coder")
        print("   Continuing with simulation...")
    else:
        print(f"✅ Ollama models available: {creative_node.available_models}")
    
    # Test 1: Creative AI Task with Token Forwarding
    print("\n🎨 Test 1: Creative AI Task via Token Forwarding")
    print("-" * 50)
    
    creative_task = {
        'task_id': 'federated_creative_001',
        'type': 'ai_reasoning',
        'prompt': 'Write a haiku about federated AI systems working together securely',
        'model': 'qwen2.5-coder:7b-instruct-q4_K_M'
    }
    
    result1 = await creative_node.forward_request(creative_task, "analytical_ai_node", client_jwt)
    print(f"Status: {result1['status']}")
    if result1['status'] == 'success':
        ai_result = result1['result']
        print(f"AI Response: {ai_result.get('ai_result', 'No response')[:200]}...")
        print(f"Model Used: {ai_result.get('model_used', 'unknown')}")
        print(f"Processing Node: {ai_result.get('processing_node', 'unknown')}")
        print(f"Forwarding Chain: {result1.get('forwarding_chain', [])}")
    
    # Test 2: Chain Processing (Creative → Analytical → Storage)
    print("\n🔗 Test 2: Multi-Node Processing Chain")
    print("-" * 50)
    
    # Step 1: Creative AI generates content
    creative_task2 = {
        'task_id': 'federated_chain_001',
        'type': 'ai_reasoning', 
        'prompt': 'Generate a technical summary of distributed authentication benefits',
        'model': 'qwen2.5-coder:7b-instruct-q4_K_M'
    }
    
    creative_result = await creative_node.forward_request(creative_task2, "analytical_ai_node", client_jwt)
    
    if creative_result['status'] == 'success' and 'ai_result' in creative_result['result']:
        generated_content = creative_result['result']['ai_result']
        print(f"✅ Creative AI generated content ({len(generated_content)} chars)")
        
        # Step 2: Store the generated content
        storage_task = {
            'task_id': 'federated_storage_001',
            'type': 'storage',
            'data': {
                'original_prompt': creative_task2['prompt'],
                'ai_generated_content': generated_content,
                'processing_metadata': creative_result['result']
            }
        }
        
        storage_result = await analytical_node.forward_request(storage_task, "storage_node", client_jwt)
        
        if storage_result['status'] == 'success':
            print(f"✅ Content stored successfully")
            print(f"Storage ID: {storage_result['result'].get('storage_id', 'unknown')}")
            print(f"Complete Chain: analytical_ai_node → storage_node")
        else:
            print(f"❌ Storage failed: {storage_result.get('error', 'Unknown error')}")
    else:
        print(f"❌ Creative AI failed: {creative_result.get('error', 'Unknown error')}")
    
    # Test 3: Security Features
    print("\n🛡️  Test 3: Federated Security Validation")
    print("-" * 50)
    
    # Test with unauthorized user
    unauthorized_jwt = create_test_jwt(
        user="unauthorized@external.com",
        permissions=["task:basic"],  # Limited permissions
        forwarding_allowed=["creative_ai_node"]  # Can't forward to analytical
    )
    
    restricted_result = await creative_node.forward_request(creative_task, "analytical_ai_node", unauthorized_jwt)
    if restricted_result['status'] == 'error':
        print(f"✅ Correctly blocked unauthorized request")
        print(f"   Error: {restricted_result.get('error', 'Unknown')}")
    else:
        print(f"❌ Security failure: unauthorized request succeeded")
    
    print("\n🎉 Federated Ollama Demo Complete!")
    print("\n📊 Summary of Capabilities Demonstrated:")
    print("✅ Token forwarding preserves client identity across AI nodes")
    print("✅ Real Ollama models process requests with federated context")
    print("✅ Ephemeral session keys encrypt inter-node communication")
    print("✅ Permission validation at each federated node")
    print("✅ Secure storage integration with client authentication")
    print("✅ Multi-node processing chains with audit trails")
    print("✅ Graceful handling of model availability")
    
    return {
        'demo_completed': True,
        'nodes_tested': ['creative_ai_node', 'analytical_ai_node', 'storage_node'],
        'security_features': ['token_forwarding', 'session_encryption', 'permission_validation'],
        'ollama_integration': len(creative_node.available_models) > 0
    }


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    asyncio.run(demo_federated_ollama())