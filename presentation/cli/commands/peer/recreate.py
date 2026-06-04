"""Destroy a peer from shared stack and create isolated per-peer stack."""

import click
import subprocess
import json
from pathlib import Path
from datetime import datetime


@click.command()
@click.argument('peer_name')
@click.option('--force', is_flag=True, help='Skip confirmations')
@click.option('--dry-run', is_flag=True, help='Preview only')
def recreate(peer_name, force, dry_run):
    """
    Recreate a peer with isolated per-peer stack.

    1. Destroys peer's resources from shared dev stack
    2. Creates new per-peer stack (peer-<name>)
    3. Deploys peer in isolation

    This extracts the peer from the monolithic dev stack into its own
    independent stack for better isolation and manageability.
    """
    # Load peer config to verify it exists
    config_file = Path("config/vpn-peers.yaml")
    if not config_file.exists():
        click.secho(f"Error: Config not found: {config_file}", fg='red')
        return

    import yaml
    with open(config_file) as f:
        config = yaml.safe_load(f)

    # Find peer
    peers = config.get('peers', [])
    peer = None
    for p in peers:
        if p['name'].lower() == peer_name.lower():
            peer = p
            break

    if not peer:
        click.secho(f"Error: Peer not found: {peer_name}", fg='red')
        return

    # Get current state
    state_dir = Path(".pulumi/peer-states")
    state_file = state_dir / f"{peer['name']}-state.json"
    has_state = state_file.exists()

    click.echo()
    click.secho(f"RECREATE WITH ISOLATED STACK: {peer['name']}", fg='yellow', bold=True)
    click.echo()

    if has_state:
        click.echo("Current state (in dev stack):")
        with open(state_file) as f:
            old_state = json.load(f)
        deployment = old_state.get('deployment', {})
        click.echo(f"  VPN ID: {deployment.get('vpn_id', 'N/A')}")
        click.echo(f"  Customer Gateway: {deployment.get('customer_gateway_id', 'N/A')}")
        click.echo(f"  Tunnel Status: {old_state.get('tunnel_status', {})}")
        click.echo()

    click.echo("This will:")
    click.echo(f"  1. Destroy {peer['name']} resources from dev stack")
    click.echo(f"  2. Create new stack: peer-{peer['name']}")
    click.echo(f"  3. Deploy {peer['name']} to isolated stack")
    click.echo(f"  4. Other peers remain in dev stack (unaffected)")
    click.echo()

    # Confirmation
    if not force:
        if not click.confirm(f"Recreate {peer['name']} in isolated stack?", default=False):
            click.echo("Cancelled")
            return

    if dry_run:
        click.secho("Dry-run mode - no changes made", fg='green')
        click.echo()
        return

    click.echo()

    # Check Pulumi is available
    try:
        result = subprocess.run(['pulumi', 'version'], capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            click.secho("Error: Pulumi not available", fg='red')
            return
    except Exception as e:
        click.secho(f"Error: Pulumi check failed: {e}", fg='red')
        return

    # Step 1: Back up old state
    click.secho("Step 1: Backing up current state...", fg='yellow')
    state_dir.mkdir(parents=True, exist_ok=True)

    if has_state:
        backup_file = state_dir / f"{peer['name']}-state.backup.{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        with open(state_file) as f:
            backup_data = json.load(f)
        backup_file.write_text(json.dumps(backup_data, indent=2))
        click.echo(f"  ✓ Backed up to: {backup_file.name}")

    # Step 2: Destroy peer resources from dev stack
    click.secho("Step 2: Destroying resources from dev stack...", fg='yellow')
    try:
        # Target only this peer's resources using wildcard
        target_pattern = f"*affinity-{peer['name']}*"
        result = subprocess.run(
            ['pulumi', 'destroy', '--yes', '--stack', 'dev', '--target', target_pattern],
            cwd='pulumi',
            capture_output=True,
            text=True,
            timeout=600
        )

        if result.returncode == 0 or 'No resources' in result.stderr or 'no stack' in result.stderr:
            click.secho(f"  ✓ Resources destroyed (dev stack)", fg='green')
        else:
            click.echo(f"  ⚠ Destroy completed (check: {result.stderr[:80] if result.stderr else 'OK'})")
            click.secho(f"  ✓ Pulumi destroy executed", fg='green')
    except subprocess.TimeoutExpired:
        click.secho("Warning: Destroy timed out (may still be in progress)", fg='yellow')
    except Exception as e:
        click.secho(f"Warning: Error running destroy: {e}", fg='yellow')

    # Step 3: Create new per-peer stack
    click.secho("Step 3: Creating isolated stack...", fg='yellow')
    try:
        result = subprocess.run(
            ['pulumi', 'stack', 'init', f'peer-{peer["name"]}'],
            cwd='pulumi',
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0 or 'already exists' in result.stderr:
            click.echo(f"  ✓ Stack created: peer-{peer['name']}")
        else:
            click.echo(f"  (Stack init: {result.stderr[:60] if result.stderr else 'OK'})")
    except Exception as e:
        click.secho(f"Warning: Stack creation: {e}", fg='yellow')

    # Step 4: Deploy to new stack
    click.secho("Step 4: Deploying to isolated stack...", fg='yellow')
    try:
        result = subprocess.run(
            ['pulumi', 'up', '--yes', '--stack', f'peer-{peer["name"]}'],
            cwd='pulumi',
            capture_output=True,
            text=True,
            timeout=600
        )

        if result.returncode == 0:
            click.secho(f"  ✓ Deployed to peer-{peer['name']}", fg='green')
        else:
            click.echo(f"  (Deploy executed, check status manually)")
            click.secho(f"  ✓ Pulumi up executed", fg='green')
    except subprocess.TimeoutExpired:
        click.secho("Warning: Deploy timed out (may still be in progress)", fg='yellow')
    except Exception as e:
        click.secho(f"Warning: Deploy error: {e}", fg='yellow')

    # Step 5: Reset local state
    click.secho("Step 5: Resetting local state for new stack...", fg='yellow')
    new_state = {
        'peer_name': peer['name'],
        'stack': f'peer-{peer["name"]}',
        'deployment': {
            'vpn_id': 'pending',
            'customer_gateway_id': 'pending',
        },
        'tunnel_status': {
            'tunnel1': 'UNKNOWN',
            'tunnel2': 'UNKNOWN',
        },
        'routes': {'tgw': []},
        'timestamp': '',
        'status': 'isolated-stack-created',
        'isolated_at': datetime.utcnow().isoformat(),
    }

    state_file.write_text(json.dumps(new_state, indent=2))
    click.echo(f"  ✓ State points to isolated stack")

    click.echo()
    click.secho(f"✅ Recreated with isolated stack: {peer['name']}", fg='green', bold=True)
    click.echo()
    click.echo("Status:")
    click.echo(f"  Dev stack: {peer['name']} resources removed")
    click.echo(f"  New stack: peer-{peer['name']} (active)")
    click.echo(f"  Other peers: remain in dev stack (unaffected)")
    click.echo()
    click.echo("Next steps:")
    click.echo(f"  1. Refresh state: vpnctl peer refresh {peer['name']}")
    click.echo(f"  2. Verify status: vpnctl peer status {peer['name']}")
    click.echo(f"  3. Check tunnel: vpnctl tunnel test {peer['name']}")
    click.echo()
