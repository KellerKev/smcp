#!/usr/bin/env python3
"""
SMCP Connector Base Framework
============================

Base classes and interfaces for creating native SMCP data connectors.
This framework allows developers to easily create custom connectors for any data source.

Connector Types Supported:
- Database connectors (SQL, NoSQL)
- File-based connectors (CSV, JSON, Parquet)
- API connectors (REST, GraphQL)
- Stream connectors (Kafka, WebSocket)
- Cloud storage connectors (S3, GCS, Azure)

Design Principles:
1. Simple, consistent interface for all connector types
2. Built-in security with SMCP authentication and encryption
3. Async/await support for high performance
4. Comprehensive error handling and validation
5. Easy extensibility for custom data sources
"""

import asyncio
import json
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Any, Optional, Union, AsyncGenerator
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class ConnectorType(Enum):
    """Supported connector types"""
    DATABASE = "database"
    FILE = "file"  
    API = "api"
    STREAM = "stream"
    CLOUD_STORAGE = "cloud_storage"

class QueryType(Enum):
    """Supported query types"""
    SELECT = "select"
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"
    CUSTOM = "custom"

@dataclass
class ConnectorConfig:
    """Configuration for SMCP connectors"""
    name: str
    connector_type: ConnectorType
    connection_params: Dict[str, Any]
    security_config: Optional[Dict[str, Any]] = None
    performance_config: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class QueryRequest:
    """Request structure for connector queries"""
    query_id: str
    query_type: QueryType
    query: str
    parameters: Optional[Dict[str, Any]] = None
    options: Optional[Dict[str, Any]] = None
    security_context: Optional[Dict[str, Any]] = None

@dataclass
class QueryResult:
    """Result structure for connector queries"""
    query_id: str
    status: str
    data: Optional[Union[List[Dict], Dict, Any]] = None
    columns: Optional[List[str]] = None
    row_count: Optional[int] = None
    execution_time: Optional[float] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class SMCPConnectorBase(ABC):
    """
    Abstract base class for all SMCP connectors
    
    This class defines the interface that all SMCP connectors must implement.
    It provides common functionality for authentication, error handling, and logging.
    """
    
    def __init__(self, config: ConnectorConfig):
        self.config = config
        self.connector_id = str(uuid.uuid4())
        self.is_connected = False
        self.connection = None
        self.logger = logging.getLogger(f"{self.__class__.__name__}_{self.connector_id[:8]}")
        
    @abstractmethod
    async def connect(self) -> bool:
        """
        Establish connection to the data source
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def disconnect(self) -> bool:
        """
        Close connection to the data source
        
        Returns:
            bool: True if disconnection successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def execute_query(self, request: QueryRequest) -> QueryResult:
        """
        Execute a query against the data source
        
        Args:
            request: QueryRequest object containing query details
            
        Returns:
            QueryResult: Result of the query execution
        """
        pass
    
    @abstractmethod
    async def get_schema(self) -> Dict[str, Any]:
        """
        Get schema information from the data source
        
        Returns:
            Dict containing schema metadata
        """
        pass
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check the health status of the connector
        
        Returns:
            Dict containing health status information
        """
        try:
            if not self.is_connected:
                return {
                    "status": "unhealthy",
                    "reason": "not_connected",
                    "connector_id": self.connector_id,
                    "timestamp": datetime.now().isoformat()
                }
            
            # Perform a lightweight test query
            test_result = await self.test_connection()
            
            return {
                "status": "healthy" if test_result else "unhealthy",
                "connector_id": self.connector_id,
                "connector_type": self.config.connector_type.value,
                "timestamp": datetime.now().isoformat(),
                "response_time_ms": getattr(test_result, 'execution_time', 0) * 1000 if test_result else None
            }
            
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return {
                "status": "unhealthy",
                "reason": str(e),
                "connector_id": self.connector_id,
                "timestamp": datetime.now().isoformat()
            }
    
    async def test_connection(self) -> bool:
        """
        Test the connection with a lightweight operation
        
        Returns:
            bool: True if test successful, False otherwise
        """
        try:
            # Default implementation - subclasses can override
            return self.is_connected
        except Exception:
            return False
    
    def validate_query_request(self, request: QueryRequest) -> bool:
        """
        Validate a query request before execution
        
        Args:
            request: QueryRequest to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        if not request.query_id:
            return False
        if not request.query:
            return False
        if not isinstance(request.query_type, QueryType):
            return False
        return True
    
    def create_error_result(self, query_id: str, error: str) -> QueryResult:
        """
        Create a standardized error result
        
        Args:
            query_id: ID of the failed query
            error: Error description
            
        Returns:
            QueryResult with error information
        """
        return QueryResult(
            query_id=query_id,
            status="error",
            error=error,
            metadata={
                "connector_id": self.connector_id,
                "connector_type": self.config.connector_type.value,
                "timestamp": datetime.now().isoformat()
            }
        )
    
    async def __aenter__(self):
        """Async context manager entry"""
        if not self.is_connected:
            await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.is_connected:
            await self.disconnect()


class SMCPConnectorManager:
    """
    Manager for SMCP connectors
    
    Handles registration, lifecycle, and routing for multiple connectors
    """
    
    def __init__(self):
        self.connectors: Dict[str, SMCPConnectorBase] = {}
        self.logger = logging.getLogger("SMCPConnectorManager")
    
    async def register_connector(self, name: str, connector: SMCPConnectorBase) -> bool:
        """
        Register a new connector
        
        Args:
            name: Unique name for the connector
            connector: SMCPConnectorBase instance
            
        Returns:
            bool: True if registration successful
        """
        try:
            if name in self.connectors:
                self.logger.warning(f"Connector {name} already exists, replacing")
            
            self.connectors[name] = connector
            self.logger.info(f"Registered connector: {name} ({connector.__class__.__name__})")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to register connector {name}: {e}")
            return False
    
    async def unregister_connector(self, name: str) -> bool:
        """
        Unregister and disconnect a connector
        
        Args:
            name: Name of the connector to unregister
            
        Returns:
            bool: True if successful
        """
        try:
            if name not in self.connectors:
                self.logger.warning(f"Connector {name} not found")
                return False
            
            connector = self.connectors[name]
            if connector.is_connected:
                await connector.disconnect()
            
            del self.connectors[name]
            self.logger.info(f"Unregistered connector: {name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to unregister connector {name}: {e}")
            return False
    
    async def execute_query(self, connector_name: str, request: QueryRequest) -> QueryResult:
        """
        Execute a query on a specific connector
        
        Args:
            connector_name: Name of the connector to use
            request: Query request
            
        Returns:
            QueryResult: Result of query execution
        """
        if connector_name not in self.connectors:
            return QueryResult(
                query_id=request.query_id,
                status="error",
                error=f"Connector {connector_name} not found"
            )
        
        connector = self.connectors[connector_name]
        
        if not connector.is_connected:
            await connector.connect()
        
        return await connector.execute_query(request)
    
    async def get_connector_status(self, connector_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get status of connectors
        
        Args:
            connector_name: Specific connector name, or None for all connectors
            
        Returns:
            Dict containing connector status information
        """
        if connector_name:
            if connector_name not in self.connectors:
                return {"error": f"Connector {connector_name} not found"}
            return await self.connectors[connector_name].health_check()
        
        # Return status of all connectors
        status = {}
        for name, connector in self.connectors.items():
            status[name] = await connector.health_check()
        
        return {
            "connectors": status,
            "total_count": len(self.connectors),
            "healthy_count": sum(1 for s in status.values() if s.get("status") == "healthy"),
            "timestamp": datetime.now().isoformat()
        }
    
    async def close_all(self):
        """Close all registered connectors"""
        for name, connector in self.connectors.items():
            try:
                if connector.is_connected:
                    await connector.disconnect()
            except Exception as e:
                self.logger.error(f"Error closing connector {name}: {e}")
        
        self.connectors.clear()
        self.logger.info("All connectors closed")