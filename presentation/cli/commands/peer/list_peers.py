"""List all VPN peers."""

import click
import yaml
from pathlib import Path


def load_peers_from_config():
    """Load peer configurations from YAML."""
    config_file = Path('config/vpn-peers.yaml')
    if not config_file.exists():
        return {}

    with open(config_file) as f:
        config = yaml.safe_load(f)

    peers = {}
    for peer in config.get('peers', []):
        peer_name = peer['name'].lower()
        peers[peer_name] = {
            'name': peer['name'],
            'enabled': peer.get('enabled', False),
            'device': peer.get('device_type', 'Unknown'),
            'public_ip': peer.get('public_ip', 'N/A'),
            'bgp_asn': peer.get('bgp_asn', 'N/A'),
            'cidrs': peer.get('destination_cidrs', []),
        }

    return peers


@click.command()
@click.option('--format', type=click.Choice(['text', 'json', 'compact']), default='text',
              help='Output format')
def list_peers(format):
    """List all VPN peers."""
    try:
        peers = load_peers_from_config()

        if not peers:
            click.echo("No peers configured.")
            return

        if format == 'json':
            import json
            output = {
                'total': len(peers),
                'peers': [
                    {
                        'name': info['name'],
                        'enabled': info['enabled'],
                        'device': info['device'],
                        'public_ip': info['public_ip'],
                        'bgp_asn': info['bgp_asn'],
                        'cidrs': info['cidrs'],
                    }
                    for info in sorted(peers.values(), key=lambda x: x['name'])
                ]
            }
            click.echo(json.dumps(output, indent=2))
        elif format == 'compact':
            for peer_key, peer_info in sorted(peers.items()):
                status = "enabled" if peer_info['enabled'] else "disabled"
                click.echo(f"{peer_info['name']:<25} {status:<10} {peer_info['device']:<30} {peer_info['public_ip']}")
        else:
            click.echo(f"{'Peer':<25} {'Status':<10} {'Device':<30} {'IP Address':<18}")
            click.echo("─" * 85)
            for peer_key, peer_info in sorted(peers.items()):
                status = "enabled" if peer_info['enabled'] else "disabled"
                click.echo(f"{peer_info['name']:<25} {status:<10} {peer_info['device']:<30} {peer_info['public_ip']:<18}")
            click.echo(f"\nTotal: {len(peers)} peers")
    except Exception as e:
        click.secho(f"Error: {e}", fg='red')
