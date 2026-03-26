#!/bin/bash

# SMCP Setup Script
echo "🚀 Setting up SMCP (Secure Model Context Protocol)"
echo "=================================================="

# Check Python version
python_version=$(python3 --version 2>&1 | grep -oP '(?<=Python )\d+\.\d+')
required_version="3.8"

if [[ $(echo "$python_version >= $required_version" | bc -l) -eq 1 ]]; then
    echo "✅ Python version $python_version is compatible"
else
    echo "❌ Python 3.8+ is required. Current version: $python_version"
    exit 1
fi

# Install dependencies
echo ""
echo "📦 Installing dependencies..."

if command -v pixi &> /dev/null; then
    echo "Using pixi package manager..."
    pixi install
else
    echo "Using pip..."
    pip install -r requirements.txt
fi

# Check for Ollama
echo ""
echo "🤖 Checking for Ollama..."
if command -v ollama &> /dev/null; then
    echo "✅ Ollama is installed"
    echo ""
    echo "Installing recommended models..."
    ollama pull tinyllama:latest
    ollama pull mistral:7b-instruct-q4_K_M
else
    echo "⚠️  Ollama not found. Install from https://ollama.ai for AI features"
fi

# Generate sample data
echo ""
echo "📊 Generating sample data..."
if [ -f tools/generate_sample_data.py ]; then
    python3 tools/generate_sample_data.py
    echo "✅ Sample data generated"
else
    echo "⚠️  Sample data generator not found"
fi

# Setup development keys (optional)
echo ""
echo "🔑 Setting up development keys..."
if [ -f tools/setup_dev_security.py ]; then
    python3 tools/setup_dev_security.py
    echo "✅ Development keys created"
else
    mkdir -p dev_keys ecdh_keys
    echo "⚠️  Using default key directories"
fi

# Create output directories
echo ""
echo "📁 Creating output directories..."
mkdir -p crewai_reports local_poems sample_data

echo ""
echo "✅ Setup complete!"
echo ""
echo "🎯 Quick Start:"
echo "   1. Start Ollama: ollama serve"
echo "   2. Run basic demo: python examples/basic/basic_poem_sample.py"
echo "   3. See all examples: ls examples/"
echo ""
echo "📚 Documentation: See README.md for detailed information"