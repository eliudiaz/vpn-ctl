# Documentation Index

Quick reference for all vpn-ctl documentation.

## Getting Started (Start Here!)

| Document | Purpose | Audience |
|----------|---------|----------|
| [README.md](./README.md) | Quick start & feature overview | Users, DevOps, Everyone |
| [ARCHITECTURE.md](./reference/ARCHITECTURE.md) | System design & architecture | Developers, Architects |
| [VPN_POOL_GUIDE.md](./VPN_POOL_GUIDE.md) | VPN pool management guide | Operators, DevOps |

## Development & Contributing

| Document | Purpose | Audience |
|----------|---------|----------|
| [DEVELOPMENT.md](./development/DEVELOPMENT.md) | Developer guide & workflow | Contributors |
| [ARCHITECTURE.md](./reference/ARCHITECTURE.md) | System design & design decisions | Developers |

---

## Document Descriptions

### README.md
**Purpose:** Quick start and feature overview  
**Topics:**
- Installation and quick start
- Feature list
- Available commands
- Configuration examples
- Troubleshooting

**Start here if:** You're new to vpn-ctl

---

### ARCHITECTURE.md
**Purpose:** Complete system design documentation  
**Topics:**
- Layered architecture overview
- Component responsibilities
- Data flow examples
- Design patterns
- Provider agnosticism
- Testing strategy

**Start here if:** You want to understand the design or add features

---

### VPN_POOL_GUIDE.md
**Purpose:** VPN pool and peer management guide  
**Topics:**
- Pool overview and management
- Peer lifecycle management
- Configuration best practices
- Scaling considerations
- Troubleshooting

**Start here if:** You need to manage VPN peers and pools

---

### DEVELOPMENT.md
**Purpose:** Developer guide for contributing to vpn-ctl  
**Topics:**
- Setup instructions
- Architecture overview for developers
- Project structure
- Development workflow
- Testing guidelines
- Code style and conventions
- Common development tasks
- Debugging tips

**Start here if:** You want to contribute or modify vpn-ctl

---

## Directory Structure

```
vpn-ctl/
├── domain/              Business logic (provider-agnostic)
├── infrastructure/      Infrastructure adapters (Pulumi, AWS)
├── application/         Application services
├── presentation/        CLI interface
├── vpnctl/              CLI commands
├── tests/               Test suite
├── config/              Configuration templates
├── scripts/             Utility scripts
└── docs/
    ├── README.md                 ← START HERE
    ├── DOCUMENTATION_INDEX.md    (this file)
    ├── VPN_POOL_GUIDE.md         (Pool management)
    ├── architecture/             (Architecture docs)
    ├── development/              (Developer guide)
    └── reference/                (Technical reference)
```

## Learning Paths

### For Users
1. [README.md](./README.md) - Quick start
2. [VPN_POOL_GUIDE.md](./VPN_POOL_GUIDE.md) - Pool management

### For Developers
1. [README.md](./README.md) - Quick overview
2. [ARCHITECTURE.md](./reference/ARCHITECTURE.md) - Understand design
3. [DEVELOPMENT.md](./development/DEVELOPMENT.md) - Setup and workflow

### For Architects
1. [ARCHITECTURE.md](./reference/ARCHITECTURE.md) - System design
2. [DEVELOPMENT.md](./development/DEVELOPMENT.md) - Extensibility

## Key Concepts

### Layered Architecture
Domain logic is completely separated from infrastructure concerns. This enables swapping providers without changing business logic.

### Mock Peer Configuration
The system uses generic mock peers (mock-peer, example-peer) for examples and testing, making it easy to adapt to your infrastructure.

### Provider Agnosticism
Domain logic has zero IaC dependencies. Infrastructure providers are pluggable adapters.

## Common Tasks

**I want to...**

- Get started with vpn-ctl → Read [README.md](./README.md)
- Manage VPN peers → Read [VPN_POOL_GUIDE.md](./VPN_POOL_GUIDE.md)
- Understand the design → Read [ARCHITECTURE.md](./reference/ARCHITECTURE.md)
- Contribute code → Read [DEVELOPMENT.md](./development/DEVELOPMENT.md)

---

**Last Updated:** June 4, 2026  
**Version:** 1.0.0  
**Status:** Cleaned & Simplified ✅
