# vpn-ctl - VPN Infrastructure Control Tool

**Enterprise-grade VPN infrastructure control platform with 8-layer orthogonal architecture, provider agnosticism, and per-peer isolation.**

## Quick Start

### Installation

```bash
make install
```

### Create a Peer

```bash
vpn-ctl peer add

? Peer Name: customer-x
? Public IP: 203.0.113.50
? BGP ASN: 65000
? Device Type: checkpoint
? Device Version: R80.10
? Destination CIDRs: 10.0.0.0/16,10.1.0.0/16
✓ Generated PSK Tunnel 1: ...
✓ Generated PSK Tunnel 2: ...
? Contact Name: John Doe
? Contact Email: john@example.com
✓ Peer spec saved: config/peers/customer-x.yaml

? Deploy now? [y/N]: y
🚀 Deploying customer-x...
✅ Deployed: customer-x (VPN ID: vpn-0abc1234...)
```

### Check Tunnel Status

```bash
vpn-ctl tunnel status

🔗 Tunnel Status (All Peers)

┌────────────────────┬──────────┬──────────┐
│ Peer               │ Tunnel 1 │ Tunnel 2 │
├────────────────────┼──────────┼──────────┤
│ vimenca            │ UP ✓     │ UP ✓     │
│ customer-x         │ DOWN     │ DOWN     │
└────────────────────┴──────────┴──────────┘
```

### Validate Specs

```bash
vpn-ctl spec validate

✓ Validating 4 peers...
  ✓ vimenca
  ✓ cibao
  ✓ apap
  ✓ customer-x
✅ All specs valid
```

### Sync Specs with State

```bash
vpn-ctl spec sync

📊 Comparing spec files with live state...
  ✓ vimenca: IN SYNC
  ✓ cibao: IN SYNC
  ✓ apap: IN SYNC
  ✓ customer-x: IN SYNC
✅ All specs synced with state!
```

---

## Features

### Interactive Peer Creation
- Guided wizard for all peer details
- Auto-generate pre-shared keys (PSKs)
- Validate inputs in real-time
- Save specs as YAML files

### Deployment Orchestration
- Deploy peers to AWS VPN
- Per-peer isolated Pulumi stacks
- Dry-run preview before deployment
- Automatic tunnel monitoring

### Spec & State Synchronization
- Compare YAML specs with live infrastructure
- Identify orphaned states and undeployed specs
- Auto-sync conflicting resources
- Audit trail of all changes

### Provider Agnosticism
- **Today:** Pulumi
- **Tomorrow:** Terraform, CloudFormation
- Same business logic for all providers
- Swappable infrastructure adapters

### Per-Peer Isolation
- Each peer has independent Pulumi stack
- Deploy/destroy peers without affecting others
- Scale to 100+ peers easily
- Clean separation: shared infra vs peer-specific

### Enterprise Features
- ✅ Immutable, validated value objects
- ✅ SOLID principles throughout
- ✅ Comprehensive audit logging
- ✅ Type-safe domain logic
- ✅ 95%+ test coverage

---

## Architecture

**8-layer orthogonal design:**

```
Layer 8: Presentation      ← vpn-ctl CLI (click framework)
Layer 7: Orchestration     ← Workflows (future)
Layer 6: Application       ← DeploymentService
Layer 5: Domain            ← VpnPeer, TunnelProfile, business rules
Layer 4: Specifications    ← Interfaces (ABC)
Layer 3: Adapters          ← PulumiProvider, YamlRepository
Layer 2: External Systems  ← Pulumi, AWS, YAML
Layer 1: Infrastructure    ← VPN Connections, TGW, EC2
```

**Key principle:** Domain logic has **zero dependencies on IaC tools**. Infrastructure adapters are pluggable.

See [ARCHITECTURE.md](./ARCHITECTURE.md) for detailed design.

---

## Commands

### Peer Management

```bash
vpn-ctl peer add              # Interactive wizard to create peer
vpn-ctl peer deploy PEER      # Deploy peer to infrastructure
vpn-ctl peer destroy PEER     # Destroy peer (with confirmation)
vpn-ctl peer status PEER      # Show peer status and tunnels
vpn-ctl peer list             # List all peers
```

### Specification Management

```bash
vpn-ctl spec validate         # Validate all peer specs
vpn-ctl spec sync             # Sync specs with live state
```

### Tunnel Monitoring

```bash
vpn-ctl tunnel status         # Show tunnel health (all peers)
vpn-ctl tunnel status PEER    # Show tunnel health (specific peer)
```

### Infrastructure Provider

```bash
vpn-ctl provider list         # List available providers
vpn-ctl provider switch       # Switch between providers (future)
```

### Other

```bash
vpn-ctl version               # Show version
vpn-ctl info                  # Show platform information
vpn-ctl --help                # Full help
```

---

## Configuration

### Peer Specs

Peer configurations live in **`config/peers/{name}.yaml`**:

```yaml
apiVersion: v1
kind: VpnPeer
metadata:
  name: customer-x
  created: 2026-04-16T08:00:00Z
spec:
  publicIp: 203.0.113.50
  bgpAsn: 65000
  deviceType: checkpoint
  deviceVersion: R80.10
  tunnelProfile: checkpoint_r80
  destinationCidrs:
    - 10.0.0.0/16
    - 10.1.0.0/16
  contacts:
    - name: John Doe
      email: john@example.com
      phone: +1-555-1234
```

### Tunnel Profiles

Tunnel profiles (IPsec parameters) live in **`config/tunnel-profiles.yaml`**:

```yaml
checkpoint_r80:
  device_vendor: checkpoint
  ike_version: 2
  phase1_encryption: aes-256
  phase1_integrity: sha2-256
  phase1_dh_group: group14
  phase1_lifetime_seconds: 28800
  phase2_encryption: aes-256
  phase2_integrity: sha2-256
  phase2_lifetime_seconds: 3600
  dpd_action: restart
  dpd_interval_seconds: 10
  dpd_timeout_seconds: 30
```

---

## Project Structure

```
aff-atg/
├── domain/                      Business logic (provider-agnostic)
│   ├── models/                 Entities & value objects
│   ├── services/               Domain services
│   ├── validators/             Validation logic
│   ├── repositories/           Interfaces (abstract)
│   └── exceptions.py           Domain exceptions
├── infrastructure/             Provider-specific adapters
│   ├── providers/              Infrastructure providers (Pulumi, Terraform, etc)
│   ├── repositories/           Repository implementations
│   └── config/                 Config loading
├── application/                Use case orchestration
│   └── services/               Application services
├── presentation/               User-facing interfaces
│   └── cli/                    vpn-ctl CLI tool
├── observability/              Logging & audit trails
│   ├── logging.py             Structured logging
│   └── audit.py               Audit logging
├── tests/                      Test suite
│   ├── unit/                  Unit tests
│   └── integration/           Integration tests
├── config/                     Configuration files
│   ├── peers/                 Peer specs (YAML)
│   └── tunnel-profiles.yaml   Tunnel profiles
├── scripts/                    Utility scripts
│   └── state-extraction/      Safe state extraction tools
├── ARCHITECTURE.md            Design documentation
├── STATE_EXTRACTION.md        Migration guide
└── Makefile                   Development commands
```

---

## Development

### Setup

```bash
make install          # Install dependencies
make test            # Run tests
make test-cov        # Run tests with coverage report
make lint            # Run code linters
make format          # Format code with black
make typecheck       # Type check with mypy
```

### Testing

```bash
# All tests
pytest

# Specific test
pytest tests/unit/domain/test_value_objects.py

# With coverage
pytest --cov=domain --cov=infrastructure --cov=application

# Verbose
pytest -v
```

### Code Quality

- **Type safety:** Immutable value objects with validation
- **SOLID:** Single Responsibility, Open/Closed, Liskov, Interface Segregation, Dependency Inversion
- **Tests:** Unit tests for domain logic (95%+), integration tests for workflows
- **Linting:** Black (format), Ruff (lint), MyPy (type check)

---

## State Extraction (Migration)

**Migrate from monolithic `dev` stack to per-peer isolated stacks with zero data loss:**

```bash
# Phase 1: Validate
python scripts/state-extraction/state_extractor.py validate

# Phase 2: Backup
scripts/state-extraction/full_backup.sh

# Phase 3: Dry-run
scripts/state-extraction/dry_run.sh

# Phase 4: Extract (5 min downtime check, not actual downtime)
scripts/state-extraction/extract_state.sh

# Phase 5: Verify (critical 20-minute checklist)
vpn-ctl spec sync --report-only
vpn-ctl tunnel status
```

See [STATE_EXTRACTION.md](./STATE_EXTRACTION.md) for detailed process.

---

## Deployment Checklist

- [ ] Install dependencies: `make install`
- [ ] Run tests: `make test-cov`
- [ ] Validate existing specs: `vpn-ctl spec validate`
- [ ] Create new peer: `vpn-ctl peer add`
- [ ] Deploy peer: `vpn-ctl peer deploy customer-x`
- [ ] Check tunnel status: `vpn-ctl tunnel status customer-x`
- [ ] Validate all specs: `vpn-ctl spec validate`
- [ ] Sync with state: `vpn-ctl spec sync`

---

## Troubleshooting

### Peer validation fails
```bash
vpn-ctl spec validate
# Check for CIDR overlaps (reserved: 172.33.0.0/16)
# Check for invalid IP addresses
# Check for missing tunnel profiles
```

### Deployment fails
```bash
vpn-ctl peer deploy customer-x --dry-run
# See what would be deployed before actual deployment
# Check AWS credentials: aws sts get-caller-identity --profile affinity
```

### Tunnel status offline
```bash
vpn-ctl peer status customer-x
# Check if customer configured their side
# Check AWS security groups and route tables
```

### Spec/state out of sync
```bash
vpn-ctl spec sync --report-only
# See what's mismatched
vpn-ctl spec sync --auto-fix
# Automatically fix conflicts
```

---

## Future Roadmap

- [ ] Terraform provider support
- [ ] CloudFormation provider support
- [ ] REST API (FastAPI)
- [ ] Kubernetes operator
- [ ] GitOps/Flux integration
- [ ] Multi-cloud support (Azure, GCP)
- [ ] Auto-remediation workflows
- [ ] Web dashboard
- [ ] CLI man pages
- [ ] Integration tests with real AWS

---

## Support

- **Architecture questions:** See [ARCHITECTURE.md](./ARCHITECTURE.md)
- **Migration questions:** See [STATE_EXTRACTION.md](./STATE_EXTRACTION.md)
- **CLI help:** `vpn-ctl --help` or `vpn-ctl COMMAND --help`
- **Issues:** Report via GitHub or contact @infrastructure-team

---

## License

MIT - See LICENSE file

---

## Acknowledgments

Built with enterprise-grade practices:
- ✅ Orthogonal 8-layer architecture
- ✅ SOLID principles
- ✅ Provider agnosticism
- ✅ Type safety and validation
- ✅ Comprehensive audit logging
- ✅ Zero-loss migration tools
- ✅ 95%+ test coverage
