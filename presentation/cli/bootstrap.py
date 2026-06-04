"""Bootstrap vpnctl CLI - Wire up all dependencies and initialize providers.

This module handles:
1. Provider initialization (register Pulumi, Terraform, etc.)
2. Service initialization (create PeerManagementService, etc.)
3. Configuration manager initialization
4. Dependency injection into CLI context
"""

from typing import Dict, Any

from infrastructure.iac_providers import bootstrap_providers as bootstrap_iac_providers
from infrastructure.iac_providers import IacProviderFactory
from application.services.peer_management_service import PeerManagementService
from infrastructure.config.config_manager import ConfigManager
from observability.logging import get_logger


logger = get_logger(__name__)


class CliBootstrapper:
    """Bootstraps CLI with all dependencies."""

    @staticmethod
    def bootstrap() -> Dict[str, Any]:
        """Bootstrap all CLI dependencies.

        Returns:
            Dictionary of initialized services for CLI context injection

        Raises:
            Exception: If bootstrap fails
        """
        logger.info("Bootstrapping vpnctl CLI...")

        try:
            # 1. Initialize IaC providers (register Pulumi, Terraform, etc.)
            logger.debug("Initializing IaC providers...")
            bootstrap_iac_providers()

            available_providers = IacProviderFactory.available_providers()
            logger.info(f"Registered IaC providers: {available_providers}")

            # 2. Initialize configuration manager
            logger.debug("Initializing configuration manager...")
            config_manager = ConfigManager()

            # 3. Initialize services
            logger.debug("Initializing application services...")
            peer_service = PeerManagementService(
                config_manager=config_manager,
                event_publisher=None  # TODO: Wire up event publisher
            )

            # 4. Return context for CLI
            context = {
                'config_manager': config_manager,
                'peer_service': peer_service,
                'iac_provider_factory': IacProviderFactory,
                'available_providers': available_providers,
            }

            logger.info("CLI bootstrap complete")
            return context

        except Exception as e:
            logger.error(f"CLI bootstrap failed: {str(e)}")
            raise


def get_cli_context() -> Dict[str, Any]:
    """Get CLI context (lazy initialization).

    Returns:
        CLI context dictionary
    """
    return CliBootstrapper.bootstrap()
