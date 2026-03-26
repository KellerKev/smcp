#!/bin/bash
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
