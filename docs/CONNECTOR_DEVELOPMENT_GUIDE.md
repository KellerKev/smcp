# SMCP Connector Development Guide

## Overview

This guide provides comprehensive documentation for creating custom SMCP (Secure Message Coordination Protocol) connectors. The SMCP Connector Framework allows developers to easily integrate any data source with the SMCP ecosystem while maintaining security, performance, and consistency.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Getting Started](#getting-started)
- [Connector Types](#connector-types)
- [Implementation Guide](#implementation-guide)
- [API Reference](#api-reference)
- [Best Practices](#best-practices)
- [Examples](#examples)
- [Testing](#testing)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)

## Architecture Overview

### Framework Components

```
┌─────────────────────────────────────────────────────────────┐
│                 SMCP Connector Framework                    │
├─────────────────────────────────────────────────────────────┤
│  SMCPConnectorBase    │  ConnectorManager  │  Security      │
│  - Abstract Interface │  - Registration    │  - Auth & Enc  │
│  - Common Operations  │  - Routing         │  - Validation  │
│  - Error Handling     │  - Health Checks   │  - Monitoring  │
├─────────────────────────────────────────────────────────────┤
│           Custom Connector Implementations                  │
│  DuckDB  │  PostgreSQL  │  MongoDB  │  S3  │  REST API     │
├─────────────────────────────────────────────────────────────┤
│              Data Sources & External Systems               │
│  Databases │  File Systems │  APIs │  Streams │  Clouds     │
└─────────────────────────────────────────────────────────────┘
```

### Design Principles

1. **Simple, Consistent Interface**: All connectors implement the same base interface
2. **Built-in Security**: SMCP authentication and encryption are integrated
3. **Async/Await Support**: High-performance async operations throughout
4. **Comprehensive Error Handling**: Clear error messages and recovery strategies
5. **Easy Extensibility**: Simple to add support for new data sources

## Getting Started

### Prerequisites

- Python 3.8+
- SMCP Framework components
- Target data source libraries (varies by connector)

### Quick Start

1. **Install Dependencies**
   ```bash
   pixi add duckdb  # Example for DuckDB connector
   ```

2. **Create Your Connector**
   ```python
   from smcp_connector_base import SMCPConnectorBase, ConnectorConfig, ConnectorType
   
   class MyConnector(SMCPConnectorBase):
       async def connect(self) -> bool:
           # Implementation here
           pass
   ```

3. **Register and Use**
   ```python
   from smcp_connector_base import SMCPConnectorManager
   
   manager = SMCPConnectorManager()
   await manager.register_connector("my_db", MyConnector(config))
   ```

## Connector Types

### DATABASE Connectors
- **Purpose**: Relational and NoSQL databases
- **Examples**: PostgreSQL, MySQL, MongoDB, DuckDB
- **Features**: SQL queries, transactions, schema discovery

### FILE Connectors
- **Purpose**: File-based data sources
- **Examples**: CSV, JSON, Parquet, Excel
- **Features**: Bulk loading, format detection, streaming

### API Connectors
- **Purpose**: REST APIs and web services
- **Examples**: Salesforce, Stripe, GitHub API
- **Features**: HTTP methods, authentication, rate limiting

### STREAM Connectors
- **Purpose**: Real-time data streams
- **Examples**: Kafka, WebSockets, message queues
- **Features**: Event handling, backpressure, ordering

### CLOUD_STORAGE Connectors
- **Purpose**: Cloud storage services
- **Examples**: AWS S3, Google Cloud Storage, Azure Blob
- **Features**: Object operations, permissions, lifecycle

## Implementation Guide

### Step 1: Define Your Connector Class

```python
from smcp_connector_base import (
    SMCPConnectorBase, ConnectorConfig, QueryRequest, QueryResult,
    QueryType, ConnectorType
)

class MyDataSourceConnector(SMCPConnectorBase):
    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        # Initialize your connector-specific properties
        self.connection_string = config.connection_params.get("connection_string")
        self.timeout = config.connection_params.get("timeout", 30)
```

### Step 2: Implement Required Methods

#### Connection Management
```python
async def connect(self) -> bool:
    """Establish connection to the data source"""
    try:
        # Your connection logic here
        self.connection = await create_connection(self.connection_string)
        self.is_connected = True
        self.logger.info("Successfully connected")
        return True
    except Exception as e:
        self.logger.error(f"Connection failed: {e}")
        self.is_connected = False
        return False

async def disconnect(self) -> bool:
    """Close connection to the data source"""
    try:
        if self.connection:
            await self.connection.close()
        self.is_connected = False
        return True
    except Exception as e:
        self.logger.error(f"Disconnect failed: {e}")
        return False
```

#### Query Execution
```python
async def execute_query(self, request: QueryRequest) -> QueryResult:
    """Execute a query against the data source"""
    start_time = time.time()
    
    # Validate request
    if not self.validate_query_request(request):
        return self.create_error_result(request.query_id, "Invalid query request")
    
    if not self.is_connected:
        return self.create_error_result(request.query_id, "Not connected")
    
    try:
        # Execute your query logic
        result = await self.connection.execute(request.query, request.parameters)
        execution_time = time.time() - start_time
        
        return QueryResult(
            query_id=request.query_id,
            status="success",
            data=result.data,
            columns=result.columns,
            row_count=len(result.data),
            execution_time=execution_time,
            metadata={
                "connector_id": self.connector_id,
                "connector_type": self.config.connector_type.value,
                "timestamp": datetime.now().isoformat()
            }
        )
        
    except Exception as e:
        execution_time = time.time() - start_time
        error_msg = f"Query execution failed: {str(e)}"
        self.logger.error(f"Query {request.query_id} failed: {e}")
        
        result = self.create_error_result(request.query_id, error_msg)
        result.execution_time = execution_time
        return result
```

#### Schema Discovery
```python
async def get_schema(self) -> Dict[str, Any]:
    """Get schema information from the data source"""
    if not self.is_connected:
        return {"error": "Not connected to data source"}
    
    try:
        # Your schema discovery logic
        tables = await self.connection.list_tables()
        
        schema = {
            "data_source": self.config.name,
            "connector_type": self.config.connector_type.value,
            "tables": [],
            "timestamp": datetime.now().isoformat()
        }
        
        for table in tables:
            columns = await self.connection.describe_table(table.name)
            schema["tables"].append({
                "name": table.name,
                "columns": columns,
                "row_count": await self.connection.count_rows(table.name)
            })
        
        return schema
        
    except Exception as e:
        self.logger.error(f"Schema discovery failed: {e}")
        return {"error": f"Failed to get schema: {str(e)}"}
```

### Step 3: Add Connector-Specific Features

#### Bulk Operations (for DATABASE/FILE connectors)
```python
async def bulk_insert(self, table_name: str, data: List[Dict]) -> QueryResult:
    """Bulk insert data"""
    query_id = f"bulk_insert_{int(time.time())}"
    
    try:
        start_time = time.time()
        rows_inserted = await self.connection.bulk_insert(table_name, data)
        execution_time = time.time() - start_time
        
        return QueryResult(
            query_id=query_id,
            status="success",
            row_count=rows_inserted,
            execution_time=execution_time,
            metadata={
                "operation": "bulk_insert",
                "table_name": table_name,
                "rows_inserted": rows_inserted
            }
        )
        
    except Exception as e:
        return self.create_error_result(query_id, f"Bulk insert failed: {str(e)}")
```

#### Stream Processing (for STREAM connectors)
```python
async def subscribe_to_stream(self, topic: str, callback) -> bool:
    """Subscribe to data stream"""
    try:
        await self.connection.subscribe(topic, callback)
        self.logger.info(f"Subscribed to stream: {topic}")
        return True
    except Exception as e:
        self.logger.error(f"Stream subscription failed: {e}")
        return False
```

### Step 4: Create Configuration Helper

```python
def create_my_connector(connection_string: str, **kwargs) -> MyDataSourceConnector:
    """Create and connect a MyDataSource connector"""
    config = ConnectorConfig(
        name=f"my_datasource_{int(time.time())}",
        connector_type=ConnectorType.DATABASE,  # Choose appropriate type
        connection_params={
            "connection_string": connection_string,
            **kwargs
        }
    )
    
    return MyDataSourceConnector(config)
```

## API Reference

### SMCPConnectorBase

#### Abstract Methods (Must Implement)
- `connect() -> bool`: Establish connection
- `disconnect() -> bool`: Close connection  
- `execute_query(request: QueryRequest) -> QueryResult`: Execute query
- `get_schema() -> Dict[str, Any]`: Get schema information

#### Provided Methods (Can Override)
- `health_check() -> Dict[str, Any]`: Check connector health
- `test_connection() -> bool`: Test connection with lightweight operation
- `validate_query_request(request: QueryRequest) -> bool`: Validate request
- `create_error_result(query_id: str, error: str) -> QueryResult`: Create error result

### Data Classes

#### ConnectorConfig
```python
@dataclass
class ConnectorConfig:
    name: str
    connector_type: ConnectorType
    connection_params: Dict[str, Any]
    security_config: Optional[Dict[str, Any]] = None
    performance_config: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
```

#### QueryRequest
```python
@dataclass
class QueryRequest:
    query_id: str
    query_type: QueryType
    query: str
    parameters: Optional[Dict[str, Any]] = None
    options: Optional[Dict[str, Any]] = None
    security_context: Optional[Dict[str, Any]] = None
```

#### QueryResult
```python
@dataclass
class QueryResult:
    query_id: str
    status: str
    data: Optional[Union[List[Dict], Dict, Any]] = None
    columns: Optional[List[str]] = None
    row_count: Optional[int] = None
    execution_time: Optional[float] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
```

### Enums

#### ConnectorType
- `DATABASE`: SQL and NoSQL databases
- `FILE`: File-based data sources
- `API`: REST APIs and web services
- `STREAM`: Real-time data streams
- `CLOUD_STORAGE`: Cloud storage services

#### QueryType
- `SELECT`: Data retrieval queries
- `INSERT`: Data insertion operations
- `UPDATE`: Data modification operations
- `DELETE`: Data deletion operations
- `CUSTOM`: Custom or complex operations

## Best Practices

### Security

1. **Parameter Validation**
   ```python
   def validate_query_request(self, request: QueryRequest) -> bool:
       # Validate SQL injection prevention
       # Check parameter types
       # Verify permissions
       return super().validate_query_request(request)
   ```

2. **Connection Security**
   ```python
   async def connect(self) -> bool:
       # Use SSL/TLS connections
       # Implement proper authentication
       # Handle credentials securely
       pass
   ```

### Performance

1. **Connection Pooling**
   ```python
   class MyConnector(SMCPConnectorBase):
       def __init__(self, config: ConnectorConfig):
           super().__init__(config)
           self.connection_pool = None
       
       async def connect(self) -> bool:
           self.connection_pool = await create_pool(
               self.connection_string,
               min_size=5,
               max_size=20
           )
   ```

2. **Query Optimization**
   ```python
   async def execute_query(self, request: QueryRequest) -> QueryResult:
       # Add query caching
       # Implement query timeouts
       # Use prepared statements
       pass
   ```

### Error Handling

1. **Comprehensive Logging**
   ```python
   try:
       result = await self.connection.execute(query)
   except SpecificException as e:
       self.logger.error(f"Specific error occurred: {e}")
       return self.create_error_result(query_id, "Specific error message")
   except Exception as e:
       self.logger.error(f"Unexpected error: {e}")
       return self.create_error_result(query_id, "General error occurred")
   ```

2. **Graceful Degradation**
   ```python
   async def health_check(self) -> Dict[str, Any]:
       try:
           return await super().health_check()
       except Exception:
           return {
               "status": "degraded",
               "message": "Limited functionality available"
           }
   ```

### Testing

1. **Unit Tests**
   ```python
   import pytest
   from unittest.mock import AsyncMock
   
   @pytest.mark.asyncio
   async def test_connect_success():
       config = ConnectorConfig(...)
       connector = MyConnector(config)
       
       result = await connector.connect()
       assert result is True
       assert connector.is_connected is True
   ```

2. **Integration Tests**
   ```python
   @pytest.mark.asyncio
   async def test_end_to_end_query():
       connector = await create_test_connector()
       
       request = QueryRequest(
           query_id="test_1",
           query_type=QueryType.SELECT,
           query="SELECT * FROM test_table LIMIT 10"
       )
       
       result = await connector.execute_query(request)
       assert result.status == "success"
       assert len(result.data) <= 10
   ```

## Examples

### Complete PostgreSQL Connector

```python
import asyncio
import asyncpg
from smcp_connector_base import *

class PostgreSQLConnector(SMCPConnectorBase):
    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        self.connection_string = config.connection_params.get("connection_string")
        self.pool = None
    
    async def connect(self) -> bool:
        try:
            self.pool = await asyncpg.create_pool(
                self.connection_string,
                min_size=2,
                max_size=10
            )
            self.is_connected = True
            self.logger.info("PostgreSQL pool created successfully")
            return True
        except Exception as e:
            self.logger.error(f"PostgreSQL connection failed: {e}")
            return False
    
    async def disconnect(self) -> bool:
        try:
            if self.pool:
                await self.pool.close()
            self.is_connected = False
            return True
        except Exception as e:
            self.logger.error(f"PostgreSQL disconnect failed: {e}")
            return False
    
    async def execute_query(self, request: QueryRequest) -> QueryResult:
        start_time = time.time()
        
        if not self.validate_query_request(request):
            return self.create_error_result(request.query_id, "Invalid query")
        
        try:
            async with self.pool.acquire() as connection:
                if request.query_type == QueryType.SELECT:
                    rows = await connection.fetch(request.query)
                    data = [dict(row) for row in rows]
                    columns = list(rows[0].keys()) if rows else []
                    
                    return QueryResult(
                        query_id=request.query_id,
                        status="success",
                        data=data,
                        columns=columns,
                        row_count=len(data),
                        execution_time=time.time() - start_time
                    )
                else:
                    result = await connection.execute(request.query)
                    return QueryResult(
                        query_id=request.query_id,
                        status="success",
                        row_count=int(result.split()[-1]),
                        execution_time=time.time() - start_time
                    )
                    
        except Exception as e:
            return self.create_error_result(
                request.query_id,
                f"PostgreSQL query failed: {str(e)}"
            )
    
    async def get_schema(self) -> Dict[str, Any]:
        if not self.is_connected:
            return {"error": "Not connected"}
        
        try:
            async with self.pool.acquire() as connection:
                tables = await connection.fetch("""
                    SELECT table_name, column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_schema = 'public'
                    ORDER BY table_name, ordinal_position
                """)
                
                schema = {"tables": {}}
                for row in tables:
                    table_name = row["table_name"]
                    if table_name not in schema["tables"]:
                        schema["tables"][table_name] = []
                    
                    schema["tables"][table_name].append({
                        "name": row["column_name"],
                        "type": row["data_type"]
                    })
                
                return schema
                
        except Exception as e:
            return {"error": f"Schema discovery failed: {str(e)}"}

# Usage example
async def create_postgresql_connector(connection_string: str):
    config = ConnectorConfig(
        name="postgresql_main",
        connector_type=ConnectorType.DATABASE,
        connection_params={"connection_string": connection_string}
    )
    
    connector = PostgreSQLConnector(config)
    await connector.connect()
    return connector
```

### REST API Connector

```python
import aiohttp
from smcp_connector_base import *

class RestAPIConnector(SMCPConnectorBase):
    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        self.base_url = config.connection_params.get("base_url")
        self.api_key = config.connection_params.get("api_key")
        self.session = None
    
    async def connect(self) -> bool:
        try:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            self.session = aiohttp.ClientSession(headers=headers)
            
            # Test connection
            async with self.session.get(f"{self.base_url}/health") as response:
                if response.status == 200:
                    self.is_connected = True
                    return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"API connection failed: {e}")
            return False
    
    async def execute_query(self, request: QueryRequest) -> QueryResult:
        # Map query to HTTP request
        # Handle different HTTP methods
        # Parse JSON responses
        pass
```

## Testing

### Unit Test Template

```python
import pytest
from unittest.mock import AsyncMock, patch
from your_connector import YourConnector
from smcp_connector_base import ConnectorConfig, ConnectorType, QueryRequest, QueryType

@pytest.fixture
def connector_config():
    return ConnectorConfig(
        name="test_connector",
        connector_type=ConnectorType.DATABASE,
        connection_params={"connection_string": "test://localhost:5432/testdb"}
    )

@pytest.fixture
def connector(connector_config):
    return YourConnector(connector_config)

@pytest.mark.asyncio
async def test_connect_success(connector):
    with patch.object(connector, 'create_connection') as mock_create:
        mock_create.return_value = AsyncMock()
        
        result = await connector.connect()
        
        assert result is True
        assert connector.is_connected is True
        mock_create.assert_called_once()

@pytest.mark.asyncio
async def test_execute_query_success(connector):
    # Setup
    await connector.connect()
    
    request = QueryRequest(
        query_id="test_query",
        query_type=QueryType.SELECT,
        query="SELECT 1 as test"
    )
    
    # Execute
    result = await connector.execute_query(request)
    
    # Assert
    assert result.status == "success"
    assert result.query_id == "test_query"
    assert result.execution_time > 0

@pytest.mark.asyncio
async def test_schema_discovery(connector):
    await connector.connect()
    
    schema = await connector.get_schema()
    
    assert "tables" in schema
    assert isinstance(schema["tables"], (list, dict))
```

### Integration Test Example

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_database_connection():
    """Integration test with real database"""
    config = ConnectorConfig(
        name="integration_test",
        connector_type=ConnectorType.DATABASE,
        connection_params={
            "connection_string": "postgresql://test:test@localhost:5432/testdb"
        }
    )
    
    connector = YourConnector(config)
    
    try:
        # Test connection
        connected = await connector.connect()
        assert connected
        
        # Test query execution
        request = QueryRequest(
            query_id="integration_test",
            query_type=QueryType.SELECT,
            query="SELECT version()"
        )
        
        result = await connector.execute_query(request)
        assert result.status == "success"
        assert result.data is not None
        
    finally:
        await connector.disconnect()
```

## Deployment

### Production Configuration

```python
# production_config.py
from smcp_connector_base import ConnectorConfig, ConnectorType

def create_production_config():
    return ConnectorConfig(
        name="production_postgres",
        connector_type=ConnectorType.DATABASE,
        connection_params={
            "connection_string": "postgresql://user:pass@prod-db:5432/maindb",
            "pool_min_size": 5,
            "pool_max_size": 20,
            "command_timeout": 30
        },
        security_config={
            "ssl_mode": "require",
            "ssl_cert": "/path/to/cert.pem",
            "ssl_key": "/path/to/key.pem"
        },
        performance_config={
            "connection_timeout": 10,
            "query_timeout": 60,
            "retry_attempts": 3
        }
    )
```

### Container Deployment

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy connector code
COPY connectors/ ./connectors/
COPY smcp_connector_base.py .

# Run connector
CMD ["python", "-m", "connectors.my_connector"]
```

### Kubernetes Deployment

```yaml
# connector-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: smcp-connector
spec:
  replicas: 3
  selector:
    matchLabels:
      app: smcp-connector
  template:
    metadata:
      labels:
        app: smcp-connector
    spec:
      containers:
      - name: connector
        image: smcp/my-connector:latest
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: db-secret
              key: connection-string
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
```

## Troubleshooting

### Common Issues

#### Connection Problems
```python
# Debug connection issues
async def debug_connection(self):
    try:
        await self.connect()
    except Exception as e:
        self.logger.error(f"Connection failed: {e}")
        # Check network connectivity
        # Verify credentials
        # Test firewall rules
```

#### Query Failures
```python
# Add detailed query logging
async def execute_query(self, request: QueryRequest) -> QueryResult:
    self.logger.debug(f"Executing query: {request.query}")
    self.logger.debug(f"Parameters: {request.parameters}")
    
    try:
        result = await super().execute_query(request)
        self.logger.debug(f"Query result: {result.status}")
        return result
    except Exception as e:
        self.logger.error(f"Query failed: {e}")
        raise
```

#### Performance Issues
```python
# Monitor query performance
async def execute_query(self, request: QueryRequest) -> QueryResult:
    start_time = time.time()
    
    result = await super().execute_query(request)
    
    execution_time = time.time() - start_time
    if execution_time > 5.0:  # Log slow queries
        self.logger.warning(f"Slow query detected: {execution_time:.2f}s")
    
    return result
```

### Logging Configuration

```python
import logging

# Configure connector logging
def setup_connector_logging():
    logger = logging.getLogger("smcp.connectors")
    logger.setLevel(logging.INFO)
    
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    return logger
```

### Health Monitoring

```python
async def advanced_health_check(self) -> Dict[str, Any]:
    """Enhanced health check with metrics"""
    basic_health = await self.health_check()
    
    # Add custom metrics
    try:
        query_latency = await self.measure_query_latency()
        connection_count = await self.get_connection_count()
        
        basic_health.update({
            "query_latency_ms": query_latency,
            "active_connections": connection_count,
            "memory_usage": self.get_memory_usage()
        })
        
    except Exception as e:
        basic_health["monitoring_error"] = str(e)
    
    return basic_health
```

## Conclusion

The SMCP Connector Framework provides a powerful, flexible foundation for integrating any data source with the SMCP ecosystem. By following this guide and implementing the required interfaces, you can create robust, secure, and high-performance connectors that seamlessly integrate with the broader SMCP architecture.

For additional support and examples, see:
- [DuckDB Connector Implementation](../connectors/smcp_duckdb_connector.py)
- [Connector Base Framework](../smcp_connector_base.py) 
- [Integration Examples](../examples/)

---
**Author**: SMCP Development Team  
**Version**: 1.0  
**Last Updated**: 2024-08-14