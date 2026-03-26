#!/usr/bin/env python3
"""
ECDH Key Generation Tool
======================
Generates ECDH key pairs for development and testing.
Provides simple tooling for setting up encrypted communication.
"""

import os
import sys
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
import click

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))


def generate_ecdh_keypair() -> tuple[str, str]:
    """Generate an ECDH key pair"""
    # Generate private key using SECP256R1 curve
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    
    # Serialize private key
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode('utf-8')
    
    # Serialize public key
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode('utf-8')
    
    return private_pem, public_pem


def create_keys_directory(keys_dir: Path) -> None:
    """Create keys directory with secure permissions"""
    keys_dir.mkdir(exist_ok=True, mode=0o700)
    print(f"📁 Created keys directory: {keys_dir}")


@click.command()
@click.option('--output-dir', '-o', default='./ecdh_keys', 
              help='Directory to store generated keys (default: ./ecdh_keys)')
@click.option('--client-name', '-c', default='client',
              help='Name prefix for client keys (default: client)')
@click.option('--server-name', '-s', default='server',
              help='Name prefix for server keys (default: server)')
@click.option('--force', '-f', is_flag=True,
              help='Overwrite existing keys without prompting')
def generate_keys(output_dir: str, client_name: str, server_name: str, force: bool):
    """Generate ECDH key pairs for client and server"""
    
    keys_dir = Path(output_dir)
    
    print("🔑 ECDH Key Generation Tool")
    print("=" * 50)
    print(f"Output directory: {keys_dir.absolute()}")
    print(f"Client key prefix: {client_name}")
    print(f"Server key prefix: {server_name}")
    print()
    
    # Check if keys already exist
    client_private_path = keys_dir / f"{client_name}_private.pem"
    client_public_path = keys_dir / f"{client_name}_public.pem"
    server_private_path = keys_dir / f"{server_name}_private.pem"
    server_public_path = keys_dir / f"{server_name}_public.pem"
    
    existing_files = [
        path for path in [client_private_path, client_public_path, 
                         server_private_path, server_public_path]
        if path.exists()
    ]
    
    if existing_files and not force:
        print("⚠️  Warning: The following key files already exist:")
        for path in existing_files:
            print(f"   • {path}")
        print()
        if not click.confirm("Do you want to overwrite them?"):
            print("❌ Key generation cancelled.")
            return
    
    # Create keys directory
    create_keys_directory(keys_dir)
    
    # Generate client keys
    print("🔐 Generating client ECDH key pair...")
    client_private, client_public = generate_ecdh_keypair()
    
    with open(client_private_path, 'w') as f:
        f.write(client_private)
    os.chmod(client_private_path, 0o600)  # Private key: owner read/write only
    
    with open(client_public_path, 'w') as f:
        f.write(client_public)
    os.chmod(client_public_path, 0o644)  # Public key: owner read/write, others read
    
    print(f"   ✓ Private key: {client_private_path}")
    print(f"   ✓ Public key: {client_public_path}")
    
    # Generate server keys
    print("\n🖥️  Generating server ECDH key pair...")
    server_private, server_public = generate_ecdh_keypair()
    
    with open(server_private_path, 'w') as f:
        f.write(server_private)
    os.chmod(server_private_path, 0o600)  # Private key: owner read/write only
    
    with open(server_public_path, 'w') as f:
        f.write(server_public)
    os.chmod(server_public_path, 0o644)  # Public key: owner read/write, others read
    
    print(f"   ✓ Private key: {server_private_path}")
    print(f"   ✓ Public key: {server_public_path}")
    
    print("\n" + "=" * 50)
    print("✅ ECDH key generation completed!")
    print("\n📋 Key Usage Instructions:")
    print(f"   Client configuration:")
    print(f"     client_private_key_path: {client_private_path}")
    print(f"     client_public_key_path: {client_public_path}")
    print(f"     server_public_key_path: {server_public_path}")
    print()
    print(f"   Server configuration:")
    print(f"     server_private_key_path: {server_private_path}")
    print(f"     server_public_key_path: {server_public_path}")
    print(f"     client_public_key_path: {client_public_path}")
    
    print("\n🔒 Security Notes:")
    print("   • Keep private keys secure (600 permissions set)")
    print("   • Public keys can be shared safely")
    print("   • Use different keys for production")
    print("   • Consider key rotation policies")
    
    print("\n💡 Example Usage:")
    print("   # Basic A2A demo (standard JWT)")
    print("   pixi run basic-a2a")
    print()
    print("   # Encrypted A2A demo (uses auto-generated keys)")
    print("   pixi run encrypted-a2a")
    print()
    print("   # Or use these generated keys in your config:")
    print("   export SCP_CLIENT_PRIVATE_KEY_PATH=" + str(client_private_path))
    print("   export SCP_SERVER_PUBLIC_KEY_PATH=" + str(server_public_path))


@click.command()
@click.option('--keys-dir', '-d', default='./ecdh_keys',
              help='Directory containing keys to validate')
def validate_keys(keys_dir: str):
    """Validate existing ECDH keys"""
    
    keys_path = Path(keys_dir)
    
    print("🔍 ECDH Key Validation Tool")
    print("=" * 50)
    print(f"Keys directory: {keys_path.absolute()}")
    print()
    
    if not keys_path.exists():
        print("❌ Keys directory does not exist")
        return
    
    # Find key files
    key_files = list(keys_path.glob("*.pem"))
    
    if not key_files:
        print("❌ No .pem key files found in directory")
        return
    
    print(f"📁 Found {len(key_files)} key files:")
    
    valid_keys = 0
    for key_file in key_files:
        print(f"\n🔑 Validating: {key_file.name}")
        
        try:
            with open(key_file, 'r') as f:
                key_data = f.read()
            
            # Try to load as private key
            try:
                serialization.load_pem_private_key(
                    key_data.encode('utf-8'),
                    password=None
                )
                print(f"   ✓ Valid ECDH private key")
                
                # Check permissions
                perms = oct(key_file.stat().st_mode)[-3:]
                if perms == '600':
                    print(f"   ✓ Secure permissions: {perms}")
                else:
                    print(f"   ⚠️  Permissions: {perms} (recommended: 600)")
                
                valid_keys += 1
                continue
                
            except Exception:
                pass
            
            # Try to load as public key
            try:
                serialization.load_pem_public_key(key_data.encode('utf-8'))
                print(f"   ✓ Valid ECDH public key")
                
                # Check permissions
                perms = oct(key_file.stat().st_mode)[-3:]
                print(f"   ✓ Permissions: {perms}")
                
                valid_keys += 1
                continue
                
            except Exception:
                pass
            
            print(f"   ❌ Invalid or unrecognized key format")
            
        except Exception as e:
            print(f"   ❌ Error reading file: {e}")
    
    print(f"\n" + "=" * 50)
    if valid_keys == len(key_files):
        print(f"✅ All {valid_keys} keys are valid!")
    else:
        print(f"⚠️  {valid_keys}/{len(key_files)} keys are valid")
    
    print("\n💡 Quick Commands:")
    print("   # Generate new keys:")
    print("   pixi run generate-ecdh-keys")
    print()
    print("   # Test with basic A2A:")
    print("   pixi run basic-a2a")
    print()
    print("   # Test with encrypted A2A:")
    print("   pixi run encrypted-a2a")


@click.group()
def cli():
    """ECDH Key Management Tools for SCP Framework"""
    pass


cli.add_command(generate_keys, name='generate')
cli.add_command(validate_keys, name='validate')


if __name__ == "__main__":
    cli()