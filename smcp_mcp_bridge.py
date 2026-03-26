#!/usr/bin/env python3
"""
SMCP-MCP Bridge Implementation
==============================
Universal bridge for integrating any MCP-compliant server into SMCP framework.
Enables seamless connection to custom MCP servers like MindDB, LangChain, and others.

Architecture:
- MCPBridge: Core bridge class for MCP server integration
- MCPServerConfig: Configuration for individual MCP servers
- MCPProtocolAdapter: Protocol translation between SMCP and MCP
- MCPCapabilityMapper: Maps MCP capabilities to SMCP capabilities

Features:
- Auto-discovery of MCP server capabilities
- Protocol translation (SMCP ↔ MCP)
- Security token management
- Connection pooling and retry logic
- Capability-based routing
"""

import asyncio
import json
import uuid
import aiohttp
import websockets
from typing import Dict, Any, Optional, List, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class MCPServerType(Enum):
    """Supported MCP server types"""
    MINDSDB = "mindsdb"
    LANGCHAIN = "langchain"
    CUSTOM = "custom"
    OPENAI_COMPATIBLE = "openai_compatible"
    HUGGINGFACE = "huggingface"
    VECTOR_DB = "vector_db"
    KNOWLEDGE_BASE = "knowledge_base"


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server"""
    server_id: str
    server_type: MCPServerType
    name: str
    url: str
    capabilities: List[str] = field(default_factory=list)
    auth_type: str = "bearer"  # bearer, api_key, oauth2, custom
    auth_token: Optional[str] = None
    api_key: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timeout: int = 30
    max_retries: int = 3
    connection_pool_size: int = 5
    
    # MindDB specific
    mindsdb_project: Optional[str] = None
    mindsdb_model: Optional[str] = None
    
    # Protocol settings
    protocol: str = "ws"  # ws, http, grpc
    version: str = "1.0"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary"""
        return {
            "server_id": self.server_id,
            "server_type": self.server_type.value,
            "name": self.name,
            "url": self.url,
            "capabilities": self.capabilities,
            "auth_type": self.auth_type,
            "metadata": self.metadata,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "protocol": self.protocol,
            "version": self.version
        }


class MCPProtocolAdapter:
    """Adapts between SMCP and MCP protocols"""
    
    def __init__(self):
        self.protocol_mappings = {
            "smcp_to_mcp": {
                "execute_task": "mcp.execute",
                "query_capability": "mcp.query",
                "store_data": "mcp.store",
                "retrieve_data": "mcp.retrieve"
            },
            "mcp_to_smcp": {
                "mcp.result": "task_result",
                "mcp.error": "task_error",
                "mcp.status": "task_status"
            }
        }
    
    def translate_request(self, smcp_request: Dict[str, Any], target_server: MCPServerConfig) -> Dict[str, Any]:
        """Translate SMCP request to MCP format"""
        
        # Base MCP request structure
        mcp_request = {
            "jsonrpc": "2.0",
            "id": smcp_request.get("request_id", str(uuid.uuid4())),
            "method": self._get_mcp_method(smcp_request.get("action", "execute"), target_server.server_type),
            "params": {}
        }
        
        # Handle different server types
        if target_server.server_type == MCPServerType.MINDSDB:
            mcp_request["params"] = self._translate_for_mindsdb(smcp_request, target_server)
        elif target_server.server_type == MCPServerType.LANGCHAIN:
            mcp_request["params"] = self._translate_for_langchain(smcp_request)
        else:
            # Generic MCP translation
            mcp_request["params"] = {
                "task": smcp_request.get("task", {}),
                "context": smcp_request.get("context", {}),
                "options": smcp_request.get("options", {})
            }
        
        return mcp_request
    
    def translate_response(self, mcp_response: Dict[str, Any], source_server: MCPServerConfig) -> Dict[str, Any]:
        """Translate MCP response to SMCP format"""
        
        smcp_response = {
            "status": "completed" if "result" in mcp_response else "error",
            "timestamp": datetime.now().isoformat(),
            "server_id": source_server.server_id,
            "server_type": source_server.server_type.value
        }
        
        if "result" in mcp_response:
            smcp_response["result"] = mcp_response["result"]
        elif "error" in mcp_response:
            smcp_response["error"] = mcp_response["error"]
            smcp_response["status"] = "error"
        
        # Add server-specific metadata
        if source_server.server_type == MCPServerType.MINDSDB:
            smcp_response["mindsdb_metadata"] = {
                "project": source_server.mindsdb_project,
                "model": source_server.mindsdb_model,
                "query_time": mcp_response.get("query_time")
            }
        
        return smcp_response
    
    def _get_mcp_method(self, action: str, server_type: MCPServerType = None) -> str:
        """Map SMCP action to MCP method"""
        if server_type == MCPServerType.MINDSDB:
            if action == "execute_task":
                return "mindsdb/query"
            elif action == "query_capability":
                return "mindsdb/models"
        
        return self.protocol_mappings["smcp_to_mcp"].get(action, "mcp.execute")
    
    def _translate_for_mindsdb(self, request: Dict[str, Any], config: MCPServerConfig) -> Dict[str, Any]:
        """Translate request for MindDB MCP protocol"""
        task = request.get("task", {})
        
        # MindDB MCP uses specific method names
        if task.get("query_type") == "sql_ml":
            # SQL-ML query
            return {
                "query": task.get("prompt", ""),
                "project": config.mindsdb_project or "mindsdb",
                "timeout": 30
            }
        else:
            # General AI task
            return {
                "messages": [{"role": "user", "content": task.get("prompt", "")}],
                "model": config.mindsdb_model or task.get("model", "gpt-4"),
                "project": config.mindsdb_project or "mindsdb",
                "parameters": {
                    "temperature": task.get("temperature", 0.7),
                    "max_tokens": task.get("max_tokens", 1000)
                }
            }
    
    def _translate_for_langchain(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Translate request for LangChain"""
        task = request.get("task", {})
        
        return {
            "chain_id": task.get("chain_id", "default"),
            "input": task.get("prompt", ""),
            "memory": task.get("memory", {}),
            "callbacks": task.get("callbacks", [])
        }


class MCPCapabilityMapper:
    """Maps MCP server capabilities to SMCP capabilities"""
    
    def __init__(self):
        self.capability_map = {
            # MindDB capabilities
            "mindsdb.predict": ["ai_prediction", "ml_inference"],
            "mindsdb.train": ["model_training", "ml_training"],
            "mindsdb.query": ["database_query", "sql_execution"],
            
            # LangChain capabilities
            "langchain.chain": ["chain_execution", "workflow"],
            "langchain.agent": ["agent_execution", "autonomous_task"],
            "langchain.memory": ["context_management", "memory_storage"],
            
            # Generic MCP capabilities
            "mcp.execute": ["task_execution", "general_processing"],
            "mcp.store": ["data_storage", "persistence"],
            "mcp.retrieve": ["data_retrieval", "query"],
            "mcp.transform": ["data_transformation", "processing"]
        }
    
    def discover_capabilities(self, mcp_capabilities: List[str]) -> List[str]:
        """Map MCP capabilities to SMCP capabilities"""
        smcp_capabilities = []
        
        for mcp_cap in mcp_capabilities:
            if mcp_cap in self.capability_map:
                smcp_capabilities.extend(self.capability_map[mcp_cap])
            else:
                # Keep unknown capabilities as-is
                smcp_capabilities.append(mcp_cap)
        
        return list(set(smcp_capabilities))  # Remove duplicates
    
    def get_required_mcp_capability(self, smcp_capability: str) -> Optional[str]:
        """Get MCP capability needed for SMCP capability"""
        for mcp_cap, smcp_caps in self.capability_map.items():
            if smcp_capability in smcp_caps:
                return mcp_cap
        return None


class MCPConnectionPool:
    """Connection pool for MCP servers"""
    
    def __init__(self, config: MCPServerConfig):
        self.config = config
        self.connections: List[Any] = []
        self.available: asyncio.Queue = asyncio.Queue()
        self.lock = asyncio.Lock()
        self.initialized = False
    
    async def initialize(self):
        """Initialize connection pool"""
        if self.initialized:
            return
        
        async with self.lock:
            if self.initialized:
                return
            
            for _ in range(self.config.connection_pool_size):
                conn = await self._create_connection()
                if conn:
                    self.connections.append(conn)
                    await self.available.put(conn)
            
            self.initialized = True
            logger.info(f"Initialized connection pool for {self.config.name} with {len(self.connections)} connections")
    
    async def _create_connection(self):
        """Create a new connection based on protocol"""
        try:
            if self.config.protocol == "ws":
                # WebSocket connection
                return await websockets.connect(
                    self.config.url,
                    extra_headers=self._get_auth_headers()
                )
            elif self.config.protocol == "http":
                # HTTP session
                session = aiohttp.ClientSession(
                    headers=self._get_auth_headers(),
                    timeout=aiohttp.ClientTimeout(total=self.config.timeout)
                )
                return session
            elif self.config.protocol == "sse":
                # Server-Sent Events connection (for MindDB MCP)
                session = aiohttp.ClientSession(
                    headers=self._get_auth_headers(),
                    timeout=aiohttp.ClientTimeout(total=self.config.timeout)
                )
                return session
            else:
                logger.warning(f"Unsupported protocol: {self.config.protocol}")
                return None
        except Exception as e:
            logger.error(f"Failed to create connection to {self.config.name}: {e}")
            return None
    
    def _get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers"""
        headers = {}
        
        if self.config.auth_type == "bearer" and self.config.auth_token:
            headers["Authorization"] = f"Bearer {self.config.auth_token}"
        elif self.config.auth_type == "api_key" and self.config.api_key:
            headers["X-API-Key"] = self.config.api_key
        
        return headers
    
    async def acquire(self):
        """Acquire a connection from pool"""
        if not self.initialized:
            await self.initialize()
        
        return await self.available.get()
    
    async def release(self, connection):
        """Release connection back to pool"""
        await self.available.put(connection)
    
    async def close(self):
        """Close all connections"""
        for conn in self.connections:
            try:
                if hasattr(conn, 'close'):
                    await conn.close()
            except Exception as e:
                logger.error(f"Error closing connection: {e}")
        
        self.connections.clear()
        self.initialized = False


class MCPBridge:
    """Main bridge class for MCP server integration"""
    
    def __init__(self):
        self.servers: Dict[str, MCPServerConfig] = {}
        self.connection_pools: Dict[str, MCPConnectionPool] = {}
        self.protocol_adapter = MCPProtocolAdapter()
        self.capability_mapper = MCPCapabilityMapper()
        self.capability_index: Dict[str, List[str]] = {}  # capability -> [server_ids]
        
    async def register_server(self, config: MCPServerConfig) -> bool:
        """Register an MCP server"""
        try:
            # Store server config
            self.servers[config.server_id] = config
            
            # Create connection pool
            pool = MCPConnectionPool(config)
            await pool.initialize()
            self.connection_pools[config.server_id] = pool
            
            # Discover and index capabilities
            if not config.capabilities:
                config.capabilities = await self._discover_server_capabilities(config)
            
            # Map to SMCP capabilities
            smcp_capabilities = self.capability_mapper.discover_capabilities(config.capabilities)
            
            # Update capability index
            for capability in smcp_capabilities:
                if capability not in self.capability_index:
                    self.capability_index[capability] = []
                self.capability_index[capability].append(config.server_id)
            
            logger.info(f"Registered MCP server: {config.name} with capabilities: {smcp_capabilities}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to register MCP server {config.name}: {e}")
            return False
    
    async def _discover_server_capabilities(self, config: MCPServerConfig) -> List[str]:
        """Discover server capabilities through introspection"""
        try:
            # Send capability discovery request
            discovery_request = {
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "mcp.capabilities",
                "params": {}
            }
            
            response = await self._send_request(config.server_id, discovery_request)
            
            if response and "result" in response:
                return response["result"].get("capabilities", [])
            
            # Return default capabilities based on server type
            if config.server_type == MCPServerType.MINDSDB:
                return ["mindsdb.predict", "mindsdb.query", "mindsdb.train"]
            elif config.server_type == MCPServerType.LANGCHAIN:
                return ["langchain.chain", "langchain.agent", "langchain.memory"]
            else:
                return ["mcp.execute", "mcp.store", "mcp.retrieve"]
                
        except Exception as e:
            logger.warning(f"Could not discover capabilities for {config.name}: {e}")
            return []
    
    async def execute_task(self, task: Dict[str, Any], capability: Optional[str] = None) -> Dict[str, Any]:
        """Execute a task on an appropriate MCP server"""
        
        # Find server with required capability
        server_id = self._select_server(capability, task)
        
        if not server_id:
            return {
                "status": "error",
                "error": f"No MCP server available for capability: {capability}"
            }
        
        server_config = self.servers[server_id]
        
        # Translate request
        mcp_request = self.protocol_adapter.translate_request(
            {"action": "execute_task", "task": task},
            server_config
        )
        
        # Send request with retry logic
        response = await self._send_request_with_retry(server_id, mcp_request)
        
        if not response:
            return {
                "status": "error",
                "error": f"Failed to execute task on {server_config.name}"
            }
        
        # Translate response
        return self.protocol_adapter.translate_response(response, server_config)
    
    def _select_server(self, capability: Optional[str], task: Dict[str, Any]) -> Optional[str]:
        """Select appropriate server for task"""
        
        # If specific capability requested
        if capability and capability in self.capability_index:
            server_ids = self.capability_index[capability]
            # TODO: Add load balancing logic
            return server_ids[0] if server_ids else None
        
        # Check for server type hints in task
        if "server_type" in task:
            server_type = MCPServerType(task["server_type"])
            for server_id, config in self.servers.items():
                if config.server_type == server_type:
                    return server_id
        
        # Default to first available server
        return next(iter(self.servers.keys())) if self.servers else None
    
    async def _send_request_with_retry(self, server_id: str, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send request with retry logic"""
        config = self.servers[server_id]
        
        for attempt in range(config.max_retries):
            try:
                response = await self._send_request(server_id, request)
                if response:
                    return response
            except Exception as e:
                logger.warning(f"Request attempt {attempt + 1} failed for {config.name}: {e}")
                if attempt < config.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
        
        return None
    
    async def _send_request(self, server_id: str, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send request to MCP server"""
        config = self.servers[server_id]
        pool = self.connection_pools[server_id]
        
        connection = await pool.acquire()
        
        try:
            if config.protocol == "ws":
                # WebSocket request
                await connection.send(json.dumps(request))
                response = await asyncio.wait_for(
                    connection.recv(),
                    timeout=config.timeout
                )
                return json.loads(response)
                
            elif config.protocol == "http":
                # HTTP request
                async with connection.post(
                    config.url,
                    json=request,
                    timeout=config.timeout
                ) as resp:
                    return await resp.json()
            
            else:
                logger.error(f"Unsupported protocol: {config.protocol}")
                return None
                
        except asyncio.TimeoutError:
            logger.error(f"Request timeout for {config.name}")
            return None
        except Exception as e:
            logger.error(f"Request failed for {config.name}: {e}")
            return None
        finally:
            await pool.release(connection)
    
    async def query_mindsdb(self, query: str, project: str = "default", model: str = "gpt-4") -> Dict[str, Any]:
        """Specialized method for MindDB queries"""
        
        # Find MindDB server
        mindsdb_server = None
        for server_id, config in self.servers.items():
            if config.server_type == MCPServerType.MINDSDB:
                mindsdb_server = config
                break
        
        if not mindsdb_server:
            return {"status": "error", "error": "No MindDB server registered"}
        
        # Create MindDB-specific request
        task = {
            "prompt": query,
            "model": model,
            "context": {"project": project}
        }
        
        return await self.execute_task(task, "mindsdb.predict")
    
    async def execute_langchain(self, chain_id: str, input_data: str, memory: Optional[Dict] = None) -> Dict[str, Any]:
        """Execute LangChain chain"""
        
        task = {
            "chain_id": chain_id,
            "prompt": input_data,
            "memory": memory or {},
            "server_type": "langchain"
        }
        
        return await self.execute_task(task, "langchain.chain")
    
    def get_registered_servers(self) -> List[Dict[str, Any]]:
        """Get list of registered servers"""
        return [config.to_dict() for config in self.servers.values()]
    
    def get_available_capabilities(self) -> Dict[str, List[str]]:
        """Get all available capabilities and their servers"""
        return dict(self.capability_index)
    
    async def health_check(self, server_id: str) -> bool:
        """Check health of specific server"""
        if server_id not in self.servers:
            return False
        
        health_request = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "mcp.health",
            "params": {}
        }
        
        response = await self._send_request(server_id, health_request)
        return response is not None and response.get("result", {}).get("status") == "healthy"
    
    async def close(self):
        """Close all connections"""
        for pool in self.connection_pools.values():
            await pool.close()
        
        self.servers.clear()
        self.connection_pools.clear()
        self.capability_index.clear()


# Configuration presets for common MCP servers
MCP_SERVER_PRESETS = {
    "mindsdb": {
        "server_type": MCPServerType.MINDSDB,
        "protocol": "sse",  # Server-Sent Events for MCP
        "auth_type": "bearer",
        "capabilities": ["mindsdb.predict", "mindsdb.query", "mindsdb.train", "mindsdb.sql"],
        "timeout": 60,
        "metadata": {
            "description": "MindDB AI Database with MCP Protocol (SSE)",
            "version": "latest",
            "features": ["sql_ml", "time_series", "nlp", "mcp", "sse"]
        }
    },
    "langchain": {
        "server_type": MCPServerType.LANGCHAIN,
        "protocol": "ws",
        "auth_type": "bearer",
        "capabilities": ["langchain.chain", "langchain.agent", "langchain.memory"],
        "timeout": 30,
        "metadata": {
            "description": "LangChain Framework",
            "version": "0.1.0",
            "features": ["chains", "agents", "memory", "tools"]
        }
    },
    "openai_compatible": {
        "server_type": MCPServerType.OPENAI_COMPATIBLE,
        "protocol": "http",
        "auth_type": "bearer",
        "capabilities": ["completion", "embedding", "moderation"],
        "timeout": 30,
        "metadata": {
            "description": "OpenAI Compatible API",
            "version": "v1",
            "features": ["chat", "completion", "embedding"]
        }
    }
}


def create_mindsdb_config(
    url: str = "http://localhost:47337/sse",
    api_key: str = "demo_key",
    project: str = "mindsdb",
    model: str = "gpt-4",
    name: str = "MindDB Server"
) -> MCPServerConfig:
    """Helper to create MindDB configuration"""
    
    preset = MCP_SERVER_PRESETS["mindsdb"]
    
    return MCPServerConfig(
        server_id=f"mindsdb_{uuid.uuid4().hex[:8]}",
        server_type=preset["server_type"],
        name=name,
        url=url,
        capabilities=preset["capabilities"],
        auth_type=preset["auth_type"],
        api_key=api_key,
        metadata=preset["metadata"],
        timeout=preset["timeout"],
        protocol=preset["protocol"],
        mindsdb_project=project,
        mindsdb_model=model
    )


def create_langchain_config(
    url: str,
    auth_token: str,
    name: str = "LangChain Server"
) -> MCPServerConfig:
    """Helper to create LangChain configuration"""
    
    preset = MCP_SERVER_PRESETS["langchain"]
    
    return MCPServerConfig(
        server_id=f"langchain_{uuid.uuid4().hex[:8]}",
        server_type=preset["server_type"],
        name=name,
        url=url,
        capabilities=preset["capabilities"],
        auth_type=preset["auth_type"],
        auth_token=auth_token,
        metadata=preset["metadata"],
        timeout=preset["timeout"],
        protocol=preset["protocol"]
    )


async def demo_mcp_bridge():
    """Demonstrate MCP Bridge functionality"""
    
    print("🌉 SMCP-MCP Bridge Demo")
    print("=" * 80)
    
    # Create bridge
    bridge = MCPBridge()
    
    # Example: Register MindDB server
    print("\n1️⃣ Registering MindDB Server...")
    mindsdb_config = create_mindsdb_config(
        url="http://localhost:47337/sse",  # MindDB MCP endpoint
        api_key="your_mindsdb_api_key",
        project="smcp_demo",
        model="gpt-4"
    )
    
    success = await bridge.register_server(mindsdb_config)
    if success:
        print("   ✅ MindDB server registered successfully")
        print(f"   📊 Capabilities: {mindsdb_config.capabilities}")
    else:
        print("   ❌ Failed to register MindDB server")
    
    # Example: Register LangChain server
    print("\n2️⃣ Registering LangChain Server...")
    langchain_config = create_langchain_config(
        url="ws://localhost:8080/langchain",
        auth_token="your_langchain_token"
    )
    
    success = await bridge.register_server(langchain_config)
    if success:
        print("   ✅ LangChain server registered successfully")
        print(f"   🔗 Capabilities: {langchain_config.capabilities}")
    else:
        print("   ❌ Failed to register LangChain server")
    
    # Show registered servers
    print("\n3️⃣ Registered MCP Servers:")
    servers = bridge.get_registered_servers()
    for server in servers:
        print(f"   • {server['name']} ({server['server_type']})")
        print(f"     URL: {server['url']}")
        print(f"     Capabilities: {', '.join(server['capabilities'])}")
    
    # Show capability mapping
    print("\n4️⃣ Available Capabilities:")
    capabilities = bridge.get_available_capabilities()
    for cap, servers in capabilities.items():
        print(f"   • {cap}: {', '.join(servers)}")
    
    # Example: Execute MindDB query
    print("\n5️⃣ Example: MindDB Query")
    result = await bridge.query_mindsdb(
        query="What are the key trends in AI for 2024?",
        project="smcp_demo",
        model="gpt-4"
    )
    
    if result["status"] == "completed":
        print("   ✅ Query successful")
        print(f"   📝 Response: {result.get('result', 'No response')[:200]}...")
    else:
        print(f"   ❌ Query failed: {result.get('error', 'Unknown error')}")
    
    # Example: Execute LangChain
    print("\n6️⃣ Example: LangChain Execution")
    result = await bridge.execute_langchain(
        chain_id="summarization_chain",
        input_data="Long document text here...",
        memory={"session_id": "demo_session"}
    )
    
    if result["status"] == "completed":
        print("   ✅ Chain execution successful")
        print(f"   📝 Result: {result.get('result', 'No result')[:200]}...")
    else:
        print(f"   ❌ Chain execution failed: {result.get('error', 'Unknown error')}")
    
    # Health check
    print("\n7️⃣ Health Checks:")
    for server_id in bridge.servers:
        healthy = await bridge.health_check(server_id)
        server_name = bridge.servers[server_id].name
        status = "✅ Healthy" if healthy else "❌ Unhealthy"
        print(f"   • {server_name}: {status}")
    
    # Cleanup
    await bridge.close()
    print("\n✅ MCP Bridge demo complete!")


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    asyncio.run(demo_mcp_bridge())