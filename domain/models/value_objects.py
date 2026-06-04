"""
Value Objects

Immutable, validated value types for domain model.
"""

import re
import ipaddress
import secrets
import string
from typing import FrozenSet
from dataclasses import dataclass

from domain.exceptions import DomainValidationError, CIDRParsingError, PSKGenerationError


@dataclass(frozen=True)
class BGPASN:
    """BGP Autonomous System Number (immutable, validated)."""

    value: int

    def __post_init__(self):
        """Validate BGP ASN."""
        if not (1 <= self.value <= 65534):
            raise DomainValidationError(
                f"Invalid BGP ASN: {self.value} (must be 1-65534)"
            )

    def __str__(self) -> str:
        return str(self.value)

    def __repr__(self) -> str:
        return f"BGPASN({self.value})"


@dataclass(frozen=True)
class CIDR:
    """CIDR Block (immutable, validated)."""

    value: str

    def __post_init__(self):
        """Validate CIDR notation."""
        try:
            ipaddress.ip_network(self.value, strict=False)
        except ValueError as e:
            raise CIDRParsingError(f"Invalid CIDR: {self.value} - {e}")

    @property
    def network(self) -> ipaddress.ip_network:
        """Get ipaddress network object."""
        try:
            return ipaddress.ip_network(self.value, strict=False)
        except ValueError:
            raise CIDRParsingError(f"Invalid CIDR: {self.value}")

    def overlaps_with(self, other: "CIDR") -> bool:
        """Check if this CIDR overlaps with another."""
        return self.network.overlaps(other.network)

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return f"CIDR({self.value})"


@dataclass(frozen=True)
class PSK:
    """Pre-Shared Key (immutable, validated)."""

    value: str

    # Minimum length for security
    MIN_LENGTH = 32

    def __post_init__(self):
        """Validate PSK."""
        if not self.value:
            raise DomainValidationError("PSK cannot be empty")
        if len(self.value) < self.MIN_LENGTH:
            raise DomainValidationError(
                f"PSK too short: {len(self.value)} chars "
                f"(minimum {self.MIN_LENGTH})"
            )

    @staticmethod
    def generate(length: int = 64) -> "PSK":
        """Generate a cryptographically secure PSK."""
        try:
            # Use letters, digits, and special chars for strength
            alphabet = string.ascii_letters + string.digits + "!@#$%^&*_+-=[]{}|:;<>?"

            # Ensure first char is letter (common requirement)
            first_char = secrets.choice(string.ascii_letters)
            rest = "".join(secrets.choice(alphabet) for _ in range(length - 1))
            psk_value = first_char + rest

            return PSK(psk_value)
        except Exception as e:
            raise PSKGenerationError(f"Failed to generate PSK: {e}")

    def __str__(self) -> str:
        # Don't expose in logs
        return "[REDACTED]"

    def __repr__(self) -> str:
        return "[REDACTED]"

    @property
    def secure_value(self) -> str:
        """Get actual PSK value (use with caution)."""
        return self.value


@dataclass(frozen=True)
class PeerName:
    """VPN Peer Name (immutable, validated)."""

    value: str

    def __post_init__(self):
        """Validate peer name."""
        if not self.value:
            raise DomainValidationError("Peer name cannot be empty")
        if not re.match(r'^[a-z0-9-]{3,64}$', self.value):
            raise DomainValidationError(
                f"Invalid peer name: {self.value} "
                f"(must be 3-64 lowercase alphanumeric + hyphen)"
            )

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return f"PeerName({self.value})"


@dataclass(frozen=True)
class PublicIP:
    """Public IP Address (immutable, validated)."""

    value: str

    def __post_init__(self):
        """Validate IP address."""
        try:
            ip_obj = ipaddress.ip_address(self.value)
            if ip_obj.version != 4:
                raise DomainValidationError(
                    f"Only IPv4 supported, got: {self.value}"
                )
            if ip_obj.is_private:
                raise DomainValidationError(
                    f"Private IP not allowed: {self.value}"
                )
        except ValueError as e:
            raise DomainValidationError(f"Invalid IP address: {self.value} - {e}")

    @property
    def ip_obj(self) -> ipaddress.ip_address:
        """Get ipaddress object."""
        try:
            return ipaddress.ip_address(self.value)
        except ValueError:
            raise DomainValidationError(f"Invalid IP: {self.value}")

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return f"PublicIP({self.value})"
