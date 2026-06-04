# vpn-ctl: Enterprise VPN Infrastructure Management Platform

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Code Coverage](https://img.shields.io/badge/coverage->80%25-brightgreen.svg)](#testing)
[![Version 1.2.0](https://img.shields.io/badge/version-1.2.0-blue.svg)](#versioning)

**vpn-ctl** is an enterprise-grade Infrastructure as Code (IaC) platform for managing VPN peer connectivity, multi-site networking, and Kubernetes cluster integration. It provides a declarative, provider-agnostic approach to VPN infrastructure management with support for Pulumi, Terraform, and CloudFormation backends.

## 🎯 Quick Start

### Installation

```bash
# Clone repository
git clone https://github.com/affinity/vpn-ctl.git
cd vpn-ctl

# Install globally
./setup.sh

# Verify installation
vpn-ctl --help
```

### Your First Command

```bash
# Export current infrastructure state
vpn-ctl infra export-config

# View VPN tunnel status
vpn-ctl tunnel info

# List all VPN peers
vpn-ctl peer list
```

---

## 🏗️ Architecture Overview

vpn-ctl uses a **layered hexagonal architecture** with clean separation of concerns:

```
┌─────────────────────────────────────────────────────────┐
│              Presentation Layer (CLI)                   │
│  ├─ vpnctl/commands/  (Tunnel, Peer, Health, Infra)   │
│  └─ presentation/cli/  (Click command groups)          │
├─────────────────────────────────────────────────────────┤
│            Application Layer (Services)                 │
│  ├─ application/services/  (Business orchestration)    │
│  └─ vpnctl/spec_runner.py  (Spec file processing)     │
├─────────────────────────────────────────────────────────┤
│             Domain Layer (Core Logic)                   │
│  ├─ domain/models/     (VpnPeer, TunnelProfile, etc)  │
│  ├─ domain/repositories/ (VpnPeerRepository, etc)     │
│  ├─ domain/services/   (PskService, VpnPeerService)  │
│  └─ domain/validators/ (Input validation rules)       │
├─────────────────────────────────────────────────────────┤
│          Infrastructure Layer (Providers)               │
│  ├─ infrastructure/iac_providers/ (Pulumi, Terraform) │
│  ├─ infrastructure/providers/     (AWS, Azure, GCP)   │
│  ├─ infrastructure/repositories/  (AWS state queries) │
│  └─ pulumi/  (Pulumi stack definitions)               │
└─────────────────────────────────────────────────────────┘
```

### Key Architectural Principles

- **Provider Agnostic**: Switch between Pulumi, Terraform, CloudFormation without changing business logic
- **Domain-Driven Design**: Core VPN logic isolated in domain layer, no cloud provider dependencies
- **Repository Pattern**: All external state access through repositories
- **Declarative**: Define desired state in YAML, apply changes via CLI
- **K8s-Native**: Health monitoring deployed as Kubernetes microservice with IRSA authentication

---

## 📋 Project Structure

```
vpn-ctl/
├── README.md                          # This file
├── pyproject.toml                     # Python package metadata & dependencies
├── setup.sh                           # Global installation & version management
├── Makefile                           # Development commands
├── requirements.txt                   # Runtime dependencies
│
├── domain/                            # ✨ Domain Layer (Provider-agnostic)
│   ├── models/
│   │   ├── vpn_peer.py               # VPN peer entity (name, region, ASN, CIDR)
│   │   ├── tunnel_profile.py         # Tunnel configuration (phase1/2 settings)
│   │   ├── test_endpoint.py          # Health check definition
│   │   └── value_objects.py          # BGPASN, CIDR, PSK value objects
│   ├── repositories/
│   │   ├── vpn_peer_repository.py    # Query/persist peer definitions
│   │   ├── tunnel_profile_repository.py
│   │   └── state_repository.py       # Infrastructure state persistence
│   ├── services/
│   │   ├── psk_service.py            # Generate/validate pre-shared keys
│   │   ├── vpn_peer_service.py       # Peer lifecycle management
│   │   └── peer_spec_manager.py      # Parse/validate peer specifications
│   ├── validators/
│   │   ├── vpn_peer_validator.py     # Peer definition validation
│   │   └── tunnel_profile_validator.py
│   └── exceptions.py                 # Domain-level exceptions
│
├── infrastructure/                    # 🔧 Infrastructure Layer (Providers)
│   ├── iac_providers/                # IaC provider abstraction
│   │   ├── pulumi_provider.py
│   │   ├── terraform_provider.py
│   │   └── cloudformation_provider.py
│   ├── providers/                    # Cloud provider SDKs
│   │   ├── aws_provider.py           # AWS EC2, TGW, VPN APIs
│   │   └── provider_factory.py       # Provider instantiation
│   └── repositories/
│       ├── aws_repository.py         # AWS query implementation
│       └── state_repository_impl.py  # State persistence
│
├── application/                       # 📦 Application Layer (Orchestration)
│   └── services/
│       ├── vpn_service.py            # Coordinate peer, tunnel, health
│       ├── health_service.py         # Health check orchestration
│       └── deployment_service.py     # Deploy to K8s
│
├── presentation/                      # 🎯 Presentation Layer (CLI)
│   └── cli/
│       ├── main.py                   # CLI entry point (Click)
│       ├── groups/                   # Command groups
│       └── formatters/               # Output formatting
│
├── vpnctl/                            # 🚀 CLI Commands (Top-level)
│   ├── main.py                       # Register command groups
│   ├── commands/
│   │   ├── tunnel.py                 # `vpnctl tunnel` commands
│   │   ├── peer.py                   # `vpnctl peer` commands
│   │   ├── health.py                 # `vpnctl health` commands
│   │   ├── infra.py                  # `vpnctl infra` commands
│   │   └── certify.py                # `vpnctl certify` commands
│   ├── health/                        # 🏥 Health Monitoring App
│   │   ├── app.py                    # FastAPI health service
│   │   ├── state.py                  # AWS state queries (boto3)
│   │   ├── config_watcher.py         # YAML config watching
│   │   ├── Dockerfile                # Container image definition
│   │   ├── entrypoint.sh             # Container startup script
│   │   └── helm/                     # Kubernetes deployment
│   │       └── vpn-health/
│   │           ├── Chart.yaml        # Helm chart metadata
│   │           ├── values.yaml       # Default values
│   │           ├── values/dev.yaml   # Dev environment overrides
│   │           └── templates/        # K8s resource templates
│   ├── spec_runner.py                # Execute spec files (apply/destroy)
│   └── tunnel_info.py                # Query tunnel information
│
├── pulumi/                            # 📡 Pulumi IaC Definitions
│   ├── __main__.py                   # Main stack orchestrator
│   ├── stack_orchestrator.py         # Coordinate multiple stacks
│   ├── vpn_ctl_cli.py                # Pulumi CLI wrapper
│   ├── vpn_manifest_loader.py        # Load peer definitions
│   ├── secrets_manager.py            # Handle secrets (PSK, etc)
│   ├── multi_provider_nat.py         # Multi-site NAT rules
│   ├── vpn_attachment.py             # TGW VPN attachment logic
│   ├── vpn_registry.py               # Registry of VPN connections
│   ├── vpn_peer_lifecycle.py         # Peer state machine
│   ├── Pulumi.yaml                   # Pulumi configuration
│   ├── config/                       # Stack configurations
│   │   ├── dev.yaml
│   │   ├── qa.yaml
│   │   └── prod.yaml
│   └── stacks/                       # Provider-specific stacks
│       ├── base_stack.py
│       ├── aws_stack.py
│       └── azure_stack.py
│
├── config/                            # 📝 Configuration Files
│   ├── vpn-peers.yaml                # VPN peer definitions (spec format)
│   ├── tunnel-profiles/              # Tunnel profile templates
│   └── providers/                    # Provider-specific configs
│
├── tests/                             # ✅ Test Suite
│   ├── unit/                         # Unit tests (mocked dependencies)
│   │   ├── test_vpn_peer.py
│   │   ├── test_tunnel_profile.py
│   │   └── test_psk_service.py
│   ├── integration/                  # Integration tests (real AWS)
│   │   ├── test_aws_repository.py
│   │   └── test_peer_spec_manager.py
│   ├── e2e/                          # End-to-end tests
│   │   └── test_apply_destroy.py
│   └── run_tests.sh                  # Test runner script
│
├── observability/                     # 📊 Observability
│   ├── logging.py                    # Structured logging
│   ├── metrics.py                    # Prometheus metrics
│   └── tracing.py                    # Distributed tracing
│
├── scripts/                           # 🛠️ Utility Scripts
│   ├── rollout.sh                    # Automated rollout pipeline
│   ├── validate-config.py            # Config validation
│   ├── generate-docs.sh              # Generate API docs
│   └── health-check.sh               # Health verification
│
├── docs/                              # 📚 Documentation
│   ├── README.md                     # Documentation index
│   ├── ARCHITECTURE.md               # Architecture deep-dive
│   ├── API.md                        # API reference
│   ├── VPN_POOL_GUIDE.md            # Pool management guide
│   ├── VIMENCA_VPN_SETUP.md         # Case study: Vimenca setup
│   └── DOCUMENTATION_INDEX.md        # Full docs index
│
├── infra-config.json                 # 💾 Exported infrastructure state
├── IMPLEMENTATION_SUMMARY.md         # Project completion summary
├── DEPLOYMENT_STATUS.md              # Deployment status & checklist
├── DEPLOYMENT_QUICK_START.md         # Quick deployment guide
└── Makefile                          # Development workflow
```

---

## 🚀 Core Features

### 1. **Declarative VPN Management**
Define VPN infrastructure in YAML, apply changes like Kubernetes:

```yaml
# config/vpn-peers.yaml
peers:
  - name: Vimenca
    region: us-east-2
    bgp_asn: 65000
    on_prem_cidr: 172.16.70.0/24
    tunnel_profile: standard-phase2
    health_check:
      enabled: true
      interval: 60
```

Apply with: `vpnctl apply --spec spec.yaml`

### 2. **Infrastructure Export**
Capture current AWS state as JSON for health monitoring and audits:

```bash
vpnctl infra export-config
# Generates: infra-config.json with all VPN connections, routes, and tunnel IPs
```

### 3. **Health Monitoring Service**
Kubernetes-deployed microservice with:
- Real-time tunnel status (up/down/degraded)
- Multi-endpoint testing (ping, HTTP, TCP, DNS)
- IRSA authentication (no long-lived credentials)
- Prometheus-compatible `/metrics` endpoint

### 4. **Multi-Provider Support**
- **Pulumi**: Native Python infrastructure definitions
- **Terraform**: CloudFormation JSON output
- **CloudFormation**: Direct template generation
- Switch providers via configuration flag

### 5. **Pre-shared Key (PSK) Management**
- Cryptographically secure generation
- Automatic rotation support
- Encrypted storage in Pulumi/Terraform state
- Integration with AWS Secrets Manager

### 6. **Validation & Testing**
- Domain-level validation (CIDR, ASN, PSK format)
- Spec file validation before apply
- Pre-commit hooks for quality gates
- Unit, integration, and E2E test coverage >80%

---

## 📖 Usage Guide

### Command Groups

#### **Tunnel Management**
```bash
# View tunnel information
vpnctl tunnel info

# Get specific tunnel details
vpnctl tunnel info vimenca

# Test tunnel connectivity
vpnctl tunnel test vimenca

# Show tunnel diagnostics
vpnctl tunnel diagnose vimenca
```

#### **Peer Management**
```bash
# List all VPN peers
vpnctl peer list

# Add new VPN peer (interactive)
vpnctl peer add

# Update peer configuration
vpnctl peer update vimenca --bgp-asn 65001

# Remove peer
vpnctl peer remove vimenca

# Get peer details
vpnctl peer get vimenca
```

#### **Infrastructure Management**
```bash
# Export current AWS state to JSON
vpnctl infra export-config

# Export with custom output
vpnctl infra export-config --output prod-config.json --region us-east-2

# Export specific peers
vpnctl infra export-config --peers vimenca,apap
```

#### **Health Monitoring**
```bash
# Deploy health service to Kubernetes
vpnctl health deploy

# Build Docker image
vpnctl health build

# View health logs
vpnctl health logs

# Restart health service
vpnctl health restart
```

#### **Spec Files** (Declarative)
```bash
# Apply VPN infrastructure from spec file
vpnctl apply --spec vpn-spec.yaml

# Destroy infrastructure from spec
vpnctl destroy --spec vpn-spec.yaml

# Validate spec without applying
vpnctl validate --spec vpn-spec.yaml

# Show what would change (dry-run)
vpnctl apply --spec vpn-spec.yaml --dry-run
```

#### **Certification**
```bash
# Generate TLS certificates
vpnctl certify generate --peer vimenca

# List certificates
vpnctl certify list

# Rotate certificate
vpnctl certify rotate --peer vimenca
```

---

## 🔧 Configuration Guide

### Peer Definition Format

```yaml
# config/vpn-peers.yaml
peers:
  - name: Vimenca                    # Unique peer identifier
    region: us-east-2                # AWS region
    bgp_asn: 65000                   # BGP Autonomous System Number
    on_prem_cidr: 172.16.70.0/24     # On-premise network CIDR
    tunnel_profile: standard-phase2  # Reference to tunnel config
    internet_ip: 203.0.113.50        # Public IP of on-prem gateway
    health_check:
      enabled: true
      interval: 60                   # Seconds between checks
      timeout: 5                     # Connection timeout
      endpoints:
        - target: 172.16.70.5
          protocol: ping
        - target: api.vimenca.com
          protocol: tcp
          port: 443
        - target: vimenca.example.com
          protocol: dns
```

### Tunnel Profile Configuration

```yaml
# config/tunnel-profiles/standard-phase2.yaml
name: standard-phase2
ipsec_phase1:
  encryption_algorithm: AES256
  integrity_algorithm: SHA256
  dh_group: 14
  lifetime: 28800

ipsec_phase2:
  encryption_algorithm: AES128
  integrity_algorithm: SHA1
  lifetime: 3600
  
bgp:
  hold_time: 30
  keepalive_interval: 10
```

### Infrastructure Configuration

```json
{
  "metadata": {
    "version": "1.0",
    "aws_account": "218833996210",
    "aws_region": "us-east-2",
    "environment": "dev"
  },
  "infrastructure": {
    "transit_gateway": {
      "id": "tgw-0d5e672d089033651",
      "asn": 64512
    },
    "eks_cluster": {
      "name": "asg-plat-dev",
      "vpc_id": "vpc-0efe6f2c199a72f9a"
    }
  }
}
```

---

## 🔐 Security Features

### Credential Management
- **AWS Credentials**: Uses AWS CLI profiles (`~/.aws/credentials`)
- **IRSA**: Kubernetes pods authenticate via IAM roles (no long-lived tokens)
- **PSK Storage**: Encrypted in Pulumi state backend
- **Secrets Manager**: Integration with AWS Secrets Manager for rotation

### Network Security
- **IPSec Encryption**: AES-256 phase 1, AES-128 phase 2
- **BGP Authentication**: MD5/SHA authentication for BGP sessions
- **VPC Isolation**: Transit Gateway routing policies enforce segmentation
- **Access Control**: IAM-based fine-grained permissions per environment

### Compliance
- **Audit Logging**: All changes logged via CloudTrail
- **State Versioning**: Git-based state version control
- **Terraform State**: Remote state stored in S3 with versioning
- **Helm Chart**: Includes RBAC and network policies

---

## 💻 Development Workflow

### Setup Development Environment

```bash
# Install dev dependencies
make dev

# Verify setup
make doctor

# Run tests
make test
```

### Code Quality

```bash
# Format code
make format

# Run linters
make lint

# Type checking
make type-check

# Generate coverage report
make coverage
```

### Testing

```bash
# Run all tests
make test

# Unit tests only
make test-unit

# Integration tests only
make test-integration

# With coverage
make coverage
```

### Common Development Tasks

```bash
# Add new peer (development)
vpn-ctl peer add --name test-peer --bgp-asn 65001

# Export local infrastructure
vpn-ctl infra export-config --output local-config.json

# Apply spec to development environment
vpn-ctl apply --spec test-spec.yaml --dry-run

# View tunnel status
vpn-ctl tunnel info

# Run full test suite
make test
```

---

## 🐳 Kubernetes Deployment

### Health Monitor Deployment

The health monitoring service is deployed as a Kubernetes microservice:

```bash
# Deploy to cluster
vpnctl health deploy --namespace vpn-system --environment dev

# Deploy with custom values
vpnctl health deploy --values helm/vpn-health/values/dev.yaml

# Verify deployment
kubectl get deployment -n vpn-system vpn-health
kubectl logs -n vpn-system deployment/vpn-health
```

### Helm Configuration

```yaml
# helm/vpn-health/values.yaml
replicaCount: 2
image:
  repository: 218833996210.dkr.ecr.us-east-2.amazonaws.com/vpn-health
  tag: latest
  pullPolicy: IfNotPresent

resources:
  requests:
    memory: "256Mi"
    cpu: "100m"
  limits:
    memory: "512Mi"
    cpu: "500m"

healthCheck:
  initialDelaySeconds: 10
  periodSeconds: 30
  timeoutSeconds: 5
  failureThreshold: 3
```

### Health Service API

```bash
# Health status
curl http://vpn-health:8080/health

# Per-peer status
curl http://vpn-health:8080/health/peers

# Liveness probe
curl http://vpn-health:8080/health/liveness

# Readiness probe
curl http://vpn-health:8080/health/readiness

# Prometheus metrics
curl http://vpn-health:8080/metrics
```

---

## 📊 Monitoring & Observability

### Health Check Endpoints

```python
# Internal API
GET  /health              # Overall system health
GET  /health/peers        # Per-peer tunnel status
GET  /health/liveness     # Kubernetes liveness probe
GET  /health/readiness    # Kubernetes readiness probe
GET  /metrics             # Prometheus metrics
```

### Prometheus Metrics

```
# Tunnel status
vpn_tunnel_status{peer="vimenca",tunnel="1"} 1      # 1=up, 0=down
vpn_tunnel_latency_ms{peer="vimenca",tunnel="1"} 15 # Latency

# Endpoint testing
vpn_test_success{peer="vimenca",endpoint="api.vimenca.com"} 1
vpn_test_latency_ms{peer="vimenca",endpoint="api.vimenca.com"} 42
```

### Logging

```python
# Structured logging (JSON format)
import logging
logger = logging.getLogger(__name__)
logger.info("VPN tunnel status", extra={
    "peer": "vimenca",
    "tunnel_id": "vpn-123",
    "status": "up"
})
```

---

## 🐛 Troubleshooting

### Common Issues

#### Health Service Not Starting

```bash
# Check pod logs
kubectl logs -n vpn-system deployment/vpn-health

# Verify config is loaded
kubectl describe pod -n vpn-system -l app=vpn-health

# Check IRSA permissions
aws sts get-caller-identity

# Verify ConfigMap
kubectl get configmap -n vpn-system vpn-health-config
```

#### VPN Tunnel Down

```bash
# Check VPN connection status
vpnctl tunnel info vimenca

# Verify TGW attachment
aws ec2 describe-transit-gateway-attachments \
  --filters Name=resource-id,Values=vgw-xxx

# Check route table
aws ec2 describe-transit-gateway-route-tables

# Test BGP session
vpnctl tunnel diagnose vimenca
```

#### Config Export Issues

```bash
# Verify AWS credentials
aws sts get-caller-identity

# Check Transit Gateway exists
aws ec2 describe-transit-gateways --filters Name=tag:Name,Values=affinity-hub-tgw

# Debug export
vpnctl infra export-config --debug
```

### Debug Mode

```bash
# Enable debug logging
export DEBUG=true
vpnctl --verbose infra export-config

# Detailed output
vpnctl infra export-config --debug --pretty
```

---

## 📝 Examples

### Example 1: Add New VPN Peer

```bash
# Interactive peer creation
vpnctl peer add
# > Enter peer name: acme-corp
# > Enter region: us-west-2
# > Enter BGP ASN: 65001
# > Enter on-prem CIDR: 10.20.0.0/16

# Verify peer added
vpnctl peer get acme-corp

# Apply to infrastructure
cat > acme-spec.yaml <<EOF
peers:
  - name: acme-corp
    region: us-west-2
    bgp_asn: 65001
    on_prem_cidr: 10.20.0.0/16
    tunnel_profile: standard-phase2
EOF

vpnctl apply --spec acme-spec.yaml --dry-run
vpnctl apply --spec acme-spec.yaml
```

### Example 2: Update Tunnel Profile

```bash
# View current tunnel config
vpnctl tunnel info vimenca

# Update phase1 encryption
vpnctl tunnel update vimenca \
  --phase1-encryption AES256 \
  --phase1-dh-group 20

# Apply changes
vpnctl apply --spec vpn-spec.yaml
```

### Example 3: Deploy Health Monitor

```bash
# Export current state
vpnctl infra export-config

# Build Docker image
vpnctl health build

# Deploy to Kubernetes
vpnctl health deploy --environment dev

# Monitor health
watch 'curl -s http://vpn-health.vpn-system:8080/health | jq .'
```

### Example 4: Disaster Recovery

```bash
# Export all infrastructure
vpnctl infra export-config --output backup-$(date +%Y%m%d).json

# Backup spec files
git commit -am "Pre-DR backup"

# Destroy and rebuild
vpnctl destroy --spec vpn-spec.yaml --confirm
vpnctl apply --spec vpn-spec.yaml

# Verify restoration
vpnctl tunnel info
vpnctl health deploy
```

---

## 🔄 Versioning

### Semantic Versioning

vpn-ctl follows [Semantic Versioning 2.0.0](https://semver.org/):

- **MAJOR**: Breaking API/CLI changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes

Current version: **1.2.0**

### Version Management

```bash
# Update version
./setup.sh version 1.3.0

# Check version
vpnctl --version
cat .vpnctl-version
```

---

## 📦 Dependencies

### Runtime Dependencies

- **click** >=8.0.0 - CLI framework
- **pydantic** >=2.0.0 - Data validation
- **pyyaml** >=6.0 - YAML parsing
- **boto3** >=1.26.0 - AWS SDK
- **pulumi** >=3.0.0 - Infrastructure as Code

### Development Dependencies

- **pytest** >=7.0.0 - Testing framework
- **pytest-cov** >=4.0.0 - Coverage reporting
- **black** >=23.0.0 - Code formatter
- **ruff** >=0.1.0 - Fast linter
- **mypy** >=1.0.0 - Type checking

### Optional Dependencies

- **sphinx** >=5.0.0 - Documentation generator
- **sphinx-rtd-theme** >=1.0.0 - ReadTheDocs theme

---

## 🤝 Contributing

### Code Standards

- **Style**: Black formatter (100 char line length)
- **Linting**: Ruff (E, F, W, I, N, UP, C90)
- **Type Hints**: mypy with strict checking
- **Testing**: Minimum 80% coverage

### Pull Request Process

1. Create feature branch: `feature/TGW-XXX-description`
2. Make changes with tests
3. Run code quality: `make format lint type-check`
4. Run tests: `make test`
5. Verify coverage: `make coverage`
6. Submit PR with description

### Commit Message Format

```
<type>: <subject>

<body (optional)>

<footer (optional)>
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`

Example:
```
feat: Add health check endpoint for peer status

- Implements /health/peers endpoint
- Returns per-tunnel status (up/down)
- Includes BGP session state

Fixes #123
```

---

## 📚 Documentation

Complete documentation is available in the `docs/` directory:

- **ARCHITECTURE.md** - Detailed architecture documentation
- **VPN_POOL_GUIDE.md** - Pool and scaling management
- **VIMENCA_VPN_SETUP.md** - Real-world case study
- **DEPLOYMENT_QUICK_START.md** - Quick deployment guide
- **DEPLOYMENT_STATUS.md** - Implementation status checklist

---

## 🎓 Key Concepts

### VPN Peer
A remote location or partner network connected via VPN. Each peer has:
- Unique name identifier
- BGP ASN for dynamic routing
- On-premise CIDR block
- Tunnel configuration (IPSec, BGP)
- Health check endpoints

### Tunnel Profile
Reusable IPSec and BGP configuration template:
- Phase 1: Authentication (DH group, encryption, integrity)
- Phase 2: Encryption (ESP encryption, integrity, lifetime)
- BGP: Session timers and authentication

### Spec File
Declarative YAML defining desired infrastructure state:
```yaml
peers:
  - name: my-peer
    region: us-east-2
    # ... peer configuration
```

### Infrastructure Export
JSON snapshot of current AWS VPN state:
```json
{
  "infrastructure": {
    "transit_gateway": { ... },
    "peers": { ... },
    "routes": { ... }
  }
}
```

### Health Service
Kubernetes-deployed microservice monitoring tunnel status:
- Real-time health checks (ping, HTTP, TCP, DNS)
- Per-endpoint latency measurement
- Prometheus metrics export
- Automatic alerting integration

---

## ⚙️ System Requirements

- **Python**: 3.10, 3.11, or 3.12
- **AWS CLI**: Configured with credentials
- **Kubernetes**: 1.20+ (for health monitoring)
- **Helm**: 3.0+ (for health deployment)
- **Docker**: 20.10+ (for building health service image)

---

## 📄 License

This project is licensed under the **MIT License** - see LICENSE file for details.

---

## 🙋 Support & Contact

- **Issues**: [GitHub Issues](https://github.com/affinity/vpn-ctl/issues)
- **Documentation**: [docs/README.md](docs/README.md)
- **Contact**: engineering@affinity.com

---

## 🎉 Acknowledgments

Built and maintained by the **Affinity Engineering** team.

**Key Technologies**:
- Pulumi - Infrastructure automation
- AWS - Cloud infrastructure
- Kubernetes - Container orchestration
- Python - Core implementation language
- FastAPI - Health monitoring API

---

## 📊 Project Status

- **Version**: 1.2.0
- **Status**: Production-ready ✅
- **Last Updated**: June 4, 2026
- **Test Coverage**: >80%
- **License**: MIT

For the latest updates, check [DEPLOYMENT_STATUS.md](DEPLOYMENT_STATUS.md)
