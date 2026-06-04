# Development Guide

This guide is for developers working on the vpn-ctl platform itself (not users of the tool).

## Setup

### Prerequisites

- Python 3.10+
- Pulumi CLI
- AWS CLI with credentials configured (`--profile affinity`)
- Git

### Install Development Environment

```bash
# Clone and navigate
cd aff-atg

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
make install

# Verify setup
vpn-ctl --version
```

---

## Architecture Overview

The codebase is organized in **8 layers**:

```
Layer 8: Presentation  (CLI: vpn-ctl commands)
Layer 7: Orchestration (Workflows - TBD)
Layer 6: Application   (Use case services)
Layer 5: Domain        (Business logic, entities, validation)
Layer 4: Specifications (Interfaces/ports)
Layer 3: Adapters      (Pulumi, YAML, AWS providers)
Layer 2: External      (Third-party systems)
Layer 1: Infrastructure (Physical resources)
```

**Key principle:** Domain logic (Layer 5) has **ZERO dependencies on IaC tools**. All provider-specific code is in Layer 3.

For detailed architecture, see [ARCHITECTURE.md](./ARCHITECTURE.md).

---

## Project Structure

```
aff-atg/
├── domain/                      Business logic (provider-agnostic)
│   ├── models/
│   │   ├── value_objects.py    Immutable types with validation
│   │   ├── vpn_peer.py         Core VpnPeer entity
│   │   └── tunnel_profile.py    IPsec configuration
│   ├── services/
│   │   ├── vpn_peer_service.py  Peer lifecycle management
│   │   └── psk_service.py       Pre-shared key handling
│   ├── validators/
│   │   ├── vpn_peer_validator.py
│   │   └── tunnel_profile_validator.py
│   ├── repositories/            Interfaces (abstract)
│   │   ├── vpn_peer_repository.py
│   │   ├── tunnel_profile_repository.py
│   │   └── state_repository.py
│   └── exceptions.py            Domain exceptions
│
├── infrastructure/              Provider-specific adapters
│   ├── providers/
│   │   ├── interfaces.py        IInfrastructureProvider (abstract)
│   │   └── pulumi_provider.py   Pulumi implementation
│   ├── repositories/
│   │   ├── yaml_peer_repository.py
│   │   ├── yaml_profile_repository.py
│   │   └── pulumi_state_repository.py
│   └── config/                  Configuration loading (TBD)
│
├── application/                 Use case orchestration
│   └── services/
│       └── deployment_service.py  Deploy/destroy orchestration
│
├── presentation/                User-facing interfaces
│   └── cli/
│       ├── main.py              CLI entry point
│       ├── commands/            Command modules
│       ├── interactive/         Interactive helpers
│       └── state_manager/       State management (TBD)
│
├── observability/               Logging & audit
│   ├── logging.py               Structured logging
│   └── audit.py                 Audit trails
│
├── tests/
│   ├── unit/                    Unit tests
│   │   ├── domain/
│   │   ├── infrastructure/
│   │   └── application/
│   └── integration/             Integration tests
│
├── scripts/
│   └── state-extraction/        Safe migration tools
│
└── config/
    ├── peers/                   YAML peer specs
    └── tunnel-profiles.yaml     IPsec profiles
```

---

## Development Workflow

### 1. Create a Feature Branch

```bash
git checkout -b feature/my-feature
git checkout -b fix/my-bug
```

### 2. Make Changes

Always follow the architecture layers. Example: Adding a new field to VpnPeer:

**Step 1:** Add to domain model
```python
# domain/models/vpn_peer.py
@dataclass(frozen=True)
class VpnPeer:
    # ... existing fields
    new_field: str  # Add new field
    
    def __post_init__(self):
        # Validate new field
        if not self.new_field:
            raise ValidationError("new_field required")
```

**Step 2:** Update validator
```python
# domain/validators/vpn_peer_validator.py
def validate_spec(self, spec):
    # Add validation for new_field
    pass
```

**Step 3:** Update repository
```python
# infrastructure/repositories/yaml_peer_repository.py
def save(self, peer):
    # Include new_field in YAML output
    pass
```

**Step 4:** Update CLI if needed
```python
# presentation/cli/commands/peer/add.py
# Add prompt for new_field
```

**Step 5:** Add tests
```python
# tests/unit/domain/test_vpn_peer.py
def test_new_field_validation():
    pass
```

### 3. Run Tests

```bash
# All tests
make test

# With coverage
make test-cov

# Specific test
pytest tests/unit/domain/test_value_objects.py -v

# Watch for changes
pytest-watch tests/
```

### 4. Check Code Quality

```bash
make lint      # Ruff linter
make format    # Black formatter
make typecheck # MyPy type checker
```

### 5. Test Manually

```bash
# Create a test peer
vpn-ctl peer add

# List peers
vpn-ctl peer list

# Validate specs
vpn-ctl spec validate

# Check syncs
vpn-ctl spec sync --report-only
```

### 6. Commit

```bash
git add domain/models/vpn_peer.py
git add tests/unit/domain/test_vpn_peer.py
# ... other files

git commit -m "feat: Add new_field to VpnPeer

- Add new_field to domain model
- Add validation in VpnPeerValidator
- Update YAML repository
- Add CLI prompt
- Add unit tests for new_field"
```

### 7. Push and Create PR

```bash
git push origin feature/my-feature

# Create PR on GitHub
```

---

## Testing Guidelines

### Unit Tests (95%+ coverage target)

Test domain logic in isolation:

```python
# tests/unit/domain/test_vpn_peer.py
def test_vpn_peer_creation():
    peer = VpnPeer(
        name=PeerName("test"),
        public_ip=PublicIP("203.0.113.50"),
        # ...
    )
    assert peer.name.value == "test"

def test_vpn_peer_invalid_cidr_overlap():
    with pytest.raises(ValidationError):
        VpnPeer(
            # ... 
            destination_cidrs=frozenset([
                CIDR("172.33.0.0/24"),  # Reserved!
            ]),
        )
```

### Integration Tests

Test layers working together:

```python
# tests/integration/test_deployment_flow.py
def test_peer_creation_and_deployment(peer_repository, peer_service):
    # Create peer via service
    peer = peer_service.create_peer(spec)
    
    # Save via repository
    peer_repository.save(peer)
    
    # Verify saved correctly
    loaded = peer_repository.get(peer.name)
    assert loaded == peer
```

### Fixtures

Use `conftest.py` for reusable test data:

```python
# tests/conftest.py
@pytest.fixture
def sample_peer():
    return VpnPeer(...)

@pytest.fixture
def peer_repository(temp_config_dir):
    return YamlVpnPeerRepository(temp_config_dir / "peers")
```

---

## Code Style

### Naming Conventions

- **Classes:** PascalCase (VpnPeer, TunnelProfile)
- **Functions:** snake_case (create_peer, get_all_peers)
- **Constants:** UPPER_SNAKE_CASE (MAX_ASN, DEFAULT_TIMEOUT)
- **Private:** _leading_underscore (_internal_method)

### Imports

```python
# Standard library
import json
from pathlib import Path
from typing import Dict, List

# Third-party
import click
from pydantic import BaseModel

# Local
from domain.models import VpnPeer
from infrastructure.repositories import YamlVpnPeerRepository
```

### Type Hints

```python
# Good
def deploy_peer(peer: VpnPeer, profile: TunnelProfile) -> Dict[str, Any]:
    pass

# Avoid
def deploy_peer(peer, profile):
    pass
```

### Docstrings

```python
def validate_peer(self, peer: VpnPeer) -> Tuple[bool, List[str]]:
    """Validate a VPN peer.
    
    Args:
        peer: VpnPeer to validate
    
    Returns:
        (is_valid: bool, errors: List[str])
    
    Raises:
        ValidationError: If peer is critically invalid
    """
```

---

## Adding a New Provider

Example: Adding Terraform support

### 1. Create Provider Class

```python
# infrastructure/providers/terraform_provider.py
from infrastructure.providers.interfaces import IInfrastructureProvider

class TerraformProvider(IInfrastructureProvider):
    def create_vpn_peer(self, peer, profile):
        # Generate Terraform config
        # Run: terraform apply
        pass
    
    def destroy_vpn_peer(self, peer_name):
        # Run: terraform destroy
        pass
    
    # ... implement other methods
```

### 2. Export from Module

```python
# infrastructure/providers/__init__.py
from .terraform_provider import TerraformProvider

__all__ = [
    "IInfrastructureProvider",
    "PulumiProvider",
    "TerraformProvider",  # Add new provider
]
```

### 3. Update CLI

```python
# presentation/cli/commands/provider/switch.py
# Update to include terraform option
```

### 4. Test

```python
# tests/unit/infrastructure/test_terraform_provider.py
def test_terraform_create_vpn_peer():
    provider = TerraformProvider("peer-name")
    result = provider.create_vpn_peer(sample_peer, sample_profile)
    assert result['vpn_id']
```

---

## Common Tasks

### Adding a New Command

```bash
# Create command module
touch presentation/cli/commands/new_group/new_command.py

# Implement
# presentation/cli/commands/new_group/new_command.py
@click.command()
@click.argument('peer_name')
@click.pass_context
def new_command(ctx, peer_name):
    """Do something with peer."""
    pass

# Register in group
# presentation/cli/commands/new_group/__init__.py
from .new_command import new_command

new_group.add_command(new_command)
```

### Adding Validation Rules

```python
# domain/validators/vpn_peer_validator.py
def validate_spec(self, spec: Dict) -> Tuple[bool, List[str]]:
    errors = []
    
    # Add new validation rule
    if "new_field" not in spec:
        errors.append("new_field is required")
    
    return len(errors) == 0, errors
```

### Adding Logging

```python
# In any module
from observability.logging import get_logger, log_operation

logger = get_logger(__name__)
logger.info("Something happened")

log_operation("deploy", peer_name="vimenca", status="success")
```

---

## Debugging

### Print Debugging

```python
# Always use logging, not print()
from observability.logging import get_logger

logger = get_logger(__name__)
logger.debug(f"Peer: {peer}")  # Won't show in CI, only in local development
```

### Check Logs

```bash
# CLI logs
tail -f logs/vpn-ctl.log

# Peer-specific audit
find .pulumi/peer-states -name "audit.jsonl" -exec cat {} \;
```

### Run Tests in Verbose Mode

```bash
pytest tests/ -vvv -s
```

### Debug Pulumi State

```bash
cd pulumi
pulumi stack select dev
pulumi export --json | python3 -m json.tool | less
```

---

## Performance

### Profile Code

```python
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

# Code to profile here

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(10)  # Top 10 functions
```

### Optimize Hot Paths

- Domain service calls (happens on every deploy)
- YAML file I/O (happens every command)
- AWS API calls (can be cached)

---

## Deployment

### Pre-Merge Checklist

- [ ] Tests passing: `make test-cov`
- [ ] Code formatted: `make format`
- [ ] Linting passing: `make lint`
- [ ] Type checking passing: `make typecheck`
- [ ] Manual testing done: `vpn-ctl ...`
- [ ] Documentation updated
- [ ] Commit message clear and descriptive

### Release Process

```bash
# Update version
# pyproject.toml: version = "1.1.0"
# presentation/cli/main.py: "vpn-ctl v1.1.0"

# Tag release
git tag -a v1.1.0 -m "Release 1.1.0"

# Push
git push origin v1.1.0

# GitHub Actions auto-builds and publishes
```

---

## Resources

- [ARCHITECTURE.md](./ARCHITECTURE.md) - System design
- [STATE_EXTRACTION.md](./STATE_EXTRACTION.md) - Migration process
- [CLI.md](./CLI.md) - Command reference
- [README.md](./README.md) - Quick start
- Domain-Driven Design book by Eric Evans
- SOLID principles: https://en.wikipedia.org/wiki/SOLID

