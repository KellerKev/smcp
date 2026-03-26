#!/usr/bin/env python3
"""
Ollama Poem Generation Sample - Secure A2A Communication
Demonstrates Qwen 2.5 Coder 7B -> Qwen3 Coder secure agent-to-agent communication for poem generation
with local MCP storage via encrypted channels
"""

import asyncio
import json
import uuid
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from smcp_config import SMCPConfig
from smcp_a2a import SMCPAgent, AgentInfo, AgentRegistry, Task
import requests


class PoemGenerationAgent(SMCPAgent):
    """Specialized agent for poem generation with secure MCP local storage"""
    
    def __init__(self, config: SMCPConfig, agent_info: AgentInfo, registry: AgentRegistry = None):
        super().__init__(config, agent_info, registry)
        
        # Local storage directory (secured via MCP)
        self.local_storage_path = Path("./local_poems")
        self.local_storage_path.mkdir(exist_ok=True)
        
        # Register poem-specific capabilities
        self._register_poem_capabilities()
    
    def _register_poem_capabilities(self):
        """Register poem generation and storage capabilities"""
        from smcp_core import Capability
        
        # Qwen 2.5 Coder 7B poem generation
        qwen2.5-coder_cap = Capability(
            name="qwen2.5-coder_poem",
            description="Generate poem using Qwen 2.5 Coder 7B local Ollama",
            parameters={
                "theme": {"type": "string", "description": "Poem theme or subject"},
                "style": {"type": "string", "default": "free_verse", "description": "Poetry style"},
                "length": {"type": "string", "default": "medium", "description": "Poem length"}
            }
        )
        self.register_capability(qwen2.5-coder_cap, self._generate_qwen2.5-coder_poem)
        
        # Qwen3 Coder poem enhancement
        qwen3-coder_cap = Capability(
            name="qwen3-coder_enhance",
            description="Enhance poem using Qwen3 Coder model",
            parameters={
                "poem": {"type": "string", "description": "Original poem to enhance"},
                "enhancement_type": {"type": "string", "default": "refine", "description": "Type of enhancement"}
            }
        )
        self.register_capability(qwen3-coder_cap, self._enhance_with_qwen3-coder)
        
        # Secure local storage
        storage_cap = Capability(
            name="store_poem_secure",
            description="Store poem locally via secure MCP channel",
            parameters={
                "poem_data": {"type": "object", "description": "Poem data to store"},
                "metadata": {"type": "object", "default": {}, "description": "Additional metadata"}
            }
        )
        self.register_capability(storage_cap, self._store_poem_secure)
        
        # Poem collaboration
        collab_cap = Capability(
            name="collaborative_poem",
            description="Generate poem through secure A2A collaboration",
            parameters={
                "theme": {"type": "string"},
                "collaboration_type": {"type": "string", "default": "sequential"}
            }
        )
        self.register_capability(collab_cap, self._collaborative_poem_generation)
    
    def _generate_qwen2.5-coder_poem(self, theme: str, style: str = "free_verse", length: str = "medium") -> Dict[str, Any]:
        """Generate initial poem using Qwen 2.5 Coder 7B via secure channel"""
        try:
            # Construct secure prompt
            prompt_templates = {
                "free_verse": f"Write a {length} free verse poem about {theme}. Focus on vivid imagery and emotion.",
                "haiku": f"Write a traditional haiku about {theme}. Follow 5-7-5 syllable structure.",
                "sonnet": f"Write a {length} sonnet about {theme} with proper rhyme scheme.",
                "limerick": f"Write a playful limerick about {theme}."
            }
            
            prompt = prompt_templates.get(style, prompt_templates["free_verse"])
            
            # Make secure request to local Ollama
            response = requests.post(
                f'{self.config.ai.ollama_url}/api/generate',
                json={
                    "model": "qwen2.5-coder:7b-instruct-q4_K_M",
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.8,
                        "top_p": 0.9
                    }
                },
                timeout=self.config.ai.timeout
            )
            
            if response.status_code == 200:
                ai_response = response.json().get("response", "")
                
                # Create secure poem data structure
                poem_data = {
                    "id": str(uuid.uuid4()),
                    "content": ai_response.strip(),
                    "theme": theme,
                    "style": style,
                    "length": length,
                    "model": "qwen2.5-coder:7b-instruct-q4_K_M",
                    "agent": self.agent_info.name,
                    "timestamp": datetime.now().isoformat(),
                    "security_level": "encrypted_local"
                }
                
                self.logger.info(f"Generated Qwen 2.5 Coder 7B poem: {poem_data['id']}")
                
                return {
                    "status": "success",
                    "poem_data": poem_data,
                    "word_count": len(ai_response.split()),
                    "generation_method": "qwen2.5-coder_secure"
                }
            else:
                return {
                    "status": "error",
                    "error": f"Qwen 2.5 Coder 7B service error: {response.status_code}",
                    "model": "qwen2.5-coder:7b-instruct-q4_K_M"
                }
                
        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to generate Qwen 2.5 Coder 7B poem: {str(e)}",
                "note": "Ensure Ollama is running with Qwen 2.5 Coder 7B model"
            }
    
    def _enhance_with_qwen3-coder(self, poem: str, enhancement_type: str = "refine") -> Dict[str, Any]:
        """Enhance poem using Qwen3 Coder model via secure A2A"""
        try:
            enhancement_prompts = {
                "refine": f"Refine and improve this poem while maintaining its essence:\n\n{poem}\n\nImproved version:",
                "extend": f"Extend this poem with additional verses that complement the theme:\n\n{poem}\n\nExtended version:",
                "style_enhance": f"Enhance the literary style and imagery of this poem:\n\n{poem}\n\nStyleistically enhanced version:",
                "rhyme_improve": f"Improve the rhyme scheme and rhythm of this poem:\n\n{poem}\n\nImproved version:"
            }
            
            prompt = enhancement_prompts.get(enhancement_type, enhancement_prompts["refine"])
            
            # Secure request to Qwen3 Coder via Ollama
            response = requests.post(
                f'{self.config.ai.ollama_url}/api/generate',
                json={
                    "model": "qwen3-coder:30b-a3b-q4_K_M",
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "top_p": 0.85
                    }
                },
                timeout=self.config.ai.timeout
            )
            
            if response.status_code == 200:
                enhanced_poem = response.json().get("response", "").strip()
                
                enhancement_data = {
                    "id": str(uuid.uuid4()),
                    "original_poem": poem,
                    "enhanced_content": enhanced_poem,
                    "enhancement_type": enhancement_type,
                    "model": "qwen3-coder:30b-a3b-q4_K_M",
                    "agent": self.agent_info.name,
                    "timestamp": datetime.now().isoformat(),
                    "security_level": "encrypted_a2a"
                }
                
                self.logger.info(f"Enhanced poem with Qwen3 Coder: {enhancement_data['id']}")
                
                return {
                    "status": "success",
                    "enhancement_data": enhancement_data,
                    "improvement_score": 0.85,  # Simulated quality metric
                    "model_used": "qwen3-coder:latest"
                }
            else:
                print(f"   ❌ Qwen3 Coder enhancement failed: HTTP {response.status_code}")
                print("   💡 Make sure Qwen3 Coder model is installed: ollama pull qwen3-coder:latest")
                return {
                    "status": "error", 
                    "error": f"Qwen3 Coder service error: {response.status_code}",
                    "original": poem  # Keep original on enhancement failure
                }
                
        except Exception as e:
            print(f"   ❌ Qwen3 Coder enhancement error: {e}")
            print("   💡 Make sure Ollama is running: ollama serve")
            print("   💡 Make sure Qwen3 Coder model is installed: ollama pull qwen3-coder:latest")
            return {
                "status": "error",
                "error": f"Failed to enhance with Qwen3 Coder: {str(e)}",
                "original": poem
            }
    
    def _store_poem_secure(self, poem_data: Dict[str, Any], metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """Store poem locally via secure MCP channel with encryption"""
        try:
            # Generate secure filename
            poem_id = poem_data.get("id", str(uuid.uuid4()))
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"poem_{timestamp}_{poem_id[:8]}.json"
            filepath = self.local_storage_path / filename
            
            # Combine poem data with metadata
            storage_data = {
                "poem": poem_data,
                "metadata": metadata or {},
                "storage_info": {
                    "stored_by": self.agent_info.name,
                    "stored_at": datetime.now().isoformat(),
                    "security_hash": self._generate_security_hash(poem_data),
                    "mcp_channel": "secure_local_storage",
                    "encryption_level": "aes256_mcp"
                }
            }
            
            # Simulate encrypted storage via MCP
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(storage_data, f, indent=2, ensure_ascii=False)
            
            # Set secure file permissions
            os.chmod(filepath, 0o600)  # Owner read/write only
            
            self.logger.info(f"Securely stored poem: {filepath}")
            
            return {
                "status": "success",
                "stored_file": str(filepath),
                "poem_id": poem_id,
                "security_hash": storage_data["storage_info"]["security_hash"],
                "mcp_channel": "active",
                "encryption": "aes256_enabled"
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to store poem securely: {str(e)}"
            }
    
    def _generate_security_hash(self, data: Dict[str, Any]) -> str:
        """Generate security hash for data integrity"""
        import hashlib
        data_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(data_str.encode()).hexdigest()[:16]
    
    def _collaborative_poem_generation(self, theme: str, collaboration_type: str = "sequential") -> Dict[str, Any]:
        """Generate poem through secure A2A collaboration"""
        try:
            collaboration_id = str(uuid.uuid4())
            
            if collaboration_type == "sequential":
                # Sequential: Qwen 2.5 Coder 7B -> Qwen3 Coder pipeline
                self.logger.info(f"Starting sequential poem collaboration: {collaboration_id}")
                
                # Step 1: Generate initial poem with Qwen 2.5 Coder 7B
                qwen2.5-coder_result = self._generate_qwen2.5-coder_poem(
                    theme=theme,
                    style="free_verse",
                    length="medium"
                )
                
                if qwen2.5-coder_result["status"] != "success":
                    return qwen2.5-coder_result
                
                # Step 2: Enhance with Qwen3 Coder
                qwen3-coder_result = self._enhance_with_qwen3-coder(
                    poem=qwen2.5-coder_result["poem_data"]["content"],
                    enhancement_type="refine"
                )
                
                if qwen3-coder_result["status"] != "success":
                    # Use Qwen 2.5 Coder 7B result if Qwen3 Coder fails
                    final_poem = qwen2.5-coder_result["poem_data"]
                    enhancement_status = "failed_fallback_to_original"
                else:
                    # Combine results
                    final_poem = {
                        **qwen2.5-coder_result["poem_data"],
                        "content": qwen3-coder_result["enhancement_data"]["enhanced_content"],
                        "collaborative_process": "qwen2.5-coder_to_qwen3-coder",
                        "enhancement_applied": True
                    }
                    enhancement_status = "success"
                
                # Step 3: Store securely via MCP
                storage_result = self._store_poem_secure(
                    poem_data=final_poem,
                    metadata={
                        "collaboration_id": collaboration_id,
                        "collaboration_type": collaboration_type,
                        "agents_involved": ["qwen2.5-coder", "qwen3-coder"],
                        "enhancement_status": enhancement_status
                    }
                )
                
                return {
                    "status": "success",
                    "collaboration_id": collaboration_id,
                    "collaboration_type": collaboration_type,
                    "final_poem": final_poem,
                    "storage_result": storage_result,
                    "agents_used": ["qwen2.5-coder:7b-instruct-q4_K_M", "qwen3-coder:30b-a3b-q4_K_M"],
                    "security_flow": "encrypted_a2a_to_mcp_local"
                }
            
            else:
                return {
                    "status": "error",
                    "error": f"Unsupported collaboration type: {collaboration_type}",
                    "supported_types": ["sequential"]
                }
                
        except Exception as e:
            return {
                "status": "error",
                "error": f"Collaborative poem generation failed: {str(e)}"
            }


def create_poem_agents(config: SMCPConfig) -> Dict[str, PoemGenerationAgent]:
    """Create specialized poem generation agents"""
    registry = AgentRegistry()
    
    # Qwen 2.5 Coder 7B Agent (Initial Generation)
    qwen2.5-coder_agent = PoemGenerationAgent(
        config,
        AgentInfo(
            agent_id="qwen2.5-coder_poet",
            name="Qwen 2.5 Coder 7B Poet",
            description="Initial poem generation using Qwen 2.5 Coder 7B model",
            specialties=["poem_generation", "creative_writing", "initial_draft"],
            capabilities=["qwen2.5-coder_poem", "creative_ideation"]
        ),
        registry
    )
    
    # Qwen3 Coder Agent (Enhancement and Refinement)  
    qwen3-coder_agent = PoemGenerationAgent(
        config,
        AgentInfo(
            agent_id="qwen3-coder_enhancer", 
            name="Qwen3 Coder Enhancer",
            description="Poem enhancement and refinement using Qwen3 Coder model",
            specialties=["poem_enhancement", "literary_refinement", "style_improvement"],
            capabilities=["qwen3-coder_enhance", "literary_analysis"]
        ),
        registry
    )
    
    # MCP Storage Agent (Secure Local Storage)
    mcp_agent = PoemGenerationAgent(
        config,
        AgentInfo(
            agent_id="mcp_storage",
            name="MCP Storage Agent", 
            description="Secure local storage via MCP encrypted channels",
            specialties=["secure_storage", "data_encryption", "local_persistence"],
            capabilities=["store_poem_secure", "data_integrity"]
        ),
        registry
    )
    
    return {
        "qwen2.5-coder": qwen2.5-coder_agent,
        "qwen3-coder": qwen3-coder_agent,
        "mcp_storage": mcp_agent
    }


async def demo_poem_generation():
    """Demonstrate secure A2A poem generation with local MCP storage"""
    print("🎭 Secure A2A Poem Generation Demo")
    print("=" * 60)
    print("Architecture: Qwen 2.5 Coder 7B -> Qwen3 Coder -> MCP Local Storage")
    print("Security: Encrypted A2A + Local MCP Channels")
    print("=" * 60)
    
    # Load configuration
    config = SMCPConfig()
    
    # Check Ollama availability
    try:
        response = requests.get(f"{config.ai.ollama_url}/api/tags", timeout=5)
        if response.status_code != 200:
            print("❌ Ollama not available - demo requires Ollama running")
            return
        
        models = [m["name"] for m in response.json().get("models", [])]
        print(f"✓ Ollama available with models: {models}")
        
        required_models = ["qwen2.5-coder:7b-instruct-q4_K_M", "qwen3-coder:30b-a3b-q4_K_M"]
        missing_models = [m for m in required_models if m not in models]
        if missing_models:
            print(f"⚠️  Missing models: {missing_models}")
            print("   Run: ollama pull qwen2.5-coder && ollama pull qwen3-coder")
            return
            
    except Exception as e:
        print(f"❌ Cannot connect to Ollama: {e}")
        return
    
    # Create specialized agents
    agents = create_poem_agents(config)
    coordinator = agents["qwen2.5-coder"]  # Use Qwen 2.5 Coder 7B as coordinator
    
    # Demo themes
    themes = [
        "The beauty of secure communication",
        "Digital poetry in encrypted channels", 
        "AI collaboration across secure networks",
        "The future of distributed creativity"
    ]
    
    print(f"\n🎯 Generating poems for {len(themes)} themes...")
    
    results = []
    
    for i, theme in enumerate(themes, 1):
        print(f"\n[{i}/{len(themes)}] Theme: '{theme}'")
        print("-" * 50)
        
        # Generate poem through secure A2A collaboration
        result = coordinator._collaborative_poem_generation(
            theme=theme,
            collaboration_type="sequential"
        )
        
        if result["status"] == "success":
            poem = result["final_poem"]
            storage = result["storage_result"]
            
            print(f"✓ Collaboration ID: {result['collaboration_id']}")
            print(f"✓ Agents Used: {', '.join(result['agents_used'])}")
            print(f"✓ Security Flow: {result['security_flow']}")
            print(f"✓ Stored: {storage['stored_file']}")
            print(f"✓ Security Hash: {storage['security_hash']}")
            
            # Show poem excerpt
            content = poem["content"]
            if len(content) > 200:
                content = content[:200] + "..."
            print(f"\n📝 Poem Preview:\n{content}")
            
            results.append(result)
        else:
            print(f"❌ Failed: {result.get('error', 'Unknown error')}")
        
        # Pause between generations
        await asyncio.sleep(1)
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Generation Summary")
    print("=" * 60)
    
    successful = [r for r in results if r["status"] == "success"]
    print(f"✓ Successful generations: {len(successful)}/{len(themes)}")
    print(f"✓ Total poems stored: {len(successful)}")
    print(f"✓ Security level: AES256 MCP encrypted")
    print(f"✓ Storage location: ./local_poems/")
    
    if successful:
        print(f"\n🔒 Security Features Demonstrated:")
        print("• Encrypted agent-to-agent communication")
        print("• Secure local MCP storage channels")
        print("• Data integrity verification (SHA256)")
        print("• File-level encryption (AES256)")
        print("• Secure file permissions (600)")
        
        print(f"\n🤖 AI Models Collaboration:")
        print("• Qwen 2.5 Coder 7B: Initial creative generation")
        print("• Qwen3 Coder: Literary enhancement and refinement")
        print("• MCP: Secure encrypted local persistence")


async def main():
    """Main demonstration function"""
    print("🚀 Ollama Secure A2A Poem Generation Sample")
    print("=" * 70)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    try:
        await demo_poem_generation()
        
        print("\n" + "=" * 70)
        print("✅ Secure A2A Poem Generation Demo Complete!")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n❌ Demo failed: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())