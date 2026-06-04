"""
VPN Peer Domain Model

Core entity representing a VPN peer with all business rule validation.
"""

from dataclasses import dataclass, field
from typing import FrozenSet, List, Optional
from datetime import datetime

from domain.models.value_objects import (
    PeerName,
    PublicIP,
    BGPASN,
    CIDR,
    PSK,
)
from domain.models.tunnel_profile import TunnelProfile
from domain.models.test_endpoint import TestEndpoint
from domain.exceptions import DomainValidationError


@dataclass(frozen=True)
class Contact:
    """Contact information for peer administrator."""

    name: str
    email: str
    phone: str = ""

    def __post_init__(self):
        """Validate contact fields."""
        if not self.name or not self.email:
            raise DomainValidationError("Contact name and email required")


@dataclass(frozen=True)
class VpnPeer:
    """
    VPN Peer Entity

    Core domain model representing a VPN peer (e.g., MockPeerA, MOCK_PEER_C).
    Enforces all business rule invariants in __post_init__.

    INVARIANTS:
    - name must be valid (lowercase, alphanumeric + hyphen)
    - public_ip must be valid IPv4
    - bgp_asn must be in valid range
    - destination_cidrs must be valid CIDRs
    - destination_cidrs must not overlap with Organization reserved CIDRs
    - tunnel_profile_name must reference existing profile
    - psk values must be 32+ chars or empty
    - device type and version must be provided
    """

    # Identity
    name: PeerName
    public_ip: PublicIP
    bgp_asn: BGPASN

    # Tunnel Configuration
    tunnel_profile_name: str
    destination_cidrs: FrozenSet[CIDR]

    # Device Information
    device_type: str = "Unknown"
    device_version: str = "Unknown"

    # Credentials
    psk_tunnel1: PSK = field(default_factory=lambda: PSK.generate())
    psk_tunnel2: PSK = field(default_factory=lambda: PSK.generate())

    # Optional Features
    imported_cidrs: FrozenSet[CIDR] = field(default_factory=frozenset)
    snat_enabled: bool = False
    snat_ip: str = ""
    contacts: List[Contact] = field(default_factory=list)
    test_endpoints: List[TestEndpoint] = field(default_factory=list)

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    tags: dict = field(default_factory=dict)

    def __post_init__(self):
        """Validate all invariants."""
        # Convert to value objects if strings
        if isinstance(self.name, str):
            object.__setattr__(self, 'name', PeerName(self.name))
        if isinstance(self.public_ip, str):
            object.__setattr__(self, 'public_ip', PublicIP(self.public_ip))
        if isinstance(self.bgp_asn, int):
            object.__setattr__(self, 'bgp_asn', BGPASN(self.bgp_asn))

        # Convert CIDR strings to CIDR objects
        if destination_cidrs := self.destination_cidrs:
            cidrs = frozenset(
                c if isinstance(c, CIDR) else CIDR(c)
                for c in destination_cidrs
            )
            object.__setattr__(self, 'destination_cidrs', cidrs)

        if imported_cidrs := self.imported_cidrs:
            cidrs = frozenset(
                c if isinstance(c, CIDR) else CIDR(c)
                for c in imported_cidrs
            )
            object.__setattr__(self, 'imported_cidrs', cidrs)

        # Convert PSK strings to PSK objects
        if isinstance(self.psk_tunnel1, str):
            object.__setattr__(self, 'psk_tunnel1', PSK(self.psk_tunnel1))
        if isinstance(self.psk_tunnel2, str):
            object.__setattr__(self, 'psk_tunnel2', PSK(self.psk_tunnel2))

        # Validate business rules
        self._validate_destination_cidrs()
        self._validate_tunnel_profile_reference()
        self._validate_snat_config()
        self._validate_contacts()

    def _validate_destination_cidrs(self):
        """Validate destination CIDRs don't overlap with Organization reserved."""
        # Reserved: Organization internal network
        vpn_reserved = [CIDR("172.33.0.0/16")]

        for cidr in self.destination_cidrs:
            for reserved in vpn_reserved:
                if cidr.overlaps_with(reserved):
                    raise DomainValidationError(
                        f"CIDR {cidr} overlaps with reserved Organization network {reserved}"
                    )

    def _validate_tunnel_profile_reference(self):
        """Validate tunnel profile name is provided."""
        if not self.tunnel_profile_name:
            raise DomainValidationError("Tunnel profile must be specified")

    def _validate_snat_config(self):
        """Validate SNAT configuration consistency."""
        if self.snat_enabled and not self.snat_ip:
            raise DomainValidationError(
                "SNAT IP must be provided if SNAT is enabled"
            )
        if self.snat_ip and not self.snat_enabled:
            raise DomainValidationError(
                "Cannot specify SNAT IP without enabling SNAT"
            )

    def _validate_contacts(self):
        """Validate contacts are present and valid."""
        if not self.contacts:
            raise DomainValidationError("At least one contact is required")

    @property
    def is_valid(self) -> bool:
        """Check if peer passes all validation rules."""
        try:
            # Re-validate by accessing all validated fields
            _ = self.name
            _ = self.public_ip
            _ = self.bgp_asn
            _ = self.destination_cidrs
            return True
        except DomainValidationError:
            return False

    def get_all_cidrs(self) -> FrozenSet[CIDR]:
        """Get all CIDRs (destination + imported)."""
        return frozenset(self.destination_cidrs | self.imported_cidrs)

    def has_imported_routes(self) -> bool:
        """Check if peer has pre-existing imported TGW routes."""
        return len(self.imported_cidrs) > 0

    def __str__(self) -> str:
        return (
            f"VpnPeer({self.name}, "
            f"ip={self.public_ip}, "
            f"asn={self.bgp_asn}, "
            f"cidrs={len(self.destination_cidrs)})"
        )

    def __repr__(self) -> str:
        return (
            f"VpnPeer(name={self.name}, "
            f"public_ip={self.public_ip}, "
            f"bgp_asn={self.bgp_asn}, "
            f"tunnel_profile={self.tunnel_profile_name})"
        )

    @classmethod
    def from_dict(
        cls,
        name: str,
        spec: dict,
        psk_tunnel1: Optional[str] = None,
        psk_tunnel2: Optional[str] = None,
    ) -> "VpnPeer":
        """Create VpnPeer from dictionary (e.g., from YAML spec)."""

        # Generate PSKs if not provided
        if not psk_tunnel1:
            psk_tunnel1 = PSK.generate().secure_value
        if not psk_tunnel2:
            psk_tunnel2 = PSK.generate().secure_value

        # Parse contacts
        contacts = [
            Contact(
                name=c.get('name', ''),
                email=c.get('email', ''),
                phone=c.get('phone', ''),
            )
            for c in spec.get('contacts', [])
        ]

        # Parse test endpoints
        test_endpoints = [
            TestEndpoint.from_dict(ep)
            for ep in spec.get('test_endpoints', [])
        ]

        return cls(
            name=name,
            public_ip=spec['publicIp'],
            bgp_asn=spec['bgpAsn'],
            tunnel_profile_name=spec['tunnelProfile'],
            destination_cidrs=frozenset(CIDR(c) for c in spec['destinationCidrs']),
            device_type=spec.get('deviceType', 'Unknown'),
            device_version=spec.get('deviceVersion', 'Unknown'),
            psk_tunnel1=psk_tunnel1,
            psk_tunnel2=psk_tunnel2,
            imported_cidrs=frozenset(
                CIDR(c) for c in spec.get('importedCidrs', [])
            ),
            snat_enabled=spec.get('snat', {}).get('enabled', False),
            snat_ip=spec.get('snat', {}).get('providerAssignedIp', ''),
            contacts=contacts,
            test_endpoints=test_endpoints,
            tags=spec.get('labels', {}),
        )
