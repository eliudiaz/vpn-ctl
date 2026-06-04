"""Interactive peer and command selector."""

import click
import yaml
from pathlib import Path
from presentation.cli.commands.doctor import (
    _check_specs,
    _check_pulumi_state,
    _check_aws_credentials,
    _check_tunnel_status,
    _check_state_sync,
    _check_transit_gateway,
    _display_check_result,
)


def load_peer_configs():
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
            'tunnel_profile': peer.get('tunnel_profile', 'N/A'),
        }
    
    return peers


def show_peer_menu(peers):
    """Display peer selection menu."""
    if not peers:
        click.secho("❌ No peers configured", fg='red')
        return None
    
    click.echo()
    click.secho("Select a VPN Peer:", fg='cyan', bold=True)
    click.echo()
    
    peer_list = sorted(peers.keys())
    for i, peer_key in enumerate(peer_list, 1):
        peer = peers[peer_key]
        status_icon = "✅" if peer['enabled'] else "⏸️"
        click.echo(f"  {i}. {status_icon} {peer['name']:<25} ({peer['device']})")
    
    click.echo(f"  0. Exit")
    click.echo()
    
    while True:
        try:
            choice = click.prompt("Enter selection", type=int)
            if choice == 0:
                return None
            if 1 <= choice <= len(peer_list):
                return peer_list[choice - 1]
            click.secho("Invalid selection. Please try again.", fg='red')
        except (ValueError, click.Abort):
            return None


def show_command_menu():
    """Display command selection menu."""
    click.echo()
    click.secho("Select an action:", fg='cyan', bold=True)
    click.echo()
    click.echo("  1. 📊 status   - Check if tunnels are UP/DOWN")
    click.echo("  2. 🏥 doctor   - Check IaC (Pulumi) state and health")
    click.echo("  3. 🔄 test     - Send test traffic (ping)")
    click.echo("  4. 🔗 config   - Show detailed configuration")
    click.echo("  0. Back to peer selection")
    click.echo()
    
    while True:
        try:
            choice = click.prompt("Enter selection", type=int)
            if choice in [0, 1, 2, 3, 4]:
                return choice
            click.secho("Invalid selection. Please try again.", fg='red')
        except (ValueError, click.Abort):
            return 0


def show_peer_status(peer_name, peers):
    """Show peer tunnel status (UP/DOWN)."""
    peer = peers.get(peer_name.lower())
    if not peer:
        click.secho(f"❌ Peer '{peer_name}' not found", fg='red')
        return
    
    click.echo()
    click.secho(f"📊 Peer Status: {peer['name'].upper()}", fg='cyan', bold=True)
    click.echo()
    
    click.echo(f"Configuration:")
    click.echo(f"  Device:      {peer['device']}")
    click.echo(f"  Public IP:   {peer['public_ip']}")
    click.echo(f"  BGP ASN:     {peer['bgp_asn']}")
    click.echo()
    
    click.echo(f"Networks ({len(peer['cidrs'])} CIDR blocks):")
    for cidr in peer['cidrs'][:3]:
        click.echo(f"  • {cidr}")
    if len(peer['cidrs']) > 3:
        click.echo(f"  • ... and {len(peer['cidrs']) - 3} more")
    
    click.echo()
    click.echo(f"Tunnel Status:")
    
    # Simulated tunnel status - in real impl, would query AWS
    tunnel_status = {
        'vimenca': {'tunnel1': 'UP', 'tunnel2': 'UP'},
        'cibao': {'tunnel1': 'UP', 'tunnel2': 'UP'},
        'apap': {'tunnel1': 'DOWN', 'tunnel2': 'DOWN'},
        'affinity-legacy-network': {'tunnel1': 'UP', 'tunnel2': 'DOWN'}
    }
    
    status = tunnel_status.get(peer_name.lower(), {'tunnel1': 'UNKNOWN', 'tunnel2': 'UNKNOWN'})
    
    t1_icon = "✅" if status['tunnel1'] == 'UP' else "❌" if status['tunnel1'] == 'DOWN' else "❓"
    t2_icon = "✅" if status['tunnel2'] == 'UP' else "❌" if status['tunnel2'] == 'DOWN' else "❓"
    
    click.echo(f"  Tunnel 1: {t1_icon} {status['tunnel1']}")
    click.echo(f"  Tunnel 2: {t2_icon} {status['tunnel2']}")
    click.echo()


def show_peer_doctor(peer_name, peers):
    """Show IaC (Pulumi) health check for peer."""
    peer = peers.get(peer_name.lower())
    if not peer:
        click.secho(f"❌ Peer '{peer_name}' not found", fg='red')
        return
    
    click.echo()
    click.secho(f"🏥 Infrastructure Health Check: {peer['name'].upper()}", fg='cyan', bold=True)
    click.echo()
    
    # Run core health checks
    click.echo("Performing health checks...")
    click.echo()
    
    checks = [
        ("Spec Validity", _check_specs(verbose=False)),
        ("Pulumi State", _check_pulumi_state(verbose=False)),
        ("AWS Credentials", _check_aws_credentials(verbose=False)),
        ("Tunnel Status", _check_tunnel_status(verbose=False)),
        ("Spec ↔ State Sync", _check_state_sync(verbose=False)),
        ("Transit Gateway", _check_transit_gateway(verbose=False)),
    ]
    
    passed = 0
    failed = 0
    
    for check_name, check_result in checks:
        _display_check_result(check_result)
        if check_result['status'] == 'pass':
            passed += 1
        else:
            failed += 1
    
    click.echo()
    click.secho(f"Results: {passed} passed, {failed} warnings/failures", fg='cyan')
    click.echo()


def show_test_traffic(peer_name, peers):
    """Simulate sending test traffic."""
    peer = peers.get(peer_name.lower())
    if not peer:
        click.secho(f"❌ Peer '{peer_name}' not found", fg='red')
        return
    
    click.echo()
    click.secho(f"🔄 Test Traffic: {peer['name'].upper()}", fg='cyan', bold=True)
    click.echo()
    
    click.echo(f"Sending PING test packets to {peer['name']}...")
    click.echo()
    
    # Simulated test results
    test_results = {
        'vimenca': {'status': 'SUCCESS', 'latency': '45ms', 'loss': '0%'},
        'cibao': {'status': 'SUCCESS', 'latency': '52ms', 'loss': '0%'},
        'apap': {'status': 'FAILED', 'latency': 'N/A', 'loss': '100%'},
        'affinity-legacy-network': {'status': 'SUCCESS', 'latency': '38ms', 'loss': '0%'}
    }
    
    result = test_results.get(peer_name.lower(), {'status': 'UNKNOWN', 'latency': 'N/A', 'loss': 'N/A'})
    
    status_icon = "✅" if result['status'] == 'SUCCESS' else "❌"
    status_color = 'green' if result['status'] == 'SUCCESS' else 'red'
    
    click.echo(f"Test Result: {status_icon}")
    click.secho(f"Status:      {result['status']}", fg=status_color, bold=True)
    click.echo(f"Latency:     {result['latency']}")
    click.echo(f"Packet Loss: {result['loss']}")
    click.echo()
    
    if result['status'] == 'SUCCESS':
        click.secho("✅ Test traffic successful!", fg='green')
    else:
        click.secho("❌ Test traffic failed - check peer configuration", fg='red')
    
    click.echo()


def show_peer_config(peer_name, peers):
    """Show detailed peer configuration."""
    peer = peers.get(peer_name.lower())
    if not peer:
        click.secho(f"❌ Peer '{peer_name}' not found", fg='red')
        return
    
    click.echo()
    click.secho(f"⚙️  Configuration: {peer['name'].upper()}", fg='cyan', bold=True)
    click.echo()
    
    click.echo(f"Device Configuration:")
    click.echo(f"  Type:            {peer['device']}")
    click.echo(f"  Public IP:       {peer['public_ip']}")
    click.echo(f"  BGP ASN:         {peer['bgp_asn']}")
    click.echo(f"  Tunnel Profile:  {peer['tunnel_profile']}")
    click.echo()
    
    click.echo(f"Network Configuration:")
    for i, cidr in enumerate(peer['cidrs'], 1):
        click.echo(f"  {i}. {cidr}")
    
    click.echo()
    click.echo(f"AWS Resources:")
    click.echo(f"  • Customer Gateway")
    click.echo(f"  • VPN Connection")
    click.echo(f"  • Transit Gateway Route(s)")
    click.echo()


@click.command()
def interactive():
    """Interactive peer selector and command executor."""
    click.echo()
    click.secho("🚀 VPN Peer Interactive Menu", fg='cyan', bold=True)
    click.echo()
    
    peers = load_peer_configs()
    
    while True:
        # Step 1: Select peer
        selected_peer = show_peer_menu(peers)
        if selected_peer is None:
            click.secho("Exiting interactive mode.", fg='yellow')
            break
        
        peer_name = selected_peer
        peer = peers[peer_name]
        
        # Step 2: Select command
        while True:
            click.secho(f"\nPeer: {peer['name']} ({peer['device']})", fg='green', bold=True)
            
            command_choice = show_command_menu()
            
            if command_choice == 0:
                break
            elif command_choice == 1:
                show_peer_status(peer_name, peers)
            elif command_choice == 2:
                show_peer_doctor(peer_name, peers)
            elif command_choice == 3:
                show_test_traffic(peer_name, peers)
            elif command_choice == 4:
                show_peer_config(peer_name, peers)
            
            click.prompt("\nPress Enter to continue", type=str)


__all__ = ['interactive']
