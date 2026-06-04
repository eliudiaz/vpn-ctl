"""vpnctl peer add-route command (provider-agnostic).

Adds destination CIDR route to peer.
Works with any IaC provider (Pulumi, Terraform, CloudFormation).
"""

import click
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from application.services.peer_management_service import PeerManagementService


@click.command(name='add-route')
@click.argument('peer_name')
@click.argument('cidr')
@click.pass_context
def add_route(ctx, peer_name: str, cidr: str):
    """Add destination CIDR route to peer.

    PEER_NAME: Name of peer (e.g., mock-peer-a, mock-peer-b)
    CIDR: Destination CIDR (e.g., 172.16.80.0/24)

    Example:
        vpnctl peer add-route mock-peer-a 172.16.80.0/24
    """
    service: PeerManagementService = ctx.obj.get('peer_service')
    config_manager = ctx.obj.get('config_manager')

    if not service:
        click.secho("❌ Service not initialized", fg='red')
        ctx.exit(1)

    # Show which provider is being used
    config = config_manager.get_peer_config(peer_name)
    if config:
        provider_name = config.get('iac_provider', 'pulumi')
        click.echo(f"Adding route via {provider_name}...")

    result = service.add_destination_cidr(peer_name, cidr)

    if result.success:
        click.secho(f"✓ Route {cidr} added to {peer_name}", fg='green')
    else:
        click.secho(f"❌ {result.message}", fg='red')
        ctx.exit(1)
