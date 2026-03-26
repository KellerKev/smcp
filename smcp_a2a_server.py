#!/usr/bin/env python3
"""
SMCP A2A Network Server - Agent-to-Agent communication over network
Demonstrates agents communicating through SMCP protocol over WebSocket
"""

import asyncio
import json
import logging
import websockets
from typing import Dict, List, Optional
from datetime import datetime
import click

from smcp_config import SMCPConfig
from smcp_server import SMCPServer, tool
from smcp_a2a import SMCPAgent, AgentInfo, AgentRegistry


class A2ANetworkServer(SMCPServer):
    """Extended SMCP Server with A2A network capabilities"""
    
    def __init__(self, config: SMCPConfig):
        super().__init__(config)
        
        # A2A specific components
        self.agent_registry = AgentRegistry()
        self.network_agents: Dict[str, SMCPAgent] = {}
        
        # Register A2A network tools
        self._register_a2a_tools()
        
        # Create some demo agents on this server
        self._create_server_agents()
    
    def _create_server_agents(self):
        """Create demo agents that run on this server"""
        
        # Coordinator Agent
        coordinator_info = AgentInfo(
            agent_id="coordinator_001",
            name="CoordinatorBot",
            description="Orchestrates tasks across multiple agents",
            specialties=["coordination", "orchestration", "task_management"],
            capabilities=["coordinate", "orchestrate", "delegate"],
            endpoint=f"ws://{self.config.server.host}:{self.config.server.port}"
        )
        
        coordinator = SMCPAgent(self.config, coordinator_info, self.agent_registry)
        self.network_agents[coordinator_info.agent_id] = coordinator
        
        # Specialized Worker Agent
        worker_info = AgentInfo(
            agent_id="worker_001",
            name="WorkerBot",
            description="Performs specialized computational tasks",
            specialties=["computation", "data_processing", "analysis"],
            capabilities=["compute", "process", "analyze"],
            endpoint=f"ws://{self.config.server.host}:{self.config.server.port}"
        )
        
        worker = SMCPAgent(self.config, worker_info, self.agent_registry)
        self.network_agents[worker_info.agent_id] = worker
        
        # AI-Enhanced Agent (with Ollama integration)
        ai_info = AgentInfo(
            agent_id="ai_enhanced_001",
            name="AI-EnhancedBot", 
            description="AI-powered agent with Ollama integration",
            specialties=["ai_reasoning", "natural_language", "knowledge_synthesis"],
            capabilities=["ai_chat", "reasoning", "synthesis"],
            endpoint=f"ws://{self.config.server.host}:{self.config.server.port}"
        )
        
        ai_agent = SMCPAgent(self.config, ai_info, self.agent_registry)
        
        # Add Ollama capability to AI agent
        ai_capability = self.node.capabilities.get("ai_chat")
        if ai_capability:
            ai_agent.register_capability(ai_capability, self.node.tool_handlers["ai_chat"])
        
        self.network_agents[ai_info.agent_id] = ai_agent
        
        self.logger.info(f"Created {len(self.network_agents)} network agents")
    
    def _register_a2a_tools(self):
        """Register A2A network-specific tools"""
        
        @tool("network_agent_discovery", "Discover agents across the network", {
            "specialty": {"type": "string", "description": "Agent specialty to find"},
            "include_remote": {"type": "boolean", "default": True}
        })
        def network_agent_discovery(specialty: str = None, include_remote: bool = True) -> dict:
            """Discover agents across the network"""
            local_agents = self.agent_registry.find_agents(specialty=specialty)
            
            result = {
                "local_agents": [
                    {
                        "agent_id": agent.agent_id,
                        "name": agent.name,
                        "description": agent.description,
                        "specialties": agent.specialties,
                        "load": agent.load,
                        "endpoint": agent.endpoint
                    }
                    for agent in local_agents
                ],
                "discovery_time": datetime.now().isoformat(),
                "total_found": len(local_agents)
            }
            
            return result
        
        @tool("network_task_coordinate", "Coordinate a task across network agents", {
            "task_description": {"type": "string"},
            "required_specialties": {"type": "array"},
            "task_data": {"type": "object"}
        })
        def network_task_coordinate(task_description: str, required_specialties: List[str], task_data: dict) -> dict:
            """Coordinate a task across multiple network agents"""
            coordinator_id = "coordinator_001"
            
            if coordinator_id in self.network_agents:
                coordinator = self.network_agents[coordinator_id]
                
                # Use coordinator to orchestrate the task
                workflow_steps = []
                for specialty in required_specialties:
                    workflow_steps.append({
                        "agent_specialty": specialty,
                        "task_type": specialty.replace("_", "")
                    })
                
                result = coordinator._handle_workflow_execution(
                    workflow_steps=workflow_steps,
                    input_data={
                        "description": task_description,
                        "data": task_data,
                        "network_coordination": True
                    }
                )
                
                result["coordination_method"] = "network_distributed"
                result["coordinator"] = coordinator.agent_info.name
                
                return result
            else:
                return {
                    "status": "failed",
                    "error": "Coordinator agent not available",
                    "available_agents": list(self.network_agents.keys())
                }
        
        @tool("agent_collaboration", "Start multi-agent collaboration session", {
            "session_name": {"type": "string"},
            "participating_agents": {"type": "array"},
            "collaboration_goal": {"type": "string"},
            "input_data": {"type": "object"}
        })
        def agent_collaboration(session_name: str, participating_agents: List[str], 
                               collaboration_goal: str, input_data: dict) -> dict:
            """Start a collaboration session between multiple agents"""
            
            # Find participating agents
            available_agents = []
            for specialty in participating_agents:
                agents = self.agent_registry.find_agents(specialty=specialty)
                if agents:
                    available_agents.extend(agents[:1])  # Take one agent per specialty
            
            if len(available_agents) < 2:
                return {
                    "status": "failed",
                    "error": "Need at least 2 agents for collaboration",
                    "found_agents": len(available_agents)
                }
            
            # Use first available agent as collaboration coordinator
            if self.network_agents:
                coord_agent = next(iter(self.network_agents.values()))
                
                result = coord_agent._handle_collaboration(
                    agents=participating_agents,
                    task=collaboration_goal,
                    data=input_data
                )
                
                result["session_name"] = session_name
                result["network_collaboration"] = True
                result["participating_specialties"] = participating_agents
                
                return result
            
            return {"status": "failed", "error": "No coordinator available"}
        
        # Register tools with the server
        tools = [network_agent_discovery, network_task_coordinate, agent_collaboration]
        for func in tools:
            if hasattr(func, '_scp_tool'):
                tool_info = func._scp_tool
                self.register_tool(
                    tool_info["name"],
                    tool_info["description"], 
                    tool_info["parameters"],
                    func
                )


@click.command()
@click.option('--config', '-c', default='scp_config.toml',
              help='Configuration file path')
@click.option('--host', default='localhost', help='Server host')
@click.option('--port', type=int, default=8765, help='Server port')
@click.option('--log-level', default='INFO', help='Logging level')
def main(config, host, port, log_level):
    """Start SMCP A2A Network Server"""
    
    # Setup logging
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Load configuration
    try:
        scp_config = SMCPConfig.load(config_file=config)
        
        # Override with CLI args
        scp_config.server.host = host
        scp_config.server.port = port
        
    except Exception as e:
        click.echo(f"❌ Configuration error: {e}")
        return
    
    # Display startup info
    click.echo("🚀 Starting SMCP A2A Network Server")
    click.echo("=" * 60)
    click.echo(f"🏢 Server Configuration:")
    click.echo(f"   Host: {scp_config.server.host}")
    click.echo(f"   Port: {scp_config.server.port}")
    click.echo(f"   Node ID: {scp_config.node_id}")
    click.echo(f"   AI Model: {scp_config.ai.default_model}")
    click.echo("=" * 60)
    
    # Create and start server
    server = A2ANetworkServer(scp_config)
    
    click.echo(f"🤖 Network Agents Available:")
    for agent_id, agent in server.network_agents.items():
        info = agent.agent_info
        click.echo(f"   - {info.name}: {', '.join(info.specialties)}")
    
    click.echo(f"\n📡 A2A Network Capabilities:")
    click.echo("   - Agent discovery across network")
    click.echo("   - Distributed task coordination")
    click.echo("   - Multi-agent collaboration")
    click.echo("   - AI-enhanced agent reasoning")
    click.echo("   - Dynamic load balancing")
    
    click.echo(f"\n🔗 Available A2A Tools:")
    a2a_tools = ["network_agent_discovery", "network_task_coordinate", "agent_collaboration"]
    for tool_name in a2a_tools:
        if tool_name in server.node.capabilities:
            cap = server.node.capabilities[tool_name]
            click.echo(f"   - {tool_name}: {cap.description}")
    
    click.echo("\n🎯 Connect with SMCP client to test A2A functionality")
    click.echo("   Example: pixi run client --tool network_agent_discovery")
    click.echo("=" * 60)
    
    try:
        asyncio.run(server.start(host=scp_config.server.host, port=scp_config.server.port))
    except KeyboardInterrupt:
        click.echo("\n🛑 A2A Network Server stopped")


if __name__ == "__main__":
    main()