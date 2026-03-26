#!/usr/bin/env python3
"""
Development Security Setup Tool
=============================
One-command setup for development security features.
Configures ECDH keys and provides guidance on security modes.
"""

import os
import sys
import subprocess
from pathlib import Path
import click

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))


@click.command()
@click.option('--mode', '-m', 
              type=click.Choice(['basic', 'encrypted', 'both']),
              default='both',
              help='Security mode to setup (default: both)')
@click.option('--force', '-f', is_flag=True,
              help='Overwrite existing configuration')
def setup_dev_security(mode: str, force: bool):
    """Setup development security configuration"""
    
    print("🔧 SCP Framework - Development Security Setup")
    print("=" * 60)
    print(f"Setup mode: {mode}")
    print()
    
    current_dir = Path.cwd()
    tools_dir = Path(__file__).parent
    
    # Step 1: Generate ECDH keys if needed
    if mode in ['encrypted', 'both']:
        print("1. Setting up ECDH keys for encrypted mode...")
        
        keys_dir = current_dir / "ecdh_keys"
        if keys_dir.exists() and not force:
            print(f"   ✓ ECDH keys already exist: {keys_dir}")
        else:
            # Run key generation tool
            cmd = [sys.executable, str(tools_dir / "generate_ecdh_keys.py"), "generate"]
            if force:
                cmd.append("--force")
            
            try:
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    print("   ✓ ECDH keys generated successfully")
                else:
                    print(f"   ❌ Key generation failed: {result.stderr}")
                    return
            except Exception as e:
                print(f"   ❌ Error generating keys: {e}")
                return
    
    # Step 2: Create development configuration examples
    print("\n2. Creating development configuration examples...")
    
    config_dir = current_dir / "dev_config_examples"
    config_dir.mkdir(exist_ok=True)
    
    if mode in ['basic', 'both']:
        basic_config = config_dir / "basic_mode.yaml"
        with open(basic_config, 'w') as f:
            f.write("""# Basic Mode Configuration - Standard JWT + HTTPS
# Suitable for production with proper TLS setup

security:
  mode: "basic"
  crypto:
    key_exchange: "static"
    perfect_forward_secrecy: false
    message_encryption: false
  
  # JWT tokens in Authorization headers
  jwt:
    enabled: true
    secret: "your_jwt_secret_here"
    algorithm: "HS256"
  
  # Assumes HTTPS in production
  transport:
    encryption: "https"  # TLS provides transport security
    token_location: "header"  # Authorization: Bearer <token>

cluster:
  enabled: true
  simulate_distributed: true  # For development

# For production, change to wss:// and configure proper TLS
server_url: "ws://localhost:8765"
""")
        print(f"   ✓ Basic mode config: {basic_config}")
    
    if mode in ['encrypted', 'both']:
        encrypted_config = config_dir / "encrypted_mode.yaml"
        with open(encrypted_config, 'w') as f:
            f.write("""# Encrypted Mode Configuration - ECDH + Full Message Encryption
# Ideal for dev/test or production hardening

security:
  mode: "encrypted"
  crypto:
    key_exchange: "ecdh"
    perfect_forward_secrecy: true
    message_encryption: true
    
    # Auto-generated keys for development
    client_private_key_path: "./ecdh_keys/client_private.pem"
    client_public_key_path: "./ecdh_keys/client_public.pem"
    server_public_key_path: "./ecdh_keys/server_public.pem"
  
  # JWT tokens encrypted inside message payload
  jwt:
    enabled: true
    secret: "your_jwt_secret_here"
    algorithm: "HS256"
    location: "encrypted_payload"  # Inside encrypted message
  
  # Full message encryption
  transport:
    encryption: "ecdh_aes256"  # Message-level encryption
    token_location: "payload"   # JWT inside encrypted payload

cluster:
  enabled: true
  simulate_distributed: true

# Can use ws:// since messages are encrypted
server_url: "ws://localhost:8765"
""")
        print(f"   ✓ Encrypted mode config: {encrypted_config}")
    
    # Step 3: Create environment setup script
    print("\n3. Creating environment setup script...")
    
    env_script = current_dir / "setup_dev_env.sh"
    with open(env_script, 'w') as f:
        f.write("""#!/bin/bash
# SCP Framework Development Environment Setup

echo "🔧 Setting up SCP Framework development environment..."

# Basic mode environment variables
export SCP_MODE="basic"
export SCP_JWT_SECRET="dev_jwt_secret_2024"
export SCP_API_KEY="demo_key_123"
export SCP_SECRET_KEY="my_secret_key_2024"

# For encrypted mode, uncomment these:
# export SCP_MODE="encrypted"
# export SCP_CRYPTO_KEY_EXCHANGE="ecdh"
# export SCP_CRYPTO_PFS="true"
# export SCP_CLIENT_PRIVATE_KEY_PATH="./ecdh_keys/client_private.pem"
# export SCP_SERVER_PUBLIC_KEY_PATH="./ecdh_keys/server_public.pem"

echo "✅ Environment variables set for basic mode"
echo "💡 To switch to encrypted mode, edit this script and uncomment the encrypted mode variables"
""")
    os.chmod(env_script, 0o755)
    print(f"   ✓ Environment script: {env_script}")
    
    # Step 4: Show usage instructions
    print("\n" + "=" * 60)
    print("✅ Development Security Setup Complete!")
    print()
    
    print("🚀 Quick Start Commands:")
    print()
    
    if mode in ['basic', 'both']:
        print("📋 Basic Mode (Standard JWT + HTTPS):")
        print("   pixi run basic-a2a          # Qwen 2.5 Coder 7B → Qwen3 Coder workflow")
        print("   # Suitable for production with HTTPS")
        print()
    
    if mode in ['encrypted', 'both']:
        print("🔐 Encrypted Mode (ECDH + Full Message Encryption):")
        print("   pixi run encrypted-a2a       # Qwen 2.5 Coder 7B → Qwen3 Coder encrypted workflow") 
        print("   # Ideal for dev/test or production hardening")
        print()
    
    print("🔧 Additional Tools:")
    print("   pixi run generate-ecdh-keys   # Generate new ECDH keys")
    print("   pixi run validate-ecdh-keys   # Validate existing keys")
    print("   source setup_dev_env.sh       # Load environment variables")
    print()
    
    print("📁 Generated Files:")
    if mode in ['encrypted', 'both']:
        print(f"   • ECDH keys: ./ecdh_keys/")
    print(f"   • Config examples: ./dev_config_examples/")
    print(f"   • Environment script: ./setup_dev_env.sh")
    print()
    
    print("🔒 Security Notes:")
    print("   • Basic mode: Relies on HTTPS for transport security")
    print("   • Encrypted mode: Provides defense-in-depth security")
    print("   • Dev keys are auto-generated (use proper keys in production)")
    print("   • Both modes support the same A2A functionality")
    print()
    
    print("💡 Next Steps:")
    print("   1. Choose your security mode (basic or encrypted)")
    print("   2. Run the corresponding demo")
    print("   3. Examine the differences in security approach")
    print("   4. Adapt the configuration for your use case")


if __name__ == "__main__":
    setup_dev_security()