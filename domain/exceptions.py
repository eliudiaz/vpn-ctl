"""
Domain Layer Exceptions

Hierarchical exception structure for business logic errors.
"""


class DomainError(Exception):
    """Base exception for domain layer."""
    pass


class DomainValidationError(DomainError):
    """Validation rule violation."""
    pass


class PSKGenerationError(DomainError):
    """Pre-shared key generation failed."""
    pass


class CIDRParsingError(DomainError):
    """CIDR parsing or validation failed."""
    pass


class ConfigValidationError(DomainError):
    """Configuration validation failed."""
    pass


class PeerNotFoundError(DomainError):
    """Peer does not exist."""
    pass


class DuplicatePeerError(DomainError):
    """Peer with same name already exists."""
    pass


class ProfileNotFoundError(DomainError):
    """Tunnel profile does not exist."""
    pass
