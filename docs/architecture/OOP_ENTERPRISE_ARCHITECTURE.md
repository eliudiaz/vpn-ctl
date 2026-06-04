# Enterprise OOP Architecture: IaC Provider Abstraction

## Overview

This document describes the enterprise-grade, OOP-based architecture for vpnctl CLI that enables:

- **Provider-agnostic** infrastructure management (Pulumi, Terraform, CloudFormation)
- **SOLID principles** throughout (Single Responsibility, Open/Closed, Liskov Substitution, Interface Segregation, Dependency Inversion)
- **Clean architecture** with clear layer separation
- **Extensibility** - adding new IaC providers requires only new class, no changes to existing code
- **Testability** - tests work with any provider implementation

## Architecture Layers (10 Layers)

```
Layer 10: Presentation (vpnctl CLI)
    ↓
Layer 9: Application Services (PeerManagementService)
    ↓
Layer 8: Domain Logic (VpnPeer, DestinationCidr, Validators)
    ↓
Layer 7: IaC Provider Abstraction (IacProvider interface)
    ↓
Layer 6: IaC Provider Implementations (PulumiProvider, TerraformProvider, etc.)
    ↓
Layer 5: State Management & Persistence
    ↓
Layer 4: Command Execution & Process Management
    ↓
Layer 3: Infrastructure Operations (AWS API)
    ↓
Layer 2: Configuration & Dependency Injection
    ↓
Layer 1: External Systems (Pulumi, AWS, Git)
```

## Key Components

### Layer 7: IaC Provider Abstraction

**File:** `infrastructure/iac_providers/abstract_provider.py`

```python
class IacProvider(ABC):
    """Abstract base for any IaC provider (Pulumi, Terraform, CloudFormation)"""

    @abstractmethod
    def add_route(self, cidr: str) -> OperationResult:
        """Add destination CIDR"""

    @abstractmethod
    def deploy(self, preview_only: bool = False) -> OperationResult:
        """Deploy configuration to AWS"""

    @abstractmethod
    def diff(self) -> DiffResult:
        """Compare config vs AWS state"""

    # ... more methods
```

**Key principle:** All providers implement this interface. vpnctl CLI uses this interface, never directly calls Pulumi/Terraform.

### Layer 6: Pulumi Provider Implementation

**File:** `infrastructure/iac_providers/pulumi_provider.py`

```python
class PulumiProvider(IacProvider):
    """Pulumi-specific implementation"""

    def add_route(self, cidr: str) -> OperationResult:
        # Pulumi-specific logic
        config = self._load_config()
        config['destination_cidrs'].append(cidr)
        self._save_config(config)
        result = self.executor.run_pulumi_up()
        return OperationResult(...)
```

**Key principle:** All Pulumi-specific logic is in PulumiProvider. If you add Terraform support, create TerraformProvider - no changes to existing code.

### Layer 7: Factory Pattern

**File:** `infrastructure/iac_providers/factory.py`

```python
class IacProviderFactory:
    """Creates provider instances based on configuration"""

    @classmethod
    def get_active_provider(cls, peer_name: str, config: dict) -> IacProvider:
        # Get 'iac_provider' from config (defaults to 'pulumi')
        provider_name = config.get('iac_provider', 'pulumi')
        return cls.create(peer_name, provider_name, config)
```

**Key principle:** Single factory for creating providers. Change `iac_provider` config value to switch providers.

### Layer 9: Application Services

**File:** `application/services/peer_management_service.py`

```python
class PeerManagementService:
    """Application service - provider-agnostic"""

    def add_destination_cidr(self, peer_name: str, cidr: str) -> PeerOperationResult:
        # Get provider (could be Pulumi, Terraform, etc.)
        provider = IacProviderFactory.get_active_provider(peer_name, config)

        # Use provider interface (same regardless of implementation)
        result = provider.add_route(cidr)

        # Publish event for audit trail
        self.event_publisher.publish({
            "event": "cidr_added",
            "provider": provider.get_provider_name(),
        })

        return PeerOperationResult(...)
```

**Key principle:** Service doesn't know which provider is being used. Works with any provider.

### Layer 10: CLI Commands

**File:** `presentation/cli/commands/peer_add_route.py`

```python
@click.command()
@click.argument('peer_name')
@click.argument('cidr')
def add_route(ctx, peer_name: str, cidr: str):
    """Add route - provider-agnostic"""
    service = ctx.obj['peer_service']
    result = service.add_destination_cidr(peer_name, cidr)

    if result.success:
        click.secho(f"✓ Route added via {result.provider_name}", fg='green')
```

**Key principle:** CLI doesn't care which provider is active. Just calls service method.

## Design Patterns Used

### 1. Strategy Pattern (IaC Provider)

Each provider is a "strategy" for managing infrastructure. The `IacProvider` interface defines the strategy contract.

```python
# At runtime, swap the strategy
config = {'iac_provider': 'pulumi'}    # Use PulumiProvider strategy
provider = IacProviderFactory.get_active_provider(peer_name, config)

# Change to Terraform
config = {'iac_provider': 'terraform'}  # Use TerraformProvider strategy
provider = IacProviderFactory.get_active_provider(peer_name, config)
```

### 2. Factory Pattern

Creates provider instances without exposing instantiation logic.

```python
IacProviderFactory.register('pulumi', PulumiProvider)
IacProviderFactory.register('terraform', TerraformProvider)

provider = IacProviderFactory.get_active_provider('mock-peer-a', config)
```

### 3. Dependency Injection

Services receive their dependencies (providers, config) rather than creating them.

```python
service = PeerManagementService(
    config_manager=config_manager,
    event_publisher=event_publisher
)
# Service uses injected config_manager to get provider
provider = IacProviderFactory.get_active_provider(peer_name, config)
```

### 4. Adapter Pattern

Providers adapt infrastructure tools (Pulumi, Terraform) to a common interface.

```
Pulumi CLI     →  PulumiProvider  →
Terraform CLI  →  TerraformProvider  →  IacProvider Interface
CloudFormation →  CloudFormationProvider  →
```

## Benefits of This Architecture

### 1. **Provider Agnosticism**

```python
# Same code works with any provider
result = service.add_destination_cidr(peer_name, cidr)

# Provider implementation can be swapped via config
# No code changes needed
```

### 2. **Testability**

```python
# Create mock provider for testing
class MockProvider(IacProvider):
    def add_route(self, cidr: str) -> OperationResult:
        return OperationResult(...)

# Tests work without actual Pulumi/AWS
provider = MockProvider('test-peer', {})
result = provider.add_route('172.16.80.0/24')
```

### 3. **Extensibility**

```python
# Adding Terraform support:
class TerraformProvider(IacProvider):
    def add_route(self, cidr: str) -> OperationResult:
        # Terraform-specific logic
        pass

# Register it
IacProviderFactory.register('terraform', TerraformProvider)

# Existing code works unchanged
provider = IacProviderFactory.get_active_provider(peer_name, config)
```

### 4. **Single Responsibility**

- **IacProvider:** Define what infrastructure operations are needed
- **PulumiProvider:** Implement those operations for Pulumi
- **PeerManagementService:** Orchestrate business logic using providers
- **CLI:** Present interface to users

Each class has one reason to change.

### 5. **Open/Closed Principle**

- Open for extension: Add new providers without changing existing code
- Closed for modification: Existing providers and services stay unchanged

## How to Add a New Provider (Terraform)

### Step 1: Create Provider Class

```python
# infrastructure/iac_providers/terraform_provider.py

class TerraformProvider(IacProvider):
    """Terraform-specific implementation"""

    def add_route(self, cidr: str) -> OperationResult:
        # Terraform-specific logic
        tf_file = f"terraform/peers/{self.peer_name}/main.tf"
        # ... modify Terraform config
        # ... run: terraform apply
        return OperationResult(...)

    # Implement all abstract methods...
```

### Step 2: Register Provider

```python
# infrastructure/iac_providers/bootstrap.py

def bootstrap_providers():
    IacProviderFactory.register('pulumi', PulumiProvider)
    IacProviderFactory.register('terraform', TerraformProvider)  # Add this
```

### Step 3: Configure to Use It

```yaml
# Pulumi.mock-peer-a.yaml

iac_provider: terraform  # Switch to Terraform

# All existing CLI commands work unchanged!
```

### Step 4: Done

No changes to CLI, services, or domain logic. Everything works with Terraform.

## Result Types: Standardized Across All Providers

All providers return standardized result types:

```python
@dataclass
class OperationResult:
    status: OperationStatus  # SUCCESS, FAILED, SKIPPED, etc.
    message: str             # "Route added"
    details: Dict[str, Any]  # Additional data
    duration_ms: int         # How long operation took
    provider_name: str       # "pulumi", "terraform", etc.
    error: Optional[Exception]

@dataclass
class DiffResult:
    added: List[Dict]     # What would be created
    removed: List[Dict]   # What would be deleted
    modified: List[Dict]  # What would change
    in_sync: bool         # Already in sync?
```

This standardization lets the CLI and services work with any provider.

## SOLID Principles Applied

### Single Responsibility Principle

- **IacProvider:** Abstract interface for infrastructure operations
- **PulumiProvider:** Pulumi-specific implementation only
- **PeerManagementService:** Business logic orchestration
- **CLI:** User interface

### Open/Closed Principle

- Open for extension: Add new providers by implementing IacProvider
- Closed for modification: Existing providers unchanged

### Liskov Substitution Principle

All providers (Pulumi, Terraform, CloudFormation) are substitutable:

```python
# Works with any provider
provider: IacProvider = IacProviderFactory.get_active_provider(...)
result = provider.add_route(cidr)  # Same interface, different implementation
```

### Interface Segregation Principle

`IacProvider` interface is cohesive:

- Only methods needed for infrastructure management
- No unnecessary methods that some providers don't use

### Dependency Inversion Principle

High-level modules (CLI, Service) depend on abstractions (IacProvider):

```
CLI → Service → IacProvider (abstraction)
              ↓
          PulumiProvider (concrete)
          TerraformProvider (concrete)
```

Services don't depend on concrete providers.

## Testing Strategy

### Unit Tests (Mock Provider)

```python
# Tests use mock provider, not real Pulumi
class MockIacProvider(IacProvider):
    def add_route(self, cidr: str) -> OperationResult:
        return OperationResult(status=OperationStatus.SUCCESS, ...)

# Register mock
IacProviderFactory.register('mock', MockIacProvider)

# Test works with any provider (mock, pulumi, terraform)
result = service.add_destination_cidr('test-peer', '172.16.80.0/24')
assert result.success
```

### Integration Tests (Real Provider)

```python
# Tests use real Pulumi provider with test AWS resources
config = {'iac_provider': 'pulumi'}
provider = IacProviderFactory.get_active_provider('test-peer', config)

result = provider.add_route('172.16.80.0/24')
# Verify in AWS
assert aws.verify_route_exists('172.16.80.0/24')
```

## File Structure

```
infrastructure/
  iac_providers/
    __init__.py                    # Public API
    abstract_provider.py           # IacProvider interface + result types
    factory.py                     # IacProviderFactory
    bootstrap.py                   # Provider registration
    pulumi_provider.py             # PulumiProvider implementation
    # terraform_provider.py        # (future) TerraformProvider
    # cloudformation_provider.py   # (future) CloudFormationProvider

application/
  services/
    peer_management_service.py     # Uses IacProvider (provider-agnostic)

presentation/
  cli/
    bootstrap.py                   # CLI initialization
    commands/
      peer_add_route.py            # CLI command (provider-agnostic)
      peer_deploy.py               # CLI command (provider-agnostic)
      peer_diff.py                 # CLI command (provider-agnostic)

tests/
  unit/
    test_iac_provider_abstraction.py  # Tests work with any provider
```

## Summary

This enterprise architecture provides:

✅ **Provider-agnostic** operations (works with Pulumi, Terraform, CloudFormation)
✅ **Clean separation** of concerns (layers, SOLID principles)
✅ **Extensibility** (add providers without changing existing code)
✅ **Testability** (mock providers for unit tests)
✅ **Maintainability** (each component has single responsibility)
✅ **Professional quality** (enterprise-grade design patterns)

The system is designed to scale from 4 VPNs to 100+ VPNs, and from one IaC provider to multiple providers, without architectural changes.
