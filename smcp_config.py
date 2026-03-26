#!/usr/bin/env python3
"""
SCP Configuration System - Supports TOML, YAML, environment variables, and CLI args
"""

import os
import sys
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from pathlib import Path
import argparse

try:
    import tomli
    import tomli_w
except ImportError:
    tomli = None
    tomli_w = None

try:
    import yaml
except ImportError:
    yaml = None


@dataclass
class ServerConfig:
    """Server-specific configuration"""
    host: str = "localhost"
    port: int = 8765
    max_connections: int = 100
    ping_interval: int = 20
    ping_timeout: int = 10


@dataclass
class ClientConfig:
    """Client-specific configuration"""
    auto_reconnect: bool = True
    reconnect_delay: int = 5
    max_retries: int = 3
    timeout: int = 30
    heartbeat_interval: int = 30


@dataclass
class OAuth2Config:
    """OAuth2 authentication configuration"""
    enabled: bool = False
    token_url: Optional[str] = None
    jwks_url: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    scope: str = "scp:read scp:write"
    # Simplified mode: use local public key instead of JWKS URL
    local_public_key_path: Optional[str] = None


@dataclass
class CryptoConfig:
    """Cryptographic configuration"""
    key_exchange: str = "static"  # "static", "ecdh", "rsa"
    perfect_forward_secrecy: bool = False
    certificate_path: Optional[str] = None
    private_key_path: Optional[str] = None
    # Enterprise mode
    ca_certificate_path: Optional[str] = None
    # Simplified mode
    use_self_signed: bool = True


@dataclass
class ClusterConfig:
    """Cluster and distributed configuration"""
    enabled: bool = False
    discovery_method: str = "static"  # "static", "consul", "etcd", "dns"
    nodes: List[Dict[str, Any]] = field(default_factory=list)
    # Simplified mode: simulate multi-server on localhost
    simulate_distributed: bool = False
    simulate_ports: List[int] = field(default_factory=lambda: [8765, 8766, 8767])


@dataclass
class AIConfig:
    """AI integration configuration"""
    ollama_url: str = "http://localhost:11434"
    default_model: str = "tinyllama:latest"
    timeout: int = 30
    max_tokens: int = 1000
    # Distributed AI configuration
    model_routing: Dict[str, List[str]] = field(default_factory=dict)
    load_balancing: str = "round_robin"  # "round_robin", "least_loaded", "random"


@dataclass
class SecurityConfig:
    """Security configuration"""
    require_signature: bool = True
    max_message_size: int = 1048576  # 1MB
    token_expiry: int = 3600  # 1 hour
    rate_limit: int = 100  # requests per minute


@dataclass
class LoggingConfig:
    """Logging configuration"""
    level: str = "INFO"
    file: Optional[str] = None
    max_size: str = "10MB"
    backup_count: int = 3
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


@dataclass
class SMCPConfig:
    """Main SMCP Configuration with multiple sources support"""
    # Core settings
    node_id: str = "scp_node"
    server_url: str = "ws://localhost:8765"
    api_key: str = "demo_key_123"
    secret_key: str = "default_secret_key"
    jwt_secret: str = "default_jwt_secret"
    
    # Enterprise features (optional, backward compatible)
    mode: str = "simple"  # "simple", "enterprise", "development"
    
    # Component configurations
    server: ServerConfig = field(default_factory=ServerConfig)
    client: ClientConfig = field(default_factory=ClientConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    
    # Enterprise configurations (optional)
    oauth2: OAuth2Config = field(default_factory=OAuth2Config)
    crypto: CryptoConfig = field(default_factory=CryptoConfig)
    cluster: ClusterConfig = field(default_factory=ClusterConfig)
    
    # Custom tools and capabilities
    custom_tools: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_file(cls, config_path: str) -> 'SCPConfig':
        """Load configuration from file (supports .toml, .yaml, .yml)"""
        path = Path(config_path)
        
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        # Determine file type and load
        if path.suffix.lower() == '.toml':
            if not tomli:
                raise ImportError("tomli is required for TOML support")
            with open(path, 'rb') as f:
                data = tomli.load(f)
        elif path.suffix.lower() in ['.yaml', '.yml']:
            if not yaml:
                raise ImportError("PyYAML is required for YAML support")
            with open(path, 'r') as f:
                data = yaml.safe_load(f)
        else:
            raise ValueError(f"Unsupported config file format: {path.suffix}")
        
        return cls.from_dict(data)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SCPConfig':
        """Create configuration from dictionary"""
        # Extract nested configurations
        server_data = data.pop('server', {})
        client_data = data.pop('client', {})
        ai_data = data.pop('ai', {})
        security_data = data.pop('security', {})
        logging_data = data.pop('logging', {})
        oauth2_data = data.pop('oauth2', {})
        crypto_data = data.pop('crypto', {})
        cluster_data = data.pop('cluster', {})
        custom_tools_data = data.pop('custom_tools', {})
        
        # Create nested config objects
        server_config = ServerConfig(**server_data)
        client_config = ClientConfig(**client_data)
        ai_config = AIConfig(**ai_data)
        security_config = SecurityConfig(**security_data)
        logging_config = LoggingConfig(**logging_data)
        oauth2_config = OAuth2Config(**oauth2_data)
        crypto_config = CryptoConfig(**crypto_data)
        cluster_config = ClusterConfig(**cluster_data)
        
        # Create main config with remaining data
        config = cls(**data)
        config.server = server_config
        config.client = client_config
        config.ai = ai_config
        config.security = security_config
        config.logging = logging_config
        config.oauth2 = oauth2_config
        config.crypto = crypto_config
        config.cluster = cluster_config
        config.custom_tools = custom_tools_data
        
        return config
    
    @classmethod
    def from_env(cls) -> 'SCPConfig':
        """Load configuration from environment variables"""
        config = cls()
        
        # Core settings
        config.node_id = os.getenv('SCP_NODE_ID', config.node_id)
        config.server_url = os.getenv('SCP_SERVER_URL', config.server_url)
        config.api_key = os.getenv('SCP_API_KEY', config.api_key)
        config.secret_key = os.getenv('SCP_SECRET_KEY', config.secret_key)
        config.jwt_secret = os.getenv('SCP_JWT_SECRET', config.jwt_secret)
        config.mode = os.getenv('SCP_MODE', config.mode)
        
        # Server settings
        config.server.host = os.getenv('SCP_HOST', config.server.host)
        config.server.port = int(os.getenv('SCP_PORT', config.server.port))
        config.server.max_connections = int(os.getenv('SCP_MAX_CONNECTIONS', config.server.max_connections))
        
        # Client settings
        config.client.timeout = int(os.getenv('SCP_TIMEOUT', config.client.timeout))
        config.client.max_retries = int(os.getenv('SCP_MAX_RETRIES', config.client.max_retries))
        
        # AI settings
        config.ai.ollama_url = os.getenv('SCP_OLLAMA_URL', config.ai.ollama_url)
        config.ai.default_model = os.getenv('SCP_DEFAULT_MODEL', config.ai.default_model)
        
        # Security settings
        config.security.max_message_size = int(os.getenv('SCP_MAX_MESSAGE_SIZE', config.security.max_message_size))
        config.security.token_expiry = int(os.getenv('SCP_TOKEN_EXPIRY', config.security.token_expiry))
        
        # Logging settings
        config.logging.level = os.getenv('SCP_LOG_LEVEL', config.logging.level)
        config.logging.file = os.getenv('SCP_LOG_FILE', config.logging.file)
        
        # OAuth2 settings
        config.oauth2.enabled = os.getenv('SCP_OAUTH2_ENABLED', 'false').lower() == 'true'
        config.oauth2.token_url = os.getenv('SCP_OAUTH2_TOKEN_URL', config.oauth2.token_url)
        config.oauth2.jwks_url = os.getenv('SCP_OAUTH2_JWKS_URL', config.oauth2.jwks_url)
        config.oauth2.client_id = os.getenv('SCP_OAUTH2_CLIENT_ID', config.oauth2.client_id)
        config.oauth2.client_secret = os.getenv('SCP_OAUTH2_CLIENT_SECRET', config.oauth2.client_secret)
        config.oauth2.scope = os.getenv('SCP_OAUTH2_SCOPE', config.oauth2.scope)
        config.oauth2.local_public_key_path = os.getenv('SCP_OAUTH2_PUBLIC_KEY_PATH', config.oauth2.local_public_key_path)
        
        # Crypto settings
        config.crypto.key_exchange = os.getenv('SCP_CRYPTO_KEY_EXCHANGE', config.crypto.key_exchange)
        config.crypto.perfect_forward_secrecy = os.getenv('SCP_CRYPTO_PFS', 'false').lower() == 'true'
        config.crypto.certificate_path = os.getenv('SCP_CRYPTO_CERT_PATH', config.crypto.certificate_path)
        config.crypto.private_key_path = os.getenv('SCP_CRYPTO_KEY_PATH', config.crypto.private_key_path)
        config.crypto.ca_certificate_path = os.getenv('SCP_CRYPTO_CA_CERT_PATH', config.crypto.ca_certificate_path)
        config.crypto.use_self_signed = os.getenv('SCP_CRYPTO_SELF_SIGNED', 'true').lower() == 'true'
        
        # Cluster settings
        config.cluster.enabled = os.getenv('SCP_CLUSTER_ENABLED', 'false').lower() == 'true'
        config.cluster.discovery_method = os.getenv('SCP_CLUSTER_DISCOVERY', config.cluster.discovery_method)
        config.cluster.simulate_distributed = os.getenv('SCP_CLUSTER_SIMULATE', 'false').lower() == 'true'
        
        return config
    
    @classmethod
    def from_args(cls, args: argparse.Namespace) -> 'SCPConfig':
        """Create configuration from command line arguments"""
        config = cls()
        
        # Apply arguments that are not None
        if hasattr(args, 'node_id') and args.node_id:
            config.node_id = args.node_id
        if hasattr(args, 'server_url') and args.server_url:
            config.server_url = args.server_url
        if hasattr(args, 'api_key') and args.api_key:
            config.api_key = args.api_key
        if hasattr(args, 'host') and args.host:
            config.server.host = args.host
        if hasattr(args, 'port') and args.port:
            config.server.port = args.port
        if hasattr(args, 'log_level') and args.log_level:
            config.logging.level = args.log_level
        if hasattr(args, 'ollama_url') and args.ollama_url:
            config.ai.ollama_url = args.ollama_url
        if hasattr(args, 'model') and args.model:
            config.ai.default_model = args.model
        
        return config
    
    @classmethod
    def load(cls, config_file: Optional[str] = None, 
             use_env: bool = True, 
             cli_args: Optional[argparse.Namespace] = None) -> 'SCPConfig':
        """
        Load configuration with priority:
        1. CLI arguments (highest priority)
        2. Environment variables
        3. Configuration file
        4. Defaults (lowest priority)
        """
        # Start with defaults
        config = cls()
        
        # Apply config file if provided
        if config_file and Path(config_file).exists():
            file_config = cls.from_file(config_file)
            config = cls.merge_configs(config, file_config)
        
        # Apply environment variables
        if use_env:
            env_config = cls.from_env()
            config = cls.merge_configs(config, env_config)
        
        # Apply CLI arguments (highest priority)
        if cli_args:
            cli_config = cls.from_args(cli_args)
            config = cls.merge_configs(config, cli_config)
        
        return config
    
    @classmethod
    def merge_configs(cls, base: 'SCPConfig', override: 'SCPConfig') -> 'SCPConfig':
        """Merge two configurations, with override taking precedence"""
        # Create a new config starting with base
        merged = cls()
        
        # Copy all fields from base
        for field_name in ['node_id', 'server_url', 'api_key', 'secret_key', 'jwt_secret']:
            setattr(merged, field_name, getattr(base, field_name))
        
        # Copy nested configurations
        merged.server = ServerConfig(**base.server.__dict__)
        merged.client = ClientConfig(**base.client.__dict__)
        merged.ai = AIConfig(**base.ai.__dict__)
        merged.security = SecurityConfig(**base.security.__dict__)
        merged.logging = LoggingConfig(**base.logging.__dict__)
        merged.custom_tools = base.custom_tools.copy()
        
        # Override with non-default values from override config
        if override.node_id != cls().node_id:
            merged.node_id = override.node_id
        if override.server_url != cls().server_url:
            merged.server_url = override.server_url
        if override.api_key != cls().api_key:
            merged.api_key = override.api_key
        if override.secret_key != cls().secret_key:
            merged.secret_key = override.secret_key
        if override.jwt_secret != cls().jwt_secret:
            merged.jwt_secret = override.jwt_secret
        
        # Override nested configurations
        for attr in ['host', 'port', 'max_connections', 'ping_interval', 'ping_timeout']:
            if getattr(override.server, attr) != getattr(ServerConfig(), attr):
                setattr(merged.server, attr, getattr(override.server, attr))
        
        for attr in ['auto_reconnect', 'reconnect_delay', 'max_retries', 'timeout', 'heartbeat_interval']:
            if getattr(override.client, attr) != getattr(ClientConfig(), attr):
                setattr(merged.client, attr, getattr(override.client, attr))
        
        for attr in ['ollama_url', 'default_model', 'timeout', 'max_tokens']:
            if getattr(override.ai, attr) != getattr(AIConfig(), attr):
                setattr(merged.ai, attr, getattr(override.ai, attr))
        
        for attr in ['require_signature', 'max_message_size', 'token_expiry', 'rate_limit']:
            if getattr(override.security, attr) != getattr(SecurityConfig(), attr):
                setattr(merged.security, attr, getattr(override.security, attr))
        
        for attr in ['level', 'file', 'max_size', 'backup_count', 'format']:
            if getattr(override.logging, attr) != getattr(LoggingConfig(), attr):
                setattr(merged.logging, attr, getattr(override.logging, attr))
        
        # Merge custom tools
        merged.custom_tools.update(override.custom_tools)
        
        return merged
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        def clean_dict(d):
            """Remove None values from dictionary"""
            return {k: v for k, v in d.items() if v is not None}
        
        return {
            'node_id': self.node_id,
            'server_url': self.server_url,
            'api_key': self.api_key,
            'secret_key': self.secret_key,
            'jwt_secret': self.jwt_secret,
            'server': clean_dict(self.server.__dict__),
            'client': clean_dict(self.client.__dict__),
            'ai': clean_dict(self.ai.__dict__),
            'security': clean_dict(self.security.__dict__),
            'logging': clean_dict(self.logging.__dict__),
            'custom_tools': self.custom_tools
        }
    
    def to_file(self, config_path: str, format: str = 'auto'):
        """Save configuration to file"""
        path = Path(config_path)
        data = self.to_dict()
        
        # Auto-detect format from extension
        if format == 'auto':
            if path.suffix.lower() == '.toml':
                format = 'toml'
            elif path.suffix.lower() in ['.yaml', '.yml']:
                format = 'yaml'
            else:
                format = 'toml'  # Default to TOML
        
        if format == 'toml':
            if not tomli_w:
                raise ImportError("tomli-w is required for TOML writing")
            with open(path, 'wb') as f:
                tomli_w.dump(data, f)
        elif format == 'yaml':
            if not yaml:
                raise ImportError("PyYAML is required for YAML writing")
            with open(path, 'w') as f:
                yaml.dump(data, f, default_flow_style=False, indent=2)
        else:
            raise ValueError(f"Unsupported format: {format}")
    
    def validate(self) -> List[str]:
        """Validate configuration and return list of issues"""
        issues = []
        
        if not self.node_id:
            issues.append("node_id cannot be empty")
        
        if not self.server_url:
            issues.append("server_url cannot be empty")
        
        if not self.api_key:
            issues.append("api_key cannot be empty")
        
        if not self.secret_key:
            issues.append("secret_key cannot be empty")
        
        if not self.jwt_secret:
            issues.append("jwt_secret cannot be empty")
        
        if self.server.port < 1 or self.server.port > 65535:
            issues.append(f"server.port must be between 1-65535, got {self.server.port}")
        
        if self.client.timeout < 1:
            issues.append(f"client.timeout must be positive, got {self.client.timeout}")
        
        if self.security.max_message_size < 1024:
            issues.append(f"security.max_message_size too small, got {self.security.max_message_size}")
        
        return issues


def create_default_config(config_path: str = "scp_config.toml"):
    """Create a default configuration file"""
    config = SCPConfig()
    config.to_file(config_path, format='toml')
    print(f"✓ Created default configuration: {config_path}")


def get_common_args() -> argparse.ArgumentParser:
    """Get common command line arguments parser"""
    parser = argparse.ArgumentParser(add_help=False)
    
    parser.add_argument('--config', '-c', 
                       help='Configuration file path (.toml or .yaml)')
    parser.add_argument('--node-id', 
                       help='Node identifier')
    parser.add_argument('--api-key', 
                       help='API key for authentication')
    parser.add_argument('--log-level', 
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Logging level')
    
    return parser


def get_server_args() -> argparse.ArgumentParser:
    """Get server-specific command line arguments"""
    parser = argparse.ArgumentParser(parents=[get_common_args()])
    
    parser.add_argument('--host', 
                       help='Server host to bind to')
    parser.add_argument('--port', type=int,
                       help='Server port to bind to')
    parser.add_argument('--ollama-url',
                       help='Ollama API URL')
    parser.add_argument('--model',
                       help='Default AI model')
    
    return parser


def get_client_args() -> argparse.ArgumentParser:
    """Get client-specific command line arguments"""
    parser = argparse.ArgumentParser(parents=[get_common_args()])
    
    parser.add_argument('--server-url', 
                       help='Server WebSocket URL')
    parser.add_argument('--timeout', type=int,
                       help='Connection timeout in seconds')
    parser.add_argument('--retries', type=int,
                       help='Maximum connection retries')
    
    return parser


# Example usage
if __name__ == "__main__":
    # Create default config
    create_default_config()
    
    # Demo loading from different sources
    print("\n📁 Loading configuration...")
    config = SCPConfig.load('scp_config.toml', use_env=True)
    
    print(f"Node ID: {config.node_id}")
    print(f"Server: {config.server.host}:{config.server.port}")
    print(f"AI Model: {config.ai.default_model}")
    
    # Validate
    issues = config.validate()
    if issues:
        print("⚠️  Configuration issues:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("✅ Configuration is valid")