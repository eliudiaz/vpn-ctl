"""
Peer Stack: Vimenca (Checkpoint R80.10)

INDEPENDENT peer stack that creates:
- Transit Gateway routes (to Vimenca destination CIDRs)
- VPC routes (EKS cluster routes to Vimenca)

DOES NOT create:
- VPN Connection (managed by vpnctl via config/vpn-peers.yaml)
- Customer Gateway (managed by vpnctl)

VPN Connection is created/managed by vpnctl and referenced here.
This stack is completely independent and can be deployed/destroyed separately.
"""

import pulumi
import pulumi_aws as aws
import boto3
import os
import yaml
from typing import List, Dict

# AWS config
aws_config = pulumi.Config("aws")
region = aws_config.get("region") or "us-east-2"
aws_profile = aws_config.get("profile") or os.environ.get("AWS_PROFILE", "default")

# Get AWS session
session = boto3.Session(profile_name=aws_profile, region_name=region)
ec2_client = session.client("ec2")

# Project config
pulumi_config = pulumi.Config()
environment = pulumi_config.get("environment") or "dev"

# Detect peer name from Pulumi stack name (e.g., "peer-vimenca" → "vimenca")
stack_name = pulumi.get_stack()
if stack_name.startswith("peer-"):
    peer_name = stack_name.replace("peer-", "")
else:
    raise Exception(f"Invalid stack name: {stack_name}. Must be 'peer-<name>'")

print(f"\n🚀 Deploying PEER STACK: {peer_name.upper()}")
print(f"   Stack: {stack_name}")
print(f"   Region: {region}, Environment: {environment}")

# =============================================================================
# LOAD PEER CONFIGURATION FROM VPNCTL
# =============================================================================

def load_peer_config(peer_name: str) -> Dict:
    """Load peer config from vpnctl config file."""
    config_path = "../../../config/vpn-peers.yaml"
    
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Find peer in config
        for peer in config.get("peers", []):
            if peer["name"].lower() == peer_name.lower():
                return peer
        
        raise Exception(f"Peer {peer_name} not found in config")
    except Exception as e:
        print(f"⚠ Error loading peer config: {e}")
        return {}

# Load Vimenca config
peer_config = load_peer_config(peer_name)
if not peer_config:
    raise Exception(f"Could not load config for {peer_name}")

destination_cidrs = peer_config.get("destination_cidrs", [])
public_ip = peer_config.get("public_ip", "")

print(f"✓ Loaded peer config: {peer_name}")
print(f"  Public IP: {public_ip}")
print(f"  Destination CIDRs: {destination_cidrs}")

# =============================================================================
# GET TGW REFERENCE (from core stack)
# =============================================================================

# For now, we'll query AWS to find the TGW
# In production, you could use stack references
def get_tgw_id() -> str:
    """Get Transit Gateway ID from AWS tags."""
    try:
        response = ec2_client.describe_transit_gateways(
            Filters=[
                {"Name": "tag:Name", "Values": ["vpn-hub-tgw"]},
                {"Name": "state", "Values": ["available"]}
            ]
        )
        
        if response["TransitGateways"]:
            return response["TransitGateways"][0]["TransitGatewayId"]
        
        raise Exception("TGW not found - run core stack first")
    except Exception as e:
        print(f"❌ Could not find TGW: {e}")
        raise

def get_tgw_route_table_id(tgw_id: str) -> str:
    """Get TGW route table ID."""
    try:
        response = ec2_client.describe_transit_gateway_route_tables(
            Filters=[
                {"Name": "transit-gateway-id", "Values": [tgw_id]},
                {"Name": "state", "Values": ["available"]}
            ]
        )
        
        if response["TransitGatewayRouteTables"]:
            return response["TransitGatewayRouteTables"][0]["TransitGatewayRouteTableId"]
        
        raise Exception("TGW route table not found")
    except Exception as e:
        print(f"❌ Could not find TGW route table: {e}")
        raise

# Get TGW info
tgw_id = get_tgw_id()
tgw_rt_id = get_tgw_route_table_id(tgw_id)
print(f"✓ Found TGW: {tgw_id}")

# =============================================================================
# GET VPN CONNECTION (managed by vpnctl)
# =============================================================================

def get_vpn_connection_id(peer_name: str) -> str:
    """Get VPN Connection ID from AWS (created by vpnctl)."""
    vpn_name = f"vpn-{peer_name.lower()}-vpn"
    
    try:
        response = ec2_client.describe_vpn_connections(
            Filters=[
                {"Name": "tag:Name", "Values": [vpn_name]},
                {"Name": "state", "Values": ["available"]}
            ]
        )
        
        if response["VpnConnections"]:
            return response["VpnConnections"][0]["VpnConnectionId"]
        
        raise Exception(f"VPN not found - create via vpnctl first")
    except Exception as e:
        print(f"❌ VPN not found (must be created by vpnctl): {e}")
        raise

# Get VPN ID
vpn_id = get_vpn_connection_id(peer_name)
print(f"✓ Found VPN Connection: {vpn_id}")
print(f"  Note: VPN is managed by vpnctl, not by this stack")

# Get TGW Attachment ID for this VPN
def get_vpn_tgw_attachment_id(vpn_id: str) -> str:
    """Get Transit Gateway attachment ID for VPN connection."""
    try:
        response = ec2_client.describe_transit_gateway_attachments(
            Filters=[
                {"Name": "resource-id", "Values": [vpn_id]},
                {"Name": "resource-type", "Values": ["vpn"]},
            ]
        )

        if response["TransitGatewayAttachments"]:
            return response["TransitGatewayAttachments"][0]["TransitGatewayAttachmentId"]

        raise Exception(f"TGW attachment not found for VPN {vpn_id}")
    except Exception as e:
        print(f"❌ Could not find TGW attachment: {e}")
        raise

vpn_attachment_id = get_vpn_tgw_attachment_id(vpn_id)
print(f"✓ Found TGW Attachment: {vpn_attachment_id}")

# =============================================================================
# CREATE TGW ROUTES (peer-specific)
# =============================================================================

print(f"\n📍 Creating Transit Gateway routes for {peer_name}...")

tgw_routes = []
for cidr in destination_cidrs:
    route_name = f"tgw-route-{peer_name}-{cidr.replace('/', '-')}"

    # Create TGW route (use TGW attachment ID, not VPN ID)
    route = aws.ec2transitgateway.Route(
        route_name,
        transit_gateway_route_table_id=tgw_rt_id,
        destination_cidr_block=cidr,
        transit_gateway_attachment_id=vpn_attachment_id,
    )

    tgw_routes.append(route)
    print(f"  ✓ TGW Route: {cidr} → {peer_name}")

# =============================================================================
# CREATE VPC ROUTES (EKS cluster routes to peer)
# =============================================================================

print(f"\n🛣️  Creating VPC routes for {peer_name}...")

def get_eks_route_table_ids(cluster_name: str) -> List[str]:
    """Get route table IDs for EKS cluster."""
    try:
        # Get EKS cluster info
        eks = session.client("eks")
        cluster = eks.describe_cluster(name=cluster_name)["cluster"]
        vpc_id = cluster["resourcesVpcConfig"]["vpcId"]
        
        # Get route tables
        response = ec2_client.describe_route_tables(
            Filters=[
                {"Name": "vpc-id", "Values": [vpc_id]},
                {"Name": "tag:Name", "Values": [f"{cluster_name}-*"]},
            ]
        )
        
        return [rt["RouteTableId"] for rt in response["RouteTables"]]
    except Exception as e:
        print(f"⚠ Could not get route tables for {cluster_name}: {e}")
        return []

# Create VPC routes for each destination CIDR
eks_clusters = ["asg-plat-dev"]  # Add more as needed
vpc_routes = []

for cluster_name in eks_clusters:
    route_table_ids = get_eks_route_table_ids(cluster_name)
    
    for rt_id in route_table_ids:
        for cidr in destination_cidrs:
            route_name = f"vpc-route-{peer_name}-{rt_id[-8:]}-{cidr.replace('/', '-')}"
            
            # Create VPC route pointing to TGW
            route = aws.ec2.Route(
                route_name,
                route_table_id=rt_id,
                destination_cidr_block=cidr,
                transit_gateway_id=tgw_id,
                tags={
                    "Name": f"default-vpc-route-{peer_name}-{cidr}",
                    "Peer": peer_name,
                    "Cluster": cluster_name,
                }
            )
            
            vpc_routes.append(route)
            print(f"  ✓ Route: {cidr} → TGW (EKS: {cluster_name})")

# =============================================================================
# OUTPUTS
# =============================================================================

pulumi.export("peer_name", peer_name)
pulumi.export("vpn_connection_id", vpn_id)
pulumi.export("vpn_attachment_id", vpn_attachment_id)
pulumi.export("transit_gateway_id", tgw_id)
pulumi.export("destination_cidrs", destination_cidrs)
pulumi.export("tgw_routes_count", len(tgw_routes))
pulumi.export("vpc_routes_count", len(vpc_routes))

print(f"\n✅ Peer stack deployment complete")
print(f"   TGW Routes: {len(tgw_routes)}")
print(f"   VPC Routes: {len(vpc_routes)}")
print(f"   VPN Connection: {vpn_id} (managed by vpnctl)")
