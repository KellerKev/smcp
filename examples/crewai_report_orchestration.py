#!/usr/bin/env python3
"""
CrewAI + SMCP Business Intelligence Report Generator
===================================================

🏢 Multi-Domain Business Analysis Demo using CrewAI + SMCP

Generates comprehensive business reports for:
• 📊 E-COMMERCE: Revenue analysis, customer metrics, city performance
• 💼 SAAS: Subscription analytics, customer retention, support metrics  
• 🔌 IOT: Device monitoring, sensor analytics, anomaly detection

Architecture:
┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
│   CrewAI Agents     │    │   SMCP A2A Network  │    │   SMCP Connectors   │
│                     │◄──►│                     │◄──►│                     │
│ • Data Analyst      │    │ • Qwen3 14B Agent   │    │ • DuckDB Connector  │
│ • Business Analyst  │    │ • Qwen3 30B Agent   │    │ • Filesystem Storage│
│ • Report Writer     │    │ • A2A Coordination  │    │ • Report Generation │
│ • Quality Reviewer  │    │ • Security Layer    │    │ • Audit Trail       │
└─────────────────────┘    └─────────────────────┘    └─────────────────────┘

Workflow:
1. 📊 Data Analyst → Executes SQL queries via SMCP DuckDB Connector
2. 🧠 Business Analyst → AI analysis via SMCP A2A (Qwen3 models)
3. ✍️  Report Writer → Generates professional reports with AI assistance
4. ✅ Quality Reviewer → Validates and approves final reports
5. 💾 Reports saved to ./crewai_reports/ via SMCP Filesystem Connector

Real Business Intelligence - Not Climate Change Reports!
"""

import asyncio
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

# Suppress LiteLLM tracking
os.environ["LITELLM_LOG"] = "ERROR"
os.environ["LITELLM_DISABLE_SPEND_LOGS"] = "true"

# Add parent directory to imports
sys.path.append(str(Path(__file__).parent.parent))

# Set up logging (INFO level for cleaner output)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('crewai_demo.log', mode='w')
    ]
)
logger = logging.getLogger(__name__)

# Disable verbose logging from CrewAI dependencies
logging.getLogger("LiteLLM").setLevel(logging.WARNING)
logging.getLogger("litellm").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)

# Pydantic imports for schema
from pydantic import BaseModel, Field

# CrewAI imports
try:
    from crewai import Agent, Crew, LLM
    from crewai import Task as CrewAITask
    from crewai.tools import BaseTool
except ImportError:
    print("❌ CrewAI not installed. Install with: pip install crewai")
    sys.exit(1)

# SMCP imports
from connectors.smcp_duckdb_connector import create_duckdb_connector
from connectors.smcp_filesystem_connector import create_filesystem_connector
from smcp_config import SMCPConfig, ClusterConfig
from smcp_distributed_a2a import DistributedA2AAgent, DistributedNodeRegistry
from smcp_a2a import AgentInfo, SMCPAgent, AgentRegistry, Task
from smcp_connector_base import QueryRequest, QueryType

# Pydantic schemas for CrewAI tool arguments
class DuckDBQuerySchema(BaseModel):
    """Schema for DuckDB query tool arguments"""
    sql_query: str = Field(..., description="SQL query to execute against DuckDB")

class A2AAnalysisSchema(BaseModel):
    """Schema for A2A analysis tool arguments"""
    analysis_request: str = Field(..., description="Analysis request to send to AI models")
    model_preference: Optional[str] = Field("qwen3", description="Preferred AI model (qwen3, creative, or both)")

class FilesystemWriteSchema(BaseModel):
    """Schema for filesystem write tool arguments"""
    file_path: str = Field(..., description="Path where to write the file")
    content: str = Field(..., description="Content to write to the file")
    file_format: str = Field("markdown", description="File format (markdown, txt, json, html, csv)")

class SMCPDuckDBTool(BaseTool):
    """CrewAI tool that uses SMCP DuckDB Connector for data access"""
    
    name: str = "smcp_duckdb_query"
    description: str = "Execute SQL queries against DuckDB via secure SMCP connector"
    args_schema: type[BaseModel] = DuckDBQuerySchema
    
    def __init__(self, duckdb_connector):
        super().__init__()
        self._duckdb_connector = duckdb_connector
    
    def _run(self, sql_query: str) -> str:
        """Execute SQL query synchronously"""
        # Run async query in sync context properly
        try:
            # Try to use existing event loop if available
            loop = asyncio.get_running_loop()
            # If we're in an async context, we need to use asyncio.run_coroutine_threadsafe
            import concurrent.futures
            import threading
            
            def run_async():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(self._execute_query(sql_query))
                finally:
                    new_loop.close()
            
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_async)
                return future.result(timeout=30)
                
        except RuntimeError:
            # No event loop running, we can create our own
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self._execute_query(sql_query))
            finally:
                loop.close()
    
    async def _execute_query(self, sql_query: str) -> str:
        """Execute SQL query and return formatted results"""
        try:
            request = QueryRequest(
                query_id=f"crewai_{int(time.time())}",
                query_type=QueryType.SELECT,
                query=sql_query
            )
            
            result = await self._duckdb_connector.execute_query(request)
            
            if result.status == "success" and result.data:
                print(f"   ✅ DuckDB query: {result.row_count} rows in {result.execution_time:.3f}s")
                # Format results for AI agent consumption
                formatted_data = []
                for row in result.data[:10]:  # Limit to first 10 rows
                    formatted_data.append(row)
                
                response_data = json.dumps({
                    "status": "success",
                    "query": sql_query,
                    "row_count": result.row_count,
                    "execution_time": result.execution_time,
                    "data": formatted_data,
                    "columns": result.columns
                }, indent=2)
                return response_data
            else:
                logger.error(f"❌ DuckDB query failed: {result.error}")
                return json.dumps({
                    "status": "error",
                    "query": sql_query,
                    "error": result.error
                })
                
        except Exception as e:
            logger.error(f"❌ DuckDB query exception: {str(e)}")
            return json.dumps({
                "status": "error",
                "query": sql_query,
                "error": str(e)
            })

class SMCPA2ATool(BaseTool):
    """CrewAI tool that uses SMCP A2A for AI model coordination"""
    
    name: str = "smcp_a2a_analysis"
    description: str = "Coordinate with AI models via secure SMCP A2A network for advanced analysis"
    args_schema: type[BaseModel] = A2AAnalysisSchema
    
    def __init__(self, a2a_agent):
        super().__init__()
        self._a2a_agent = a2a_agent
    
    def _run(self, analysis_request: str = "", model_preference: str = "qwen3", **kwargs) -> str:
        """Execute A2A analysis synchronously"""
        try:
            # Try to use existing event loop if available
            loop = asyncio.get_running_loop()
            import concurrent.futures
            
            def run_async():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(self._execute_a2a_analysis(analysis_request, model_preference))
                finally:
                    new_loop.close()
            
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_async)
                return future.result(timeout=30)
                
        except RuntimeError:
            # No event loop running, we can create our own
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self._execute_a2a_analysis(analysis_request, model_preference))
            finally:
                loop.close()
    
    async def _execute_a2a_analysis(self, analysis_request: str, model_preference: str) -> str:
        """Execute A2A analysis and return results"""
        try:
            # Validate inputs
            if not analysis_request:
                return json.dumps({
                    "status": "error",
                    "error": "No analysis request provided"
                })
            
            # Create A2A workflow based on model preference  
            if model_preference == "qwen3" or model_preference == "qwen3-coder":
                workflow_steps = [{"capability": "qwen3", "task_type": "business_analysis"}]
            elif model_preference == "creative":
                workflow_steps = [{"capability": "qwen2.5-coder", "task_type": "creative_generation"}]
            else:
                # Use both models for comprehensive analysis
                workflow_steps = [
                    {"capability": "qwen2.5-coder", "task_type": "initial_analysis"},
                    {"capability": "qwen3", "task_type": "enhancement"}
                ]
            
            print(f"   🧠 A2A analysis: {model_preference} model")
            result = await self._a2a_agent._handle_distributed_workflow(
                workflow_steps=workflow_steps,
                input_data={"analysis_request": analysis_request},
                routing_strategy="optimal"
            )
            
            # Extract final result from the workflow response
            final_data = result.get("final_data", {})
            analysis_result = "No result available"
            
            if final_data:
                # Try to get generated content or analysis result
                analysis_result = (
                    final_data.get("content") or 
                    final_data.get("generated_content") or
                    final_data.get("enhanced_content") or
                    final_data.get("analysis_result") or
                    str(final_data)
                )
                print(f"   ✅ Generated {len(analysis_result)} chars of analysis")
            else:
                print(f"   ⚠️  No analysis result returned")
            
            return json.dumps({
                "status": "success" if result.get("status") == "completed" else "error",
                "analysis_request": analysis_request,
                "model_preference": model_preference,
                "workflow_id": result.get("workflow_id"),
                "analysis_result": analysis_result,
                "models_used": final_data.get("models_used", []),
                "execution_time": result.get("execution_time", 0),
                "steps_executed": result.get("steps_executed", 0),
                "distributed": result.get("distributed", False)
            }, indent=2)
            
        except Exception as e:
            logger.error(f"❌ A2A analysis exception: {str(e)}")
            return json.dumps({
                "status": "error",
                "analysis_request": analysis_request,
                "error": str(e)
            })

class SMCPFilesystemTool(BaseTool):
    """CrewAI tool that uses SMCP Filesystem Connector for report storage"""
    
    name: str = "smcp_filesystem_write"
    description: str = "Write reports and files via secure SMCP filesystem connector"
    args_schema: type[BaseModel] = FilesystemWriteSchema
    
    def __init__(self, filesystem_connector):
        super().__init__()
        self._filesystem_connector = filesystem_connector
    
    def _run(self, file_path: str, content: str, file_format: str = "markdown") -> str:
        """Write file synchronously"""
        try:
            # Try to use existing event loop if available
            loop = asyncio.get_running_loop()
            import concurrent.futures
            
            def run_async():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(self._write_file(file_path, content, file_format))
                finally:
                    new_loop.close()
            
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_async)
                return future.result(timeout=30)
                
        except RuntimeError:
            # No event loop running, we can create our own
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self._write_file(file_path, content, file_format))
            finally:
                loop.close()
    
    async def _write_file(self, file_path: str, content: str, file_format: str) -> str:
        """Write file and return results"""
        try:
            result = await self._filesystem_connector.write_file(
                file_path=file_path,
                content=content,
                file_format=file_format
            )
            
            if result.status == "success" and result.data:
                file_info = result.data[0]
                return json.dumps({
                    "status": "success",
                    "file_path": file_info["file_path"],
                    "full_path": file_info["full_path"],
                    "size": file_info["size"],
                    "created": file_info["created"]
                }, indent=2)
            else:
                return json.dumps({
                    "status": "error",
                    "file_path": file_path,
                    "error": result.error
                })
                
        except Exception as e:
            return json.dumps({
                "status": "error",
                "file_path": file_path,
                "error": str(e)
            })


class LocalAIAgent(SMCPAgent):
    """Local AI agent that can handle A2A tasks using Ollama"""
    
    def __init__(self, config: SMCPConfig, agent_info: AgentInfo, model_name: str):
        local_registry = AgentRegistry()
        super().__init__(config, agent_info, local_registry)
        self.model_name = model_name
        self.tool_handlers = {
            "business_analysis": self._handle_business_analysis,
            "creative_generation": self._handle_creative_generation, 
            "enhancement": self._handle_enhancement,
            "poem_generation": self._handle_creative_generation
        }
    
    async def _handle_business_analysis(self, analysis_request: str = None, **kwargs) -> dict:
        """Handle business analysis requests"""
        try:
            # Extract analysis request from various parameter formats
            if not analysis_request:
                analysis_request = (
                    kwargs.get("analysis_request") or
                    kwargs.get("task_data", {}).get("analysis_request") or
                    kwargs.get("content") or
                    "General business analysis"
                )
            
            # Use Ollama to generate business analysis
            import aiohttp
            
            prompt = f"""
            Analyze the following business request and provide strategic insights:
            {analysis_request}
            
            Please provide:
            1. Key insights and patterns
            2. Strategic recommendations  
            3. Risk factors to consider
            4. Opportunities for growth
            
            Be concise but comprehensive.
            """
            
            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "stream": False
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post("http://localhost:11434/api/generate", json=payload) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        content = result.get("response", "No analysis available")
                        
                        return {
                            "status": "completed",
                            "generated_content": content,
                            "model": self.model_name,
                            "task_type": "business_analysis"
                        }
                    else:
                        return {"status": "error", "error": f"Ollama request failed: {resp.status}"}
                        
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    async def _handle_creative_generation(self, theme: str = None, analysis_request: str = None, **kwargs) -> dict:
        """Handle creative generation requests"""
        try:
            import aiohttp
            
            # Extract content request from various parameter formats
            content_request = (
                theme or analysis_request or 
                kwargs.get("analysis_request") or
                kwargs.get("task_data", {}).get("analysis_request") or
                kwargs.get("content") or 
                "creative writing"
            )
            
            prompt = f"""
            Generate creative content based on: {content_request}
            
            Be creative, engaging, and insightful. Provide substantive content.
            """
            
            payload = {
                "model": self.model_name,
                "prompt": prompt, 
                "stream": False
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post("http://localhost:11434/api/generate", json=payload) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        content = result.get("response", "No content available")
                        
                        return {
                            "status": "completed", 
                            "generated_content": content,
                            "model": self.model_name,
                            "task_type": "creative_generation"
                        }
                    else:
                        return {"status": "error", "error": f"Ollama request failed: {resp.status}"}
                        
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    async def _handle_enhancement(self, content: str = None, **kwargs) -> dict:
        """Handle content enhancement requests"""
        try:
            import aiohttp
            
            # Extract content from various parameter formats
            base_content = (
                content or 
                kwargs.get("generated_content") or
                kwargs.get("analysis_request") or
                kwargs.get("task_data", {}).get("analysis_request") or
                kwargs.get("content") or
                ""
            )
            
            prompt = f"""
            Enhance and improve the following content:
            {base_content}
            
            Make it more:
            - Professional and polished
            - Insightful and analytical  
            - Actionable and specific
            - Well-structured and clear
            
            Provide enhanced version:
            """
            
            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "stream": False
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post("http://localhost:11434/api/generate", json=payload) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        enhanced_content = result.get("response", "No enhancement available")
                        
                        return {
                            "status": "completed",
                            "enhanced_content": enhanced_content, 
                            "model": self.model_name,
                            "task_type": "enhancement"
                        }
                    else:
                        return {"status": "error", "error": f"Ollama request failed: {resp.status}"}
                        
        except Exception as e:
            return {"status": "error", "error": str(e)}


class CrewAISMCPOrchestrator:
    """Main orchestrator combining CrewAI with SMCP A2A coordination"""
    
    def __init__(self):
        self.duckdb_connector = None
        self.filesystem_connector = None
        self.a2a_agent = None
        self.crew = None
        
    async def setup_smcp_infrastructure(self):
        """Setup all SMCP connectors and A2A coordination"""
        print("🔧 Setting up SMCP infrastructure...")
        
        # Setup DuckDB connector (use existing database)
        print("   🦆 Setting up DuckDB connector...")
        self.duckdb_connector = await create_duckdb_connector(
            database_path="demo_analytics.db",
            memory_limit="2GB",
            threads=4
        )
        
        # Setup filesystem connector for reports
        print("   📁 Setting up filesystem connector...")
        self.filesystem_connector = await create_filesystem_connector(
            base_path="./crewai_reports",
            create_dirs=True,
            allowed_extensions=[".md", ".txt", ".json", ".html", ".csv"]
        )
        
        # Setup A2A coordination
        print("   🤖 Setting up A2A coordination...")
        config = SMCPConfig(
            mode="basic",
            node_id="crewai_orchestrator",
            server_url="ws://localhost:8765",
            api_key="crewai_key",
            secret_key="crewai_secret",
            jwt_secret="crewai_jwt"
        )
        
        config.cluster = ClusterConfig(
            enabled=True,
            simulate_distributed=True,
            simulate_ports=[8766, 8767, 8768]
        )
        
        cluster_registry = DistributedNodeRegistry(config.cluster)
        
        agent_info = AgentInfo(
            agent_id="crewai_smcp_orchestrator",
            name="CrewAI SMCP Orchestrator",
            description="Multi-agent orchestration with SMCP connector integration",
            specialties=["orchestration", "data_analysis", "report_generation"],
            capabilities=["crewai_coordination", "smcp_connectors", "a2a_routing"]
        )
        
        self.a2a_agent = DistributedA2AAgent(config, agent_info, cluster_registry)
        
        # Register AI agents for A2A capabilities
        await self._register_ai_agents(cluster_registry)
        
        print("✅ SMCP infrastructure ready")
    
    async def _register_ai_agents(self, cluster_registry):
        """Register local AI agents for A2A capabilities"""
        print("   🧠 Registering AI agents for A2A capabilities...")
        
        # Create Qwen3 14B creative agent (replacing Qwen 2.5 Coder 7B)
        qwen2.5-coder_info = AgentInfo(
            agent_id="local_qwen14b",
            name="Local Qwen3 14B Agent", 
            description="Fast creative text generation and analysis using Qwen3 14B",
            specialties=["qwen2.5-coder", "creative_writing", "initial_analysis", "qwen3"],
            capabilities=["poem_generation", "creative_generation", "business_analysis"]
        )
        
        qwen_creative_agent = LocalAIAgent(self.a2a_agent.config, qwen2.5-coder_info, "qwen3:14b-q4_K_M")
        cluster_registry.register_local_agent(qwen_creative_agent)
        
        # Create Qwen3 30B agent for advanced analysis
        qwen30b_info = AgentInfo(
            agent_id="local_qwen30b",
            name="Local Qwen3 30B Agent",
            description="Advanced analysis and strategic insights using Qwen3 30B", 
            specialties=["qwen3", "enhancement", "analysis", "strategic_planning"],
            capabilities=["enhancement", "business_analysis", "strategic_analysis", "complex_reasoning"]
        )
        
        qwen30b_agent = LocalAIAgent(self.a2a_agent.config, qwen30b_info, "qwen3:30b-instruct")
        cluster_registry.register_local_agent(qwen30b_agent)
        
        print(f"   ✓ Registered {len(cluster_registry.local_agents)} AI agents")
    
    def setup_crewai_agents(self):
        """Setup CrewAI agents with SMCP tool integration"""
        print("🎭 Setting up CrewAI agents...")
        
        # Create SMCP tools
        duckdb_tool = SMCPDuckDBTool(self.duckdb_connector)
        a2a_tool = SMCPA2ATool(self.a2a_agent)
        filesystem_tool = SMCPFilesystemTool(self.filesystem_connector)
        
        # Configure Ollama LLM for CrewAI - using more powerful model
        ollama_llm = LLM(
            model="ollama/qwen3:14b-q4_K_M",
            base_url="http://localhost:11434"
        )
        
        # Data Analyst Agent
        data_analyst = Agent(
            role="Data Analyst",
            goal="Extract and analyze business data from DuckDB using SMCP connectors",
            backstory="Expert in SQL analysis and data extraction with secure database connectivity",
            tools=[duckdb_tool],
            llm=ollama_llm,
            verbose=True,
            allow_delegation=False
        )
        
        # Business Intelligence Analyst
        business_analyst = Agent(
            role="Business Intelligence Analyst", 
            goal="Transform data insights into strategic business recommendations using AI analysis",
            backstory="Senior business analyst with expertise in AI-driven strategic planning",
            tools=[a2a_tool],
            llm=ollama_llm,
            verbose=True,
            allow_delegation=False
        )
        
        # Report Writer Agent
        report_writer = Agent(
            role="Report Writer",
            goal="Create comprehensive business reports combining data analysis and strategic insights",
            backstory="Professional business writer specializing in executive-level reporting",
            tools=[a2a_tool, filesystem_tool],
            llm=ollama_llm,
            verbose=True,
            allow_delegation=False
        )
        
        # Quality Reviewer Agent
        quality_reviewer = Agent(
            role="Quality Reviewer",
            goal="Review and validate final reports for accuracy and completeness",
            backstory="Senior quality assurance specialist ensuring report excellence",
            tools=[filesystem_tool],
            llm=ollama_llm,
            verbose=True,
            allow_delegation=False
        )
        
        print("✅ CrewAI agents configured")
        return data_analyst, business_analyst, report_writer, quality_reviewer
    
    def create_analysis_tasks(self, data_analyst, business_analyst, report_writer, quality_reviewer, business_domain: str):
        """Create CrewAI tasks for the analysis workflow"""
        print(f"📋 Creating analysis tasks for domain: {business_domain}")
        
        # Determine domain-specific queries and focus areas
        if business_domain == "ecommerce":
            data_query = """
            SELECT 
                c.city,
                COUNT(DISTINCT c.customer_id) as total_customers,
                COUNT(DISTINCT o.order_id) as total_orders, 
                SUM(o.total_amount) as total_revenue,
                AVG(o.total_amount) as avg_order_value
            FROM ecommerce_customers c
            JOIN ecommerce_orders o ON c.customer_id = o.customer_id
            GROUP BY c.city
            ORDER BY total_revenue DESC
            LIMIT 10
            """
            focus_area = "e-commerce revenue optimization and customer satisfaction"
            
        elif business_domain == "saas":
            data_query = """
            SELECT 
                s.plan,
                COUNT(DISTINCT u.user_id) as total_users,
                AVG(u.monthly_spend) as avg_monthly_spend,
                AVG(st.satisfaction_score) as avg_satisfaction,
                COUNT(st.ticket_id) as support_tickets
            FROM saas_subscriptions s
            JOIN saas_users u ON s.user_id = u.user_id
            LEFT JOIN saas_support_tickets st ON u.user_id = st.user_id
            GROUP BY s.plan
            ORDER BY total_users DESC
            """
            focus_area = "SaaS subscription optimization and customer retention"
            
        else:  # iot
            data_query = """
            SELECT 
                d.device_type,
                d.location,
                COUNT(DISTINCT d.device_id) as device_count,
                AVG(sr.value) as avg_sensor_value,
                COUNT(CASE WHEN sr.is_anomaly = true THEN 1 END) as anomaly_count,
                COUNT(a.alert_id) as alert_count
            FROM iot_devices d
            LEFT JOIN iot_sensor_readings sr ON d.device_id = sr.device_id
            LEFT JOIN iot_alerts a ON d.device_id = a.device_id
            GROUP BY d.device_type, d.location
            ORDER BY anomaly_count DESC
            LIMIT 10
            """
            focus_area = "IoT device monitoring and predictive maintenance"
        
        # Task 1: Data Analysis
        data_analysis_task = CrewAITask(
            description=f"""
            Extract and analyze {business_domain} business data.
            
            Use the tool smcp_duckdb_query to execute this exact SQL query:
            
            sql_query: {data_query}
            
            After getting the query results, analyze:
            1. Key performance indicators and trends
            2. Top performing segments/locations/products
            3. Areas of concern or opportunity
            4. Data quality and completeness assessment
            
            Focus on actionable insights for {focus_area}.
            Important: Use only the 'smcp_duckdb_query' tool for database queries.
            """,
            expected_output="Comprehensive data analysis with key metrics, trends, and initial insights",
            agent=data_analyst
        )
        
        # Task 2: Business Intelligence Analysis
        business_intelligence_task = CrewAITask(
            description=f"""
            Using the data analysis results, perform advanced business intelligence analysis.
            
            Use the tool smcp_a2a_analysis with these exact parameters:
            
            analysis_request: "Analyze the {business_domain} performance data and provide strategic recommendations for {focus_area}. Focus on growth opportunities, risk mitigation, and operational improvements."
            model_preference: "qwen3"
            
            Provide:
            1. Strategic interpretation of the data patterns
            2. Business impact assessment and implications
            3. Competitive positioning insights
            4. Risk factors and mitigation strategies  
            5. Growth opportunities and expansion recommendations
            
            Important: Use only the 'smcp_a2a_analysis' tool for AI analysis.
            """,
            expected_output="Strategic business intelligence with actionable recommendations and risk assessment",
            agent=business_analyst
        )
        
        # Task 3: Executive Report Writing
        report_writing_task = CrewAITask(
            description=f"""
            Create a comprehensive executive-level business report.
            
            First, use 'smcp_a2a_analysis' to help generate report content with this request:
            "Help write an executive business report for {business_domain} performance analysis, incorporating data insights and strategic recommendations for C-suite presentation."
            
            Set model_preference to "both" for comprehensive report generation.
            
            The report should include:
            1. Executive Summary (key findings and recommendations)
            2. Business Performance Analysis (data-driven insights)
            3. Strategic Recommendations (actionable next steps)
            4. Risk Assessment and Mitigation
            5. Implementation Roadmap
            6. Appendix (supporting data and methodology)
            
            Then use 'smcp_filesystem_write' to save the report:
            - file_path: "reports/{business_domain}_executive_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            - file_format: "markdown"
            
            Important: Use 'smcp_a2a_analysis' for content generation and 'smcp_filesystem_write' for saving.
            """,
            expected_output="Professional executive report saved to filesystem via SMCP connector",
            agent=report_writer
        )
        
        # Task 4: Quality Review and Validation
        quality_review_task = CrewAITask(
            description=f"""
            Review and validate the final {business_domain} executive report.
            
            Use 'smcp_filesystem_read' to read the generated report, then perform quality assurance:
            1. Verify all data references and calculations
            2. Check report structure and flow
            3. Ensure recommendations are actionable and specific
            4. Validate business terminology and accuracy
            5. Review for grammar, clarity, and professional presentation
            
            Create a quality assessment and use 'smcp_filesystem_write' to save it:
            - file_path: "reports/{business_domain}_quality_review_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            - file_format: "markdown"
            
            Include:
            - Overall quality score (1-10)
            - Areas of strength
            - Areas for improvement
            - Final validation status
            
            Important: Use 'smcp_filesystem_read' to read reports and 'smcp_filesystem_write' to save the review.
            """,
            expected_output="Quality review assessment with validation status and recommendations",
            agent=quality_reviewer
        )
        
        print("✅ Analysis tasks created")
        return [data_analysis_task, business_intelligence_task, report_writing_task, quality_review_task]
    
    async def execute_crewai_workflow(self, business_domain: str = "ecommerce"):
        """Execute the complete CrewAI + SMCP orchestrated workflow"""
        print(f"🚀 Starting CrewAI + SMCP orchestrated workflow for {business_domain}")
        print("=" * 80)
        
        # Setup infrastructure
        await self.setup_smcp_infrastructure()
        
        # Setup agents
        agents = self.setup_crewai_agents()
        data_analyst, business_analyst, report_writer, quality_reviewer = agents
        
        # Create tasks
        tasks = self.create_analysis_tasks(*agents, business_domain)
        
        # Create and configure crew with agent assignments
        print("🎭 Creating CrewAI crew...")
        
        # Assign agents to tasks
        tasks[0].agent = data_analyst           # Data Analysis Task
        tasks[1].agent = business_analyst       # Business Intelligence Task  
        tasks[2].agent = report_writer          # Report Writing Task
        tasks[3].agent = quality_reviewer       # Quality Review Task
        
        self.crew = Crew(
            agents=[data_analyst, business_analyst, report_writer, quality_reviewer],
            tasks=tasks,
            verbose=True  # Enable verbose logging for demonstration
        )
        
        # Execute workflow
        print("\n🏃 Executing CrewAI workflow with SMCP A2A coordination...")
        print("=" * 80)
        
        start_time = time.time()
        result = self.crew.kickoff()
        execution_time = time.time() - start_time
        
        print("\n" + "=" * 80)
        print("✅ CrewAI + SMCP Orchestration Complete!")
        print("=" * 80)
        
        # Summary
        print(f"📊 Execution Summary:")
        print(f"   • Domain: {business_domain.title()}")
        print(f"   • Total time: {execution_time:.2f} seconds")
        print(f"   • Agents: 4 (Data Analyst, Business Analyst, Report Writer, Quality Reviewer)")
        print(f"   • SMCP Connectors: DuckDB, Filesystem, A2A Coordination")
        print(f"   • AI Models: Qwen 2.5 Coder 7B, Qwen3 Coder (via SMCP A2A)")
        print(f"   • Reports stored: ./crewai_reports/")
        
        # Clean up
        if self.duckdb_connector:
            await self.duckdb_connector.disconnect()
        if self.filesystem_connector:
            await self.filesystem_connector.disconnect()
        
        return {
            "execution_time": execution_time,
            "business_domain": business_domain,
            "agents_used": 4,
            "smcp_connectors": ["duckdb", "filesystem", "a2a"],
            "ai_models": ["qwen3-14b", "qwen3-30b"],
            "reports_generated": True,
            "final_result": str(result)
        }

async def main():
    """Main function to run the CrewAI + SMCP orchestration demo"""
    
    print("🏢 CrewAI + SMCP Business Intelligence Report Generator")
    print("=" * 80)
    print("📊 Multi-Domain Analysis: E-commerce | SaaS | IoT")
    print("🚀 Architecture: CrewAI → SMCP A2A → Qwen3 Models → DuckDB/Filesystem")
    print("📋 Workflow: Data Analysis → AI Analysis → Report Writing → Quality Review")
    print("=" * 80)
    
    # Check prerequisites
    print("\n🔍 Checking Prerequisites...")
    
    # Check if sample data exists
    if not Path("sample_data").exists():
        print("   ❌ Sample data not found")
        print("   💡 Generate sample data: pixi run python tools/generate_sample_data.py")
        return
    
    if not Path("demo_analytics.db").exists():
        print("   ❌ Demo database not found")  
        print("   💡 Run DuckDB demo first: pixi run python examples/duckdb_integration_example.py")
        return
    
    # Check Ollama
    try:
        import requests
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get("models", [])
            print(f"   ✅ Ollama running with {len(models)} models")
        else:
            print("   ⚠️ Ollama status unclear")
    except:
        print("   ❌ Ollama not available")
        print("   💡 Start Ollama: ollama serve")
        return
    
    print("   ✅ All prerequisites met")
    
    # Create orchestrator
    orchestrator = CrewAISMCPOrchestrator()
    
    # Run workflow for different business domains
    domains = ["ecommerce", "saas", "iot"]
    
    for domain in domains:
        print(f"\n{'=' * 60}")
        print(f"🏢 Running {domain.title()} Analysis Workflow")
        print(f"{'=' * 60}")
        
        try:
            result = await orchestrator.execute_crewai_workflow(domain)
            
            print(f"\n✅ {domain.title()} workflow completed successfully!")
            print(f"   Execution time: {result['execution_time']:.2f}s")
            print(f"   Reports: ./crewai_reports/")
            
        except Exception as e:
            print(f"\n❌ {domain.title()} workflow failed: {e}")
            continue
        
        # Brief pause between workflows
        print(f"\n⏱️ Brief pause before next workflow...")
        await asyncio.sleep(2)
    
    print(f"\n{'=' * 80}")
    print("🎉 All CrewAI + SMCP Orchestration Workflows Complete!")
    print(f"{'=' * 80}")
    print("🔍 Check ./crewai_reports/ directory for generated business reports")

if __name__ == "__main__":
    asyncio.run(main())