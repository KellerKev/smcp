#!/bin/bash

# SMCP Multi-Agent Demo Script for Asciinema Recording
# This creates a visually engaging demo of SMCP's capabilities

# Color codes for better visual output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Helper function for typing effect
type_command() {
    echo -ne "${GREEN}$ ${NC}"
    echo -n "$1" | while IFS= read -r -n1 char; do
        echo -n "$char"
        sleep 0.05
    done
    echo
    sleep 0.5
}

# Helper function for section headers
show_header() {
    echo
    echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║${CYAN}${BOLD}  $1${NC}${BLUE}║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
    echo
    sleep 1
}

# Clear screen
clear

# Welcome message
echo -e "${CYAN}${BOLD}"
cat << "EOF"
   _____ __  __  _____ _____  
  / ____|  \/  |/ ____|  __ \ 
 | (___ | \  / | |    | |__) |
  \___ \| |\/| | |    |  ___/ 
  ____) | |  | | |____| |     
 |_____/|_|  |_|\_____|_|     
                              
 Secure Model Context Protocol
EOF
echo -e "${NC}"
sleep 2

echo -e "${YELLOW}Welcome to the SMCP Multi-Agent Coordination Demo!${NC}"
echo -e "This demo showcases how SMCP extends MCP with:"
echo -e "  • ${GREEN}✓${NC} Security layers (JWT, encryption)"
echo -e "  • ${GREEN}✓${NC} Multi-agent orchestration"
echo -e "  • ${GREEN}✓${NC} Dynamic task distribution"
echo
sleep 3

# Section 1: Show architecture
show_header "1. SMCP Architecture Overview"

cat << "EOF"
┌──────────────────────────────────────────┐
│          SMCP System Architecture        │
├──────────────────────────────────────────┤
│                                           │
│   Client    ═══►  Security  ═══► A2A     │
│                      Layer       Layer    │
│                        │           │      │
│                        ▼           ▼      │
│                    [JWT Auth]  [Registry] │
│                    [Encrypt]   [Agents]   │
│                                           │
└──────────────────────────────────────────┘
EOF
sleep 3

# Section 2: Start the registry
show_header "2. Starting SMCP Registry & Nodes"

type_command "# Start the distributed registry for agent discovery"
echo -e "${YELLOW}Starting registry server on port 8000...${NC}"
cat << "EOF"
[Registry] Initializing...
[Registry] ✓ Agent discovery service ready
[Registry] ✓ Load balancer configured
[Registry] ✓ Health monitoring active
[Registry] Listening on http://localhost:8000
EOF
sleep 2

echo
type_command "# Launch 3 agent nodes with different capabilities"
echo -e "${YELLOW}Starting agent nodes...${NC}"

echo -e "[${GREEN}Node-1${NC}] Starting Research Agent (specialized in data gathering)..."
echo -e "[${BLUE}Node-2${NC}] Starting Analysis Agent (specialized in processing)..."
echo -e "[${CYAN}Node-3${NC}] Starting Writer Agent (specialized in content generation)..."
sleep 2

echo
echo -e "${GREEN}✓ All nodes registered with discovery service${NC}"
sleep 2

# Section 3: Security demonstration
show_header "3. Security Layer Demonstration"

type_command "# Configure security mode"
cat << "EOF"
Security Configuration:
├── Mode: Basic (JWT + TLS)
├── Encryption: AES-256
├── Auth Token: JWT (RS256)
└── Audit: Enabled
EOF
sleep 2

echo
type_command "# Generate secure connection"
echo -e "${YELLOW}Performing secure handshake...${NC}"
echo "Client => Server: Authentication request"
echo "Server => Client: JWT Token (valid for 3600s)"
echo "Client => Server: Encrypted request"
echo -e "${GREEN}✓ Secure connection established${NC}"
sleep 2

# Section 4: Multi-agent task
show_header "4. Multi-Agent Task Orchestration"

type_command "# Submit complex task: 'Generate AI Security Report'"
echo
echo -e "${YELLOW}Task submitted to orchestrator...${NC}"
sleep 1

cat << "EOF"
┌─────────────────────────────────────┐
│     Task Decomposition              │
├─────────────────────────────────────┤
│  Main Task: AI Security Report      │
│                                      │
│  Subtasks:                          │
│  1. Research current threats        │
│  2. Analyze security patterns       │
│  3. Generate recommendations        │
│  4. Format report                   │
└─────────────────────────────────────┘
EOF
sleep 3

echo
echo -e "${YELLOW}Distributing tasks to specialized agents...${NC}"
echo

# Simulate parallel execution with progress
echo -e "[${GREEN}Research Agent${NC}] Gathering threat intelligence... [░░░░░░░░░░] 0%"
sleep 0.5
echo -e "[${BLUE}Analysis Agent${NC}] Waiting for data..."
sleep 0.5
echo -e "[${CYAN}Writer Agent${NC}] Standing by..."
sleep 1

# Update progress
echo -e "\033[3A" # Move up 3 lines
echo -e "[${GREEN}Research Agent${NC}] Gathering threat intelligence... [████░░░░░░] 40%"
echo -e "[${BLUE}Analysis Agent${NC}] Processing patterns...         [██░░░░░░░░] 20%"
echo -e "[${CYAN}Writer Agent${NC}] Standing by..."
sleep 1

echo -e "\033[3A" # Move up 3 lines
echo -e "[${GREEN}Research Agent${NC}] Gathering threat intelligence... [████████░░] 80%"
echo -e "[${BLUE}Analysis Agent${NC}] Processing patterns...         [██████░░░░] 60%"
echo -e "[${CYAN}Writer Agent${NC}] Drafting sections...           [████░░░░░░] 40%"
sleep 1

echo -e "\033[3A" # Move up 3 lines
echo -e "[${GREEN}Research Agent${NC}] Gathering threat intelligence... [██████████] 100% ✓"
echo -e "[${BLUE}Analysis Agent${NC}] Processing patterns...         [██████████] 100% ✓"
echo -e "[${CYAN}Writer Agent${NC}] Drafting sections...           [██████████] 100% ✓"
sleep 1

echo
echo -e "${GREEN}✓ All agents completed their tasks${NC}"
sleep 2

# Section 5: Results aggregation
show_header "5. Result Aggregation"

cat << "EOF"
Aggregating results from all agents...

Report Structure Generated:
├── Executive Summary
├── Current Threat Landscape (Research Agent)
├── Security Pattern Analysis (Analysis Agent)
├── Recommendations (Writer Agent)
└── Implementation Roadmap

Total processing time: 3.2 seconds
Pages generated: 12
Security score: A+
EOF
sleep 3

# Section 6: Show compatibility
show_header "6. MCP Compatibility"

type_command "# SMCP maintains 100% MCP compatibility"
cat << "EOF"
┌────────────────────────────────┐
│   Protocol Compatibility       │
├────────────────────────────────┤
│ Standard MCP:  ✓ Supported    │
│ MCP + Security: ✓ Enhanced     │
│ Multi-Agent:    ✓ Extended     │
│ Legacy Apps:    ✓ Compatible   │
└────────────────────────────────┘
EOF
sleep 2

# Final summary
show_header "Demo Complete!"

echo -e "${GREEN}${BOLD}Key Takeaways:${NC}"
echo
echo -e "  1. ${CYAN}Security First${NC}: Multiple authentication & encryption modes"
echo -e "  2. ${CYAN}Multi-Agent${NC}: Dynamic discovery and task orchestration"
echo -e "  3. ${CYAN}Performance${NC}: Parallel processing with load balancing"
echo -e "  4. ${CYAN}Compatible${NC}: Works with existing MCP implementations"
echo -e "  5. ${CYAN}Scalable${NC}: Add nodes dynamically as needed"
echo
sleep 3

echo -e "${YELLOW}Learn more:${NC} https://github.com/KellerKev/smcp"
echo
echo -e "${GREEN}Thank you for watching!${NC} 🚀"
echo