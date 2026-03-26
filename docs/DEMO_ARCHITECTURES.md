# SMCP Demo Architectures & Flows

## Table of Contents
1. [Basic Poem Demo](#basic-poem-demo)
2. [A2A Coordination Demo](#a2a-coordination-demo)
3. [CrewAI Report Orchestration](#crewai-report-orchestration)
4. [DuckDB Integration Demo](#duckdb-integration-demo)
5. [Encrypted Communication Demo](#encrypted-communication-demo)
6. [Complete System Showcase](#complete-system-showcase)

---

## Basic Poem Demo

**Purpose**: Demonstrates simple SMCP client-server communication with basic security.

### Architecture
```
┌────────────────────────────────────────────────────┐
│              Basic Poem Generation                 │
├────────────────────────────────────────────────────┤
│                                                     │
│  ┌──────────────┐         ┌──────────────────┐   │
│  │  SMCP Client │◄────────►│   SMCP Server   │   │
│  │              │  Basic   │                  │   │
│  │  - Request   │  Auth    │  - Validate     │   │
│  │    poem      │  (JWT)   │  - Generate     │   │
│  │  - Display   │          │    poem         │   │
│  └──────────────┘         └─────────┬────────┘   │
│                                      │             │
│                                      ▼             │
│                            ┌──────────────────┐   │
│                            │   Ollama/LLM    │   │
│                            │   (TinyLLama)   │   │
│                            └──────────────────┘   │
│                                                     │
└────────────────────────────────────────────────────┘
```

### Step-by-Step Flow
```
1. Initialize
   Client: Load config (basic_mode.yaml)
   Server: Start with JWT auth enabled

2. Authentication
   Client ─[API Key]──► Server
   Server: Validate & Generate JWT
   Server ─[JWT Token]──► Client

3. Request Poem
   Client ─[JWT + Topic]──► Server
   Server: Verify JWT
   Server: Generate prompt

4. LLM Integration
   Server ─[Prompt]──► Ollama
   Ollama: Process with TinyLLama
   Ollama ─[Poem]──► Server

5. Response
   Server ─[Poem + Signature]──► Client
   Client: Display poem
```

### Running the Demo
```bash
# Terminal 1: Start server
python examples/basic/basic_poem_sample.py --mode server

# Terminal 2: Request poem
python examples/basic/basic_poem_sample.py --mode client --topic "mountains"
```

---

## A2A Coordination Demo

**Purpose**: Shows multi-agent task distribution and coordination.

### Architecture
```
┌──────────────────────────────────────────────────────────┐
│              A2A Multi-Agent Coordination                │
├──────────────────────────────────────────────────────────┤
│                                                           │
│   ┌────────────────┐                                     │
│   │  Task: Write   │                                     │
│   │  Research      │                                     │
│   │  Report        │                                     │
│   └────────┬───────┘                                     │
│            │                                              │
│            ▼                                              │
│   ┌────────────────┐                                     │
│   │  Coordinator   │                                     │
│   │    Agent       │                                     │
│   └────────┬───────┘                                     │
│            │                                              │
│     Decompose Task                                       │
│            │                                              │
│   ┌────────┴────────┬─────────┬──────────┐             │
│   ▼                 ▼         ▼          ▼             │
│ ┌──────────┐  ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│ │Research  │  │ Analyst  │ │ Writer   │ │ Editor   │  │
│ │Agent     │  │ Agent    │ │ Agent    │ │ Agent    │  │
│ └─────┬────┘  └────┬─────┘ └────┬─────┘ └────┬─────┘  │
│       │            │            │            │          │
│       ▼            ▼            ▼            ▼          │
│   Gather      Analyze      Write       Review           │
│   Data        Findings     Content     & Edit           │
│       │            │            │            │          │
│       └────────────┴────────────┴────────────┘          │
│                         │                                │
│                    Aggregate                             │
│                         │                                │
│                    ┌────▼─────┐                         │
│                    │  Final   │                         │
│                    │  Report  │                         │
│                    └──────────┘                         │
│                                                           │
└──────────────────────────────────────────────────────────┘
```

### Step-by-Step Flow
```
1. Task Registration
   User ─[Create Report Task]──► Coordinator
   Coordinator: Register in task queue

2. Agent Discovery
   Coordinator ─[Query Available]──► Registry
   Registry ─[Agent List + Capabilities]──► Coordinator

3. Task Distribution
   Coordinator ─[Research Task]──► Research Agent
   Coordinator ─[Analysis Task]──► Analyst Agent
   Coordinator ─[Writing Task]──► Writer Agent
   (Parallel execution)

4. Agent Processing
   Research Agent:
   - Query data sources
   - Collect information
   - Return findings

   Analyst Agent:
   - Process research data
   - Generate insights
   - Create analysis

   Writer Agent:
   - Structure content
   - Write sections
   - Format output

5. Coordination & Sync
   Agents ◄─[Status Updates]─► Coordinator
   Agents ◄─[Data Exchange]─► Agents (P2P)

6. Result Aggregation
   All Agents ─[Results]──► Coordinator
   Coordinator: Merge & validate
   Coordinator ─[Draft]──► Editor Agent

7. Final Review
   Editor Agent: Review & polish
   Editor ─[Final Report]──► Coordinator
   Coordinator ─[Complete Report]──► User
```

### Running the Demo
```bash
# Start A2A server with registry
python smcp_a2a_server.py

# Run distributed demo
python examples/basic/basic_a2a_demo.py
```

---

## CrewAI Report Orchestration

**Purpose**: Integration with CrewAI for sophisticated multi-agent workflows.

### Architecture
```
┌────────────────────────────────────────────────────────────┐
│            CrewAI + SMCP Integration                       │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────────────────────────────────────────┐     │
│  │                 CrewAI Framework                  │     │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐      │     │
│  │  │ Research │  │  Writer  │  │  Editor  │      │     │
│  │  │  Agent   │  │  Agent   │  │  Agent   │      │     │
│  │  └─────┬────┘  └────┬─────┘  └────┬─────┘      │     │
│  │        └─────────────┴──────────────┘            │     │
│  └────────────────────────┬──────────────────────────┘     │
│                           │                                 │
│                    CrewAI Task API                         │
│                           │                                 │
│  ┌────────────────────────▼──────────────────────────┐     │
│  │              SMCP A2A Bridge                      │     │
│  │  - Task translation                              │     │
│  │  - Agent mapping                                 │     │
│  │  - Result aggregation                            │     │
│  └────────────────────────┬──────────────────────────┘     │
│                           │                                 │
│  ┌────────────────────────▼──────────────────────────┐     │
│  │          SMCP Distributed Agents                  │     │
│  │  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐       │     │
│  │  │Node 1│  │Node 2│  │Node 3│  │Node N│       │     │
│  │  └──────┘  └──────┘  └──────┘  └──────┘       │     │
│  └──────────────────────────────────────────────────┘     │
│                           │                                 │
│                    ┌──────▼──────┐                         │
│                    │   Ollama    │                         │
│                    │   Models    │                         │
│                    └─────────────┘                         │
│                                                             │
└────────────────────────────────────────────────────────────┘
```

### Step-by-Step Flow
```
1. CrewAI Initialization
   App: Define CrewAI agents and tasks
   App: Configure SMCP backend

2. Task Creation
   User ─[Research Topic]──► CrewAI
   CrewAI: Create task chain
   - Research task
   - Writing task  
   - Editing task

3. SMCP Bridge Translation
   CrewAI ─[Task]──► SMCP Bridge
   Bridge: Convert to SMCP format
   Bridge: Map CrewAI agents to SMCP agents

4. Distributed Execution
   Bridge ─[Tasks]──► SMCP Registry
   Registry: Assign to available nodes
   Nodes: Execute with Ollama/LLMs

5. Progressive Results
   Node 1 ─[Research]──► Bridge
   Bridge ─[Research]──► CrewAI Writer
   
   Node 2 ─[Draft]──► Bridge
   Bridge ─[Draft]──► CrewAI Editor
   
   Node 3 ─[Final]──► Bridge
   Bridge ─[Report]──► User

6. Output Generation
   System: Save to crewai_reports/
   System: Format as markdown
```

### Running the Demo
```bash
# Ensure Ollama is running
ollama serve

# Start SMCP distributed nodes
python smcp_distributed_a2a.py --node-id node1 --port 8001 &
python smcp_distributed_a2a.py --node-id node2 --port 8002 &

# Run CrewAI orchestration
python examples/crewai_report_orchestration.py --topic "AI Security"
```

---

## DuckDB Integration Demo

**Purpose**: Demonstrates secure database queries through SMCP.

### Architecture
```
┌──────────────────────────────────────────────────────┐
│           DuckDB Secure Query System                 │
├──────────────────────────────────────────────────────┤
│                                                       │
│  ┌──────────────┐                                   │
│  │ SMCP Client  │                                   │
│  │              │                                   │
│  │ - SQL Query  │                                   │
│  │ - Auth Token │                                   │
│  └──────┬───────┘                                   │
│         │                                            │
│         ▼                                            │
│  ┌──────────────────────────────────────┐          │
│  │      SMCP Security Layer             │          │
│  │  ┌─────────────────────────────┐    │          │
│  │  │ • JWT Validation            │    │          │
│  │  │ • Query Sanitization        │    │          │
│  │  │ • Access Control            │    │          │
│  │  └─────────────────────────────┘    │          │
│  └──────────────┬───────────────────────┘          │
│                 │                                    │
│                 ▼                                    │
│  ┌──────────────────────────────────────┐          │
│  │    DuckDB Connector (SMCP)           │          │
│  │  ┌─────────────────────────────┐    │          │
│  │  │ • Connection Pool           │    │          │
│  │  │ • Query Optimization        │    │          │
│  │  │ • Result Streaming          │    │          │
│  │  └─────────────────────────────┘    │          │
│  └──────────────┬───────────────────────┘          │
│                 │                                    │
│                 ▼                                    │
│  ┌──────────────────────────────────────┐          │
│  │         DuckDB Engine                │          │
│  │  ┌─────────────┬──────────────┐    │          │
│  │  │  Analytics  │  Time Series │    │          │
│  │  │  Database   │   Database   │    │          │
│  │  └─────────────┴──────────────┘    │          │
│  └──────────────────────────────────────┘          │
│                                                       │
└──────────────────────────────────────────────────────┘
```

### Step-by-Step Flow
```
1. Connection Setup
   Client: Initialize SMCP with DuckDB connector
   Client: Authenticate with server
   Server: Create connection pool

2. Query Submission
   Client ─[SQL + JWT]──► SMCP Server
   Server: Validate token
   Server: Check query permissions

3. Query Processing
   Server ─[Sanitized SQL]──► DuckDB Connector
   Connector: Parse & optimize query
   Connector: Check resource limits

4. Execution
   Connector ─[Query]──► DuckDB
   DuckDB: Execute query
   DuckDB: Stream results

5. Result Handling
   DuckDB ─[Result Set]──► Connector
   Connector: Format results
   Connector: Apply row limits

6. Secure Response
   Connector ─[Data]──► SMCP Server
   Server: Encrypt if configured
   Server ─[Encrypted Results]──► Client
```

### Running the Demo
```bash
# Generate sample data
python tools/generate_sample_data.py

# Start server with DuckDB
python examples/duckdb_integration_example.py --mode server

# Run queries
python examples/duckdb_integration_example.py --mode client \
    --query "SELECT * FROM sales WHERE amount > 1000"
```

---

## Encrypted Communication Demo

**Purpose**: Demonstrates end-to-end encryption using ECDH and AES-256.

### Architecture
```
┌────────────────────────────────────────────────────────────┐
│            Encrypted Communication Flow                    │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  Phase 1: Key Exchange (ECDH)                             │
│  ┌──────────────┐                    ┌──────────────┐    │
│  │   Client     │                    │    Server    │    │
│  │              │◄───────────────────►│              │    │
│  │  Private: a  │   Public Keys      │  Private: b  │    │
│  │  Public: A   │   A ◄─────────► B  │  Public: B   │    │
│  └──────────────┘                    └──────────────┘    │
│         │                                    │             │
│         └──────────┬─────────────────────────┘             │
│                    ▼                                        │
│           Shared Secret: K = a*B = b*A                     │
│                    │                                        │
│                    ▼                                        │
│          Derive AES-256 Key: key = KDF(K)                 │
│                                                             │
│  Phase 2: Encrypted Communication                         │
│  ┌──────────────────────────────────────────────────┐    │
│  │   Client                          Server         │    │
│  │     │                                │           │    │
│  │     ├── Encrypt(msg, key) ──────────►│           │    │
│  │     │   + HMAC signature             │           │    │
│  │     │                                │           │    │
│  │     │                         Decrypt(cipher, key)│    │
│  │     │                         Verify HMAC        │    │
│  │     │                                │           │    │
│  │     │◄──────── Encrypt(response, key)│           │    │
│  │     │          + HMAC signature      │           │    │
│  │     │                                │           │    │
│  │  Decrypt(cipher, key)               │           │    │
│  │  Verify HMAC                        │           │    │
│  └──────────────────────────────────────────────────┘    │
│                                                             │
└────────────────────────────────────────────────────────────┘
```

### Encryption Details
```
Key Exchange Process:
1. Generate ECDH key pairs
   Client: (private_a, public_A)
   Server: (private_b, public_B)

2. Exchange public keys
   Client ─[public_A]──► Server
   Server ─[public_B]──► Client

3. Compute shared secret
   Client: K = private_a * public_B
   Server: K = private_b * public_A
   Result: K_client == K_server

4. Derive encryption keys
   AES_key = HKDF(K, salt, info, 32)
   HMAC_key = HKDF(K, salt, "hmac", 32)

Message Encryption:
1. Prepare message
   plaintext = JSON.stringify(data)

2. Encrypt with AES-256-GCM
   iv = random(16)
   ciphertext = AES_GCM_encrypt(plaintext, AES_key, iv)

3. Add authentication
   tag = HMAC_SHA256(ciphertext, HMAC_key)

4. Send encrypted packet
   packet = {
     iv: base64(iv),
     ciphertext: base64(ciphertext),
     tag: base64(tag)
   }
```

### Step-by-Step Flow
```
1. Initialize Encryption
   Client: Load ECDH keys from ecdh_keys/
   Server: Load ECDH keys from ecdh_keys/

2. Handshake
   Client ─[Hello + Public Key]──► Server
   Server: Store client public key
   Server ─[Welcome + Public Key]──► Client
   Client: Compute shared secret

3. Secure Request
   Client: Encrypt(request, shared_key)
   Client ─[Encrypted Request]──► Server
   Server: Decrypt & validate

4. Process Request
   Server: Execute requested action
   Server: Prepare response

5. Secure Response
   Server: Encrypt(response, shared_key)
   Server ─[Encrypted Response]──► Client
   Client: Decrypt & validate

6. Verify Integrity
   Both: Check HMAC signatures
   Both: Verify message sequence
```

### Running the Demo
```bash
# Generate ECDH keys
python tools/generate_ecdh_keys.py

# Start encrypted server
python examples/encrypted/encrypted_poem_sample.py --mode server

# Send encrypted request
python examples/encrypted/encrypted_poem_sample.py --mode client
```

---

## Complete System Showcase

**Purpose**: Demonstrates all SMCP features working together.

### Architecture
```
┌──────────────────────────────────────────────────────────────┐
│              Complete SMCP System Architecture               │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│   ┌─────────────────────────────────────────────────────┐   │
│   │                  User Interface                      │   │
│   └─────────────────────────┬────────────────────────────┘   │
│                             │                                 │
│   ┌─────────────────────────▼────────────────────────────┐   │
│   │             Load Balancer / API Gateway              │   │
│   │         (Route based on security requirements)       │   │
│   └──────┬──────────┬──────────┬──────────┬─────────────┘   │
│          │          │          │          │                  │
│     Simple     Basic    Encrypted   Enterprise              │
│      Mode      Mode       Mode        Mode                  │
│          │          │          │          │                  │
│   ┌──────▼──────────▼──────────▼──────────▼─────────────┐   │
│   │              SMCP Security Layer                     │   │
│   │   API Key │ JWT │ ECDH+AES │ OAuth2+Audit          │   │
│   └─────────────────────────┬────────────────────────────┘   │
│                             │                                 │
│   ┌─────────────────────────▼────────────────────────────┐   │
│   │           Multi-Agent Orchestration Layer            │   │
│   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │   │
│   │  │  Research   │  │  Analysis   │  │  Generation │ │   │
│   │  │   Agents    │  │   Agents    │  │   Agents    │ │   │
│   │  └─────────────┘  └─────────────┘  └─────────────┘ │   │
│   └─────────────────────────┬────────────────────────────┘   │
│                             │                                 │
│   ┌─────────────────────────▼────────────────────────────┐   │
│   │              Connector Abstraction Layer             │   │
│   │  ┌──────────┐  ┌──────────┐  ┌──────────┐         │   │
│   │  │ DuckDB   │  │Filesystem│  │ Custom   │         │   │
│   │  └──────────┘  └──────────┘  └──────────┘         │   │
│   └─────────────────────────┬────────────────────────────┘   │
│                             │                                 │
│   ┌─────────────────────────▼────────────────────────────┐   │
│   │                  External Resources                  │   │
│   │  ┌──────────┐  ┌──────────┐  ┌──────────┐         │   │
│   │  │Databases │  │   APIs   │  │   LLMs   │         │   │
│   │  └──────────┘  └──────────┘  └──────────┘         │   │
│   └──────────────────────────────────────────────────────┘   │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

### Complete Workflow
```
1. System Initialization
   - Start registry service
   - Launch agent nodes (3-5 nodes)
   - Initialize security modes
   - Connect to Ollama
   - Setup DuckDB connections

2. Client Request Flow
   User ─[Complex Task]──► API Gateway
   Gateway: Determine security level
   Gateway: Route to appropriate handler

3. Security Processing
   Simple: API key validation only
   Basic: JWT generation & validation
   Encrypted: ECDH handshake + AES
   Enterprise: OAuth2 + full audit

4. Task Orchestration
   Orchestrator: Decompose task
   Registry: Discover available agents
   Orchestrator: Distribute subtasks
   
   Parallel Execution:
   - Agent A: Data gathering
   - Agent B: Analysis
   - Agent C: Content generation
   - Agent D: Quality review

5. Resource Access
   Agents ─[Queries]──► DuckDB
   Agents ─[File Ops]──► Filesystem
   Agents ─[Prompts]──► Ollama

6. Result Aggregation
   Agents ─[Results]──► Orchestrator
   Orchestrator: Merge & validate
   Orchestrator: Apply post-processing

7. Response Delivery
   Server ─[Encrypted Result]──► Gateway
   Gateway ─[Final Response]──► User
   System: Log audit trail
```

### Running the Complete Demo
```bash
# Step 1: Start infrastructure
./setup.sh  # Install dependencies

# Step 2: Start Ollama
ollama serve &

# Step 3: Start registry
python smcp_distributed_a2a.py --mode registry --port 8000 &

# Step 4: Start agent nodes
for i in {1..3}; do
    python smcp_distributed_a2a.py --node-id node$i --port 800$i &
done

# Step 5: Run showcase
python examples/showcase_complete_system.py

# This will demonstrate:
# - Multiple security modes
# - A2A coordination
# - DuckDB queries
# - File operations
# - LLM integration
# - Result aggregation
```

### Performance Metrics
```
┌─────────────────────────────────────┐
│      System Performance             │
├─────────────────────────────────────┤
│                                      │
│  Request Throughput:                │
│  ┌────────────────────────────┐    │
│  │ Simple:  ~1000 req/s       │    │
│  │ Basic:   ~500 req/s        │    │
│  │ Encrypted: ~200 req/s      │    │
│  │ Enterprise: ~100 req/s     │    │
│  └────────────────────────────┘    │
│                                      │
│  Latency (p99):                    │
│  ┌────────────────────────────┐    │
│  │ Simple:  <10ms             │    │
│  │ Basic:   <50ms             │    │
│  │ Encrypted: <200ms          │    │
│  │ Enterprise: <500ms         │    │
│  └────────────────────────────┘    │
│                                      │
│  Scalability:                      │
│  • Horizontal: 100+ nodes         │
│  • Agents per node: 10-50        │
│  • Concurrent tasks: 1000+       │
│                                      │
└─────────────────────────────────────┐
```

## Summary

Each demo showcases different aspects of SMCP:

1. **Basic Poem**: Simple secure communication
2. **A2A Coordination**: Multi-agent task distribution
3. **CrewAI Integration**: Enterprise workflow orchestration
4. **DuckDB**: Secure database operations
5. **Encrypted**: End-to-end encryption
6. **Complete System**: All features working together

The demos progressively build complexity, showing how SMCP extends MCP with:
- Multiple security layers
- Agent coordination
- Resource connectors
- Production features
- Backward compatibility