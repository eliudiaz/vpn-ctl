"""Bootstrap IaC providers - Register implementations at startup."""

from .factory import IacProviderFactory
from .pulumi_provider import PulumiProvider


def bootstrap_providers():
    """Register all available IaC provider implementations.

    Called at application startup to register all provider implementations.
    New providers can be added by calling IacProviderFactory.register().

    Usage:
        # In main application startup
        from infrastructure.iac_providers import bootstrap_providers
        bootstrap_providers()
    """

    # Register Pulumi (current implementation)
    IacProviderFactory.register('pulumi', PulumiProvider)

    # TODO: Register Terraform provider when ready
    # IacProviderFactory.register('terraform', TerraformProvider)

    # TODO: Register CloudFormation provider when ready
    # IacProviderFactory.register('cloudformation', CloudFormationProvider)
