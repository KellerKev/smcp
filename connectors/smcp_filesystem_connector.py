#!/usr/bin/env python3
"""
SMCP Filesystem Connector
=========================

Native SMCP connector for local filesystem operations - file reading, writing, and management.

Features:
- Secure file operations with path validation
- Support for multiple file formats (txt, json, csv, md, etc.)
- Directory management and recursive operations
- File metadata and permissions handling
- Integration with SMCP security framework

Usage Example:
    config = ConnectorConfig(
        name="local_filesystem",
        connector_type=ConnectorType.FILE,
        connection_params={"base_path": "/secure/data", "create_dirs": True}
    )
    
    connector = FilesystemConnector(config)
    async with connector:
        result = await connector.write_file(
            file_path="reports/analysis_2024.md",
            content="# Business Analysis Report...",
            file_format="markdown"
        )
"""

import asyncio
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Union

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from smcp_connector_base import (
    SMCPConnectorBase, ConnectorConfig, QueryRequest, QueryResult, 
    QueryType, ConnectorType
)

class FilesystemConnector(SMCPConnectorBase):
    """
    SMCP connector for local filesystem operations
    
    Provides secure file system connectivity with support for:
    - File reading and writing with format detection
    - Directory management and creation  
    - Path validation and security checks
    - Metadata extraction and file operations
    """
    
    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        self.base_path = Path(config.connection_params.get("base_path", "./data"))
        self.create_dirs = config.connection_params.get("create_dirs", True)
        self.allowed_extensions = config.connection_params.get(
            "allowed_extensions", 
            [".txt", ".md", ".json", ".csv", ".yaml", ".yml", ".html", ".xml"]
        )
        self.max_file_size = config.connection_params.get("max_file_size", 50 * 1024 * 1024)  # 50MB
        
        self.logger.info(f"Initializing filesystem connector: {self.base_path}")
    
    async def connect(self) -> bool:
        """
        Establish connection to filesystem (validate base path)
        
        Returns:
            bool: True if connection successful
        """
        try:
            self.logger.info(f"Connecting to filesystem: {self.base_path}")
            
            # Create base directory if needed
            if self.create_dirs and not self.base_path.exists():
                self.base_path.mkdir(parents=True, exist_ok=True)
                self.logger.info(f"Created base directory: {self.base_path}")
            
            # Validate base path exists and is accessible
            if not self.base_path.exists():
                raise Exception(f"Base path does not exist: {self.base_path}")
            
            if not os.access(self.base_path, os.R_OK | os.W_OK):
                raise Exception(f"No read/write access to base path: {self.base_path}")
            
            self.is_connected = True
            self.logger.info("Successfully connected to filesystem")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to connect to filesystem: {e}")
            self.is_connected = False
            return False
    
    async def disconnect(self) -> bool:
        """
        Close filesystem connection
        
        Returns:
            bool: True if disconnection successful
        """
        try:
            self.is_connected = False
            self.logger.info("Disconnected from filesystem")
            return True
            
        except Exception as e:
            self.logger.error(f"Error disconnecting from filesystem: {e}")
            return False
    
    async def execute_query(self, request: QueryRequest) -> QueryResult:
        """
        Execute filesystem operation
        
        Args:
            request: QueryRequest containing operation and parameters
            
        Returns:
            QueryResult with operation results
        """
        start_time = time.time()
        
        # Validate request
        if not self.validate_query_request(request):
            return self.create_error_result(request.query_id, "Invalid query request")
        
        if not self.is_connected:
            return self.create_error_result(request.query_id, "Not connected to filesystem")
        
        try:
            self.logger.debug(f"Executing filesystem operation {request.query_id}: {request.query_type}")
            
            # Parse operation from query
            operation = request.query.strip().upper()
            params = request.parameters or {}
            
            if operation == "WRITE_FILE" or request.query_type == QueryType.INSERT:
                result = await self._write_file(params)
            elif operation == "READ_FILE" or request.query_type == QueryType.SELECT:
                result = await self._read_file(params)
            elif operation == "LIST_FILES":
                result = await self._list_files(params)
            elif operation == "DELETE_FILE" or request.query_type == QueryType.DELETE:
                result = await self._delete_file(params)
            elif operation == "CREATE_DIRECTORY":
                result = await self._create_directory(params)
            elif operation == "FILE_EXISTS":
                result = await self._file_exists(params)
            else:
                return self.create_error_result(
                    request.query_id, 
                    f"Unsupported filesystem operation: {operation}"
                )
            
            execution_time = time.time() - start_time
            
            return QueryResult(
                query_id=request.query_id,
                status="success",
                data=result.get("data"),
                columns=result.get("columns"),
                row_count=result.get("row_count", 0),
                execution_time=execution_time,
                metadata={
                    "connector_id": self.connector_id,
                    "base_path": str(self.base_path),
                    "operation": operation,
                    "timestamp": datetime.now().isoformat(),
                    **result.get("metadata", {})
                }
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"Filesystem operation failed: {str(e)}"
            self.logger.error(f"Operation {request.query_id} failed: {e}")
            
            result = self.create_error_result(request.query_id, error_msg)
            result.execution_time = execution_time
            return result
    
    async def get_schema(self) -> Dict[str, Any]:
        """
        Get filesystem schema information
        
        Returns:
            Dict containing schema metadata
        """
        if not self.is_connected:
            return {"error": "Not connected to filesystem"}
        
        try:
            # Get directory structure
            directories = []
            files = []
            
            if self.base_path.exists():
                for item in self.base_path.rglob("*"):
                    relative_path = item.relative_to(self.base_path)
                    if item.is_dir():
                        directories.append({
                            "path": str(relative_path),
                            "full_path": str(item),
                            "created": item.stat().st_ctime,
                            "modified": item.stat().st_mtime
                        })
                    elif item.is_file():
                        files.append({
                            "path": str(relative_path),
                            "full_path": str(item),
                            "size": item.stat().st_size,
                            "extension": item.suffix,
                            "created": item.stat().st_ctime,
                            "modified": item.stat().st_mtime
                        })
            
            return {
                "base_path": str(self.base_path),
                "directories": directories,
                "files": files,
                "directory_count": len(directories),
                "file_count": len(files),
                "total_size": sum(f["size"] for f in files),
                "allowed_extensions": self.allowed_extensions,
                "max_file_size": self.max_file_size,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get filesystem schema: {e}")
            return {"error": f"Failed to get schema: {str(e)}"}
    
    async def write_file(self, file_path: str, content: str, file_format: str = "auto") -> QueryResult:
        """
        Write file with content
        
        Args:
            file_path: Relative path to file
            content: File content
            file_format: File format (auto-detect if "auto")
            
        Returns:
            QueryResult with write status
        """
        query_id = f"write_file_{int(time.time())}"
        
        params = {
            "file_path": file_path,
            "content": content,
            "file_format": file_format
        }
        
        request = QueryRequest(
            query_id=query_id,
            query_type=QueryType.INSERT,
            query="WRITE_FILE",
            parameters=params
        )
        
        return await self.execute_query(request)
    
    async def read_file(self, file_path: str, encoding: str = "utf-8") -> QueryResult:
        """
        Read file content
        
        Args:
            file_path: Relative path to file
            encoding: File encoding
            
        Returns:
            QueryResult with file content
        """
        query_id = f"read_file_{int(time.time())}"
        
        params = {
            "file_path": file_path,
            "encoding": encoding
        }
        
        request = QueryRequest(
            query_id=query_id,
            query_type=QueryType.SELECT,
            query="READ_FILE",
            parameters=params
        )
        
        return await self.execute_query(request)
    
    async def _write_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Write file implementation"""
        file_path = params.get("file_path")
        content = params.get("content", "")
        file_format = params.get("file_format", "auto")
        encoding = params.get("encoding", "utf-8")
        
        if not file_path:
            raise Exception("file_path parameter is required")
        
        # Validate and resolve path
        full_path = await self._resolve_path(file_path)
        
        # Auto-detect format
        if file_format == "auto":
            file_format = full_path.suffix.lower() or ".txt"
        
        # Validate file extension
        if file_format not in self.allowed_extensions and f".{file_format}" not in self.allowed_extensions:
            raise Exception(f"File format not allowed: {file_format}")
        
        # Create parent directories
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write file
        if isinstance(content, (dict, list)):
            # JSON content
            with open(full_path, 'w', encoding=encoding) as f:
                json.dump(content, f, indent=2, ensure_ascii=False)
        else:
            # Text content
            with open(full_path, 'w', encoding=encoding) as f:
                f.write(str(content))
        
        # Get file stats
        stats = full_path.stat()
        
        return {
            "data": [{
                "file_path": str(full_path.relative_to(self.base_path)),
                "full_path": str(full_path),
                "size": stats.st_size,
                "created": datetime.fromtimestamp(stats.st_ctime).isoformat(),
                "modified": datetime.fromtimestamp(stats.st_mtime).isoformat(),
                "status": "written"
            }],
            "columns": ["file_path", "full_path", "size", "created", "modified", "status"],
            "row_count": 1,
            "metadata": {
                "operation": "write_file",
                "file_format": file_format,
                "encoding": encoding,
                "bytes_written": stats.st_size
            }
        }
    
    async def _read_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Read file implementation"""
        file_path = params.get("file_path")
        encoding = params.get("encoding", "utf-8")
        
        if not file_path:
            raise Exception("file_path parameter is required")
        
        # Validate and resolve path
        full_path = await self._resolve_path(file_path)
        
        if not full_path.exists():
            raise Exception(f"File does not exist: {file_path}")
        
        if not full_path.is_file():
            raise Exception(f"Path is not a file: {file_path}")
        
        # Check file size
        stats = full_path.stat()
        if stats.st_size > self.max_file_size:
            raise Exception(f"File too large: {stats.st_size} bytes (max: {self.max_file_size})")
        
        # Read file content
        try:
            if full_path.suffix.lower() == ".json":
                with open(full_path, 'r', encoding=encoding) as f:
                    content = json.load(f)
            else:
                with open(full_path, 'r', encoding=encoding) as f:
                    content = f.read()
        except UnicodeDecodeError:
            # Try binary read if text fails
            with open(full_path, 'rb') as f:
                content = f.read().decode('utf-8', errors='replace')
        
        return {
            "data": [{
                "file_path": str(full_path.relative_to(self.base_path)),
                "full_path": str(full_path),
                "content": content,
                "size": stats.st_size,
                "extension": full_path.suffix,
                "created": datetime.fromtimestamp(stats.st_ctime).isoformat(),
                "modified": datetime.fromtimestamp(stats.st_mtime).isoformat()
            }],
            "columns": ["file_path", "full_path", "content", "size", "extension", "created", "modified"],
            "row_count": 1,
            "metadata": {
                "operation": "read_file",
                "encoding": encoding,
                "bytes_read": stats.st_size
            }
        }
    
    async def _list_files(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List files implementation"""
        directory = params.get("directory", ".")
        pattern = params.get("pattern", "*")
        recursive = params.get("recursive", False)
        
        # Resolve directory path
        dir_path = await self._resolve_path(directory)
        
        if not dir_path.exists():
            raise Exception(f"Directory does not exist: {directory}")
        
        if not dir_path.is_dir():
            raise Exception(f"Path is not a directory: {directory}")
        
        # List files
        files = []
        if recursive:
            file_paths = dir_path.rglob(pattern)
        else:
            file_paths = dir_path.glob(pattern)
        
        for file_path in file_paths:
            if file_path.is_file():
                stats = file_path.stat()
                files.append({
                    "file_path": str(file_path.relative_to(self.base_path)),
                    "full_path": str(file_path),
                    "name": file_path.name,
                    "size": stats.st_size,
                    "extension": file_path.suffix,
                    "created": datetime.fromtimestamp(stats.st_ctime).isoformat(),
                    "modified": datetime.fromtimestamp(stats.st_mtime).isoformat()
                })
        
        return {
            "data": files,
            "columns": ["file_path", "full_path", "name", "size", "extension", "created", "modified"],
            "row_count": len(files),
            "metadata": {
                "operation": "list_files",
                "directory": directory,
                "pattern": pattern,
                "recursive": recursive
            }
        }
    
    async def _delete_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Delete file implementation"""
        file_path = params.get("file_path")
        
        if not file_path:
            raise Exception("file_path parameter is required")
        
        # Validate and resolve path
        full_path = await self._resolve_path(file_path)
        
        if not full_path.exists():
            raise Exception(f"File does not exist: {file_path}")
        
        # Delete file
        full_path.unlink()
        
        return {
            "data": [{
                "file_path": file_path,
                "status": "deleted"
            }],
            "columns": ["file_path", "status"],
            "row_count": 1,
            "metadata": {
                "operation": "delete_file"
            }
        }
    
    async def _create_directory(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create directory implementation"""
        directory = params.get("directory")
        parents = params.get("parents", True)
        
        if not directory:
            raise Exception("directory parameter is required")
        
        # Validate and resolve path
        dir_path = await self._resolve_path(directory)
        
        # Create directory
        dir_path.mkdir(parents=parents, exist_ok=True)
        
        return {
            "data": [{
                "directory": str(dir_path.relative_to(self.base_path)),
                "full_path": str(dir_path),
                "status": "created"
            }],
            "columns": ["directory", "full_path", "status"],
            "row_count": 1,
            "metadata": {
                "operation": "create_directory",
                "parents": parents
            }
        }
    
    async def _file_exists(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Check file existence implementation"""
        file_path = params.get("file_path")
        
        if not file_path:
            raise Exception("file_path parameter is required")
        
        # Validate and resolve path
        full_path = await self._resolve_path(file_path)
        
        exists = full_path.exists()
        is_file = full_path.is_file() if exists else False
        is_dir = full_path.is_dir() if exists else False
        
        return {
            "data": [{
                "file_path": file_path,
                "exists": exists,
                "is_file": is_file,
                "is_directory": is_dir
            }],
            "columns": ["file_path", "exists", "is_file", "is_directory"],
            "row_count": 1,
            "metadata": {
                "operation": "file_exists"
            }
        }
    
    async def _resolve_path(self, file_path: str) -> Path:
        """Resolve and validate file path"""
        # Convert to Path and resolve relative to base_path
        path = Path(file_path)
        
        # Prevent path traversal attacks
        if path.is_absolute():
            raise Exception("Absolute paths not allowed")
        
        if ".." in path.parts:
            raise Exception("Parent directory references not allowed")
        
        # Resolve full path
        full_path = (self.base_path / path).resolve()
        
        # Ensure path is within base_path
        if not str(full_path).startswith(str(self.base_path.resolve())):
            raise Exception("Path outside base directory not allowed")
        
        return full_path

# Convenience function for common filesystem operations
async def create_filesystem_connector(base_path: str = "./data", **kwargs) -> FilesystemConnector:
    """
    Create and connect a filesystem connector with common configuration
    
    Args:
        base_path: Base directory for filesystem operations
        **kwargs: Additional connection parameters
        
    Returns:
        Connected FilesystemConnector instance
    """
    config = ConnectorConfig(
        name=f"filesystem_{int(time.time())}",
        connector_type=ConnectorType.FILE,
        connection_params={
            "base_path": base_path,
            "create_dirs": True,
            **kwargs
        }
    )
    
    connector = FilesystemConnector(config)
    await connector.connect()
    return connector