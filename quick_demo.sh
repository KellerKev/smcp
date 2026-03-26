#!/bin/bash

# Quick SMCP Demo for Asciinema
clear

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}SMCP - Secure Model Context Protocol Demo${NC}"
echo "=========================================="
echo
sleep 1

echo -e "${YELLOW}1. Security Modes:${NC}"
echo "   • Simple: API Key authentication"
echo "   • Basic: JWT tokens"
echo "   • Encrypted: AES-256 + ECDH"
echo "   • Enterprise: OAuth2 + Audit"
echo
sleep 2

echo -e "${YELLOW}2. Starting Multi-Agent System:${NC}"
echo
echo "$ python smcp_server.py --mode=registry"
echo "[Registry] Started on port 8000"
sleep 1
echo
echo "$ python smcp_agent.py --id=research"
echo "[Agent] Research agent registered"
sleep 1
echo
echo "$ python smcp_agent.py --id=analysis"  
echo "[Agent] Analysis agent registered"
sleep 1
echo
echo "$ python smcp_agent.py --id=writer"
echo "[Agent] Writer agent registered"
echo
sleep 1

echo -e "${YELLOW}3. Executing Multi-Agent Task:${NC}"
echo
echo "$ python smcp_client.py --task='Generate Security Report'"
echo
echo "Task Distribution:"
echo "├── Research Agent: Gathering data..."
sleep 1
echo "├── Analysis Agent: Processing patterns..."
sleep 1
echo "├── Writer Agent: Generating content..."
sleep 1
echo "└── Complete: Report generated (3.2s)"
echo
sleep 1

echo -e "${GREEN}✓ Task completed successfully!${NC}"
echo
echo -e "${YELLOW}Key Features:${NC}"
echo "• 100% MCP compatible"
echo "• Security layers (JWT, encryption)"
echo "• Multi-agent orchestration"
echo "• Dynamic load balancing"
echo
echo "GitHub: https://github.com/KellerKev/smcp"
echo