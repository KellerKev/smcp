# SMCP Complete Setup Guide

## Prerequisites Installation

### 1. Install Pixi (Package Manager)
```bash
curl -fsSL https://pixi.sh/install.sh | bash
```

### 2. Install Dependencies
```bash
# Clone the repository
git clone https://github.com/KellerKev/smcp.git
cd smcp

# Install all dependencies via pixi
pixi install
```

### 3. Install and Setup Ollama
```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Start Ollama service
ollama serve &

# Pull required models (recommended Qwen models)
ollama pull qwen2.5-coder:7b-instruct-q4_K_M    # Fast, efficient coding model
ollama pull qwen3-coder:30b-a3b-q4_K_M          # Powerful analysis model

# Optional: Legacy models for compatibility
ollama pull tinyllama:latest                     # Lightweight fallback
ollama pull mistral:7b-instruct-q4_K_M          # Alternative reasoning model
```

### 4. Setup DuckDB with Sample Data
```bash
# Generate sample data (creates CSV files)
pixi run python tools/generate_sample_data.py

# Initialize DuckDB and create tables
pixi run python examples/duckdb_integration_example.py

# This creates:
# - demo_analytics.db database
# - Tables: ecommerce_orders, ecommerce_customers, ecommerce_products, ecommerce_reviews
# - Tables: saas_users, saas_subscriptions, saas_support_tickets, saas_usage_metrics  
# - Tables: iot_devices, iot_sensor_readings, iot_alerts
```

### 5. Setup MindsDB (via Docker)
```bash
# Pull MindsDB Docker image
docker pull mindsdb/mindsdb

# Run MindsDB container
docker run -d \
  --name mindsdb_smcp \
  -p 47335:47334 \
  -p 47336:47335 \
  mindsdb/mindsdb

# Verify MindsDB is running
curl http://localhost:47335/
# Should return MindsDB web interface HTML

# Test MindsDB API
pixi run python test_mindsdb.py
```

### 6. Setup Security Keys (Optional - for encrypted demos)
```bash
# Generate ECDH keys for encrypted mode
pixi run generate-ecdh-keys

# Setup development security
pixi run setup-dev-security
```

## Quick Verification

Run this command to verify everything is set up correctly:

```bash
# Create verification script
cat > verify_setup.py << 'EOF'
#!/usr/bin/env python3
import subprocess
import requests
import os
import sys

print("🔍 Verifying SMCP Setup...")
print("=" * 50)

# Check Ollama
try:
    response = requests.get("http://localhost:11434/api/tags", timeout=5)
    models = response.json().get("models", [])
    print(f"✅ Ollama: Running with {len(models)} models")
    required = ["qwen2.5-coder:7b-instruct-q4_K_M", "qwen3-coder:30b-a3b-q4_K_M"]
    for model in required:
        if any(m['name'] == model for m in models):
            print(f"   ✓ {model} installed")
        else:
            print(f"   ❌ {model} missing - run: ollama pull {model}")
except:
    print("❌ Ollama: Not running - run: ollama serve")

# Check DuckDB data
if os.path.exists("demo_analytics.db"):
    print("✅ DuckDB: Database exists")
    if os.path.exists("sample_data/ecommerce/orders.csv"):
        print("   ✓ Sample data generated")
    else:
        print("   ❌ Sample data missing - run: pixi run python tools/generate_sample_data.py")
else:
    print("❌ DuckDB: Database missing - run: pixi run python examples/duckdb_integration_example.py")

# Check MindsDB
try:
    response = requests.get("http://localhost:47335/", timeout=5)
    if response.status_code == 200:
        print("✅ MindsDB: Running on port 47335")
    else:
        print("❌ MindsDB: Not responding correctly")
except:
    print("❌ MindsDB: Not running - see setup instructions")

# Check Python dependencies
try:
    import websockets
    import cryptography
    import jwt
    import aiohttp
    import duckdb
    import crewai
    print("✅ Python: All dependencies installed")
except ImportError as e:
    print(f"❌ Python: Missing dependency - {e}")

print("=" * 50)
print("Setup verification complete!")
EOF

pixi run python verify_setup.py
```

## Running Examples

Once everything is set up, you can run any example:

### Quick Demos (< 10 seconds)
```bash
pixi run showcase                    # Complete system showcase
pixi run python examples/basic/basic_poem_sample.py  # Basic JWT demo
```

### Database Demos
```bash
pixi run python examples/duckdb_integration_example.py    # DuckDB analytics
pixi run python examples/mindsdb_integration_example.py   # MindsDB ML queries
```

### Multi-Agent Demos (30-60 seconds)
```bash
pixi run python examples/basic/basic_a2a_demo.py         # Multi-agent coordination
pixi run python examples/encrypted/encrypted_a2a_demo.py  # Encrypted coordination
pixi run python examples/enterprise_poem_sample.py        # Enterprise features
```

### Business Intelligence Demo
```bash
pixi run crewai-report-demo  # Generate business reports
```

## Troubleshooting

### Ollama Issues
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Restart Ollama
pkill ollama
ollama serve &
```

### MindsDB Issues
```bash
# Check container status
docker ps | grep mindsdb

# View logs
docker logs mindsdb_smcp

# Restart container
docker restart mindsdb_smcp
```

### DuckDB Issues
```bash
# Regenerate sample data
rm -rf sample_data/
pixi run python tools/generate_sample_data.py

# Recreate database
rm demo_analytics.db
pixi run python examples/duckdb_integration_example.py
```

### Port Conflicts
If you get port conflict errors:
- MindsDB HTTP: Change 47335 to another port
- MindsDB MySQL: Change 47336 to another port
- Update examples/mindsdb_integration_example.py with new ports

## Complete Setup in One Script

```bash
#!/bin/bash
# save as setup_all.sh

echo "🚀 Setting up SMCP..."

# Install dependencies
pixi install

# Start Ollama
ollama serve &
sleep 5

# Pull models
ollama pull tinyllama:latest
ollama pull mistral:7b-instruct-q4_K_M

# Generate sample data
pixi run python tools/generate_sample_data.py

# Initialize DuckDB
pixi run python examples/duckdb_integration_example.py

# Start MindsDB
docker run -d --name mindsdb_smcp \
  -p 47335:47334 \
  -p 47336:47335 \
  mindsdb/mindsdb

echo "✅ Setup complete! Run 'pixi run showcase' to test"
```

## Verification Checklist

- [ ] Ollama running (`curl http://localhost:11434/api/tags`)
- [ ] Models installed (`ollama list`)
- [ ] DuckDB database exists (`ls demo_analytics.db`)
- [ ] Sample data generated (`ls sample_data/`)
- [ ] MindsDB running (`docker ps | grep mindsdb`)
- [ ] Dependencies installed (`pixi list`)

## Next Steps

1. Run `pixi run showcase` to see all features
2. Try `pixi run crewai-report-demo` for business reports
3. Explore examples/ directory for more demos
4. Check docs/ for architecture and guides