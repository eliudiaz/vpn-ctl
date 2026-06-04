"""Test traffic connectivity for a peer."""

import click
import yaml
import json
from pathlib import Path


@click.command()
@click.argument('peer_name')
@click.option('--count', default=4, help='Number of packets to send')
@click.option('--timeout', default=5, help='Timeout in seconds')
def test(peer_name, count, timeout):
    """
    Test traffic connectivity for a peer.

    Simulates ping test to peer's destination networks and reports
    connectivity status, latency, and packet loss.
    """
    # Load peer configuration
    config_file = Path("config/vpn-peers.yaml")
    if not config_file.exists():
        click.secho(f"❌ Config not found: {config_file}", fg='red')
        return

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
        click.secho(f"❌ Peer not found: {peer_name}", fg='red')
        return

    # Get destination networks
    cidrs = peer.get('destination_cidrs', [])
    if not cidrs:
        click.secho("Error: No destination networks configured", fg='red')
        return

    # Get peer state
    state_dir = Path(".pulumi/peer-states")
    peer_state = {}
    if state_dir.exists():
        state_file = state_dir / f"{peer['name']}-state.json"
        if state_file.exists():
            try:
                with open(state_file) as f:
                    peer_state = json.load(f)
            except json.JSONDecodeError:
                pass

    tunnel_status = peer_state.get('tunnel_status', {})
    tunnel1 = tunnel_status.get('tunnel1', 'UNKNOWN')
    tunnel2 = tunnel_status.get('tunnel2', 'UNKNOWN')

    if tunnel1 == 'DOWN' and tunnel2 == 'DOWN':
        click.secho("Error: Both tunnels DOWN", fg='red')
        return

    click.echo(f"Testing {peer['name']} ({len(cidrs)} networks):")

    total_packets = 0
    total_received = 0

    for cidr in cidrs:
        packets_sent = count
        packets_received = count
        packet_loss = 0
        min_latency = 15.2
        avg_latency = 18.5
        max_latency = 22.1

        total_packets += packets_sent
        total_received += packets_received

        status = "OK" if packet_loss == 0 else ("DEGRADED" if packet_loss < 25 else "FAILED")
        click.echo(f"  {cidr:<20} {status:<10} loss={packet_loss}% latency={avg_latency:.1f}ms")

    loss_percent = 100 - (total_received/total_packets*100)
    click.echo(f"\nTotal: {total_received}/{total_packets} packets, {loss_percent:.0f}% loss")
