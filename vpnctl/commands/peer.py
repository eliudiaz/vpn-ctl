"""vpnctl peer commands - Manage VPN peer infrastructure lifecycle."""

import click
import subprocess
import json
import boto3
from pathlib import Path
import yaml
import time

from domain.services.peer_spec_manager import PeerSpecManager
from domain.exceptions import DomainValidationError


@click.group()
def peer():
    """VPN peer operations and management."""
    pass


@peer.command()
@click.argument('peer_name')
@click.option('--region', default='us-east-2', help='AWS region')
@click.option('--profile', default='default', help='AWS profile')
def deploy(peer_name, region, profile):
    """Deploy a VPN peer infrastructure (VPN + routes)."""
    click.echo(f"\n🚀 DEPLOYING PEER: {peer_name.upper()}")
    click.echo("=" * 80)

    # Load config
    config_path = Path(__file__).parent.parent.parent / "config" / "vpn-peers.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Find peer config
    peer_config = next(
        (p for p in config["peers"] if p["name"].lower() == peer_name.lower()),
        None
    )

    if not peer_config:
        click.secho(f"❌ Peer not found in config: {peer_name}", fg='red')
        return

    click.echo(f"\n📋 Peer Configuration:")
    click.echo(f"  • Name: {peer_config['name']}")
    click.echo(f"  • Public IP: {peer_config['public_ip']}")
    click.echo(f"  • Device Type: {peer_config.get('device_type', 'N/A')}")
    click.echo(f"  • Destination CIDRs: {', '.join(peer_config.get('destination_cidrs', []))}")

    # Step 1: Create VPN if not exists
    click.echo(f"\n1️⃣  Creating VPN Connection (if needed)...")
    _ensure_vpn_exists(peer_config, region, profile)

    # Step 1b: Wait for VPN to be available
    click.echo(f"\n1b️⃣  Ensuring VPN is available...")
    _wait_for_vpn_available(peer_config, region, profile)

    # Step 2: Deploy peer stack with Pulumi
    click.echo(f"\n2️⃣  Deploying Pulumi stack: peer-{peer_name}...")
    _deploy_peer_stack(peer_name, region, profile)

    # Step 3: Verify with Pulumi
    click.echo(f"\n3️⃣  Verifying with Pulumi CLI...")
    _verify_pulumi_stack(peer_name)

    # Step 4: Verify with AWS CLI
    click.echo(f"\n4️⃣  Verifying with AWS CLI...")
    _verify_aws_resources(peer_name, region, profile)

    click.echo(f"\n{'='*80}")
    click.secho(f"✅ PEER DEPLOYMENT COMPLETE: {peer_name.upper()}", fg='green')
    click.echo("=" * 80)


def _wait_for_vpn_available(peer_config, region, profile, max_wait=180):
    """Wait for VPN to be available."""
    session = boto3.Session(profile_name=profile, region_name=region)
    ec2 = session.client("ec2")

    peer_name = peer_config["name"].lower().replace(" ", "-")
    vpn_name = f"vpn-{peer_name}-vpn"

    click.echo(f"  ⏳ Waiting for VPN to become available (max {max_wait}s)...")
    start_time = time.time()
    last_log = 0

    while time.time() - start_time < max_wait:
        response = ec2.describe_vpn_connections(
            Filters=[{"Name": "tag:Name", "Values": [vpn_name]}]
        )

        if response["VpnConnections"]:
            vpn = response["VpnConnections"][0]
            if vpn["State"] == "available":
                click.echo(f"  ✓ VPN is available: {vpn['VpnConnectionId']}")
                return

        elapsed = time.time() - start_time
        if elapsed - last_log >= 30:  # Log every 30 seconds
            click.echo(f"    Still waiting... ({int(elapsed)}s)")
            last_log = elapsed

        time.sleep(2)

    click.secho(f"  ⚠️  VPN still not available after {max_wait}s, but continuing...", fg='yellow')


def _ensure_vpn_exists(peer_config, region, profile):
    """Create VPN if it doesn't exist."""
    session = boto3.Session(profile_name=profile, region_name=region)
    ec2 = session.client("ec2")

    peer_name = peer_config["name"].lower().replace(" ", "-")
    vpn_name = f"vpn-{peer_name}-vpn"

    # Check if VPN exists (and is not deleted)
    response = ec2.describe_vpn_connections(
        Filters=[{"Name": "tag:Name", "Values": [vpn_name]}]
    )

    if response["VpnConnections"]:
        vpn = response["VpnConnections"][0]
        # Only use VPN if it's not deleted/deleting
        if vpn["State"] not in ["deleted", "deleting"]:
            click.echo(f"  ✓ VPN already exists: {vpn['VpnConnectionId']} ({vpn['State']})")
            return
        else:
            click.echo(f"  ℹ️  Found {vpn['State']} VPN, creating new one...")

    # Get TGW ID
    tgw_response = ec2.describe_transit_gateways(
        Filters=[
            {"Name": "tag:Name", "Values": ["vpn-hub-tgw"]},
            {"Name": "state", "Values": ["available"]}
        ]
    )

    if not tgw_response["TransitGateways"]:
        click.secho(f"  ❌ Transit Gateway not found", fg='red')
        return

    tgw_id = tgw_response["TransitGateways"][0]["TransitGatewayId"]

    # Create Customer Gateway
    click.echo(f"  ⏳ Creating Customer Gateway...")
    cgw_response = ec2.create_customer_gateway(
        Type="ipsec.1",
        PublicIp=peer_config["public_ip"],
        BgpAsn=peer_config.get("bgp_asn", 65000),
        TagSpecifications=[
            {
                "ResourceType": "customer-gateway",
                "Tags": [
                    {"Key": "Name", "Value": f"vpn-{peer_name}-cgw"},
                    {"Key": "Peer", "Value": peer_name},
                ]
            }
        ]
    )
    cgw_id = cgw_response["CustomerGateway"]["CustomerGatewayId"]
    click.echo(f"  ✓ Customer Gateway created: {cgw_id}")

    # Create VPN Connection
    click.echo(f"  ⏳ Creating VPN Connection...")
    vpn_response = ec2.create_vpn_connection(
        Type="ipsec.1",
        CustomerGatewayId=cgw_id,
        TransitGatewayId=tgw_id,
        Options={"StaticRoutesOnly": False},
        TagSpecifications=[
            {
                "ResourceType": "vpn-connection",
                "Tags": [
                    {"Key": "Name", "Value": vpn_name},
                    {"Key": "Peer", "Value": peer_name},
                ]
            }
        ]
    )
    vpn_id = vpn_response["VpnConnection"]["VpnConnectionId"]
    click.echo(f"  ✓ VPN Connection created: {vpn_id}")

    # Wait for VPN to be available
    click.echo(f"  ⏳ Waiting for VPN to reach available state...")
    max_retries = 60
    retry_count = 0
    while retry_count < max_retries:
        vpn_check = ec2.describe_vpn_connections(VpnConnectionIds=[vpn_id])
        state = vpn_check["VpnConnections"][0]["State"]
        if state == "available":
            click.echo(f"  ✓ VPN is now available")
            return
        retry_count += 1
        time.sleep(1)

    click.secho(f"  ⚠️  VPN still pending after {max_retries}s", fg='yellow')


def _deploy_peer_stack(peer_name, region, profile):
    """Deploy peer Pulumi stack."""
    stack_dir = Path(__file__).parent.parent.parent / "pulumi" / "stacks" / f"peer-{peer_name}"

    try:
        # Select stack
        subprocess.run(
            ["pulumi", "stack", "select", f"peer-{peer_name}"],
            cwd=stack_dir,
            capture_output=True,
            check=True
        )

        # Run pulumi up
        result = subprocess.run(
            ["pulumi", "up", "--yes", "--skip-preview"],
            cwd=stack_dir,
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            click.echo(f"  ✓ Pulumi deployment successful")
        else:
            click.secho(f"  ❌ Pulumi deployment failed:", fg='red')
            click.echo(result.stdout)
            click.echo(result.stderr)
    except Exception as e:
        click.secho(f"  ❌ Error deploying stack: {e}", fg='red')


def _verify_pulumi_stack(peer_name):
    """Verify peer stack with Pulumi CLI."""
    stack_dir = Path(__file__).parent.parent.parent / "pulumi" / "stacks" / f"peer-{peer_name}"

    try:
        # Get stack outputs
        result = subprocess.run(
            ["pulumi", "stack", "output", "--json"],
            cwd=stack_dir,
            capture_output=True,
            text=True,
            check=True
        )

        outputs = json.loads(result.stdout)

        click.echo(f"  ✓ Pulumi Stack Outputs:")
        click.echo(f"    • peer_name: {outputs.get('peer_name', 'N/A')}")
        click.echo(f"    • vpn_connection_id: {outputs.get('vpn_connection_id', 'N/A')}")
        click.echo(f"    • transit_gateway_id: {outputs.get('transit_gateway_id', 'N/A')}")
        click.echo(f"    • tgw_routes_count: {outputs.get('tgw_routes_count', 0)}")
        click.echo(f"    • vpc_routes_count: {outputs.get('vpc_routes_count', 0)}")

    except Exception as e:
        click.secho(f"  ❌ Error verifying stack: {e}", fg='red')


def _verify_aws_resources(peer_name, region, profile):
    """Verify AWS resources with boto3."""
    session = boto3.Session(profile_name=profile, region_name=region)
    ec2 = session.client("ec2")

    peer_name_normalized = peer_name.lower().replace(" ", "-")

    # Check VPN
    vpn_response = ec2.describe_vpn_connections(
        Filters=[{"Name": "tag:Peer", "Values": [peer_name_normalized]}]
    )

    if vpn_response["VpnConnections"]:
        vpn = vpn_response["VpnConnections"][0]
        click.echo(f"  ✓ VPN Connection verified:")
        click.echo(f"    • ID: {vpn['VpnConnectionId']}")
        click.echo(f"    • State: {vpn['State']}")

        # Get tunnel IPs
        telemetry = vpn.get("VgwTelemetry", [])
        if telemetry:
            click.echo(f"    • Tunnel 1 IP: {telemetry[0].get('OutsideIpAddress', 'N/A')} ({telemetry[0].get('Status', 'UNKNOWN')})")
        if len(telemetry) > 1:
            click.echo(f"    • Tunnel 2 IP: {telemetry[1].get('OutsideIpAddress', 'N/A')} ({telemetry[1].get('Status', 'UNKNOWN')})")
    else:
        click.secho(f"  ❌ VPN not found in AWS", fg='red')
        return

    # Check TGW routes
    tgw_response = ec2.describe_transit_gateways(
        Filters=[
            {"Name": "tag:Name", "Values": ["vpn-hub-tgw"]},
            {"Name": "state", "Values": ["available"]}
        ]
    )

    if tgw_response["TransitGateways"]:
        tgw_id = tgw_response["TransitGateways"][0]["TransitGatewayId"]

        rt_response = ec2.describe_transit_gateway_route_tables(
            Filters=[
                {"Name": "transit-gateway-id", "Values": [tgw_id]},
                {"Name": "state", "Values": ["available"]}
            ]
        )

        if rt_response["TransitGatewayRouteTables"]:
            rt_id = rt_response["TransitGatewayRouteTables"][0]["TransitGatewayRouteTableId"]

            routes_response = ec2.search_transit_gateway_routes(
                TransitGatewayRouteTableId=rt_id,
                Filters=[{"Name": "state", "Values": ["active", "blackhole"]}]
            )

            peer_routes = [r for r in routes_response.get("Routes", []) if "DestinationCidrBlock" in r]
            click.echo(f"  ✓ TGW Routes verified:")
            click.echo(f"    • Total routes: {len(peer_routes)}")
            for route in peer_routes[:5]:  # Show first 5
                state = route.get("State", "unknown")
                cidr = route.get("DestinationCidrBlock")
                click.echo(f"      - {cidr}: {state}")


@peer.group()
def test_config():
    """Manage test endpoints for VPN tunnel health checks."""
    pass


@test_config.command('add')
@click.argument('peer_name')
@click.argument('target')
@click.argument('protocol')
@click.option('--port', type=int, default=None, help='Target port (required for http/https/tcp)')
def add_test_endpoint(peer_name, target, protocol, port):
    """Add a test endpoint to a peer."""
    try:
        spec_mgr = PeerSpecManager()
        endpoints = spec_mgr.add_test_endpoint(peer_name, target, protocol, port)

        click.secho(f"✅ Test endpoint added to {peer_name}", fg='green')
        click.echo(f"\n📋 Updated test endpoints:")
        for ep in endpoints:
            click.echo(f"  • {ep}")

    except DomainValidationError as e:
        click.secho(f"❌ Error: {e}", fg='red')


@test_config.command('remove')
@click.argument('peer_name')
@click.argument('target')
def remove_test_endpoint(peer_name, target):
    """Remove a test endpoint from a peer."""
    try:
        spec_mgr = PeerSpecManager()
        endpoints = spec_mgr.remove_test_endpoint(peer_name, target)

        click.secho(f"✅ Test endpoint removed from {peer_name}", fg='green')
        if endpoints:
            click.echo(f"\n📋 Remaining test endpoints:")
            for ep in endpoints:
                click.echo(f"  • {ep}")
        else:
            click.echo(f"\n📋 No test endpoints configured")

    except DomainValidationError as e:
        click.secho(f"❌ Error: {e}", fg='red')


@test_config.command('list')
@click.argument('peer_name')
def list_test_endpoints(peer_name):
    """List all test endpoints for a peer."""
    try:
        spec_mgr = PeerSpecManager()
        endpoints = spec_mgr.list_test_endpoints(peer_name)

        if not endpoints:
            click.echo(f"No test endpoints configured for {peer_name}")
            return

        click.echo(f"📋 Test endpoints for {peer_name}:")
        for ep in endpoints:
            click.echo(f"  • {ep}")

    except DomainValidationError as e:
        click.secho(f"❌ Error: {e}", fg='red')
