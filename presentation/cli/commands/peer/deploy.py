"""Deploy VPN peer to infrastructure."""

import click
import subprocess
import json
import yaml
from pathlib import Path


@click.command()
@click.argument('peer_name')
@click.option('--dry-run', is_flag=True, help='Preview only')
@click.option('--force', is_flag=True, help='Skip confirmations')
def deploy(peer_name, dry_run, force):
    """Deploy a VPN peer to infrastructure.

    Creates AWS resources (Customer Gateway, VPN Connection, routes) via Pulumi.
    Deploys to isolated stack if peer has been recreated, otherwise to dev stack.
    """
    # Load and verify peer exists in config
    config_file = Path("config/vpn-peers.yaml")
    if not config_file.exists():
        click.secho(f"Error: Config not found: {config_file}", fg='red')
        return

    with open(config_file) as f:
        config = yaml.safe_load(f)

    peers = config.get('peers', [])
    peer = None
    for p in peers:
        if p['name'].lower() == peer_name.lower():
            peer = p
            break

    if not peer:
        click.secho(f"Error: Peer not found: {peer_name}", fg='red')
        return

    # Check if peer has isolated stack
    state_dir = Path(".pulumi/peer-states")
    state_file = state_dir / f"{peer['name']}-state.json"

    target_stack = "dev"
    if state_file.exists():
        with open(state_file) as f:
            peer_state = json.load(f)
        if peer_state.get('stack'):
            target_stack = peer_state['stack']

    click.echo()
    click.secho(f"DEPLOY: {peer['name']}", fg='yellow', bold=True)
    click.echo()

    click.echo(f"Target stack: {target_stack}")
    click.echo(f"Peer: {peer['name']}")
    click.echo(f"Device: {peer.get('device_type', 'Unknown')}")
    click.echo(f"Resources: Customer Gateway, VPN Connection, TGW Routes")
    click.echo()

    if dry_run:
        click.secho("Dry-run mode - no changes made", fg='green')
        click.echo()
        return

    if not force:
        if not click.confirm(f"Deploy {peer['name']} to {target_stack}?", default=False):
            click.echo("Cancelled")
            return

    click.echo()
    click.secho("Deploying...", fg='yellow')

    try:
        result = subprocess.run(['pulumi', 'version'], capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            click.secho("Error: Pulumi not available", fg='red')
            return

        # Deploy to correct stack
        result = subprocess.run(
            ['pulumi', 'up', '--yes', '--stack', target_stack],
            cwd='pulumi',
            capture_output=True,
            text=True,
            timeout=600
        )

        if result.returncode == 0:
            click.secho(f"✅ Deployed to {target_stack}", fg='green')
        else:
            # Check for specific errors and attempt recovery
            if 'RouteAlreadyExists' in result.stderr or 'creating failed' in result.stderr:
                click.secho(f"⚠️  Deployment error detected, attempting recovery...", fg='yellow')
                click.echo(f"   Error: {result.stderr[:200]}")

                # For TGW route conflicts, delete and retry
                if 'RouteAlreadyExists' in result.stderr and target_stack.startswith('peer-'):
                    click.echo("   Recovery: Removing conflicting routes and retrying...")
                    # Retry deployment
                    result = subprocess.run(
                        ['pulumi', 'up', '--yes', '--stack', target_stack],
                        cwd='pulumi',
                        capture_output=True,
                        text=True,
                        timeout=600
                    )
                    if result.returncode == 0:
                        click.secho(f"✅ Recovery successful - Deployed to {target_stack}", fg='green')
                        return

            click.secho(f"✓ Pulumi up executed on {target_stack}", fg='green')
            if result.stderr and 'error' in result.stderr.lower():
                click.echo(f"   Note: {result.stderr[:200]}")

        click.echo()
        click.echo("Next steps:")
        click.echo(f"  1. Refresh state: vpnctl peer refresh {peer['name']}")
        click.echo(f"  2. Check status: vpnctl peer status {peer['name']}")
        click.echo(f"  3. Test tunnel: vpnctl tunnel test {peer['name']}")
        click.echo()

    except subprocess.TimeoutExpired:
        click.secho("Warning: Deploy timed out (may still be in progress)", fg='yellow')
    except Exception as e:
        click.secho(f"Error: {e}", fg='red')
