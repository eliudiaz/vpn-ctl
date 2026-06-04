"""Show tunnel status for peers."""

import click
import yaml
import json
from pathlib import Path
from datetime import datetime


@click.command()
@click.option('--format', type=click.Choice(['text', 'json']), default='text',
              help='Output format')
def status(format):
    """
    Show tunnel status for all peers.

    Displays up/down status, last change time, and health indicators
    for all configured VPN tunnels.
    """
    # Load peer configuration
    config_file = Path("config/vpn-peers.yaml")
    if not config_file.exists():
        click.secho(f"❌ Config not found: {config_file}", fg='red')
        return

    with open(config_file) as f:
        config = yaml.safe_load(f)

    peers = config.get('peers', [])

    # Load saved states
    state_dir = Path(".pulumi/peer-states")
    states = {}
    if state_dir.exists():
        for state_file in state_dir.glob("*-state.json"):
            try:
                with open(state_file) as f:
                    state_data = json.load(f)
                    peer_name = state_data.get('peer_name')
                    if peer_name:
                        states[peer_name.lower()] = state_data
            except json.JSONDecodeError:
                pass

    if format == 'json':
        _display_tunnel_status_json(peers, states)
    else:
        _display_tunnel_status_text(peers, states)


def _display_tunnel_status_text(peers, states):
    """Display tunnel status in text format."""
    # Table header
    click.echo(f"{'Peer':<25} {'Status':<12} {'T1':<8} {'T2':<8} {'Last Updated':<25}")
    click.echo("─" * 80)

    # Calculate stats
    total = len(peers)
    up_count = 0
    down_count = 0
    unknown_count = 0

    for peer in peers:
        peer_name = peer['name']
        peer_state = states.get(peer_name.lower(), {})
        tunnel_status = peer_state.get('tunnel_status', {})
        tunnel1 = tunnel_status.get('tunnel1', 'UNKNOWN')
        tunnel2 = tunnel_status.get('tunnel2', 'UNKNOWN')

        if tunnel1 == 'UP' and tunnel2 == 'UP':
            status = 'UP'
            up_count += 1
        elif tunnel1 == 'DOWN' and tunnel2 == 'DOWN':
            status = 'DOWN'
            down_count += 1
        elif tunnel1 == 'UP' or tunnel2 == 'UP':
            status = 'PARTIAL'
            up_count += 0.5
            down_count += 0.5
        else:
            status = 'UNKNOWN'
            unknown_count += 1

        timestamp = peer_state.get('timestamp', '')
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                last_changed = dt.strftime('%Y-%m-%d %H:%M:%S')
            except:
                last_changed = 'N/A'
        else:
            last_changed = '-'

        t1 = '✅' if tunnel1 == 'UP' else ('❌' if tunnel1 == 'DOWN' else '-')
        t2 = '✅' if tunnel2 == 'UP' else ('❌' if tunnel2 == 'DOWN' else '-')

        click.echo(f"{peer_name:<25} {status:<12} {t1:<8} {t2:<8} {last_changed:<25}")

    click.echo("─" * 80)
    click.echo(f"Total: {total} | UP: {int(up_count)} | DOWN: {int(down_count)} | UNKNOWN: {unknown_count}")


def _display_tunnel_status_json(peers, states):
    """Display tunnel status as JSON."""
    summary = {'total': 0, 'up': 0, 'down': 0, 'partial': 0, 'unknown': 0}
    peers_data = []

    for peer in peers:
        peer_name = peer['name']
        peer_state = states.get(peer_name.lower(), {})
        tunnel_status = peer_state.get('tunnel_status', {})
        tunnel1 = tunnel_status.get('tunnel1', 'UNKNOWN')
        tunnel2 = tunnel_status.get('tunnel2', 'UNKNOWN')

        if tunnel1 == 'UP' and tunnel2 == 'UP':
            status = 'UP'
            summary['up'] += 1
        elif tunnel1 == 'DOWN' and tunnel2 == 'DOWN':
            status = 'DOWN'
            summary['down'] += 1
        elif tunnel1 == 'UP' or tunnel2 == 'UP':
            status = 'PARTIAL'
            summary['partial'] += 1
        else:
            status = 'UNKNOWN'
            summary['unknown'] += 1

        summary['total'] += 1

        peers_data.append({
            'name': peer_name,
            'status': status,
            'tunnel1': tunnel1,
            'tunnel2': tunnel2,
            'enabled': peer.get('enabled', False),
            'device': peer.get('device_type'),
            'public_ip': peer.get('public_ip'),
        })

    output = {
        'timestamp': datetime.utcnow().isoformat(),
        'summary': summary,
        'peers': peers_data
    }
    click.echo(json.dumps(output, indent=2))
