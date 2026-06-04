"""Show peer status and health."""

import click
import yaml
import json
import boto3
from pathlib import Path
from datetime import datetime


@click.command()
@click.argument('peer_name')
@click.option('--region', default='us-east-2', help='AWS region')
@click.option('--profile', default='affinity', help='AWS profile')
def status(peer_name, region, profile):
    """
    Show detailed status for a VPN peer.

    Displays specification, infrastructure state, tunnel status, and health.
    """
    # Load peer configuration from main config file
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

    # Load peer state if it exists
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

    click.echo(f"Peer: {peer['name']}")
    click.echo(f"Public IP: {peer.get('public_ip', 'N/A')}")
    click.echo(f"BGP ASN: {peer.get('bgp_asn', 'N/A')}")
    click.echo(f"Device: {peer.get('device_type', 'Unknown')} {peer.get('device_version', '')}")
    click.echo(f"Profile: {peer.get('tunnel_profile', 'N/A')}")
    click.echo(f"Enabled: {'Yes' if peer.get('enabled', False) else 'No'}")

    cidrs = peer.get('destination_cidrs', [])
    if cidrs:
        click.echo(f"Destination CIDRs: {', '.join(cidrs)}")

    if peer_state:
        click.echo("")
        deployment = peer_state.get('deployment', {})
        vpn_id = deployment.get('vpn_id', 'N/A')
        click.echo(f"VPN ID: {vpn_id}")
        click.echo(f"Customer Gateway: {deployment.get('customer_gateway_id', 'N/A')}")
        click.echo(f"Last Updated: {peer_state.get('timestamp', 'N/A')}")

        tunnel_status = peer_state.get('tunnel_status', {})
        tunnel1 = tunnel_status.get('tunnel1', 'UNKNOWN')
        tunnel2 = tunnel_status.get('tunnel2', 'UNKNOWN')

        # Query AWS for tunnel public IPs
        try:
            session = boto3.Session(profile_name=profile, region_name=region)
            ec2 = session.client('ec2')

            # Try multiple ways to find the VPN
            vpn_conn = None

            # Method 1: Use VPN ID from state
            if vpn_id != 'N/A':
                try:
                    response = ec2.describe_vpn_connections(VpnConnectionIds=[vpn_id])
                    if response['VpnConnections']:
                        vpn_conn = response['VpnConnections'][0]
                except:
                    pass

            # Method 2: Search by peer name tag
            if not vpn_conn:
                peer_name_lower = peer['name'].lower()
                response = ec2.describe_vpn_connections(
                    Filters=[
                        {'Name': 'tag:Name', 'Values': [peer_name_lower]},
                        {'Name': 'state', 'Values': ['available']}
                    ]
                )
                if response['VpnConnections']:
                    vpn_conn = response['VpnConnections'][0]

            if vpn_conn:
                # Extract tunnel IPs from VPN connection
                tunnel_options = vpn_conn.get('Options', {}).get('TunnelOptions', [])
                vgw_telemetry = vpn_conn.get('VgwTelemetry', [])

                if tunnel_options and len(tunnel_options) >= 2:
                    tunnel1_ip = tunnel_options[0].get('OutsideIpAddress', 'N/A')
                    tunnel2_ip = tunnel_options[1].get('OutsideIpAddress', 'N/A')

                    # Get status from VgwTelemetry
                    t1_status = vgw_telemetry[0].get('Status', 'UNKNOWN') if len(vgw_telemetry) > 0 else 'UNKNOWN'
                    t2_status = vgw_telemetry[1].get('Status', 'UNKNOWN') if len(vgw_telemetry) > 1 else 'UNKNOWN'

                    click.echo(f"Tunnel 1: {tunnel1} (AWS IP: {tunnel1_ip}, Status: {t1_status})")
                    click.echo(f"Tunnel 2: {tunnel2} (AWS IP: {tunnel2_ip}, Status: {t2_status})")
                else:
                    click.echo(f"Tunnel 1: {tunnel1}")
                    click.echo(f"Tunnel 2: {tunnel2}")
            else:
                click.echo(f"Tunnel 1: {tunnel1}")
                click.echo(f"Tunnel 2: {tunnel2}")
        except Exception as e:
            # Fallback if AWS query fails
            click.echo(f"Tunnel 1: {tunnel1}")
            click.echo(f"Tunnel 2: {tunnel2}")

        routes = peer_state.get('routes', {})
        tgw_routes = routes.get('tgw', [])
        if tgw_routes:
            click.echo(f"TGW Routes: {', '.join(tgw_routes)}")
    else:
        click.echo("")
        click.echo("Status: Not deployed")
