#!/usr/bin/env python3
"""
SCP Server - Configurable reference implementation
Supports configuration via TOML/YAML files, environment variables, and CLI arguments
"""

import asyncio
import logging
import sys
from pathlib import Path
from datetime import datetime
import click

from smcp_config import SMCPConfig, get_server_args, create_default_config
from smcp_server import SMCPServer, tool


def setup_logging(config: SMCPConfig):
    """Setup logging based on configuration"""
    level = getattr(logging, config.logging.level.upper())
    
    handlers = []
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(config.logging.format))
    handlers.append(console_handler)
    
    # File handler if specified
    if config.logging.file:
        file_handler = logging.FileHandler(config.logging.file)
        file_handler.setFormatter(logging.Formatter(config.logging.format))
        handlers.append(file_handler)
    
    logging.basicConfig(
        level=level,
        handlers=handlers,
        format=config.logging.format
    )


def register_default_tools(server: SMCPServer, config: SMCPConfig):
    """Register default tools based on configuration"""
    
    @tool("echo", "Echo back the input", {"message": {"type": "string"}})
    def echo_tool(message: str) -> dict:
        return {
            "echo": message,
            "timestamp": datetime.now().isoformat(),
            "server_id": config.node_id
        }
    
    @tool("config_info", "Get server configuration info", {})
    def config_info() -> dict:
        return {
            "node_id": config.node_id,
            "server": f"{config.server.host}:{config.server.port}",
            "ai_model": config.ai.default_model,
            "max_connections": config.server.max_connections,
            "security_enabled": config.security.require_signature
        }
    
    @tool("uptime", "Get server uptime", {})
    def uptime() -> dict:
        # This would be implemented with actual uptime tracking
        return {
            "message": "Server uptime tracking not implemented yet",
            "timestamp": datetime.now().isoformat()
        }
    
    # Register tools
    for func in [echo_tool, config_info, uptime]:
        if hasattr(func, '_scp_tool'):
            tool_info = func._scp_tool
            server.register_tool(
                tool_info["name"],
                tool_info["description"],
                tool_info["parameters"],
                func
            )


@click.command()
@click.option('--config', '-c', default='scp_config.toml',
              help='Configuration file path (.toml or .yaml)')
@click.option('--create-config', is_flag=True,
              help='Create a default configuration file and exit')
@click.option('--node-id', help='Node identifier')
@click.option('--host', help='Server host to bind to')
@click.option('--port', type=int, help='Server port to bind to')
@click.option('--api-key', help='API key for authentication')
@click.option('--log-level', 
              type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR']),
              help='Logging level')
@click.option('--ollama-url', help='Ollama API URL')
@click.option('--model', help='Default AI model')
@click.option('--no-env', is_flag=True, help='Disable environment variable loading')
@click.option('--validate-only', is_flag=True, help='Validate configuration and exit')
def main(config, create_config, node_id, host, port, api_key, log_level, 
         ollama_url, model, no_env, validate_only):
    """
    SCP Server - Secure Context Protocol Server
    
    Configuration priority (highest to lowest):
    1. Command line arguments
    2. Environment variables (unless --no-env)
    3. Configuration file
    4. Built-in defaults
    
    Environment variables:
    - SCP_NODE_ID: Node identifier
    - SCP_HOST: Server host
    - SCP_PORT: Server port
    - SCP_API_KEY: API key
    - SCP_SECRET_KEY: Secret key for encryption
    - SCP_JWT_SECRET: JWT signing secret
    - SCP_LOG_LEVEL: Logging level
    - SCP_OLLAMA_URL: Ollama API URL
    - SCP_DEFAULT_MODEL: Default AI model
    """
    
    # Create default config if requested
    if create_config:
        create_default_config(config)
        return
    
    try:
        # Create namespace from click options
        class Args:
            pass
        
        args = Args()
        args.node_id = node_id
        args.host = host
        args.port = port
        args.api_key = api_key
        args.log_level = log_level
        args.ollama_url = ollama_url
        args.model = model
        
        # Load configuration with all sources
        scp_config = SCPConfig.load(
            config_file=config if Path(config).exists() else None,
            use_env=not no_env,
            cli_args=args
        )
        
        # Validate configuration
        issues = scp_config.validate()
        if issues:
            click.echo("❌ Configuration validation failed:", err=True)
            for issue in issues:
                click.echo(f"  • {issue}", err=True)
            if not validate_only:
                sys.exit(1)
        
        if validate_only:
            click.echo("✅ Configuration is valid")
            click.echo(f"Node ID: {scp_config.node_id}")
            click.echo(f"Server: {scp_config.server.host}:{scp_config.server.port}")
            click.echo(f"AI Model: {scp_config.ai.default_model}")
            return
        
        # Setup logging
        setup_logging(scp_config)
        logger = logging.getLogger('scp_server_main')
        
        # Display startup info
        click.echo("🚀 Starting SCP Server")
        click.echo("=" * 50)
        click.echo(f"📋 Configuration:")
        click.echo(f"   Node ID: {scp_config.node_id}")
        click.echo(f"   Host: {scp_config.server.host}")
        click.echo(f"   Port: {scp_config.server.port}")
        click.echo(f"   Max Connections: {scp_config.server.max_connections}")
        click.echo(f"   API Key: {scp_config.api_key[:8]}...")
        click.echo(f"   AI Model: {scp_config.ai.default_model}")
        click.echo(f"   Log Level: {scp_config.logging.level}")
        
        if Path(config).exists():
            click.echo(f"   Config File: {config}")
        
        click.echo("=" * 50)
        
        # Create and configure server
        server = SMCPServer(scp_config)
        
        # Register default tools
        register_default_tools(server, scp_config)
        
        # Start server
        logger.info(f"Starting SCP server on {scp_config.server.host}:{scp_config.server.port}")
        asyncio.run(server.start(
            host=scp_config.server.host,
            port=scp_config.server.port
        ))
        
    except KeyboardInterrupt:
        click.echo("\n🛑 Server stopped by user")
    except FileNotFoundError as e:
        click.echo(f"❌ Configuration file not found: {e}", err=True)
        click.echo(f"💡 Create one with: {sys.argv[0]} --create-config", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Server error: {e}", err=True)
        logging.exception("Server startup failed")
        sys.exit(1)


if __name__ == "__main__":
    main()