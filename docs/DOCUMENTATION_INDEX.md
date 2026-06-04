# Documentation Index

Quick reference for all vpn-ctl documentation.

## Getting Started (Start Here!)

| Document | Purpose | Audience |
|----------|---------|----------|
| [README.md](./README.md) | Quick start & feature overview | Users, DevOps, Everyone |
| [CLI.md](./CLI.md) | Command reference with examples | CLI users |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | System design & 8-layer architecture | Developers, Architects |

## Operations

| Document | Purpose | Audience |
|----------|---------|----------|
| [STATE_EXTRACTION.md](./STATE_EXTRACTION.md) | Safe migration from monolith to per-peer | Operators, DevOps |
| [CLI.md](./CLI.md) | Detailed command reference | CLI users |

## Development

| Document | Purpose | Audience |
|----------|---------|----------|
| [DEVELOPMENT.md](./DEVELOPMENT.md) | Developer guide & workflow | Contributors |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | System design & design decisions | Developers |
| [pyproject.toml](./pyproject.toml) | Project configuration | Python developers |
| [Makefile](./Makefile) | Development automation | Developers |

## Project Status

| Document | Purpose |
|----------|---------|
| [COMPLETION_SUMMARY.md](./COMPLETION_SUMMARY.md) | What's been built, what's planned |

---

## Document Descriptions

### README.md
**Purpose:** Quick start and feature overview  
**Length:** ~200 lines  
**Topics:**
- Installation and quick start
- Feature list
- Available commands
- Configuration
- Troubleshooting

**Start here if:** You're new to vpn-ctl

---

### ARCHITECTURE.md
**Purpose:** Complete system design documentation  
**Length:** ~300 lines  
**Topics:**
- 8-layer orthogonal design
- Layer responsibilities and dependencies
- Data flow examples
- Dependency injection pattern
- SOLID principles applied
- Type safety approach
- Provider agnosticism
- Testing strategy
- Future extensions

**Start here if:** You want to understand the design or add features

---

### CLI.md
**Purpose:** Complete command reference  
**Length:** ~250 lines  
**Topics:**
- All peer commands (add, deploy, destroy, status, list)
- Spec commands (validate, sync)
- Tunnel monitoring
- Provider commands
- Configuration files
- Examples and use cases
- Troubleshooting

**Start here if:** You need to use the CLI or debug issues

---

### STATE_EXTRACTION.md
**Purpose:** Safe migration from monolithic to per-peer stacks  
**Length:** ~400 lines  
**Topics:**
- Current vs target state
- 7-phase extraction process
- Pre-extraction validation (8 checks)
- Full backup procedure
- Dry-run testing
- Resource count verification
- Post-extraction checklist (20 verifications)
- Emergency rollback
- Timeline and tools reference

**Start here if:** You need to migrate from dev stack to per-peer stacks

---

### DEVELOPMENT.md
**Purpose:** Developer guide for contributing to vpn-ctl  
**Length:** ~300 lines  
**Topics:**
- Setup instructions
- Architecture overview for developers
- Project structure
- Development workflow (6 steps)
- Testing guidelines and examples
- Code style and conventions
- Adding new providers (Terraform example)
- Common tasks
- Debugging tips
- Deployment checklist

**Start here if:** You want to contribute or modify vpn-ctl

---

### COMPLETION_SUMMARY.md
**Purpose:** Project completion status  
**Length:** ~400 lines  
**Topics:**
- Architecture overview
- Implemented components (by layer)
- Code quality metrics
- What's not yet implemented
- How to continue
- Design decisions
- Enterprise readiness checklist
- Known limitations

**Start here if:** You want to understand what's been built and what's next

---

## Quick Command Reference

```bash
# Installation
make install

# Development
make test              # Run tests
make test-cov         # Tests with coverage
make lint             # Lint check
make format           # Format code
make typecheck        # Type check

# CLI Usage
vpn-ctl peer add                  # Create new peer
vpn-ctl peer deploy PEER          # Deploy peer
vpn-ctl peer list                 # List all peers
vpn-ctl spec validate             # Validate specs
vpn-ctl spec sync                 # Sync specs with state
vpn-ctl tunnel status             # Show tunnel health
vpn-ctl --help                    # Full help
```

## Directory Structure

```
aff-atg/
├── domain/              Business logic (provider-agnostic)
├── infrastructure/      Infrastructure adapters (Pulumi, AWS, YAML)
├── application/         Application services (use cases)
├── presentation/        CLI interface
├── observability/       Logging and audit trails
├── scripts/             Utility scripts
├── tests/               Test suite
├── config/              Configuration files
├── .github/             CI/CD workflows
└── Documentation files:
    ├── README.md                 ← START HERE
    ├── ARCHITECTURE.md           (System design)
    ├── CLI.md                    (Command reference)
    ├── STATE_EXTRACTION.md       (Migration guide)
    ├── DEVELOPMENT.md            (Developer guide)
    ├── COMPLETION_SUMMARY.md     (Project status)
    └── DOCUMENTATION_INDEX.md    (this file)
```

## Learning Path

### For Users
1. [README.md](./README.md) - Quick start
2. [CLI.md](./CLI.md) - Command reference
3. [STATE_EXTRACTION.md](./STATE_EXTRACTION.md) - If migrating stacks

### For Developers
1. [README.md](./README.md) - Quick overview
2. [ARCHITECTURE.md](./ARCHITECTURE.md) - Understand design
3. [DEVELOPMENT.md](./DEVELOPMENT.md) - Setup and workflow
4. [CLI.md](./CLI.md) - For reference

### For Architects
1. [ARCHITECTURE.md](./ARCHITECTURE.md) - System design
2. [COMPLETION_SUMMARY.md](./COMPLETION_SUMMARY.md) - What's implemented
3. [DEVELOPMENT.md](./DEVELOPMENT.md) - Extensibility

### For Operations
1. [README.md](./README.md) - Feature overview
2. [CLI.md](./CLI.md) - Command reference
3. [STATE_EXTRACTION.md](./STATE_EXTRACTION.md) - Migration procedure
4. [DEVELOPMENT.md](./DEVELOPMENT.md) - Troubleshooting section

## File Statistics

| Category | Count | Lines |
|----------|-------|-------|
| Python source code | 30+ files | 2000+ |
| Tests | 5+ files | 300+ |
| Documentation | 6 files | 1500+ |
| Configuration | 5 files | 200+ |
| Scripts | 8 files | 400+ |
| CI/CD | 2 files | 100+ |

**Total:** 56+ files, 4500+ lines

## Key Concepts

### 8-Layer Architecture
Domain logic is completely separated from infrastructure concerns. This enables swapping Pulumi → Terraform → CloudFormation without changing business logic.

See: [ARCHITECTURE.md - Layer Architecture](./ARCHITECTURE.md#layer-architecture)

### Per-Peer Isolation
Each VPN peer has its own Pulumi stack, enabling independent lifecycle management and low-risk deployments.

See: [STATE_EXTRACTION.md - Target State](./STATE_EXTRACTION.md#target-state-per-peer-isolated)

### Zero-Loss State Extraction
Safe migration from monolithic stack to per-peer stacks with backups, dry-runs, and multi-phase verification.

See: [STATE_EXTRACTION.md](./STATE_EXTRACTION.md)

### Provider Agnosticism
Domain logic has zero IaC dependencies. Infrastructure providers are pluggable adapters.

See: [ARCHITECTURE.md - Provider Agnosticism](./ARCHITECTURE.md#provider-agnosticism)

### SOLID Principles
Professional code following all five SOLID principles for maintainability and extensibility.

See: [ARCHITECTURE.md - SOLID Principles](./ARCHITECTURE.md#solid-principles)

## Common Tasks

**I want to...**

- Use vpn-ctl → Read [README.md](./README.md) and [CLI.md](./CLI.md)
- Add a new command → Read [DEVELOPMENT.md](./DEVELOPMENT.md#adding-a-new-command)
- Add a new provider → Read [DEVELOPMENT.md](./DEVELOPMENT.md#adding-a-new-provider)
- Understand the design → Read [ARCHITECTURE.md](./ARCHITECTURE.md)
- Migrate from dev stack → Read [STATE_EXTRACTION.md](./STATE_EXTRACTION.md)
- Fix a bug → Read [DEVELOPMENT.md](./DEVELOPMENT.md#debugging)
- Understand what's built → Read [COMPLETION_SUMMARY.md](./COMPLETION_SUMMARY.md)

## Support

- **General questions:** See [CLI.md](./CLI.md#troubleshooting)
- **Design questions:** See [ARCHITECTURE.md](./ARCHITECTURE.md)
- **Development questions:** See [DEVELOPMENT.md](./DEVELOPMENT.md)
- **Operations questions:** See [STATE_EXTRACTION.md](./STATE_EXTRACTION.md)

---

**Last Updated:** April 16, 2026  
**Version:** 1.0.0  
**Status:** Complete ✅
