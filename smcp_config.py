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
    default_model: str = "qwen2.5-coder:7b-instruct-q4_K_M"
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
    max_connections: int = 100  # concurrent connection cap
    # Transport security (TLS). When tls_enabled is True the server serves wss://
    # and the client/bridge require TLS with certificate verification.
    tls_enabled: bool = False
    tls_cert_path: Optional[str] = None
    tls_key_path: Optional[str] = None
    tls_ca_path: Optional[str] = None  # CA bundle for verifying peers (optional)
    # Escape hatch for local development ONLY: permit plaintext ws://http:// when
    # the peer host is loopback. Never allows plaintext to a remote host.
    allow_insecure_transit: bool = False
    # JWT signing. HS256 (default) uses the shared jwt_secret — any holder can mint
    # tokens. RS256 with a server-held private key + client public key means clients
    # can verify but cannot forge tokens (recommended for multi-party deployments).
    jwt_algorithm: str = "HS256"
    jwt_private_key_path: Optional[str] = None  # server: sign
    jwt_public_key_path: Optional[str] = None   # client/server: verify


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
    # No built-in secrets: the previous "default_secret_key"/"default_jwt_secret"
    # constants were publicly known, so any unconfigured deployment could have
    # its channel keys derived and its auth JWTs forged. These must be set
    # per-deployment (SCP_SECRET_KEY / SCP_JWT_SECRET); validate() enforces it.
    secret_key: str = ""
    jwt_secret: str = ""
    kdf_salt: str = ""  # v3 per-deployment KDF salt (must match the server)
    
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
        config.kdf_salt = os.getenv('SCP_KDF_SALT', config.kdf_salt)
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
        for field_name in ['node_id', 'server_url', 'api_key', 'secret_key', 'jwt_secret', 'kdf_salt', 'mode']:
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
        if override.kdf_salt != cls().kdf_salt:
            merged.kdf_salt = override.kdf_salt
        if override.mode != cls().mode:
            merged.mode = override.mode

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
            'kdf_salt': self.kdf_salt,
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
        
        # Every credential-shaped string that has ever been published in this
        # repo (defaults, examples, dev setup scripts, docs). A deployment using
        # any of these has a publicly-known secret, so reject them outright.
        _PUBLISHED_SECRETS = {
            "", "default_secret_key", "default_jwt_secret", "default_secret",
            "default_jwt", "demo_key_123", "my_secret_key_2024",
            "dev_jwt_secret_2024", "demo_secret_2024", "enterprise_key_abc123",
            "your_secure_api_key_here", "your_encryption_secret_key_here",
            "your_jwt_signing_secret_here",
        }
        _MIN_SECRET_LEN = 32  # ~256 bits when using token_urlsafe(32)

        # Obvious placeholder prefixes shipped in examples/.env.example — reject so
        # a copy-paste deployment cannot run with a non-secret "secret".
        _PLACEHOLDER_PREFIXES = ("CHANGE_ME", "your_", "your-", "changeme")

        def _is_placeholder(value: str) -> bool:
            return any(value.lower().startswith(p.lower()) for p in _PLACEHOLDER_PREFIXES)

        def _check_secret(value: str, name: str, env: str, purpose: str):
            if _is_placeholder(value):
                issues.append(
                    f"{name} is still a placeholder value; set a real per-deployment "
                    f"secret ({env})"
                )
                return
            if value in _PUBLISHED_SECRETS:
                issues.append(
                    f"{name} must be set to a strong per-deployment value ({env}); "
                    f"the configured value is empty or publicly known and lets "
                    f"anyone {purpose}"
                )
            elif len(value) < _MIN_SECRET_LEN:
                issues.append(
                    f"{name} is too short ({len(value)} chars); use at least "
                    f"{_MIN_SECRET_LEN} chars, e.g. "
                    f"python -c \"import secrets;print(secrets.token_urlsafe(32))\""
                )

        if not self.api_key:
            issues.append("api_key cannot be empty")
        elif _is_placeholder(self.api_key):
            issues.append(
                "api_key is still a placeholder value; set a real per-deployment "
                "value (SCP_API_KEY)"
            )
        elif self.api_key in _PUBLISHED_SECRETS:
            issues.append(
                "api_key must be set to a strong per-deployment value (SCP_API_KEY); "
                "the configured value is publicly known and lets anyone authenticate"
            )

        _check_secret(self.secret_key, "secret_key", "SCP_SECRET_KEY",
                      "derive the channel encryption/MAC keys")
        _check_secret(self.jwt_secret, "jwt_secret", "SCP_JWT_SECRET",
                      "forge authentication tokens")

        # v3 KDF salt: an empty salt silently falls back to the global hardcoded
        # constant, which defeats per-deployment key separation and enables
        # cross-deployment precomputation on the secret.
        if not self.kdf_salt:
            issues.append(
                "kdf_salt must be set to a per-deployment value (SCP_KDF_SALT); "
                "an empty salt falls back to a publicly-known constant"
            )
        elif len(self.kdf_salt) < 16:
            issues.append(
                f"kdf_salt is too short ({len(self.kdf_salt)} chars); use at least 16 chars"
            )

        if self.server.port < 1 or self.server.port > 65535:
            issues.append(f"server.port must be between 1-65535, got {self.server.port}")
        
        if self.client.timeout < 1:
            issues.append(f"client.timeout must be positive, got {self.client.timeout}")
        
        if self.security.max_message_size < 1024:
            issues.append(f"security.max_message_size too small, got {self.security.max_message_size}")
        
        return issues


# Backward/forward-compatible alias: much of the codebase (and external
# callers) refer to this class as ``SCPConfig``; the canonical name is
# ``SMCPConfig``. Keep both importable so those references resolve.
SCPConfig = SMCPConfig


def _host_is_loopback(host: Optional[str]) -> bool:
    return host in ("localhost", "127.0.0.1", "::1", "", None)


def enforce_secure_url(url: str, allow_insecure: bool = False) -> None:
    """Raise unless ``url`` is TLS, or plaintext is explicitly allowed to loopback.

    Plaintext (ws://, http://) is only ever permitted when allow_insecure is set
    AND the target host is loopback. A plaintext URL to a remote host always raises.
    """
    from urllib.parse import urlparse
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme in ("wss", "https"):
        return
    if scheme in ("ws", "http"):
        if allow_insecure and _host_is_loopback(parsed.hostname):
            return
        raise ValueError(
            f"Refusing plaintext transport to '{url}'. Use wss://https:// (set "
            f"security.tls_enabled), or set security.allow_insecure_transit for a "
            f"loopback target only."
        )
    raise ValueError(f"Unsupported URL scheme in '{url}'")


def build_server_ssl_context(config: 'SMCPConfig'):
    """Build a server-side SSLContext from config, or None if TLS is disabled."""
    import ssl
    sec = config.security
    if not sec.tls_enabled:
        return None
    if not sec.tls_cert_path or not sec.tls_key_path:
        raise ValueError("tls_enabled is set but tls_cert_path/tls_key_path are missing")
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(certfile=sec.tls_cert_path, keyfile=sec.tls_key_path)
    if sec.tls_ca_path:  # enable mutual TLS if a CA bundle is provided
        ctx.load_verify_locations(cafile=sec.tls_ca_path)
        ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx


def build_client_ssl_context(config: 'SMCPConfig'):
    """Build a client-side SSLContext with verification on, or None if TLS is off."""
    import ssl
    sec = config.security
    if not sec.tls_enabled:
        return None
    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH,
                                     cafile=sec.tls_ca_path or None)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx


def create_default_config(config_path: str = "scp_config.toml"):
    """Create a default configuration file.

    Fresh, strong secrets are generated so the created config is secure and
    runnable out of the box. For a multi-node/federated deployment, copy the
    same secret_key and jwt_secret to every participant.
    """
    import secrets as _secrets

    config = SCPConfig()
    config.api_key = _secrets.token_urlsafe(32)
    config.secret_key = _secrets.token_urlsafe(32)
    config.jwt_secret = _secrets.token_urlsafe(32)
    config.kdf_salt = _secrets.token_urlsafe(16)
    config.to_file(config_path, format='toml')
    print(f"✓ Created default configuration: {config_path}")
    print("  Generated fresh api_key, secret_key, jwt_secret and kdf_salt; "
          "share secret_key/jwt_secret/kdf_salt across nodes for federation.")


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