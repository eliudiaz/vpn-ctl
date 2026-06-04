"""vpnctl infra commands - Infrastructure state management and export."""

import click
import json
import boto3
import yaml
from pathlib import Path
from datetime import datetime


@click.group()
def infra():
    """Infrastructure management and monitoring."""
    pass


@infra.command('export-config')
@click.option('--output', type=click.Path(), default='infra-config.json',
              help='Output file for infrastructure config')
@click.option('--peers-config', type=click.Path(exists=True),
              default='config/vpn-peers.yaml', help='Path to peers config')
@click.option('--region', default='us-east-2', help='AWS region')
@click.option('--profile', default='default', help='AWS profile')
def export_config(output, peers_config, region, profile):
    """
    Export current infrastructure state to JSON config.

    Captures:
    - Transit Gateway ID, state, ASN
    - EKS cluster info, VPC, TGW attachment
    - VPN connection IDs and tunnel IPs for each peer
    - TGW route table and routes
    - Test endpoint configuration from peers YAML

    This becomes the source of truth for health monitoring.

    Example:
      vpnctl infra export-config
      vpnctl infra export-config --output prod-config.json
    """
    click.echo("🔍 Exporting infrastructure state from AWS...")
    click.echo(f"   Profile: {profile}")
    click.echo(f"   Region: {region}")
    click.echo(f"   Peers config: {peers_config}")

    try:
        # Load peer definitions from YAML
        click.echo("\n📋 Loading peer definitions...")
        peers_yaml = load_peers_yaml(peers_config)
        peer_names = {p['name']: p for p in peers_yaml.get('peers', [])}
        click.secho(f"✓ Loaded {len(peer_names)} peers", fg='green')

        # Initialize AWS session
        session = boto3.Session(profile_name=profile, region_name=region)
        ec2 = session.client('ec2')

        # Get Transit Gateway info
        click.echo("\n🌐 Querying Transit Gateway...")
        tgw_data = get_transit_gateway(ec2)
        click.secho(f"✓ TGW: {tgw_data['id']} ({tgw_data['state']})", fg='green')

        # Get EKS cluster info
        click.echo("\n🎯 Querying EKS cluster...")
        eks_data = get_eks_info(ec2, session)
        click.secho(f"✓ EKS: {eks_data['name']} (TGW attachment: {eks_data['tgw_attachment_id']})", fg='green')

        # Get TGW route table
        click.echo("\n📍 Querying Transit Gateway route table...")
        rtb_data = get_tgw_route_table(ec2, tgw_data['id'])
        click.secho(f"✓ Route table: {rtb_data['id']}", fg='green')

        # Get VPN state for each peer
        click.echo("\n📡 Querying VPN connections for each peer...")
        peers_data = {}
        for peer_name, peer_spec in peer_names.items():
            vpn_data = get_peer_vpn_state(ec2, peer_name, peer_spec)
            if vpn_data:
                peers_data[peer_name] = vpn_data
                click.secho(f"✓ {peer_name}: VPN {vpn_data['aws_resources']['vpn_connection_id']}", fg='green')
            else:
                click.secho(f"⚠️  {peer_name}: No VPN found (may not be deployed)", fg='yellow')

        # Build complete config
        click.echo("\n🔨 Building infrastructure config...")
        config = {
            "metadata": {
                "version": "1.0",
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "aws_account": session.client('sts').get_caller_identity()['Account'],
                "aws_region": region,
                "environment": "dev",  # Can be overridden
                "exported_by": "vpnctl infra export-config"
            },
            "infrastructure": {
                "transit_gateway": tgw_data,
                "eks_cluster": eks_data,
                "tgw_route_table": rtb_data
            },
            "peers": peers_data,
            "test_config": build_test_config(peer_names)
        }

        # Write to file
        click.echo(f"\n💾 Writing to {output}...")
        output_path = Path(output)
        with open(output_path, 'w') as f:
            json.dump(config, f, indent=2)

        click.secho(f"✓ Infrastructure config exported to {output}", fg='green')
        click.echo(f"\nConfig includes:")
        click.echo(f"  • Transit Gateway: {tgw_data['id']}")
        click.echo(f"  • EKS Cluster: {eks_data['name']}")
        click.echo(f"  • Peers: {len(peers_data)}")
        click.echo(f"  • Routes: {len(rtb_data.get('routes', []))}")
        click.echo(f"\nNext steps:")
        click.echo(f"  vpnctl health deploy --target helm --environment prod")

    except Exception as e:
        click.secho(f"❌ Export failed: {e}", fg='red')
        raise click.Abort()


def load_peers_yaml(config_file):
    """Load peer definitions from YAML."""
    with open(config_file) as f:
        config = yaml.safe_load(f)
    return config or {}


def get_transit_gateway(ec2):
    """Query Transit Gateway by name tag."""
    response = ec2.describe_transit_gateways(
        Filters=[
            {'Name': 'tag:Name', 'Values': ['vpn-hub-tgw']},
            {'Name': 'state', 'Values': ['available']}
        ]
    )

    if not response['TransitGateways']:
        raise Exception("Transit Gateway 'vpn-hub-tgw' not found")

    tgw = response['TransitGateways'][0]
    return {
        'id': tgw['TransitGatewayId'],
        'name': next((tag['Value'] for tag in tgw.get('Tags', []) if tag['Key'] == 'Name'), 'unknown'),
        'asn': tgw['Options']['AmazonSideAsn'],
        'owner_id': tgw['OwnerId'],
        'state': tgw['State']
    }


def get_eks_info(ec2, session):
    """Query EKS cluster info and TGW attachment."""
    eks = session.client('eks')

    # Get cluster info
    response = eks.describe_cluster(name='asg-plat-dev')
    cluster = response['cluster']

    # Get TGW attachment for EKS
    attachments = ec2.describe_transit_gateway_attachments(
        Filters=[
            {'Name': 'resource-id', 'Values': [cluster['name']]},
            {'Name': 'resource-type', 'Values': ['peering']}
        ]
    )

    attachment_id = None
    if attachments['TransitGatewayAttachments']:
        attachment_id = attachments['TransitGatewayAttachments'][0]['TransitGatewayAttachmentId']

    return {
        'name': cluster['name'],
        'arn': cluster['arn'],
        'region': 'us-east-2',
        'vpc_id': cluster['resourcesVpcConfig']['vpcId'],
        'vpc_cidr': cluster['resourcesVpcConfig'].get('cidr', '172.31.0.0/16'),
        'tgw_attachment_id': attachment_id or 'not-attached',
        'tgw_attachment_state': attachments['TransitGatewayAttachments'][0]['State'] if attachments['TransitGatewayAttachments'] else 'detached'
    }


def get_tgw_route_table(ec2, tgw_id):
    """Query TGW route table and routes."""
    response = ec2.describe_transit_gateway_route_tables(
        Filters=[
            {'Name': 'transit-gateway-id', 'Values': [tgw_id]},
            {'Name': 'state', 'Values': ['available']}
        ]
    )

    if not response['TransitGatewayRouteTables']:
        raise Exception(f"Route table not found for TGW {tgw_id}")

    rtb = response['TransitGatewayRouteTables'][0]

    # Get routes
    routes_response = ec2.search_transit_gateway_routes(
        TransitGatewayRouteTableId=rtb['TransitGatewayRouteTableId'],
        Filters=[{'Name': 'state', 'Values': ['active', 'blackhole']}]
    )

    routes = []
    for route in routes_response.get('Routes', []):
        if 'DestinationCidrBlock' in route:
            routes.append({
                'cidr': route['DestinationCidrBlock'],
                'state': route['State'],
                'type': route.get('Type', 'propagated')
            })

    return {
        'id': rtb['TransitGatewayRouteTableId'],
        'transit_gateway_id': tgw_id,
        'state': rtb['State'],
        'routes': routes
    }


def get_peer_vpn_state(ec2, peer_name, peer_spec):
    """Query VPN connection state for a peer."""
    peer_name_normalized = peer_name.lower().replace(' ', '-')

    # Find VPN by peer tag
    response = ec2.describe_vpn_connections(
        Filters=[
            {'Name': 'tag:Peer', 'Values': [peer_name_normalized]},
            {'Name': 'state', 'Values': ['available']}
        ]
    )

    if not response['VpnConnections']:
        return None

    vpn = response['VpnConnections'][0]
    vpn_id = vpn['VpnConnectionId']

    # Extract tunnel IPs and status
    tunnel_options = vpn.get('Options', {}).get('TunnelOptions', [])
    vgw_telemetry = vpn.get('VgwTelemetry', [])

    tunnel1_ip = tunnel_options[0].get('OutsideIpAddress', 'N/A') if tunnel_options else 'N/A'
    tunnel1_status = vgw_telemetry[0].get('Status', 'UNKNOWN').upper() if vgw_telemetry else 'UNKNOWN'

    tunnel2_ip = tunnel_options[1].get('OutsideIpAddress', 'N/A') if len(tunnel_options) > 1 else 'N/A'
    tunnel2_status = vgw_telemetry[1].get('Status', 'UNKNOWN').upper() if len(vgw_telemetry) > 1 else 'UNKNOWN'

    # Find TGW attachment
    attachments = ec2.describe_transit_gateway_attachments(
        Filters=[
            {'Name': 'resource-id', 'Values': [vpn_id]},
            {'Name': 'resource-type', 'Values': ['vpn']}
        ]
    )

    attachment_id = None
    attachment_state = 'unknown'
    if attachments['TransitGatewayAttachments']:
        attachment_id = attachments['TransitGatewayAttachments'][0]['TransitGatewayAttachmentId']
        attachment_state = attachments['TransitGatewayAttachments'][0]['State']

    # Get destination CIDRs from peer spec
    destination_cidrs = peer_spec.get('destination_cidrs', [])

    # Get TGW routes for this peer's CIDRs
    tgw_id = vpn.get('TransitGatewayId')
    tgw_routes = []
    if tgw_id:
        rtb_response = ec2.describe_transit_gateway_route_tables(
            Filters=[{'Name': 'transit-gateway-id', 'Values': [tgw_id]}]
        )
        if rtb_response['TransitGatewayRouteTables']:
            rtb_id = rtb_response['TransitGatewayRouteTables'][0]['TransitGatewayRouteTableId']
            routes_response = ec2.search_transit_gateway_routes(
                TransitGatewayRouteTableId=rtb_id,
                Filters=[{'Name': 'state', 'Values': ['active', 'blackhole']}]
            )
            for route in routes_response.get('Routes', []):
                cidr = route.get('DestinationCidrBlock')
                if cidr in destination_cidrs:
                    tgw_routes.append({
                        'cidr': cidr,
                        'state': route['State'],
                        'type': route.get('Type', 'propagated')
                    })

    return {
        'enabled': peer_spec.get('enabled', True),
        'public_ip': peer_spec.get('public_ip'),
        'device_type': peer_spec.get('device_type'),
        'device_version': peer_spec.get('device_version'),
        'aws_resources': {
            'vpn_connection_id': vpn_id,
            'customer_gateway_id': vpn.get('CustomerGatewayId'),
            'tgw_attachment_id': attachment_id,
            'tgw_attachment_state': attachment_state,
            'tgw_route_table_id': vpn.get('TransitGatewayOwnerId')
        },
        'tunnels': {
            'tunnel1': {
                'ip': tunnel1_ip,
                'status': tunnel1_status,
                'last_status_change': datetime.utcnow().isoformat() + 'Z'
            },
            'tunnel2': {
                'ip': tunnel2_ip,
                'status': tunnel2_status,
                'last_status_change': datetime.utcnow().isoformat() + 'Z'
            }
        },
        'routes': {
            'destination_cidrs': destination_cidrs,
            'tgw_routes': tgw_routes
        }
    }


def build_test_config(peer_specs):
    """Build test configuration from peer specs."""
    test_config = {
        'global': {
            'timeout_seconds': 5,
            'refresh_interval_seconds': 60,
            'enabled': True
        },
        'peer_tests': {}
    }

    for peer_name, peer_spec in peer_specs.items():
        # Get test endpoints from peer spec if they exist
        test_endpoints = peer_spec.get('test_endpoints', [])

        test_config['peer_tests'][peer_name] = {
            'enabled': peer_spec.get('enabled', True),
            'endpoints': test_endpoints
        }

    return test_config
