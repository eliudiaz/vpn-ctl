"""
Test Endpoint Value Object

Represents a target (IP or URL) and protocol for VPN tunnel testing.
"""

import re
from dataclasses import dataclass
from typing import Optional
from domain.exceptions import DomainValidationError


@dataclass(frozen=True)
class TestEndpoint:
    """
    Test Endpoint Value Object

    Represents a single test target for VPN tunnel health checks.

    INVARIANTS:
    - target must be valid IPv4, IPv6, or hostname/FQDN
    - protocol must be one of: ping, http, https, tcp, dns
    - port required for http, https, tcp
    - port must be 1-65535 if provided
    """

    target: str
    protocol: str
    port: Optional[int] = None

    VALID_PROTOCOLS = {"ping", "http", "https", "tcp", "dns"}
    PROTOCOLS_REQUIRING_PORT = {"http", "https", "tcp"}

    def __post_init__(self):
        """Validate all invariants."""
        self._validate_target()
        self._validate_protocol()
        self._validate_port()

    def _validate_target(self):
        """Validate target is valid IP or hostname."""
        # IPv4 pattern - strictly match valid IPv4 (0-255 per octet)
        ipv4_pattern = r'^(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.){3}([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])$'
        if re.match(ipv4_pattern, self.target):
            return

        # IPv6 pattern (simplified)
        ipv6_pattern = r'^([a-f0-9:]+)$'
        if re.match(ipv6_pattern, self.target):
            return

        # Hostname/FQDN pattern (alphanumeric, hyphens, dots, underscores)
        # Must not be all digits/dots (which would be a malformed IP)
        hostname_pattern = r'^([a-zA-Z0-9]([a-zA-Z0-9\-_]*[a-zA-Z0-9])?\.)*[a-zA-Z0-9]([a-zA-Z0-9\-_]*[a-zA-Z0-9])?$'

        # Check if target looks like an IP (all digits and dots)
        if re.match(r'^[\d.]+$', self.target):
            # It looks like an IP but didn't match the strict IPv4 pattern, so reject it
            raise DomainValidationError(
                f"Invalid target '{self.target}': looks like an IPv4 address but is invalid"
            )

        if re.match(hostname_pattern, self.target):
            return

        raise DomainValidationError(
            f"Invalid target '{self.target}': must be valid IPv4, IPv6, or hostname"
        )

    def _validate_protocol(self):
        """Validate protocol is in allowed set."""
        if self.protocol not in self.VALID_PROTOCOLS:
            raise DomainValidationError(
                f"Invalid protocol '{self.protocol}': must be one of {self.VALID_PROTOCOLS}"
            )

    def _validate_port(self):
        """Validate port is provided when required and in valid range."""
        if self.protocol in self.PROTOCOLS_REQUIRING_PORT:
            if self.port is None:
                raise DomainValidationError(
                    f"Port required for protocol '{self.protocol}'"
                )

        if self.port is not None:
            if not (1 <= self.port <= 65535):
                raise DomainValidationError(
                    f"Port must be between 1 and 65535, got {self.port}"
                )

    def __str__(self) -> str:
        if self.port:
            return f"{self.target}:{self.port} ({self.protocol})"
        return f"{self.target} ({self.protocol})"

    def __repr__(self) -> str:
        return f"TestEndpoint(target={self.target}, protocol={self.protocol}, port={self.port})"

    def to_dict(self) -> dict:
        """Convert to dictionary for YAML serialization."""
        result = {"target": self.target, "protocol": self.protocol}
        if self.port:
            result["port"] = self.port
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "TestEndpoint":
        """Create from dictionary (e.g., from YAML)."""
        return cls(
            target=data["target"],
            protocol=data["protocol"],
            port=data.get("port"),
        )
