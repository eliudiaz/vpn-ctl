"""Factory pattern for creating IaC provider instances.

Single responsibility: Instantiate the correct provider type based on configuration.
"""

from typing import Dict, List, Any, Type, Optional
from .abstract_provider import IacProvider
from observability.logging import get_logger


logger = get_logger(__name__)


class IacProviderFactory:
    """
    Creates provider instances based on active provider configuration.

    Usage:
        # Create provider for specific peer
        config = config_manager.get_peer_config('vimenca')
        provider = IacProviderFactory.get_active_provider('vimenca', config)

        # Now use provider (same interface regardless of implementation)
        provider.add_route('172.16.80.0/24')
        provider.deploy()

    Supports:
        - pulumi: Pulumi IaC (current)
        - terraform: Terraform (future)
        - cloudformation: AWS CloudFormation (future)
    """

    _registry: Dict[str, Type[IacProvider]] = {}

    @classmethod
    def register(cls, provider_name: str, provider_class: Type[IacProvider]) -> None:
        """Register a provider implementation.

        Args:
            provider_name: Short name ('pulumi', 'terraform', etc.)
            provider_class: Provider class implementing IacProvider interface
        """
        cls._registry[provider_name] = provider_class
        logger.info(f"Registered IaC provider: {provider_name}")

    @classmethod
    def create(
        cls,
        peer_name: str,
        provider_name: str,
        config: Dict[str, Any]
    ) -> IacProvider:
        """Create provider instance.

        Args:
            peer_name: 'vimenca', 'cibao', etc.
            provider_name: 'pulumi', 'terraform', 'cloudformation'
            config: Configuration for this peer

        Returns:
            Provider instance implementing IacProvider interface

        Raises:
            ValueError: If provider_name not registered
        """
        if provider_name not in cls._registry:
            available = list(cls._registry.keys())
            raise ValueError(
                f"Unknown IaC provider: {provider_name}. "
                f"Available: {available}"
            )

        provider_class = cls._registry[provider_name]
        logger.debug(f"Creating {provider_name} provider for peer {peer_name}")

        return provider_class(peer_name, config)

    @classmethod
    def get_active_provider(
        cls,
        peer_name: str,
        config: Dict[str, Any]
    ) -> IacProvider:
        """Get provider based on active configuration.

        Reads 'iac_provider' from config, defaults to 'pulumi'.

        Args:
            peer_name: Peer name
            config: Peer configuration

        Returns:
            Provider instance for configured provider
        """
        provider_name = config.get('iac_provider', 'pulumi')
        return cls.create(peer_name, provider_name, config)

    @classmethod
    def available_providers(cls) -> List[str]:
        """List available providers.

        Returns:
            List of provider names
        """
        return list(cls._registry.keys())

    @classmethod
    def get_provider_class(cls, provider_name: str) -> Type[IacProvider]:
        """Get provider class (for testing/introspection).

        Args:
            provider_name: Provider name

        Returns:
            Provider class

        Raises:
            ValueError: If provider not found
        """
        if provider_name not in cls._registry:
            raise ValueError(f"Unknown provider: {provider_name}")

        return cls._registry[provider_name]

    @classmethod
    def unregister(cls, provider_name: str) -> None:
        """Unregister a provider (mainly for testing).

        Args:
            provider_name: Provider to unregister
        """
        if provider_name in cls._registry:
            del cls._registry[provider_name]
            logger.debug(f"Unregistered provider: {provider_name}")

    @classmethod
    def clear_registry(cls) -> None:
        """Clear all registrations (mainly for testing)."""
        cls._registry.clear()
        logger.debug("Cleared IaC provider registry")
