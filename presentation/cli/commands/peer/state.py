"""View and manage peer deployment state."""

import click
import json
from pathlib import Path
from datetime import datetime


@click.command()
@click.argument('peer_name', required=False)
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.option('--audit', is_flag=True, help='Show audit log')
def state(peer_name, output_json, audit):
    """
    View peer deployment state.

    Shows the saved state snapshot from the last refresh operation,
    including deployment details and tunnel status.
    """
    if not peer_name:
        _show_state_summary()
        return

    state_file = Path(f".pulumi/peer-states/{peer_name}-state.json")

    if not state_file.exists():
        click.secho(f"❌ No state found for {peer_name}", fg='red')
        click.echo(f"   Run: vpn-ctl peer refresh {peer_name}")
        return

    try:
        with open(state_file) as f:
            peer_state = json.load(f)

        if output_json:
            click.echo(json.dumps(peer_state, indent=2))
            return

        # Format display
        click.echo()
        click.secho(f"📊 Peer State: {peer_name}", fg='cyan', bold=True)
        click.echo()

        # Metadata
        timestamp = peer_state.get('timestamp', 'N/A')
        click.secho("Metadata:", fg='yellow', bold=True)
        click.echo(f"  Updated: {timestamp}")
        click.echo(f"  Stack: {peer_state.get('pulumi_stack', 'N/A')}")
        click.echo()

        # Deployment info
        deployment = peer_state.get('deployment', {})
        click.secho("Deployment:", fg='yellow', bold=True)
        click.echo(f"  VPN ID: {deployment.get('vpn_id', 'N/A')}")
        click.echo(f"  CGW ID: {deployment.get('customer_gateway_id', 'N/A')}")

        tgw_routes = deployment.get('transit_gateway_routes', [])
        if tgw_routes:
            click.echo(f"  TGW Routes: {len(tgw_routes)} active")
            for route in tgw_routes[:5]:  # Show first 5
                click.echo(f"    • {route}")
        click.echo()

        # Tunnel status
        tunnel_status = peer_state.get('tunnel_status', {})
        click.secho("Tunnel Status:", fg='yellow', bold=True)
        click.echo(f"  Tunnel 1: {tunnel_status.get('tunnel1', 'UNKNOWN')}")
        click.echo(f"  Tunnel 2: {tunnel_status.get('tunnel2', 'UNKNOWN')}")
        click.echo()

        # Resources count
        resources = peer_state.get('resources', [])
        click.secho("Resources:", fg='yellow', bold=True)
        click.echo(f"  Total: {len(resources)}")
        click.echo()

        # Audit log if requested
        if audit:
            _show_audit_log(peer_name)

    except json.JSONDecodeError:
        click.secho(f"❌ Invalid state file: {state_file}", fg='red')


def _show_state_summary():
    """Show summary of all saved peer states."""
    state_dir = Path(".pulumi/peer-states")

    click.echo()
    click.secho("📊 Peer State Summary", fg='cyan', bold=True)
    click.echo()

    if not state_dir.exists():
        click.echo("  No peer states saved")
        click.echo("  Run: vpn-ctl peer refresh --all")
        return

    state_files = sorted(state_dir.glob("*-state.json"))

    if not state_files:
        click.echo("  No peer states saved")
        click.echo("  Run: vpn-ctl peer refresh --all")
        return

    click.echo("Peers with saved state:")
    click.echo()

    for state_file in state_files:
        try:
            with open(state_file) as f:
                peer_state = json.load(f)

            peer_name = peer_state.get('peer_name', '?')
            timestamp = peer_state.get('timestamp', 'N/A')
            vpn_id = peer_state.get('deployment', {}).get('vpn_id', 'N/A')
            resources = len(peer_state.get('resources', []))

            click.echo(f"  • {peer_name}")
            click.echo(f"    Updated: {timestamp}")
            if vpn_id != 'N/A':
                click.echo(f"    VPN ID: {vpn_id}")
            click.echo(f"    Resources: {resources}")
            click.echo()
        except json.JSONDecodeError:
            pass


def _show_audit_log(peer_name: str):
    """Show audit log for a peer."""
    audit_file = Path(f".pulumi/peer-states/{peer_name}-audit.jsonl")

    if not audit_file.exists():
        click.echo("  No audit log available")
        return

    click.secho("Audit Log:", fg='yellow', bold=True)
    try:
        with open(audit_file) as f:
            entries = [json.loads(line) for line in f if line.strip()]

        for entry in entries[-10:]:  # Show last 10 entries
            timestamp = entry.get('timestamp', '?')
            action = entry.get('action', '?')
            status = entry.get('status', '?')
            click.echo(f"  {timestamp} - {action} ({status})")
    except (json.JSONDecodeError, IOError):
        click.echo("  Error reading audit log")


__all__ = ['state']
