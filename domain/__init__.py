"""
VPN Infrastructure Domain Layer

Provider-agnostic business logic for VPN peer management.
No Pulumi, Terraform, or IaC dependencies in this layer.
"""

__version__ = "1.2.0"

from domain.models.vpn_peer import VpnPeer
from domain.models.tunnel_profile import TunnelProfile
from domain.models.test_endpoint import TestEndpoint
from domain.models.value_objects import BGPASN, CIDR, PSK
from domain.exceptions import (
    DomainError,
    DomainValidationError,
    PSKGenerationError,
    CIDRParsingError,
    ConfigValidationError,
)

__all__ = [
    "VpnPeer",
    "TunnelProfile",
    "TestEndpoint",
    "BGPASN",
    "CIDR",
    "PSK",
    "DomainError",
    "DomainValidationError",
    "PSKGenerationError",
    "CIDRParsingError",
    "ConfigValidationError",
]
