"""Refresh peer state from Pulumi infrastructure."""

import click
import json
import subprocess
from pathlib import Path
from datetime import datetime


@click.command()
@click.argument('peer_name', required=False)
@click.option('--all', is_flag=True, help='Refresh all peers')
@click.option('--force', is_flag=True, help='Force refresh even if recent')
def refresh(peer_name, all, force):
    """
    Refresh peer state from Pulumi infrastructure.

    Queries Pulumi stack state for each peer and creates independent
    state snapshots separate from spec files.
    """
    click.echo()
    click.secho("🔄 Refreshing peer state from Pulumi", fg='cyan', bold=True)
    click.echo()

    # Determine which peers to refresh
    if all:
        peers_to_refresh = _get_all_peers()
        click.echo(f"📋 Refreshing {len(peers_to_refresh)} peers...")
    elif peer_name:
        peers_to_refresh = [peer_name]
        click.echo(f"📋 Refreshing peer: {peer_name}")
    else:
        click.secho("❌ Specify peer name or use --all", fg='red')
        return

    click.echo()

    # Create state directory
    state_dir = Path(".pulumi/peer-states")
    state_dir.mkdir(parents=True, exist_ok=True)

    refreshed = 0
    failed = 0

    for peer in peers_to_refresh:
        try:
            click.echo(f"  🔄 {peer}...", nl=False)

            # Get Pulumi stack state
            state = _get_pulumi_stack_state(peer)

            if state:
                # Save peer state
                peer_state_file = state_dir / f"{peer}-state.json"
                peer_state = {
                    'peer_name': peer,
                    'timestamp': datetime.utcnow().isoformat(),
                    'pulumi_stack': f"peer-{peer}",
                    'resources': state.get('resources', []),
                    'outputs': state.get('outputs', {}),
                    'deployment': {
                        'vpn_id': _extract_vpn_id(state),
                        'customer_gateway_id': _extract_cgw_id(state),
                        'transit_gateway_routes': _extract_tgw_routes(state),
                    },
                    'tunnel_status': {
                        'tunnel1': 'UNKNOWN',  # Would query AWS API
                        'tunnel2': 'UNKNOWN',  # Would query AWS API
                    },
                }

                with open(peer_state_file, 'w') as f:
                    json.dump(peer_state, f, indent=2)

                click.secho(" ✓", fg='green')
                refreshed += 1

                # Log in audit file
                audit_file = state_dir / f"{peer}-audit.jsonl"
                with open(audit_file, 'a') as f:
                    audit_entry = {
                        'timestamp': datetime.utcnow().isoformat(),
                        'action': 'state_refresh',
                        'status': 'success',
                        'resources': len(state.get('resources', [])),
                    }
                    f.write(json.dumps(audit_entry) + '\n')
            else:
                click.secho(" ⏳ (not deployed)", fg='yellow')

        except Exception as e:
            click.secho(f" ❌", fg='red')
            click.echo(f"      Error: {e}")
            failed += 1

    click.echo()
    click.echo("Summary:")
    click.echo(f"  Refreshed: {refreshed}")
    if failed > 0:
        click.echo(f"  Failed: {failed}")
    click.echo()

    if refreshed > 0:
        click.secho(f"✅ Peer state saved to .pulumi/peer-states/", fg='green')
        click.echo()
        click.echo("State files created:")
        for peer in peers_to_refresh:
            state_file = state_dir / f"{peer}-state.json"
            if state_file.exists():
                size = state_file.stat().st_size
                click.echo(f"  • {peer}-state.json ({size} bytes)")


def _get_all_peers() -> list:
    """Get list of all peer names from config."""
    import yaml
    config_file = Path("config/vpn-peers.yaml")
    if not config_file.exists():
        return []

    with open(config_file) as f:
        config = yaml.safe_load(f)

    return [peer['name'] for peer in config.get('peers', [])]


def _get_pulumi_stack_state(peer_name: str) -> dict:
    """Get Pulumi stack state for a peer."""
    try:
        # Try to get state from Pulumi
        result = subprocess.run(
            ['pulumi', 'stack', 'select', f'peer-{peer_name}'],
            capture_output=True,
            text=True,
            timeout=5,
            cwd='pulumi'
        )

        if result.returncode == 0:
            # Get stack exports/outputs
            result = subprocess.run(
                ['pulumi', 'stack', 'output', '--json'],
                capture_output=True,
                text=True,
                timeout=5,
                cwd='pulumi'
            )

            if result.returncode == 0:
                try:
                    return json.loads(result.stdout)
                except json.JSONDecodeError:
                    return {}

        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        # Pulumi not available - return None to indicate not deployed
        return None


def _extract_vpn_id(state: dict) -> str:
    """Extract VPN Connection ID from Pulumi state."""
    outputs = state.get('outputs', {})
    if 'vpn_id' in outputs:
        return outputs['vpn_id'].get('value', 'N/A')
    return 'N/A'


def _extract_cgw_id(state: dict) -> str:
    """Extract Customer Gateway ID from Pulumi state."""
    outputs = state.get('outputs', {})
    if 'customer_gateway_id' in outputs:
        return outputs['customer_gateway_id'].get('value', 'N/A')
    return 'N/A'


def _extract_tgw_routes(state: dict) -> list:
    """Extract Transit Gateway routes from Pulumi state."""
    outputs = state.get('outputs', {})
    if 'tgw_routes' in outputs:
        routes = outputs['tgw_routes'].get('value', [])
        return routes if isinstance(routes, list) else []
    return []


__all__ = ['refresh']
