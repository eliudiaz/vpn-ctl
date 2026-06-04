"""IaC Provider abstraction layer - Provider-agnostic infrastructure management.

This module provides a unified interface for managing infrastructure across multiple
IaC providers (Pulumi, Terraform, CloudFormation). All vpnctl CLI commands use this
abstraction, making the system provider-agnostic.

Key components:
- IacProvider: Abstract base class defining the interface
- OperationResult: Standardized result from any IaC operation
- DiffResult: Comparison between desired config and actual AWS state
- StateSnapshot: Point-in-time infrastructure state
- IacProviderFactory: Creates provider instances based on configuration
"""

from .abstract_provider import (
    IacProvider,
    OperationStatus,
    OperationResult,
    DiffResult,
    StateSnapshot,
    ImmutableResources,
)
from .factory import IacProviderFactory
from .pulumi_provider import PulumiProvider

__all__ = [
    'IacProvider',
    'OperationStatus',
    'OperationResult',
    'DiffResult',
    'StateSnapshot',
    'ImmutableResources',
    'IacProviderFactory',
    'PulumiProvider',
]
