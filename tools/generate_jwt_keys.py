#!/usr/bin/env python3
"""
RS256 JWT Key Generation Tool
=============================
Generates an RSA key pair for federated / multi-party JWT signing.

The **issuer** node holds the private key and mints client tokens
(``smcp_federated_auth.mint_client_jwt``); every other node holds only the
public key and *verifies* tokens (``security.jwt_algorithm="RS256"`` +
``security.jwt_public_key_path``), so a compromised verifier cannot forge
identities. This is the recommended posture for multi-party federations, where
a single shared HS256 secret would let any holder mint any identity.

Note: this is distinct from ``generate_ecdh_keys.py``, which emits SECP256R1
ECDH keys for the transport/crypto layer — those are not RSA and won't work as
RS256 JWT keys.
"""
import sys
from pathlib import Path

import click
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

sys.path.append(str(Path(__file__).parent.parent))


def generate_rsa_keypair(key_size: int = 2048):
    """Return (private_pem_bytes, public_pem_bytes) for a fresh RSA keypair."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=key_size)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


@click.group()
def cli():
    """Generate and validate RS256 JWT signing keys."""


@cli.command()
@click.option('--output-dir', '-o', default='./jwt_keys',
              help='Directory to store generated keys (default: ./jwt_keys)')
@click.option('--name', '-n', default='jwt',
              help='Filename prefix (default: jwt -> jwt_private.pem / jwt_public.pem)')
@click.option('--key-size', default=2048, type=int, help='RSA key size (default: 2048)')
@click.option('--force', '-f', is_flag=True, help='Overwrite existing keys without prompting')
def generate(output_dir: str, name: str, key_size: int, force: bool):
    """Generate an RSA-2048 keypair for RS256 JWT signing/verification."""
    keys_dir = Path(output_dir)
    keys_dir.mkdir(exist_ok=True, mode=0o700)

    private_path = keys_dir / f"{name}_private.pem"
    public_path = keys_dir / f"{name}_public.pem"

    if (private_path.exists() or public_path.exists()) and not force:
        click.echo(f"❌ Keys already exist in {keys_dir} (use --force to overwrite)")
        sys.exit(1)

    private_pem, public_pem = generate_rsa_keypair(key_size)

    # Private key: never world-readable.
    private_path.write_bytes(private_pem)
    private_path.chmod(0o600)
    public_path.write_bytes(public_pem)
    public_path.chmod(0o644)

    click.echo(f"🔑 RSA-{key_size} JWT keypair written:")
    click.echo(f"   private (issuer, keep secret): {private_path}  [0600]")
    click.echo(f"   public  (verifiers, shareable): {public_path}  [0644]")
    click.echo("")
    click.echo("Wire into config:")
    click.echo('   [security]')
    click.echo('   jwt_algorithm = "RS256"')
    click.echo(f'   jwt_private_key_path = "{private_path}"   # issuer only')
    click.echo(f'   jwt_public_key_path  = "{public_path}"    # every node')


@cli.command()
@click.option('--private', 'private_path', required=True, help='Path to the private key PEM')
@click.option('--public', 'public_path', required=True, help='Path to the public key PEM')
def validate(private_path: str, public_path: str):
    """Verify the keypair matches by signing and verifying a test RS256 token."""
    priv = Path(private_path).read_bytes()
    pub = Path(public_path).read_bytes()
    token = jwt.encode({"test": "ok"}, priv, algorithm="RS256")
    try:
        decoded = jwt.decode(token, pub, algorithms=["RS256"])
    except jwt.InvalidTokenError as e:
        click.echo(f"❌ Keypair mismatch: {e}")
        sys.exit(1)
    assert decoded["test"] == "ok"
    click.echo("✅ Keypair valid: a token signed with the private key verifies with the public key.")


if __name__ == "__main__":
    cli()
