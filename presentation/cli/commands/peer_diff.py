"""vpnctl peer diff command (provider-agnostic).

Shows what would change if deployed.
"""

import click
from typing import TYPE_CHECKING
import json

if TYPE_CHECKING:
    from application.services.peer_management_service import PeerManagementService


@click.command(name='diff')
@click.argument('peer_name')
@click.option('--json-output', is_flag=True, help='Output as JSON')
@click.pass_context
def diff(ctx, peer_name: str, json_output: bool):
    """Show what would change if peer is deployed.

    PEER_NAME: Name of peer

    Example:
        vpnctl peer diff mock-peer-a
        vpnctl peer diff mock-peer-a --json-output
    """
    service: PeerManagementService = ctx.obj.get('peer_service')

    if not service:
        click.secho("❌ Service not initialized", fg='red')
        ctx.exit(1)

    result = service.show_peer_diff(peer_name)

    if not result.get('success'):
        click.secho(f"❌ {result.get('error')}", fg='red')
        ctx.exit(1)

    if json_output:
        click.echo(json.dumps(result, indent=2))
        return

    provider = result.get('provider', 'unknown')
    in_sync = result.get('in_sync', False)

    click.echo(f"\n📊 Diff for {peer_name} (via {provider}):\n")

    if in_sync:
        click.secho("✓ In sync - no changes needed", fg='green')
        return

    added = result.get('added', [])
    removed = result.get('removed', [])
    modified = result.get('modified', [])

    if added:
        click.secho(f"\n+ Added ({len(added)}):", fg='green')
        for item in added:
            click.echo(f"  • {item}")

    if removed:
        click.secho(f"\n- Removed ({len(removed)}):", fg='red')
        for item in removed:
            click.echo(f"  • {item}")

    if modified:
        click.secho(f"\n~ Modified ({len(modified)}):", fg='yellow')
        for item in modified:
            click.echo(f"  • {item}")
