#!/usr/bin/env python3
"""
SCP Client - Configurable reference implementation
Supports configuration via TOML/YAML files, environment variables, and CLI arguments
"""

import asyncio
import logging
import sys
import json
from pathlib import Path
from datetime import datetime
import click

from smcp_config import SMCPConfig, get_client_args, create_default_config
from smcp_client import SMCPClient, scp_client


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


async def run_interactive_session(client: SMCPClient, config: SMCPConfig):
    """Run interactive client session"""
    click.echo("\n🎮 Interactive Mode")
    click.echo("Type 'help' for commands, 'quit' to exit")
    click.echo("-" * 40)
    
    capabilities = client.list_capabilities()
    
    while True:
        try:
            command = input("\nscp> ").strip()
            
            if not command:
                continue
            
            if command.lower() in ['quit', 'exit']:
                break
            
            if command.lower() == 'help':
                click.echo("Available commands:")
                click.echo("  help                 - Show this help")
                click.echo("  list                 - List available tools")
                click.echo("  info <tool>          - Show tool info")
                click.echo("  call <tool> [args]   - Call a tool")
                click.echo("  ai <prompt>          - Chat with AI")
                click.echo("  quit/exit           - Exit interactive mode")
                continue
            
            if command.lower() == 'list':
                click.echo("Available tools:")
                for name, cap in capabilities.items():
                    click.echo(f"  • {name}: {cap['description']}")
                continue
            
            if command.startswith('info '):
                tool_name = command[5:].strip()
                if tool_name in capabilities:
                    cap = capabilities[tool_name]
                    click.echo(f"Tool: {cap['name']}")
                    click.echo(f"Description: {cap['description']}")
                    if cap['parameters']:
                        click.echo("Parameters:")
                        for param, info in cap['parameters'].items():
                            click.echo(f"  • {param}: {info}")
                else:
                    click.echo(f"Tool '{tool_name}' not found")
                continue
            
            if command.startswith('call '):
                parts = command[5:].split()
                if not parts:
                    click.echo("Usage: call <tool> [key=value ...]")
                    continue
                
                tool_name = parts[0]
                params = {}
                
                # Parse key=value parameters
                for part in parts[1:]:
                    if '=' in part:
                        key, value = part.split('=', 1)
                        # Try to parse as JSON, fallback to string
                        try:
                            params[key] = json.loads(value)
                        except:
                            params[key] = value
                
                try:
                    result = await client.invoke_tool(tool_name, **params)
                    click.echo(f"Result: {result}")
                except Exception as e:
                    click.echo(f"Error: {e}")
                continue
            
            if command.startswith('ai '):
                prompt = command[3:].strip()
                if 'ai_chat' in capabilities:
                    try:
                        response = await client.chat_with_ai(prompt, model=config.ai.default_model)
                        click.echo(f"AI: {response}")
                    except Exception as e:
                        click.echo(f"AI Error: {e}")
                else:
                    click.echo("AI chat not available on this server")
                continue
            
            click.echo(f"Unknown command: {command}")
            click.echo("Type 'help' for available commands")
            
        except KeyboardInterrupt:
            click.echo("\nUse 'quit' to exit")
        except Exception as e:
            click.echo(f"Error: {e}")


async def run_batch_commands(client: SMCPClient, commands: list):
    """Run batch commands"""
    results = []
    
    for i, cmd in enumerate(commands, 1):
        click.echo(f"[{i}/{len(commands)}] Executing: {cmd['tool']}")
        
        try:
            result = await client.invoke_tool(cmd['tool'], **cmd.get('parameters', {}))
            results.append({
                'command': cmd,
                'result': result,
                'success': True
            })
            click.echo(f"✅ Success: {result}")
        except Exception as e:
            results.append({
                'command': cmd,
                'error': str(e),
                'success': False
            })
            click.echo(f"❌ Error: {e}")
    
    return results


async def run_demo_tests(client: SMCPClient, config: SMCPConfig):
    """Run demonstration tests"""
    click.echo("\n🧪 Running Demo Tests")
    click.echo("=" * 30)
    
    capabilities = client.list_capabilities()
    click.echo(f"📋 Available tools: {', '.join(capabilities.keys())}")
    
    # Test basic tools
    test_commands = [
        {"tool": "calculator", "parameters": {"operation": "add", "a": 15, "b": 27}},
        {"tool": "system_info", "parameters": {}},
    ]
    
    # Add custom tools if available
    if "echo" in capabilities:
        test_commands.append({"tool": "echo", "parameters": {"message": "Hello SCP!"}})
    
    if "config_info" in capabilities:
        test_commands.append({"tool": "config_info", "parameters": {}})
    
    # Test AI if available
    if "ai_chat" in capabilities:
        test_commands.append({
            "tool": "ai_chat", 
            "parameters": {
                "prompt": "What is 2+2?", 
                "model": config.ai.default_model
            }
        })
    
    results = await run_batch_commands(client, test_commands)
    
    # Summary
    successful = sum(1 for r in results if r['success'])
    click.echo(f"\n📊 Test Results: {successful}/{len(results)} successful")
    
    return results


@click.command()
@click.option('--config', '-c', default='scp_config.toml',
              help='Configuration file path (.toml or .yaml)')
@click.option('--create-config', is_flag=True,
              help='Create a default configuration file and exit')
@click.option('--node-id', help='Node identifier')
@click.option('--server-url', help='Server WebSocket URL')
@click.option('--api-key', help='API key for authentication')
@click.option('--timeout', type=int, help='Connection timeout in seconds')
@click.option('--retries', type=int, help='Maximum connection retries')
@click.option('--log-level', 
              type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR']),
              help='Logging level')
@click.option('--no-env', is_flag=True, help='Disable environment variable loading')
@click.option('--validate-only', is_flag=True, help='Validate configuration and exit')
@click.option('--mode', '-m', 
              type=click.Choice(['interactive', 'demo', 'batch']),
              default='demo',
              help='Client mode: interactive, demo, or batch')
@click.option('--batch-file', help='JSON file with batch commands')
@click.option('--tool', help='Single tool to invoke')
@click.option('--params', help='Tool parameters as JSON string')
@click.option('--ai-prompt', help='Send prompt to AI and exit')
def main(config, create_config, node_id, server_url, api_key, timeout, retries,
         log_level, no_env, validate_only, mode, batch_file, tool, params, ai_prompt):
    """
    SCP Client - Secure Context Protocol Client
    
    Configuration priority (highest to lowest):
    1. Command line arguments
    2. Environment variables (unless --no-env)
    3. Configuration file
    4. Built-in defaults
    
    Environment variables:
    - SCP_NODE_ID: Node identifier
    - SCP_SERVER_URL: Server WebSocket URL
    - SCP_API_KEY: API key
    - SCP_SECRET_KEY: Secret key for encryption
    - SCP_JWT_SECRET: JWT signing secret
    - SCP_LOG_LEVEL: Logging level
    - SCP_TIMEOUT: Connection timeout
    - SCP_MAX_RETRIES: Maximum retries
    
    Examples:
    - Interactive mode: scp-client --mode interactive
    - Single tool: scp-client --tool calculator --params '{"operation":"add","a":5,"b":3}'
    - AI chat: scp-client --ai-prompt "What is Python?"
    - Demo tests: scp-client --mode demo
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
        args.server_url = server_url
        args.api_key = api_key
        args.timeout = timeout
        args.retries = retries
        args.log_level = log_level
        
        # Load configuration
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
            click.echo(f"Server URL: {scp_config.server_url}")
            return
        
        # Setup logging
        setup_logging(scp_config)
        
        # Display startup info
        click.echo("📱 Starting SCP Client")
        click.echo("=" * 50)
        click.echo(f"📋 Configuration:")
        click.echo(f"   Node ID: {scp_config.node_id}")
        click.echo(f"   Server URL: {scp_config.server_url}")
        click.echo(f"   Timeout: {scp_config.client.timeout}s")
        click.echo(f"   Max Retries: {scp_config.client.max_retries}")
        click.echo(f"   AI Model: {scp_config.ai.default_model}")
        
        if Path(config).exists():
            click.echo(f"   Config File: {config}")
        
        click.echo("=" * 50)
        
        # Run the client
        asyncio.run(run_client(scp_config, mode, batch_file, tool, params, ai_prompt))
        
    except KeyboardInterrupt:
        click.echo("\n🛑 Client stopped by user")
    except Exception as e:
        click.echo(f"❌ Client error: {e}", err=True)
        logging.exception("Client error")
        sys.exit(1)


async def run_client(config: SCPConfig, mode: str, batch_file: str, 
                    tool: str, params: str, ai_prompt: str):
    """Run the client with specified mode"""
    
    async with scp_client(config) as client:
        click.echo("✅ Connected to SCP server")
        
        # Single tool invocation
        if tool:
            try:
                tool_params = json.loads(params) if params else {}
                result = await client.invoke_tool(tool, **tool_params)
                click.echo(f"Result: {result}")
            except Exception as e:
                click.echo(f"Error: {e}")
            return
        
        # AI prompt
        if ai_prompt:
            try:
                response = await client.chat_with_ai(ai_prompt, model=config.ai.default_model)
                click.echo(f"AI: {response}")
            except Exception as e:
                click.echo(f"AI Error: {e}")
            return
        
        # Batch mode
        if mode == 'batch':
            if not batch_file:
                click.echo("❌ Batch mode requires --batch-file", err=True)
                return
            
            try:
                with open(batch_file, 'r') as f:
                    commands = json.load(f)
                await run_batch_commands(client, commands)
            except Exception as e:
                click.echo(f"❌ Batch execution failed: {e}", err=True)
            return
        
        # Demo mode
        if mode == 'demo':
            await run_demo_tests(client, config)
            return
        
        # Interactive mode
        if mode == 'interactive':
            await run_interactive_session(client, config)
            return
        
        click.echo(f"❌ Unknown mode: {mode}")


if __name__ == "__main__":
    main()