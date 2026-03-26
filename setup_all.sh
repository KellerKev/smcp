#!/bin/bash
# SMCP Complete Setup Script
# This script sets up everything needed to run SMCP examples

set -e

echo "🚀 SMCP Complete Setup Script"
echo "=============================="
echo ""

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check prerequisites
echo "📋 Checking prerequisites..."

if ! command_exists pixi; then
    echo "❌ Pixi not found. Please install it first:"
    echo "   curl -fsSL https://pixi.sh/install.sh | bash"
    exit 1
fi

if ! command_exists docker; then
    echo "⚠️  Docker not found. MindsDB integration will not work."
    echo "   Install Docker from: https://docs.docker.com/get-docker/"
fi

if ! command_exists ollama; then
    echo "❌ Ollama not found. Installing..."
    curl -fsSL https://ollama.ai/install.sh | sh
fi

echo "✅ Prerequisites checked"
echo ""

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pixi install
echo "✅ Dependencies installed"
echo ""

# Setup Ollama
echo "🤖 Setting up Ollama..."
if pgrep -x "ollama" > /dev/null; then
    echo "   Ollama is already running"
else
    echo "   Starting Ollama service..."
    ollama serve > /dev/null 2>&1 &
    sleep 5
fi

echo "   Pulling required AI models (Qwen models)..."
ollama pull qwen2.5-coder:7b-instruct-q4_K_M || true
ollama pull qwen3-coder:30b-a3b-q4_K_M || true
# Pull legacy models for compatibility
ollama pull tinyllama:latest || true
ollama pull mistral:7b-instruct-q4_K_M || true
echo "✅ Ollama setup complete"
echo ""

# Generate sample data
echo "📊 Generating sample data..."
if [ ! -d "sample_data" ]; then
    pixi run python tools/generate_sample_data.py
    echo "✅ Sample data generated"
else
    echo "   Sample data already exists"
fi
echo ""

# Initialize DuckDB
echo "🦆 Setting up DuckDB..."
if [ ! -f "demo_analytics.db" ]; then
    pixi run python examples/duckdb_integration_example.py || true
    echo "✅ DuckDB initialized"
else
    echo "   DuckDB already initialized"
fi
echo ""

# Setup MindsDB (if Docker is available)
if command_exists docker; then
    echo "🧠 Setting up MindsDB..."
    
    # Check if container exists
    if docker ps -a | grep -q mindsdb_smcp; then
        echo "   MindsDB container exists"
        # Start it if not running
        if ! docker ps | grep -q mindsdb_smcp; then
            docker start mindsdb_smcp
            echo "   Started MindsDB container"
        else
            echo "   MindsDB is already running"
        fi
    else
        echo "   Creating MindsDB container..."
        docker run -d --name mindsdb_smcp \
            -p 47335:47334 \
            -p 47336:47335 \
            mindsdb/mindsdb
        echo "   MindsDB container created and started"
    fi
    
    # Wait for MindsDB to be ready
    echo "   Waiting for MindsDB to be ready..."
    for i in {1..30}; do
        if curl -s http://localhost:47335/ > /dev/null 2>&1; then
            echo "✅ MindsDB is ready"
            break
        fi
        sleep 2
    done
else
    echo "⚠️  Docker not available - skipping MindsDB setup"
fi
echo ""

# Generate security keys (optional)
echo "🔐 Setting up security keys..."
if [ ! -d "dev_keys" ] && [ ! -d "encrypted_dev_keys" ]; then
    pixi run setup-dev-security || true
    echo "✅ Security keys generated"
else
    echo "   Security keys already exist"
fi
echo ""

# Verify setup
echo "🔍 Verifying setup..."
echo "=============================="

# Check Ollama
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    MODEL_COUNT=$(curl -s http://localhost:11434/api/tags | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('models', [])))" 2>/dev/null || echo "0")
    echo "✅ Ollama: Running with $MODEL_COUNT models"
else
    echo "❌ Ollama: Not responding"
fi

# Check DuckDB
if [ -f "demo_analytics.db" ]; then
    echo "✅ DuckDB: Database ready"
else
    echo "❌ DuckDB: Database not found"
fi

# Check MindsDB
if curl -s http://localhost:47335/ > /dev/null 2>&1; then
    echo "✅ MindsDB: Running on port 47335"
else
    echo "⚠️  MindsDB: Not running (optional)"
fi

# Check sample data
if [ -d "sample_data" ]; then
    FILE_COUNT=$(find sample_data -name "*.csv" | wc -l)
    echo "✅ Sample Data: $FILE_COUNT CSV files"
else
    echo "❌ Sample Data: Not found"
fi

echo "=============================="
echo ""

# Success message
echo "🎉 Setup Complete!"
echo ""
echo "📝 Quick Test Commands:"
echo "   pixi run showcase                # Complete system demo"
echo "   pixi run basic-poem              # Basic security demo"
echo "   pixi run crewai-report-demo      # Business report generation"
echo ""
echo "📚 For more examples, see: examples/"
echo "📖 For documentation, see: docs/"
echo ""
echo "Enjoy using SMCP! 🚀"