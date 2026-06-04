"""
Tunnel Profile Domain Model

Immutable IPsec/IKE tunnel configuration profile.
"""

from dataclasses import dataclass
from typing import List

from domain.exceptions import DomainValidationError


@dataclass(frozen=True)
class TunnelProfile:
    """
    IPsec/IKE tunnel configuration profile.

    Defines Phase 1 and Phase 2 parameters for VPN tunnels.
    Immutable - created once, used by all peers with this profile.
    """

    name: str
    description: str

    # IKE Phase 1
    ike_versions: List[str]
    phase1_encryption: List[str]
    phase1_integrity: List[str]
    phase1_dh_groups: List[int]
    phase1_lifetime: int

    # IPsec Phase 2
    phase2_encryption: List[str]
    phase2_integrity: List[str]
    phase2_dh_groups: List[int]
    phase2_lifetime: int

    # Options
    dpd_timeout: int
    dpd_action: str
    static_routes_only: bool = True

    def __post_init__(self):
        """Validate tunnel profile invariants."""
        self._validate_name()
        self._validate_ike_versions()
        self._validate_phase1()
        self._validate_phase2()
        self._validate_dpd()

    def _validate_name(self):
        """Name must be alphanumeric + underscore."""
        if not self.name or not all(c.isalnum() or c == '_' for c in self.name):
            raise DomainValidationError(f"Invalid profile name: {self.name}")

    def _validate_ike_versions(self):
        """IKE versions must be ikev1 or ikev2."""
        valid = {'ikev1', 'ikev2'}
        invalid = set(self.ike_versions) - valid
        if invalid:
            raise DomainValidationError(
                f"Invalid IKE versions: {invalid} (must be {valid})"
            )

    def _validate_phase1(self):
        """Phase 1 parameters must be valid."""
        if self.phase1_lifetime < 600:
            raise DomainValidationError(
                f"Phase 1 lifetime too short: {self.phase1_lifetime}s "
                f"(minimum 600s)"
            )
        if not self.phase1_dh_groups:
            raise DomainValidationError("Phase 1 DH groups cannot be empty")

    def _validate_phase2(self):
        """Phase 2 parameters must be valid."""
        if self.phase2_lifetime < 600:
            raise DomainValidationError(
                f"Phase 2 lifetime too short: {self.phase2_lifetime}s "
                f"(minimum 600s)"
            )

    def _validate_dpd(self):
        """DPD timeout must be reasonable."""
        if self.dpd_timeout < 10:
            raise DomainValidationError(
                f"DPD timeout too short: {self.dpd_timeout}s (minimum 10s)"
            )
        valid_actions = {'restart', 'clear', 'hold', 'none'}
        if self.dpd_action not in valid_actions:
            raise DomainValidationError(
                f"Invalid DPD action: {self.dpd_action} (must be {valid_actions})"
            )

    @property
    def is_pfs_enabled(self) -> bool:
        """Check if Perfect Forward Secrecy is enabled."""
        return bool(self.phase2_dh_groups)

    def __str__(self) -> str:
        return f"{self.name} ({self.description})"

    def __repr__(self) -> str:
        return f"TunnelProfile(name={self.name}, pfs={self.is_pfs_enabled})"

    @classmethod
    def from_dict(cls, name: str, data: dict) -> "TunnelProfile":
        """Create from dictionary (e.g., from YAML)."""
        return cls(
            name=name,
            description=data.get('description', ''),
            ike_versions=data.get('ike_versions', ['ikev2']),
            phase1_encryption=data['phase1']['encryption'],
            phase1_integrity=data['phase1']['integrity'],
            phase1_dh_groups=data['phase1']['dh_groups'],
            phase1_lifetime=data['phase1']['lifetime'],
            phase2_encryption=data['phase2']['encryption'],
            phase2_integrity=data['phase2']['integrity'],
            phase2_dh_groups=data['phase2'].get('dh_groups', []),
            phase2_lifetime=data['phase2']['lifetime'],
            dpd_timeout=data['dpd']['timeout'],
            dpd_action=data['dpd']['action'],
            static_routes_only=data.get('static_routes_only', True),
        )
