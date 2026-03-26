# SMCP Architecture Overview

## Table of Contents
1. [Core Concept](#core-concept)
2. [Architecture Comparison](#architecture-comparison)
3. [Data Flow Diagrams](#data-flow-diagrams)
4. [Security Layers](#security-layers)
5. [Multi-Agent Coordination](#multi-agent-coordination)
6. [Integration Points](#integration-points)

## Core Concept

SMCP (Secure Model Context Protocol) builds upon the standard MCP by adding security layers and multi-agent coordination while maintaining full backward compatibility.

### What is MCP?

The Model Context Protocol (MCP) is a standardized protocol for communication between AI models and external tools/resources. It provides:
- Standardized message format
- Tool discovery and invocation
- Resource access patterns
- Stateless request-response model

### What SMCP Adds

```
┌─────────────────────────────────────────────────────────┐
│                    SMCP Architecture                     │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │            Application Layer                      │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │  │
│  │  │ CrewAI   │  │  Ollama  │  │ Custom Apps  │  │  │
│  │  └──────────┘  └──────────┘  └──────────────┘  │  │
│  └──────────────────────────────────────────────────┘  │
│                           │                             │
│  ┌──────────────────────────────────────────────────┐  │
│  │         Agent-to-Agent (A2A) Layer               │  │
│  │  ┌──────────────────────────────────────────┐   │  │
│  │  │  Distributed Registry & Discovery        │   │  │
│  │  ├──────────────────────────────────────────┤   │  │
│  │  │  Task Orchestration & Load Balancing     │   │  │
│  │  ├──────────────────────────────────────────┤   │  │
│  │  │  Multi-Agent Coordination Patterns       │   │  │
│  │  └──────────────────────────────────────────┘   │  │
│  └──────────────────────────────────────────────────┘  │
│                           │                             │
│  ┌──────────────────────────────────────────────────┐  │
│  │            Security Layer                        │  │
│  │  ┌──────────────────────────────────────────┐   │  │
│  │  │   Simple  │  Basic  │ Encrypted │ OAuth2 │   │  │
│  │  ├──────────┴─────────┴───────────┴────────┤   │  │
│  │  │   JWT  │  ECDH  │  AES-256  │  Audit    │   │  │
│  │  └──────────────────────────────────────────┘   │  │
│  └──────────────────────────────────────────────────┘  │
│                           │                             │
│  ┌──────────────────────────────────────────────────┐  │
│  │          MCP Compatibility Layer                 │  │
│  │  ┌──────────────────────────────────────────┐   │  │
│  │  │     Standard MCP Protocol Support        │   │  │
│  │  ├──────────────────────────────────────────┤   │  │
│  │  │     Tool Discovery & Invocation          │   │  │
│  │  ├──────────────────────────────────────────┤   │  │
│  │  │     Resource Access Patterns             │   │  │
│  │  └──────────────────────────────────────────┘   │  │
│  └──────────────────────────────────────────────────┘  │
│                           │                             │
│  ┌──────────────────────────────────────────────────┐  │
│  │            Connector Layer                       │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │  │
│  │  │ DuckDB   │  │Filesystem│  │   Custom     │  │  │
│  │  └──────────┘  └──────────┘  └──────────────┘  │  │
│  └──────────────────────────────────────────────────┘  │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

## Architecture Comparison

### Standard MCP Architecture

```
┌─────────────────────────────────┐
│         AI Model/Client         │
└────────────────┬────────────────┘
                 │
         MCP Protocol
                 │
┌────────────────▼────────────────┐
│         MCP Server              │
│  ┌──────────────────────────┐  │
│  │     Tool Handlers        │  │
│  └──────────────────────────┘  │
└────────────────┬────────────────┘
                 │
┌────────────────▼────────────────┐
│      External Resources         │
└─────────────────────────────────┘

Characteristics:
- Single client-server connection
- No built-in security
- No agent coordination
- Stateless operations
```

### SMCP Enhanced Architecture

```
┌──────────────────────────────────────────────────────┐
│                   SMCP Cluster                       │
├──────────────────────────────────────────────────────┤
│                                                       │
│  ┌─────────────┐     ┌─────────────┐                │
│  │   Agent A   │◄────►│   Agent B   │                │
│  │  (Secured)  │     │  (Secured)  │                │
│  └──────┬──────┘     └──────┬──────┘                │
│         │                    │                        │
│         │   ┌─────────────┐  │                       │
│         └──►│  Registry   │◄─┘                       │
│             │  & Router   │                          │
│             └──────┬──────┘                          │
│                    │                                  │
│         ┌──────────▼───────────┐                     │
│         │   Load Balancer      │                     │
│         └──────────┬───────────┘                     │
│                    │                                  │
│    ┌───────────────┼───────────────┐                 │
│    │               │               │                 │
│  ┌─▼────────┐  ┌──▼────────┐  ┌──▼────────┐        │
│  │ Worker 1 │  │  Worker 2  │  │  Worker N  │        │
│  │(Encrypted)│ │   (JWT)    │  │  (OAuth2)  │        │
│  └──────────┘  └───────────┘  └───────────┘        │
│                                                       │
└──────────────────────────────────────────────────────┘

Characteristics:
- Multi-agent coordination
- Multiple security modes
- Agent discovery & routing
- Stateful coordination
- Load balancing
- Failover support
```

## Data Flow Diagrams

### Standard MCP Data Flow

```
Client                  Server
  │                       │
  ├─── Request ──────────►│
  │                       │
  │                       ├─── Process
  │                       │
  │◄─── Response ─────────┤
  │                       │

Simple request-response pattern
No encryption or authentication
```

### SMCP Secure Data Flow

```
Client                          SMCP Node                    Backend
  │                                │                            │
  ├─── 1. Auth Request ───────────►│                            │
  │     (API Key/JWT)              │                            │
  │                                ├─── 2. Validate             │
  │◄─── 3. Auth Token ─────────────┤                            │
  │     (Signed JWT)               │                            │
  │                                │                            │
  ├─── 4. Encrypted Request ──────►│                            │
  │     (AES-256 + HMAC)           │                            │
  │                                ├─── 5. Decrypt & Verify     │
  │                                │                            │
  │                                ├─── 6. Route to Agent ─────►│
  │                                │                            │
  │                                │◄─── 7. Process & Reply ────┤
  │                                │                            │
  │                                ├─── 8. Encrypt Response     │
  │                                │                            │
  │◄─── 9. Encrypted Response ─────┤                            │
  │     (AES-256 + Signature)      │                            │
  │                                │                            │
  └─── 10. Audit Log ──────────────►                            │

Full encryption and authentication pipeline
Complete audit trail
Secure key exchange (ECDH)
```

### SMCP Multi-Agent Coordination Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    A2A Coordination Flow                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Initiator          Registry         Agent A         Agent B    │
│     │                  │                │               │       │
│     ├── 1. Register ──►│                │               │       │
│     │   Task           │                │               │       │
│     │                  ├── 2. Discover ─►│               │       │
│     │                  │   Agents       │               │       │
│     │                  │                │               │       │
│     │                  ├── 3. Assign ───►│               │       │
│     │                  │   Subtask A    │               │       │
│     │                  │                │               │       │
│     │                  ├── 4. Assign ───────────────────►│       │
│     │                  │   Subtask B    │               │       │
│     │                  │                │               │       │
│     │                  │                ├── 5. Process  │       │
│     │                  │                │   Subtask A   │       │
│     │                  │                │               │       │
│     │                  │                │               ├── 6.  │
│     │                  │                │               │Process│
│     │                  │                │               │Task B │
│     │                  │                │               │       │
│     │                  │                ├── 7. Coordinate       │
│     │                  │                │◄──────────────►│       │
│     │                  │                │   (Optional)   │       │
│     │                  │                │               │       │
│     │                  │◄── 8. Report ──┤               │       │
│     │                  │   Result A     │               │       │
│     │                  │                │               │       │
│     │                  │◄── 9. Report ──────────────────┤       │
│     │                  │   Result B     │               │       │
│     │                  │                │               │       │
│     │◄── 10. Aggregate ┤                │               │       │
│     │    Results       │                │               │       │
│     │                  │                │               │       │
└─────────────────────────────────────────────────────────────────┘

Features:
- Dynamic agent discovery
- Parallel task execution
- Inter-agent coordination
- Result aggregation
- Failure handling
```

## Security Layers

### Security Mode Comparison

```
┌──────────────────────────────────────────────────────────────┐
│                     Security Modes                           │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  Simple Mode (Development)                                   │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Client ──[API Key]──► Server                       │    │
│  │  - Basic API key authentication                     │    │
│  │  - No encryption                                    │    │
│  │  - Fast development iteration                       │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                               │
│  Basic Mode (Testing/Staging)                                │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Client ──[JWT/HTTPS]──► Server                     │    │
│  │  - JWT token authentication                         │    │
│  │  - TLS encryption in transit                        │    │
│  │  - Token refresh mechanism                          │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                               │
│  Encrypted Mode (Production)                                 │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Client ◄──[ECDH]──► Server                         │    │
│  │     └──[AES-256]──┘                                 │    │
│  │  - ECDH key exchange                                │    │
│  │  - AES-256 message encryption                       │    │
│  │  - HMAC message authentication                      │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                               │
│  Enterprise Mode (High Security)                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Client ◄──[OAuth2/SAML]──► Identity Provider       │    │
│  │     └──[Encrypted+Audit]──► Server                  │    │
│  │  - OAuth2/SAML authentication                       │    │
│  │  - Full encryption + audit logs                     │    │
│  │  - Compliance tracking                              │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

## Multi-Agent Coordination

### Traditional A2A vs SMCP A2A

```
Traditional A2A:                    SMCP A2A:
┌──────────────┐                   ┌──────────────────────────┐
│   Agent A    │                   │      Agent Registry      │
└──────┬───────┘                   └────────────┬─────────────┘
       │                                        │
   (hardcoded)                           (dynamic discovery)
       │                                        │
       ▼                                        ▼
┌──────────────┐                   ┌──────────────────────────┐
│   Agent B    │                   │   Load Balanced Pool     │
└──────────────┘                   │  ┌─────┐ ┌─────┐ ┌─────┐│
                                   │  │A1   │ │A2   │ │A3   ││
Problems:                          │  └─────┘ └─────┘ └─────┘│
- No discovery                     └──────────────────────────┘
- No load balancing                
- No failover                      Benefits:
- Tight coupling                   - Automatic discovery
- No security                      - Load distribution
                                   - Failover support
                                   - Loose coupling
                                   - Built-in security
```

### Task Distribution Pattern

```
┌─────────────────────────────────────────────────────────────┐
│                 SMCP Task Distribution                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   Complex Task                                              │
│        │                                                     │
│        ▼                                                     │
│   ┌─────────────┐                                          │
│   │ Orchestrator│                                          │
│   └──────┬──────┘                                          │
│          │                                                  │
│    Decompose into                                          │
│    subtasks                                                │
│          │                                                  │
│    ┌─────┴──────┬──────────┬──────────┐                   │
│    ▼            ▼          ▼          ▼                   │
│  Research    Analysis   Generate   Review                  │
│    Task        Task       Task      Task                   │
│    │            │          │          │                    │
│    ▼            ▼          ▼          ▼                    │
│  Agent Pool  Agent Pool Agent Pool Agent Pool              │
│  ┌─┬─┬─┐    ┌─┬─┬─┐    ┌─┬─┬─┐    ┌─┬─┬─┐              │
│  │││││││    │││││││    │││││││    │││││││              │
│  └─┴─┴─┘    └─┴─┴─┘    └─┴─┴─┘    └─┴─┴─┘              │
│     │           │          │          │                    │
│     └───────────┴──────────┴──────────┘                    │
│                      │                                      │
│                 Aggregate                                   │
│                   Results                                   │
│                      │                                      │
│                  ┌───▼────┐                                │
│                  │ Output │                                │
│                  └────────┘                                │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Integration Points

### How SMCP Integrates with Existing Systems

```
┌──────────────────────────────────────────────────────────────┐
│                    Integration Architecture                  │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │               Existing MCP Clients                   │    │
│  │  (Claude, ChatGPT, Custom Apps)                     │    │
│  └────────────────────┬─────────────────────────────────┘    │
│                       │                                       │
│                       ▼                                       │
│  ┌─────────────────────────────────────────────────────┐    │
│  │            SMCP Compatibility Layer                  │    │
│  │  - Transparent MCP protocol support                 │    │
│  │  - Optional security upgrade negotiation            │    │
│  │  - Backward compatibility maintained                │    │
│  └────────────────────┬─────────────────────────────────┘    │
│                       │                                       │
│           ┌───────────┴───────────┐                          │
│           ▼                       ▼                          │
│  ┌──────────────┐        ┌──────────────┐                  │
│  │ Legacy MCP   │        │  SMCP Mode   │                  │
│  │    Mode      │        │  (Enhanced)  │                  │
│  └──────────────┘        └──────────────┘                  │
│                                   │                          │
│                          ┌────────┴────────┐                 │
│                          ▼                 ▼                 │
│                   ┌──────────┐      ┌──────────┐            │
│                   │ Security │      │   A2A    │            │
│                   │  Layer   │      │  Layer   │            │
│                   └──────────┘      └──────────┘            │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

## Common MCP vs SMCP Features

| Feature | Standard MCP | SMCP |
|---------|--------------|------|
| Tool Discovery | ✅ | ✅ Enhanced with agent capabilities |
| Resource Access | ✅ | ✅ With security policies |
| Message Format | JSON-RPC | JSON-RPC + Optional encryption |
| Authentication | ❌ | ✅ Multiple modes |
| Encryption | ❌ | ✅ AES-256, TLS |
| Multi-Agent | ❌ | ✅ Full A2A coordination |
| Load Balancing | ❌ | ✅ Automatic |
| Audit Logs | ❌ | ✅ Comprehensive |
| Failover | ❌ | ✅ Automatic retry |
| Agent Discovery | ❌ | ✅ Dynamic registry |

## Use Cases

### When to Use Standard MCP
- Simple tool integrations
- Development environments
- Single-user applications
- Low-security requirements
- Prototype development

### When to Use SMCP
- Multi-user environments
- Security-sensitive data
- Complex multi-agent workflows
- Compliance requirements
- Production deployments
- Distributed systems
- High-availability needs

## Migration Path

```
Step 1: Standard MCP
├── Basic tool integration
└── No security

Step 2: SMCP Simple Mode
├── Add API key auth
└── Minimal code changes

Step 3: SMCP Basic Mode
├── JWT authentication
└── HTTPS encryption

Step 4: SMCP Encrypted Mode
├── Full message encryption
└── Key management

Step 5: SMCP Enterprise Mode
├── OAuth2/SAML
├── Audit compliance
└── Multi-tenancy
```