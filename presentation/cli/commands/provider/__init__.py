"""Provider management commands (list, switch)."""

import click
from .list_providers import list_providers
from .switch import switch


@click.group(name='provider')
def provider_group():
    """Manage IaC providers (Pulumi, Terraform, CloudFormation)."""
    pass


provider_group.add_command(list_providers, name='list')
provider_group.add_command(switch)

__all__ = ['provider_group']
