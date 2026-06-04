"""vpnctl peer deploy command (provider-agnostic).

Deploys peer configuration to infrastructure.
Works with any IaC provider configured.
"""

import click
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from application.services.peer_management_service import PeerManagementService


@click.command(name='deploy')
@click.argument('peer_name')
@click.option('--dry-run', is_flag=True, help='Preview only (do not deploy)')
@click.option('--no-confirm', is_flag=True, help='Skip confirmation prompt')
@click.pass_context
def deploy(ctx, peer_name: str, dry_run: bool, no_confirm: bool):
    """Deploy peer configuration to infrastructure.

    PEER_NAME: Name of peer to deploy

    Uses the active IaC provider (Pulumi, Terraform, or CloudFormation).

    Example:
        vpnctl peer deploy vimenca
        vpnctl peer deploy vimenca --dry-run
    """
    service: PeerManagementService = ctx.obj.get('peer_service')
    config_manager = ctx.obj.get('config_manager')

    if not service:
        click.secho("❌ Service not initialized", fg='red')
        ctx.exit(1)

    # Get peer config to show provider
    config = config_manager.get_peer_config(peer_name)
    if not config:
        click.secho(f"❌ Peer {peer_name} not found", fg='red')
        ctx.exit(1)

    provider_name = config.get('iac_provider', 'pulumi')

    # Show diff first
    click.echo(f"\n📋 Changes for {peer_name} (via {provider_name}):\n")
    diff_result = service.show_peer_diff(peer_name)

    if diff_result.get('success'):
        if diff_result.get('in_sync'):
            click.secho("✓ In sync - no changes needed", fg='green')
            return
        else:
            if diff_result.get('added'):
                click.echo(f"  + Adding: {len(diff_result['added'])} resources")
            if diff_result.get('removed'):
                click.echo(f"  - Removing: {len(diff_result['removed'])} resources")
            if diff_result.get('modified'):
                click.echo(f"  ~ Modifying: {len(diff_result['modified'])} resources")

    # Confirm
    if not no_confirm and not dry_run:
        if not click.confirm("\n? Deploy these changes?"):
            click.echo("Aborted.")
            return

    # Deploy
    mode = "preview" if dry_run else "deploy"
    click.echo(f"\n🚀 {mode.capitalize()}ing...")

    result = service.deploy_peer(peer_name, preview_only=dry_run)

    if result.success:
        if dry_run:
            click.secho(f"✓ Preview generated (no changes made)", fg='green')
        else:
            click.secho(f"✓ Deployment successful", fg='green')
    else:
        click.secho(f"❌ {result.message}", fg='red')
        ctx.exit(1)
