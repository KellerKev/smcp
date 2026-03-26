#!/usr/bin/env python3
"""
SCP A2A (Agent-to-Agent) Communication System
Enables agents to discover, coordinate, and collaborate with each other
"""

import asyncio
import json
import uuid
import time
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import logging

from smcp_core import SMCPNode, MessageType, SMCPMessage, Capability
from smcp_config import SMCPConfig


class A2AMessageType(Enum):
    AGENT_DISCOVERY = "agent_discovery"
    AGENT_REGISTER = "agent_register"
    TASK_REQUEST = "task_request"
    TASK_DELEGATE = "task_delegate"
    TASK_RESULT = "task_result"
    COORDINATION_REQUEST = "coordination_request"
    COLLABORATION_INVITE = "collaboration_invite"
    WORKFLOW_EXECUTE = "workflow_execute"


@dataclass
class AgentInfo:
    """Information about an agent"""
    agent_id: str
    name: str
    description: str
    specialties: List[str]
    capabilities: List[str]
    load: float = 0.0
    endpoint: Optional[str] = None
    last_seen: float = field(default_factory=time.time)


@dataclass
class Task:
    """Represents a task that can be delegated between agents"""
    task_id: str
    type: str
    description: str
    input_data: Any
    requirements: List[str] = field(default_factory=list)
    priority: int = 1
    timeout: int = 60
    callback: Optional[Callable] = None


@dataclass
class WorkflowStep:
    """A step in an agent workflow"""
    step_id: str
    agent_specialty: str
    task_type: str
    input_mapping: Dict[str, str] = field(default_factory=dict)
    output_mapping: Dict[str, str] = field(default_factory=dict)


class AgentRegistry:
    """Central registry for agent discovery and coordination"""
    
    def __init__(self):
        self.agents: Dict[str, AgentInfo] = {}
        self.logger = logging.getLogger('agent_registry')
    
    def register_agent(self, agent: AgentInfo):
        """Register an agent"""
        self.agents[agent.agent_id] = agent
        self.logger.info(f"Registered agent: {agent.name} ({agent.agent_id})")
    
    def unregister_agent(self, agent_id: str):
        """Unregister an agent"""
        if agent_id in self.agents:
            agent = self.agents.pop(agent_id)
            self.logger.info(f"Unregistered agent: {agent.name} ({agent_id})")
    
    def find_agents(self, specialty: str = None, capability: str = None) -> List[AgentInfo]:
        """Find agents by specialty or capability"""
        agents = []
        for agent in self.agents.values():
            if specialty and specialty in agent.specialties:
                agents.append(agent)
            elif capability and capability in agent.capabilities:
                agents.append(agent)
            elif not specialty and not capability:
                agents.append(agent)
        
        # Sort by load (least loaded first)
        return sorted(agents, key=lambda a: a.load)
    
    def get_best_agent(self, specialty: str) -> Optional[AgentInfo]:
        """Get the best available agent for a specialty"""
        agents = self.find_agents(specialty=specialty)
        return agents[0] if agents else None
    
    def update_agent_load(self, agent_id: str, load: float):
        """Update agent load"""
        if agent_id in self.agents:
            self.agents[agent_id].load = load
            self.agents[agent_id].last_seen = time.time()


class SMCPAgent(SMCPNode):
    """Extended SCP Node with A2A capabilities"""
    
    def __init__(self, config: SMCPConfig, agent_info: AgentInfo, registry: AgentRegistry = None):
        super().__init__(config.node_id, config.secret_key, config.jwt_secret)
        self.agent_info = agent_info
        self.registry = registry or AgentRegistry()
        self.config = config
        
        # A2A specific attributes
        self.active_tasks: Dict[str, Task] = {}
        self.peer_agents: Dict[str, str] = {}  # agent_id -> connection_info
        self.collaboration_sessions: Dict[str, List[str]] = {}  # session_id -> [agent_ids]
        
        # Logger
        self.logger = logging.getLogger(f'scp_agent_{agent_info.name}')
        
        # Register self in registry
        if self.registry:
            self.registry.register_agent(self.agent_info)
        
        # Register A2A capabilities
        self._register_a2a_capabilities()
    
    def _register_a2a_capabilities(self):
        """Register A2A specific capabilities"""
        
        # Agent discovery
        discovery_cap = Capability(
            name="agent_discovery",
            description="Discover other agents in the network",
            parameters={
                "specialty": {"type": "string", "description": "Agent specialty to search for"},
                "capability": {"type": "string", "description": "Capability to search for"}
            }
        )
        self.register_capability(discovery_cap, self._handle_agent_discovery)
        
        # Task delegation
        delegation_cap = Capability(
            name="task_delegate",
            description="Delegate a task to another agent",
            parameters={
                "task_type": {"type": "string"},
                "task_data": {"type": "object"},
                "target_specialty": {"type": "string"},
                "priority": {"type": "number", "default": 1}
            }
        )
        self.register_capability(delegation_cap, self._handle_task_delegation)
        
        # Workflow execution
        workflow_cap = Capability(
            name="workflow_execute",
            description="Execute a multi-agent workflow",
            parameters={
                "workflow_steps": {"type": "array"},
                "input_data": {"type": "object"}
            }
        )
        self.register_capability(workflow_cap, self._handle_workflow_execution)
        
        # Collaboration
        collab_cap = Capability(
            name="collaborate",
            description="Start a collaboration session with multiple agents",
            parameters={
                "agents": {"type": "array", "description": "List of agent specialties"},
                "task": {"type": "string", "description": "Collaborative task description"},
                "data": {"type": "object"}
            }
        )
        self.register_capability(collab_cap, self._handle_collaboration)
    
    def _handle_agent_discovery(self, specialty: str = None, capability: str = None) -> Dict[str, Any]:
        """Handle agent discovery requests"""
        agents = self.registry.find_agents(specialty, capability)
        
        return {
            "found_agents": [
                {
                    "agent_id": agent.agent_id,
                    "name": agent.name,
                    "description": agent.description,
                    "specialties": agent.specialties,
                    "capabilities": agent.capabilities,
                    "load": agent.load
                }
                for agent in agents
            ],
            "total_count": len(agents)
        }
    
    def _handle_task_delegation(self, task_type: str, task_data: Dict[str, Any], 
                               target_specialty: str, priority: int = 1) -> Dict[str, Any]:
        """Handle task delegation to other agents"""
        # Find best agent for the task
        target_agent = self.registry.get_best_agent(target_specialty)
        
        if not target_agent:
            return {
                "status": "failed",
                "error": f"No agent found with specialty: {target_specialty}"
            }
        
        # Create task
        task = Task(
            task_id=str(uuid.uuid4()),
            type=task_type,
            description=f"Delegated task: {task_type}",
            input_data=task_data,
            requirements=[target_specialty],
            priority=priority
        )
        
        # Store active task
        self.active_tasks[task.task_id] = task
        
        # In a real implementation, this would send the task to the target agent
        # For now, simulate task execution
        result = self._simulate_task_execution(task, target_agent)
        
        return {
            "status": "completed",
            "task_id": task.task_id,
            "target_agent": target_agent.name,
            "result": result
        }
    
    def _handle_workflow_execution(self, workflow_steps: List[Dict], input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a multi-agent workflow"""
        workflow_id = str(uuid.uuid4())
        results = {}
        current_data = input_data.copy()
        
        self.logger.info(f"Starting workflow {workflow_id} with {len(workflow_steps)} steps")
        
        for i, step_config in enumerate(workflow_steps):
            step_id = f"step_{i+1}"
            specialty = step_config.get("agent_specialty")
            task_type = step_config.get("task_type")
            
            # Find agent for this step
            agent = self.registry.get_best_agent(specialty)
            if not agent:
                return {
                    "status": "failed",
                    "error": f"No agent found for specialty: {specialty}",
                    "failed_step": step_id
                }
            
            # Execute step
            step_result = self._simulate_task_execution(
                Task(
                    task_id=f"{workflow_id}_{step_id}",
                    type=task_type,
                    description=f"Workflow step: {task_type}",
                    input_data=current_data
                ),
                agent
            )
            
            results[step_id] = {
                "agent": agent.name,
                "result": step_result
            }
            
            # Update data for next step
            if isinstance(step_result, dict):
                current_data.update(step_result)
        
        return {
            "status": "completed",
            "workflow_id": workflow_id,
            "steps_executed": len(workflow_steps),
            "results": results,
            "final_data": current_data
        }
    
    def _handle_collaboration(self, agents: List[str], task: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle collaboration between multiple agents"""
        session_id = str(uuid.uuid4())
        
        # Find agents for collaboration
        collaborators = []
        for specialty in agents:
            agent = self.registry.get_best_agent(specialty)
            if agent:
                collaborators.append(agent)
        
        if len(collaborators) < 2:
            return {
                "status": "failed",
                "error": "Need at least 2 agents for collaboration"
            }
        
        # Start collaboration session
        self.collaboration_sessions[session_id] = [agent.agent_id for agent in collaborators]
        
        # Simulate collaborative work
        results = {}
        for agent in collaborators:
            # Each agent contributes their specialty to the task
            contribution = self._simulate_collaborative_work(agent, task, data)
            results[agent.name] = contribution
        
        # Combine results
        final_result = self._combine_collaboration_results(results)
        
        return {
            "status": "completed",
            "session_id": session_id,
            "collaborators": [agent.name for agent in collaborators],
            "individual_results": results,
            "final_result": final_result
        }
    
    def _simulate_task_execution(self, task: Task, agent: AgentInfo) -> Any:
        """Simulate task execution by an agent (replace with real implementation)"""
        # Update agent load
        self.registry.update_agent_load(agent.agent_id, agent.load + 0.1)
        
        # Simulate different task types
        if task.type == "analysis":
            return {
                "analysis_result": f"Analysis of {task.input_data} by {agent.name}",
                "confidence": 0.85,
                "agent_specialty": agent.specialties[0] if agent.specialties else "general"
            }
        elif task.type == "research":
            return {
                "research_findings": f"Research on {task.input_data} by {agent.name}",
                "sources": ["source1", "source2", "source3"],
                "summary": f"Summary from {agent.name}"
            }
        elif task.type == "generation":
            return {
                "generated_content": f"Content generated by {agent.name} for {task.input_data}",
                "quality_score": 0.9
            }
        else:
            return {
                "result": f"Task {task.type} completed by {agent.name}",
                "execution_time": 2.5
            }
    
    def _simulate_collaborative_work(self, agent: AgentInfo, task: str, data: Dict[str, Any]) -> Any:
        """Simulate collaborative work by an agent"""
        if "research" in agent.specialties:
            return {
                "research_contribution": f"Research insights for {task}",
                "sources": [f"source_{i}" for i in range(3)]
            }
        elif "analysis" in agent.specialties:
            return {
                "analysis_contribution": f"Analysis of {task}",
                "key_findings": ["finding1", "finding2"]
            }
        elif "writing" in agent.specialties:
            return {
                "content_contribution": f"Written content for {task}",
                "word_count": 500
            }
        else:
            return {
                "general_contribution": f"General assistance with {task}"
            }
    
    def _combine_collaboration_results(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Combine results from multiple collaborating agents"""
        combined = {
            "collaborative_output": "Combined result from multiple agents",
            "contributors": list(results.keys()),
            "details": results,
            "quality_score": 0.92
        }
        
        # Combine specific types of results
        all_sources = []
        all_findings = []
        
        for agent_result in results.values():
            if isinstance(agent_result, dict):
                if "sources" in agent_result:
                    all_sources.extend(agent_result["sources"])
                if "key_findings" in agent_result:
                    all_findings.extend(agent_result["key_findings"])
        
        if all_sources:
            combined["aggregated_sources"] = list(set(all_sources))
        if all_findings:
            combined["aggregated_findings"] = list(set(all_findings))
        
        return combined


def create_demo_agents(config: SMCPConfig) -> List[SMCPAgent]:
    """Create demo agents for testing A2A functionality"""
    registry = AgentRegistry()
    
    agents = []
    
    # Research Agent
    research_agent = SMCPAgent(
        config,
        AgentInfo(
            agent_id="research_001",
            name="ResearchBot",
            description="Specialized in research and information gathering",
            specialties=["research", "information_gathering", "web_search"],
            capabilities=["search", "summarize", "fact_check"]
        ),
        registry
    )
    agents.append(research_agent)
    
    # Analysis Agent
    analysis_agent = SMCPAgent(
        config,
        AgentInfo(
            agent_id="analysis_001", 
            name="AnalysisBot",
            description="Specialized in data analysis and insights",
            specialties=["analysis", "data_processing", "insights"],
            capabilities=["analyze", "correlate", "predict"]
        ),
        registry
    )
    agents.append(analysis_agent)
    
    # Writing Agent
    writing_agent = SMCPAgent(
        config,
        AgentInfo(
            agent_id="writing_001",
            name="WritingBot", 
            description="Specialized in content creation and writing",
            specialties=["writing", "content_creation", "editing"],
            capabilities=["write", "edit", "format"]
        ),
        registry
    )
    agents.append(writing_agent)
    
    # AI Integration Agent (uses Ollama)
    ai_agent = SMCPAgent(
        config,
        AgentInfo(
            agent_id="ai_001",
            name="AIBot",
            description="AI-powered agent using local Ollama",
            specialties=["ai_reasoning", "language_processing", "generation"],
            capabilities=["ai_chat", "text_generation", "reasoning"]
        ),
        registry
    )
    
    # Add Ollama integration to AI agent
    ai_capability = Capability(
        name="ai_reasoning",
        description="Perform AI reasoning using local Ollama",
        parameters={
            "prompt": {"type": "string"},
            "model": {"type": "string", "default": "tinyllama:latest"},
            "context": {"type": "object", "default": {}}
        }
    )
    
    def ai_reasoning_handler(prompt: str, model: str = "tinyllama:latest", context: Dict = None) -> Dict[str, Any]:
        import requests
        try:
            # Combine context with prompt if provided
            full_prompt = prompt
            if context:
                context_str = json.dumps(context, indent=2)
                full_prompt = f"Context: {context_str}\n\nTask: {prompt}"
            
            response = requests.post(
                f'{config.ai.ollama_url}/api/generate',
                json={
                    "model": model,
                    "prompt": full_prompt,
                    "stream": False
                },
                timeout=30
            )
            
            if response.status_code == 200:
                ai_response = response.json().get("response", "No response")
                return {
                    "reasoning_result": ai_response,
                    "model": model,
                    "context_used": bool(context),
                    "prompt_length": len(full_prompt)
                }
            else:
                return {
                    "error": f"AI service error: {response.status_code}",
                    "model": model
                }
        except Exception as e:
            return {
                "error": f"Failed to connect to Ollama: {str(e)}",
                "note": "Make sure Ollama is running"
            }
    
    ai_agent.register_capability(ai_capability, ai_reasoning_handler)
    agents.append(ai_agent)
    
    return agents


# Demo workflow examples
DEMO_WORKFLOWS = {
    "research_analysis_report": [
        {"agent_specialty": "research", "task_type": "research"},
        {"agent_specialty": "analysis", "task_type": "analysis"},
        {"agent_specialty": "writing", "task_type": "generation"}
    ],
    "ai_assisted_analysis": [
        {"agent_specialty": "research", "task_type": "research"},
        {"agent_specialty": "ai_reasoning", "task_type": "ai_reasoning"},
        {"agent_specialty": "analysis", "task_type": "analysis"},
        {"agent_specialty": "writing", "task_type": "generation"}
    ]
}