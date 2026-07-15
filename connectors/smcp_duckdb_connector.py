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
import re
import time
from datetime import datetime
from typing import Dict, List, Any, Optional, Union
from pathlib import Path

# A SQL identifier we are willing to interpolate into a statement. DuckDB cannot
# bind identifiers as parameters, so we allow only a conservative charset.
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# SQL constructs that reach the host filesystem, the network, or the extension
# loader. Raw queries submitted to execute_query are screened for these; touching
# files is only allowed through the confined helper methods (which bind paths
# under data_dir) unless a deployment explicitly opts into raw file SQL.
_FILE_ACCESS_RE = re.compile(
    r"\b("
    r"read_csv|read_csv_auto|read_parquet|read_json|read_json_auto|read_ndjson|"
    r"read_text|read_blob|parquet_scan|csv_scan|glob|"
    r"copy|install|load|attach|"
    r"httpfs|read_json_objects"
    r")\b"
    r"|\b(?:https?|s3|gcs|azure|hf|r2)://",
    re.IGNORECASE,
)

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
        
        # DuckDB-specific configuration.
        # SECURITY: external access lets SQL read/write the host filesystem and
        # fetch remote URLs (read_csv_auto, COPY ... TO, httpfs). It defaults to
        # OFF and must be explicitly opted into per deployment.
        self.enable_external_access = config.connection_params.get("enable_external_access", False)
        # Even when external access is enabled at the engine level, raw queries
        # submitted through execute_query are screened for file/network/extension
        # access so they cannot escape data_dir. Sanctioned file loading goes
        # through the confined helper methods. Set this True to allow arbitrary
        # file SQL on the raw path (implies enable_external_access).
        self.allow_raw_file_sql = config.connection_params.get("allow_raw_file_sql", False)
        self.threads = config.connection_params.get("threads", 4)
        self.memory_limit = config.connection_params.get("memory_limit", "1GB")
        # File operations are confined to this directory (resolved, symlink-safe).
        # Defaults to the current working directory; set "data_dir" to restrict it.
        self.data_dir = Path(config.connection_params.get("data_dir", ".")).resolve()

        self.logger.info(f"Initializing DuckDB connector: {self.database_path}")

    @staticmethod
    def _validate_identifier(name: str) -> str:
        """Return a safe SQL identifier or raise ValueError."""
        if not isinstance(name, str) or not _IDENTIFIER_RE.match(name):
            raise ValueError(f"Invalid table/identifier name: {name!r}")
        return name

    def _validate_file_path(self, file_path: str) -> str:
        """Confine a file path to data_dir (symlink-safe) and require external
        access to be enabled. Returns the resolved absolute path or raises."""
        if not self.enable_external_access:
            raise ValueError(
                "File access is disabled (enable_external_access=False). Refusing "
                "to read/write host files."
            )
        resolved = Path(file_path).resolve()
        if resolved != self.data_dir and self.data_dir not in resolved.parents:
            raise ValueError(f"Path {file_path!r} is outside the allowed data directory")
        return str(resolved)

    def _screen_raw_query(self, query: str) -> None:
        """Reject raw queries that reach the host filesystem, network, or
        extension loader, unless the deployment has opted into raw file SQL.
        Sanctioned file loading goes through the confined helper methods."""
        if self.allow_raw_file_sql:
            return
        if not isinstance(query, str):
            raise ValueError("Query must be a string")
        if _FILE_ACCESS_RE.search(query):
            raise ValueError(
                "Query rejected: file/network/extension access is not permitted "
                "on the raw query path. Load files via bulk_insert_from_file / "
                "create_table_from_file (confined to data_dir), or set "
                "allow_raw_file_sql=True to allow arbitrary file SQL."
            )
    
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
            # SECURITY: DuckDB's engine default for this setting is True, so it
            # MUST be set explicitly on both branches — omitting it leaves the
            # host filesystem/network reachable from SQL. Raw file SQL requires
            # opting into external access too.
            config['enable_external_access'] = bool(
                self.enable_external_access or self.allow_raw_file_sql
            )
            
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

        # SECURITY: screen the raw SQL for host filesystem/network/extension
        # access before it reaches the engine (defense-in-depth on top of the
        # engine-level enable_external_access flag).
        try:
            self._screen_raw_query(request.query)
        except ValueError as e:
            return self.create_error_result(request.query_id, str(e))

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
                columns_result = self.connection.execute("""
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_name = ? AND table_schema = 'main'
                    ORDER BY ordinal_position
                """, [table_name]).fetchall()
                
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
                
                # Get row count for tables (only for well-formed identifiers)
                try:
                    safe_name = self._validate_identifier(table_name)
                    row_count_result = self.connection.execute(f"SELECT COUNT(*) FROM {safe_name}").fetchone()
                    table_info["row_count"] = row_count_result[0] if row_count_result else 0
                except Exception:
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

            # Validate the identifier and confine/parameterize the file path.
            table_name = self._validate_identifier(table_name)
            safe_path = self._validate_file_path(file_path)

            # Auto-detect file format if needed
            if file_format == "auto":
                file_ext = Path(file_path).suffix.lower()
                format_map = {".csv": "csv", ".parquet": "parquet", ".json": "json"}
                file_format = format_map.get(file_ext, "csv")

            # File path is bound as a parameter (no string interpolation).
            reader = {
                "csv": "read_csv_auto", "parquet": "read_parquet", "json": "read_json_auto",
            }.get(file_format)
            if reader is None:
                return self.create_error_result(query_id, f"Unsupported file format: {file_format}")
            query = f"INSERT INTO {table_name} SELECT * FROM {reader}(?)"

            result = self.connection.execute(query, [safe_path])
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

            # Validate the identifier and confine/parameterize the file path.
            table_name = self._validate_identifier(table_name)
            safe_path = self._validate_file_path(file_path)

            # Auto-detect file format if needed
            if file_format == "auto":
                file_ext = Path(file_path).suffix.lower()
                format_map = {".csv": "csv", ".parquet": "parquet", ".json": "json"}
                file_format = format_map.get(file_ext, "csv")

            # File path is bound as a parameter (no string interpolation).
            reader = {
                "csv": "read_csv_auto", "parquet": "read_parquet", "json": "read_json_auto",
            }.get(file_format)
            if reader is None:
                return self.create_error_result(query_id, f"Unsupported file format: {file_format}")
            query = f"CREATE TABLE {table_name} AS SELECT * FROM {reader}(?)"

            result = self.connection.execute(query, [safe_path])
            execution_time = time.time() - start_time

            # Get row count of new table (identifier already validated)
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