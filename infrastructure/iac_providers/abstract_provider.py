"""Abstract base class for IaC providers.

Defines the interface that all IaC implementations (Pulumi, Terraform, CloudFormation)
must implement. Enables provider-agnostic infrastructure operations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any
from datetime import datetime


class OperationStatus(Enum):
    """Status of an IaC operation"""
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"
    SKIPPED = "skipped"
    ROLLBACK = "rollback"


@dataclass
class OperationResult:
    """Standardized result from any IaC operation"""
    status: OperationStatus
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0
    provider_name: str = ""
    error: Optional[Exception] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def is_success(self) -> bool:
        return self.status == OperationStatus.SUCCESS

    def __str__(self) -> str:
        status_str = "✓" if self.is_success else "❌"
        return f"{status_str} {self.message}"


@dataclass
class DiffResult:
    """Diff between desired (config) and actual (AWS) state"""
    added: List[Dict[str, Any]] = field(default_factory=list)
    removed: List[Dict[str, Any]] = field(default_factory=list)
    modified: List[Dict[str, Any]] = field(default_factory=list)
    in_sync: bool = False

    def has_drift(self) -> bool:
        """Check if there's any drift between desired and actual state"""
        return len(self.added) > 0 or len(self.removed) > 0 or len(self.modified) > 0


@dataclass
class StateSnapshot:
    """Point-in-time snapshot of infrastructure state"""
    peer_name: str
    timestamp: str
    provider_name: str
    resources: Dict[str, Any] = field(default_factory=dict)
    routes: List[str] = field(default_factory=list)
    tunnel_ips: List[str] = field(default_factory=list)
    health_checks: List[str] = field(default_factory=list)
    config_hash: str = ""


@dataclass
class ImmutableResources:
    """References to immutable resources that must never change"""
    vpn_id: str
    customer_gateway_id: str
    tgw_attachment_id: str
    tunnel_ips: List[str]
    last_verified: str = field(default_factory=lambda: datetime.now().isoformat())


class IacProvider(ABC):
    """
    Abstract base for any IaC provider (Pulumi, Terraform, CloudFormation).

    Key principle: Implementations handle provider-specific details.
    All callers use this interface - completely provider-agnostic.

    Usage:
        # Get active provider (Pulumi, Terraform, or CloudFormation)
        provider = IacProviderFactory.get_active_provider(peer_name, config)

        # Use same interface regardless of provider
        result = provider.add_route("172.16.80.0/24")
        result = provider.deploy()
        diff = provider.diff()
    """

    def __init__(self, peer_name: str, config: Dict[str, Any]):
        """Initialize provider for a specific peer.

        Args:
            peer_name: Name of peer (e.g., 'mock-peer-a', 'mock-peer-b')
            config: Peer configuration (e.g., Pulumi.yaml content)
        """
        self.peer_name = peer_name
        self.config = config

    # ========================================================================
    # PROVIDER IDENTITY
    # ========================================================================

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return provider name: 'pulumi', 'terraform', 'cloudformation'"""
        pass

    # ========================================================================
    # ROUTE MANAGEMENT (Mutable Resources)
    # ========================================================================

    @abstractmethod
    def add_route(self, cidr: str) -> OperationResult:
        """Add destination CIDR route for this peer.

        Guarantees:
        - Idempotent: calling twice with same CIDR is safe
        - Atomic: all related resources created together or rolled back
        - Auditable: changes tracked in git/provider state

        Args:
            cidr: Destination CIDR (e.g., '172.16.80.0/24')

        Returns:
            OperationResult with status and details
        """
        pass

    @abstractmethod
    def remove_route(self, cidr: str) -> OperationResult:
        """Remove destination CIDR route.

        Args:
            cidr: CIDR to remove

        Returns:
            OperationResult with status
        """
        pass

    @abstractmethod
    def update_routes(self, cidrs: List[str]) -> OperationResult:
        """Update routes to EXACTLY match cidr list.

        Removes routes not in list, adds routes in list.
        Atomic operation - all succeed or all rollback.

        Args:
            cidrs: Exact list of destination CIDRs

        Returns:
            OperationResult with changes made
        """
        pass

    # ========================================================================
    # HEALTH CHECK MANAGEMENT (Mutable Resources)
    # ========================================================================

    @abstractmethod
    def set_health_checks(self, target_ips: List[str]) -> OperationResult:
        """Create Route53 health checks for target IPs.

        Args:
            target_ips: List of IPs to monitor

        Returns:
            OperationResult with created health check IDs
        """
        pass

    # ========================================================================
    # BGP & TUNNEL CONFIGURATION (Partially Mutable)
    # ========================================================================

    @abstractmethod
    def set_bgp_metric(self, metric: int) -> OperationResult:
        """Update BGP metric (affects route preference).

        Args:
            metric: BGP metric value (0-65535)

        Returns:
            OperationResult with status
        """
        pass

    @abstractmethod
    def set_tunnel_preference(self, preferred_tunnel: int) -> OperationResult:
        """Set which tunnel is preferred (1 or 2).

        Args:
            preferred_tunnel: 1 or 2

        Returns:
            OperationResult with status
        """
        pass

    # ========================================================================
    # PSK MANAGEMENT (Sensitive - Immutable at Pulumi level, mutable at AWS)
    # ========================================================================

    @abstractmethod
    def rotate_psk(self) -> OperationResult:
        """Rotate Pre-Shared Keys (security operation).

        Returns:
            OperationResult with masked PSK information for verification
        """
        pass

    # ========================================================================
    # STATE & DIFF OPERATIONS (Read-Only)
    # ========================================================================

    @abstractmethod
    def get_current_state(self) -> StateSnapshot:
        """Get current state snapshot from provider.

        Returns:
            StateSnapshot containing all infrastructure details
        """
        pass

    @abstractmethod
    def diff(self) -> DiffResult:
        """Compare desired config vs actual AWS state.

        Returns:
            DiffResult showing what would be added/removed/modified
        """
        pass

    @abstractmethod
    def refresh(self) -> OperationResult:
        """Refresh provider state from AWS.

        Useful if AWS changed outside provider (manual Console changes).

        Returns:
            OperationResult with status
        """
        pass

    # ========================================================================
    # DEPLOYMENT & ROLLBACK (Critical Operations)
    # ========================================================================

    @abstractmethod
    def deploy(self, preview_only: bool = False) -> OperationResult:
        """Deploy configuration to AWS via provider.

        Guarantees:
        - Immutable resources (VPN, CGW, attachment) are never recreated
        - All changes are atomic (all succeed or all rollback)
        - Audit trail is created (git commit)

        Args:
            preview_only: If True, show what would happen (dry-run)

        Returns:
            OperationResult with deployment details
        """
        pass

    @abstractmethod
    def rollback(self, target_state: StateSnapshot) -> OperationResult:
        """Rollback to previous state snapshot.

        Args:
            target_state: State to rollback to

        Returns:
            OperationResult with rollback details
        """
        pass

    @abstractmethod
    def destroy(self) -> OperationResult:
        """Destroy all peer infrastructure (DANGEROUS).

        Returns:
            OperationResult with destruction details
        """
        pass

    # ========================================================================
    # IMMUTABLE RESOURCE PROTECTION (Safety Mechanisms)
    # ========================================================================

    @abstractmethod
    def verify_tunnel_ips(self, expected_ips: List[str]) -> OperationResult:
        """CRITICAL: Verify tunnel IPs haven't changed.

        Hard-stops if they have (prevents accidental VPN recreation).

        Args:
            expected_ips: Expected tunnel IPs

        Returns:
            OperationResult with verification result
        """
        pass

    @abstractmethod
    def verify_vpn_connection(self, expected_vpn_id: str) -> OperationResult:
        """Verify VPN connection ID is correct (immutable).

        Args:
            expected_vpn_id: Expected VPN connection ID

        Returns:
            OperationResult with verification result
        """
        pass

    @abstractmethod
    def get_immutable_resources(self) -> ImmutableResources:
        """Get immutable resource IDs (VPN, CGW, attachment, tunnel IPs).

        These should NEVER change during operations.

        Returns:
            ImmutableResources with all immutable resource references
        """
        pass

    # ========================================================================
    # CONFIGURATION & METADATA
    # ========================================================================

    @abstractmethod
    def get_config(self) -> Dict[str, Any]:
        """Get current configuration.

        Returns:
            Configuration dictionary
        """
        pass

    @abstractmethod
    def validate_config(self) -> OperationResult:
        """Validate configuration syntax and constraints.

        Returns:
            OperationResult with validation result
        """
        pass

    @abstractmethod
    def export_state(self, format: str = "json") -> str:
        """Export state for backup/analysis.

        Args:
            format: 'json' or 'yaml'

        Returns:
            State export as string
        """
        pass
