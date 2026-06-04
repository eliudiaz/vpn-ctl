# vpn-ctl Architecture - 8-Layer Orthogonal Design

## Overview

**vpn-ctl** is an enterprise-grade VPN infrastructure control platform built on an **8-layer orthogonal architecture** that separates concerns and enables provider agnosticism (Pulumi, Terraform, CloudFormation).

The architecture ensures:
- ✅ **Provider agnosticism** - Zero IaC code in domain logic
- ✅ **Per-peer isolation** - Each peer has independent state and lifecycle
- ✅ **SOLID principles** - Clean, testable, maintainable code
- ✅ **Type safety** - Immutable value objects with validation
- ✅ **Audit trails** - Complete operation tracking and compliance
- ✅ **Safe migrations** - Zero-loss state extraction from monolith

---

## Layer Architecture

### Layer 8: Presentation
**User-facing interfaces**

```
presentation/cli/
├── main.py                    CLI entry point
├── commands/                  Command modules
│   ├── peer/                 Peer management (add, deploy, destroy, status, list)
│   ├── spec/                 Spec management (validate, sync)
│   ├── tunnel/               Tunnel monitoring (status, health)
│   └── provider/             Provider management (list, switch)
├── interactive/              Interactive helpers
│   ├── peer_wizard.py        Guided peer creation
│   ├── prompts.py            Reusable prompts
│   └── formatters.py         Output formatting
└── state_manager/            State management
    ├── peer_state_store.py   Per-peer state
    └── state_sync.py         Spec/state sync logic
```

**Responsibility:** User interaction, CLI workflows, input collection, output formatting.

**Technology:** Click framework, interactive prompts.

---

### Layer 7: Orchestration
**Workflows that coordinate multiple services**

```
Not yet implemented - future layers as needed:
- DeploymentWorkflow (validate → preview → deploy → audit)
- MigrationWorkflow (state extraction)
- SpecSyncWorkflow (spec ↔ state reconciliation)
```

**Responsibility:** Complex multi-step operations, error recovery, rollback.

---

### Layer 6: Application
**Use case orchestration**

```
application/services/
├── deployment_service.py      Deployment use case
│   - deploy_peer()           Deploy a peer
│   - destroy_peer()          Destroy peer
│   - preview_deployment()    Dry-run preview
│   - get_peer_status()       Query status
```

**Responsibility:** Use case implementation, validation sequencing, error handling.

**Dependencies:** Domain services, repositories, providers (injected).

---

### Layer 5: Domain
**Business logic and entities (provider-agnostic)**

```
domain/
├── models/
│   ├── value_objects.py      BGPASN, CIDR, PSK, PeerName, PublicIP
│   ├── vpn_peer.py           VpnPeer entity with validation
│   └── tunnel_profile.py      TunnelProfile entity with IPsec config
├── services/
│   ├── vpn_peer_service.py    Peer lifecycle (create, get, delete)
│   └── psk_service.py         PSK generation and validation
├── validators/
│   ├── vpn_peer_validator.py  Spec validation
│   └── tunnel_profile_validator.py  Profile validation
├── repositories/              Interfaces (no implementation)
│   ├── vpn_peer_repository.py
│   ├── tunnel_profile_repository.py
│   └── state_repository.py
└── exceptions.py              Domain-specific exceptions
```

**Responsibility:** Business rules, validation, entities.

**Technology:** Dataclasses with `__post_init__` validation, immutable value objects.

**Key principle:** ZERO dependencies on IaC tools. Domain logic works with any provider.

---

### Layer 4: Specifications & Ports
**Interfaces defining contracts (domain → infrastructure)**

```
domain/repositories/ (abstract interfaces):
- VpnPeerRepository: save(), get(), get_all(), exists(), delete()
- TunnelProfileRepository: get(), get_all(), save()
- StateRepository: get_stack_state(), import_stack_state(), backup(), restore()
```

**Responsibility:** Define contracts that adapters must implement.

**Technology:** Python abstract base classes (ABC).

---

### Layer 3: Adapters & Infrastructure
**Provider-specific implementations**

```
infrastructure/
├── providers/
│   ├── interfaces.py                    IInfrastructureProvider (abstract)
│   └── pulumi_provider.py               PulumiProvider (Pulumi implementation)
│                                        (TerraformProvider, CloudFormationProvider future)
├── repositories/
│   ├── yaml_peer_repository.py          YAML file storage
│   ├── yaml_profile_repository.py       YAML profile storage
│   └── pulumi_state_repository.py       Pulumi state management
└── config/                              Configuration loading
    ├── loader.py                        YAML config loader
    └── validator.py                     Schema validation
```

**Responsibility:** Adapt domain logic to external systems (Pulumi, AWS, YAML files).

**Technology:** Subprocess (Pulumi CLI), boto3 (AWS), PyYAML.

---

### Layer 2: External Systems
**Third-party services and tools**

```
- Pulumi (Infrastructure as Code)
- AWS (VPN endpoints, Transit Gateway, EC2)
- YAML (Peer specifications, tunnel profiles)
```

---

### Layer 1: Infrastructure
**Physical/cloud resources**

```
- VPN Connections (AWS)
- Customer Gateways (AWS)
- Transit Gateway Routes
- VPC Route Tables
- Security Groups
```

---

## Data Flow Example: Deploy a Peer

```
┌─ Layer 8: Presentation ─────────────────────────────────┐
│ vpn-ctl peer deploy customer-x                          │
│ ├─ Load peer spec from YAML (config/peers/customer-x.yaml)
│ └─ Create DeploymentService                             │
└────────────────────┬──────────────────────────────────────┘
                     │
┌─ Layer 6: Application ──────────────────────────────────┐
│ DeploymentService.deploy_peer(peer)                     │
│ ├─ Validate peer (calls VpnPeerService.validate_peer) │
│ ├─ Get tunnel profile (calls TunnelProfileRepository)  │
│ └─ Call provider.create_vpn_peer()                      │
└────────────────────┬──────────────────────────────────────┘
                     │
┌─ Layer 5: Domain ──────────────────────────────────────┐
│ VpnPeerService.validate_peer(peer)                      │
│ ├─ Check CIDR overlap (business rule)                  │
│ ├─ Verify no conflicts                                  │
│ └─ Return validation result                             │
└────────────────────┬──────────────────────────────────────┘
                     │
┌─ Layer 3: Adapters ────────────────────────────────────┐
│ PulumiProvider.create_vpn_peer(peer, profile)           │
│ ├─ Generate Pulumi program (Python)                     │
│ ├─ Run: pulumi up --yes                                │
│ └─ Parse outputs (VPN ID, tunnel IPs)                   │
└────────────────────┬──────────────────────────────────────┘
                     │
┌─ Layer 2: External Systems ───────────────────────────┐
│ Pulumi CLI                                             │
│ ├─ Read stack configuration                            │
│ └─ Call AWS SDK                                         │
└────────────────────┬──────────────────────────────────────┘
                     │
┌─ Layer 1: Infrastructure ─────────────────────────────┐
│ AWS VPC Service                                        │
│ ├─ Create Customer Gateway                             │
│ ├─ Create VPN Connection                               │
│ ├─ Create Transit Gateway Routes                       │
│ └─ Return resource IDs and status                       │
└──────────────────────────────────────────────────────┘
```

---

## Dependency Injection Pattern

All layers use **constructor injection** to receive dependencies:

```python
# Layer 6: Application
class DeploymentService:
    def __init__(
        self,
        provider: IInfrastructureProvider,      # Interface, not implementation
        peer_service: VpnPeerService,
        profile_repo: TunnelProfileRepository,
    ):
        self.provider = provider

# At CLI entry point (main.py):
provider = PulumiProvider("peer-name")         # Today: Pulumi
# provider = TerraformProvider("peer-name")   # Tomorrow: Terraform
deployment_svc = DeploymentService(provider, peer_svc, profile_repo)
```

This enables:
- Swapping providers without changing application logic
- Easy testing (inject mock provider)
- Provider-agnostic business logic

---

## SOLID Principles

| Principle | Application |
|-----------|-------------|
| **S** - Single Responsibility | Each class has one reason to change: VpnPeer validates peer logic, PulumiProvider handles Pulumi integration |
| **O** - Open/Closed | Open to extension (new providers), closed to modification (domain logic unchanged) |
| **L** - Liskov Substitution | All providers implement IInfrastructureProvider interface identically |
| **I** - Interface Segregation | Interfaces are focused: StateRepository for state, VpnPeerRepository for peers |
| **D** - Dependency Inversion | Depend on abstractions (interfaces), not concrete implementations |

---

## Type Safety

**Immutable value objects** enforce constraints:

```python
# ✅ Type-safe, validated
bgp_asn = BGPASN(65000)      # Valid
peer_name = PeerName("my-peer")

# ❌ Type-safe validation
try:
    BGPASN(99999)             # Raises ValidationError
except ValidationError:
    pass

# Frozenset ensures CIDRs can't be modified
destination_cidrs: frozenset[CIDR] = frozenset([CIDR("10.0.0.0/16")])
destination_cidrs.add(...)  # TypeError: frozenset object does not support item assignment
```

---

## Configuration Management

**YAML specs** follow Kubernetes-like structure:

```yaml
# config/peers/customer-x.yaml
apiVersion: v1
kind: VpnPeer
metadata:
  name: customer-x
  created: 2026-04-16T08:00:00Z
spec:
  publicIp: 203.0.113.50
  bgpAsn: 65000
  deviceType: checkpoint
  tunnelProfile: checkpoint_r80
  destinationCidrs:
    - 10.0.0.0/16
    - 10.1.0.0/16
  contacts:
    - name: John Doe
      email: john@example.com
      phone: +1-555-1234
```

Benefits:
- Familiar to Kubernetes users
- Version-controlled
- Easy to diff changes
- Enables spec ↔ state synchronization

---

## Testing Strategy

**Layer-by-layer testing:**

```
tests/
├── unit/
│   ├── domain/
│   │   ├── test_value_objects.py      Value object validation
│   │   ├── test_vpn_peer.py           Entity business logic
│   │   └── test_services.py           Domain services
│   ├── infrastructure/
│   │   ├── test_yaml_repository.py    File persistence
│   │   └── test_pulumi_provider.py    Provider integration (mocked)
│   └── application/
│       └── test_deployment_service.py  Use case orchestration
└── integration/
    └── test_deployment_flow.py         End-to-end scenarios
```

**Coverage targets:**
- Domain logic: 95%+ (business rules must be rock-solid)
- Application: 85%+
- Infrastructure: 70%+ (more integration-dependent)
- Presentation: Tested manually via CLI

---

## Provider Agnosticism

### Today: Pulumi
```python
provider = PulumiProvider("peer-name")
```

### Tomorrow: Terraform or CloudFormation
```python
provider = TerraformProvider("peer-name")
provider = CloudFormationProvider("peer-name")

# Same interface, different provider
result = provider.create_vpn_peer(peer, profile)
```

**All adapters implement:**
```python
class IInfrastructureProvider(ABC):
    def create_vpn_peer(self, peer, profile) -> Dict
    def destroy_vpn_peer(self, peer_name: str) -> None
    def get_peer_status(self, peer_name: str) -> Dict
    def preview_deployment(self, peer, profile) -> Dict
```

---

## Key Files

| File | Responsibility |
|------|-----------------|
| `domain/models/value_objects.py` | Immutable, validated types |
| `domain/models/vpn_peer.py` | VpnPeer entity with business rules |
| `domain/services/vpn_peer_service.py` | Peer lifecycle orchestration |
| `infrastructure/providers/interfaces.py` | Provider contract |
| `infrastructure/providers/pulumi_provider.py` | Pulumi implementation |
| `infrastructure/repositories/yaml_peer_repository.py` | YAML persistence |
| `application/services/deployment_service.py` | Deployment use case |
| `presentation/cli/main.py` | CLI entry point |
| `observability/audit.py` | Audit trails for compliance |

---

## Future Extensions

This architecture enables:

1. **Additional providers**: TerraformProvider, CloudFormationProvider
2. **REST API**: Build a FastAPI server using same services/domain
3. **Kubernetes operator**: Use same services in a controller
4. **GitOps/Flux**: Observe spec Git repo, sync with infrastructure
5. **Multi-cloud**: Add AWS, Azure, GCP providers
6. **Advanced workflows**: Auto-remediation, self-healing tunnels

All without changing domain logic!

---

## Deployment Checklist

- [ ] Install dependencies: `make install`
- [ ] Run tests: `make test-cov`
- [ ] Validate specs: `vpn-ctl spec validate`
- [ ] Deploy peer: `vpn-ctl peer deploy customer-x`
- [ ] Check tunnel status: `vpn-ctl tunnel status`
- [ ] Review audit log: `vpn-ctl state audit customer-x`
