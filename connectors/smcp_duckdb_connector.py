#!/usr/bin/env python3
"""
SMCP DuckDB Connector
====================

Native SMCP connector for DuckDB - a high-performance analytical database.

Features:
- High-performance analytical queries
- Supports SQL with advanced analytics functions
- In-memory and persistent database modes
- Parquet, CSV, and JSON file integration
- Vectorized query execution
- ACID transactions

Usage Example:
    config = ConnectorConfig(
        name="analytics_db",
        connector_type=ConnectorType.DATABASE,
        connection_params={"database_path": ":memory:"}
    )
    
    connector = DuckDBConnector(config)
    async with connector:
        result = await connector.execute_query(QueryRequest(
            query_id="test_1",
            query_type=QueryType.SELECT,
            query="SELECT COUNT(*) FROM customers"
        ))
"""

import asyncio
import duckdb
import json
import time
from datetime import datetime
from typing import Dict, List, Any, Optional, Union
from pathlib import Path

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from smcp_connector_base import (
    SMCPConnectorBase, ConnectorConfig, QueryRequest, QueryResult, 
    QueryType, ConnectorType
)

class DuckDBConnector(SMCPConnectorBase):
    """
    SMCP connector for DuckDB databases
    
    Provides high-performance analytical database connectivity with support for:
    - SQL queries with advanced analytics
    - Bulk data loading from files (CSV, Parquet, JSON)
    - In-memory and persistent database modes
    - Vectorized operations for large datasets
    """
    
    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        self.database_path = config.connection_params.get("database_path", ":memory:")
        self.connection = None
        
        # DuckDB-specific configuration
        self.enable_external_access = config.connection_params.get("enable_external_access", True)
        self.threads = config.connection_params.get("threads", 4)
        self.memory_limit = config.connection_params.get("memory_limit", "1GB")
        
        self.logger.info(f"Initializing DuckDB connector: {self.database_path}")
    
    async def connect(self) -> bool:
        """
        Establish connection to DuckDB database
        
        Returns:
            bool: True if connection successful
        """
        try:
            self.logger.info(f"Connecting to DuckDB: {self.database_path}")
            
            # Create DuckDB connection with configuration
            config = {}
            if self.threads > 0:
                config['threads'] = self.threads
            if self.memory_limit:
                config['memory_limit'] = self.memory_limit
            if self.enable_external_access:
                config['enable_external_access'] = True
            
            self.connection = duckdb.connect(
                database=self.database_path,
                read_only=False,
                config=config
            )
            
            # Test the connection
            self.connection.execute("SELECT 1 as test")
            
            self.is_connected = True
            self.logger.info("Successfully connected to DuckDB")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to connect to DuckDB: {e}")
            self.is_connected = False
            return False
    
    async def disconnect(self) -> bool:
        """
        Close DuckDB connection
        
        Returns:
            bool: True if disconnection successful
        """
        try:
            if self.connection:
                self.connection.close()
                self.connection = None
            
            self.is_connected = False
            self.logger.info("Disconnected from DuckDB")
            return True
            
        except Exception as e:
            self.logger.error(f"Error disconnecting from DuckDB: {e}")
            return False
    
    async def execute_query(self, request: QueryRequest) -> QueryResult:
        """
        Execute SQL query on DuckDB
        
        Args:
            request: QueryRequest containing SQL query and parameters
            
        Returns:
            QueryResult with query results
        """
        start_time = time.time()
        
        # Validate request
        if not self.validate_query_request(request):
            return self.create_error_result(request.query_id, "Invalid query request")
        
        if not self.is_connected:
            return self.create_error_result(request.query_id, "Not connected to database")
        
        try:
            self.logger.debug(f"Executing query {request.query_id}: {request.query[:100]}...")
            
            # Handle parameterized queries
            if request.parameters:
                # DuckDB supports parameterized queries with $1, $2, etc.
                result = self.connection.execute(request.query, list(request.parameters.values()))
            else:
                result = self.connection.execute(request.query)
            
            execution_time = time.time() - start_time
            
            # Handle different query types
            if request.query_type in [QueryType.SELECT, QueryType.CUSTOM]:
                # Fetch results for SELECT queries
                rows = result.fetchall()
                columns = [desc[0] for desc in result.description] if result.description else []
                
                # Convert to list of dictionaries for easier consumption
                data = []
                if rows and columns:
                    data = [dict(zip(columns, row)) for row in rows]
                
                return QueryResult(
                    query_id=request.query_id,
                    status="success",
                    data=data,
                    columns=columns,
                    row_count=len(rows),
                    execution_time=execution_time,
                    metadata={
                        "connector_id": self.connector_id,
                        "database_path": self.database_path,
                        "query_type": request.query_type.value,
                        "timestamp": datetime.now().isoformat()
                    }
                )
            else:
                # For INSERT, UPDATE, DELETE operations
                row_count = result.rowcount if hasattr(result, 'rowcount') else 0
                
                return QueryResult(
                    query_id=request.query_id,
                    status="success",
                    data=None,
                    columns=None,
                    row_count=row_count,
                    execution_time=execution_time,
                    metadata={
                        "connector_id": self.connector_id,
                        "database_path": self.database_path,
                        "query_type": request.query_type.value,
                        "rows_affected": row_count,
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
    
    async def get_schema(self) -> Dict[str, Any]:
        """
        Get database schema information
        
        Returns:
            Dict containing schema metadata
        """
        if not self.is_connected:
            return {"error": "Not connected to database"}
        
        try:
            # Get all tables
            tables_result = self.connection.execute("""
                SELECT table_name, table_type 
                FROM information_schema.tables 
                WHERE table_schema = 'main'
                ORDER BY table_name
            """).fetchall()
            
            schema = {
                "database_path": self.database_path,
                "tables": [],
                "table_count": len(tables_result),
                "timestamp": datetime.now().isoformat()
            }
            
            # Get detailed info for each table
            for table_name, table_type in tables_result:
                # Get column information
                columns_result = self.connection.execute(f"""
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns 
                    WHERE table_name = '{table_name}' AND table_schema = 'main'
                    ORDER BY ordinal_position
                """).fetchall()
                
                table_info = {
                    "name": table_name,
                    "type": table_type,
                    "columns": [
                        {
                            "name": col_name,
                            "type": data_type,
                            "nullable": is_nullable == "YES"
                        }
                        for col_name, data_type, is_nullable in columns_result
                    ],
                    "column_count": len(columns_result)
                }
                
                # Get row count for tables
                try:
                    row_count_result = self.connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
                    table_info["row_count"] = row_count_result[0] if row_count_result else 0
                except:
                    table_info["row_count"] = None
                
                schema["tables"].append(table_info)
            
            return schema
            
        except Exception as e:
            self.logger.error(f"Failed to get schema: {e}")
            return {"error": f"Failed to get schema: {str(e)}"}
    
    async def test_connection(self) -> bool:
        """
        Test DuckDB connection with a simple query
        
        Returns:
            bool: True if test successful
        """
        try:
            if not self.is_connected:
                return False
            
            result = self.connection.execute("SELECT 1 as health_check").fetchone()
            return result[0] == 1
            
        except Exception as e:
            self.logger.error(f"Connection test failed: {e}")
            return False
    
    async def bulk_insert_from_file(self, table_name: str, file_path: str, file_format: str = "auto") -> QueryResult:
        """
        Bulk insert data from file (CSV, Parquet, JSON)
        
        Args:
            table_name: Target table name
            file_path: Path to the data file
            file_format: File format (auto, csv, parquet, json)
            
        Returns:
            QueryResult with operation status
        """
        query_id = f"bulk_insert_{int(time.time())}"
        
        if not self.is_connected:
            return self.create_error_result(query_id, "Not connected to database")
        
        try:
            start_time = time.time()
            
            # Auto-detect file format if needed
            if file_format == "auto":
                file_ext = Path(file_path).suffix.lower()
                format_map = {".csv": "csv", ".parquet": "parquet", ".json": "json"}
                file_format = format_map.get(file_ext, "csv")
            
            # Build appropriate query based on file format
            if file_format == "csv":
                query = f"INSERT INTO {table_name} SELECT * FROM read_csv_auto('{file_path}')"
            elif file_format == "parquet":
                query = f"INSERT INTO {table_name} SELECT * FROM read_parquet('{file_path}')"
            elif file_format == "json":
                query = f"INSERT INTO {table_name} SELECT * FROM read_json_auto('{file_path}')"
            else:
                return self.create_error_result(query_id, f"Unsupported file format: {file_format}")
            
            result = self.connection.execute(query)
            execution_time = time.time() - start_time
            row_count = result.rowcount if hasattr(result, 'rowcount') else 0
            
            return QueryResult(
                query_id=query_id,
                status="success",
                row_count=row_count,
                execution_time=execution_time,
                metadata={
                    "connector_id": self.connector_id,
                    "operation": "bulk_insert_from_file",
                    "file_path": file_path,
                    "file_format": file_format,
                    "table_name": table_name,
                    "rows_inserted": row_count,
                    "timestamp": datetime.now().isoformat()
                }
            )
            
        except Exception as e:
            error_msg = f"Bulk insert failed: {str(e)}"
            self.logger.error(f"Bulk insert from {file_path} failed: {e}")
            return self.create_error_result(query_id, error_msg)
    
    async def create_table_from_file(self, table_name: str, file_path: str, file_format: str = "auto") -> QueryResult:
        """
        Create table and import data from file in one operation
        
        Args:
            table_name: New table name
            file_path: Path to the data file
            file_format: File format (auto, csv, parquet, json)
            
        Returns:
            QueryResult with operation status
        """
        query_id = f"create_table_from_file_{int(time.time())}"
        
        if not self.is_connected:
            return self.create_error_result(query_id, "Not connected to database")
        
        try:
            start_time = time.time()
            
            # Auto-detect file format if needed
            if file_format == "auto":
                file_ext = Path(file_path).suffix.lower()
                format_map = {".csv": "csv", ".parquet": "parquet", ".json": "json"}
                file_format = format_map.get(file_ext, "csv")
            
            # Build appropriate query based on file format
            if file_format == "csv":
                query = f"CREATE TABLE {table_name} AS SELECT * FROM read_csv_auto('{file_path}')"
            elif file_format == "parquet":
                query = f"CREATE TABLE {table_name} AS SELECT * FROM read_parquet('{file_path}')"
            elif file_format == "json":
                query = f"CREATE TABLE {table_name} AS SELECT * FROM read_json_auto('{file_path}')"
            else:
                return self.create_error_result(query_id, f"Unsupported file format: {file_format}")
            
            result = self.connection.execute(query)
            execution_time = time.time() - start_time
            
            # Get row count of new table
            row_count_result = self.connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
            row_count = row_count_result[0] if row_count_result else 0
            
            return QueryResult(
                query_id=query_id,
                status="success",
                row_count=row_count,
                execution_time=execution_time,
                metadata={
                    "connector_id": self.connector_id,
                    "operation": "create_table_from_file",
                    "file_path": file_path,
                    "file_format": file_format,
                    "table_name": table_name,
                    "rows_imported": row_count,
                    "timestamp": datetime.now().isoformat()
                }
            )
            
        except Exception as e:
            error_msg = f"Create table from file failed: {str(e)}"
            self.logger.error(f"Create table {table_name} from {file_path} failed: {e}")
            return self.create_error_result(query_id, error_msg)

# Convenience functions for common DuckDB operations

async def create_duckdb_connector(database_path: str = ":memory:", **kwargs) -> DuckDBConnector:
    """
    Create and connect a DuckDB connector with common configuration
    
    Args:
        database_path: Path to DuckDB file or ":memory:" for in-memory
        **kwargs: Additional connection parameters
        
    Returns:
        Connected DuckDBConnector instance
    """
    config = ConnectorConfig(
        name=f"duckdb_{int(time.time())}",
        connector_type=ConnectorType.DATABASE,
        connection_params={
            "database_path": database_path,
            **kwargs
        }
    )
    
    connector = DuckDBConnector(config)
    await connector.connect()
    return connector