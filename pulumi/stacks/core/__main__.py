"""
Core Infrastructure Stack - Shared VPN Hub

Creates ONLY shared infrastructure:
- Transit Gateway Hub (central VPN hub)
- EKS cluster attachments to TGW
- Shared TGW route table

DOES NOT create:
- Customer Gateways (managed by vpnctl)
- VPN Connections (managed by vpnctl)  
- Peer-specific resources (managed in peer stacks)

Each peer stack independently:
- Defines its own routes to TGW
- Defines its own VPC routes
- References the TGW hub created here
"""

import sys
from pathlib import Path
import pulumi
import pulumi_aws as aws
import boto3
import os
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# AWS config
aws_config = pulumi.Config("aws")
region = aws_config.get("region") or "us-east-2"
aws_profile = aws_config.get("profile") or os.environ.get("AWS_PROFILE", "default")

# Get AWS session
session = boto3.Session(profile_name=aws_profile, region_name=region)
ec2_client = session.client("ec2")
eks_client = session.client("eks")

# Project config
pulumi_config = pulumi.Config()
environment = pulumi_config.get("environment") or "dev"

print(f"🚀 Deploying CORE stack (shared TGW infrastructure)")
print(f"   Region: {region}, Environment: {environment}")

# =============================================================================
# TRANSIT GATEWAY HUB (CORE - SHARED)
# =============================================================================

print("\n📡 Creating Transit Gateway Hub...")

tgw = aws.ec2transitgateway.TransitGateway(
    "vpn-hub-tgw",
    description="Central VPN hub for multi-cluster connectivity",
    default_route_table_association="disable",
    default_route_table_propagation="disable",
    tags={
        "Name": "vpn-hub-tgw",
        "Environment": environment,
        "ManagedBy": "Pulumi",
        "Component": "CoreTransitGateway",
    }
)

# Create TGW route table
tgw_route_table = aws.ec2transitgateway.RouteTable(
    "vpn-hub-tgw-rt",
    transit_gateway_id=tgw.id,
    tags={
        "Name": "vpn-hub-tgw-rt",
        "Environment": environment,
    }
)

print("✓ Transit Gateway Hub created")

# =============================================================================
# EKS CLUSTER ATTACHMENTS
# =============================================================================

def attach_eks_cluster(cluster_name: str):
    """Attach EKS cluster VPC to TGW."""
    try:
        print(f"\n🔗 Attaching EKS cluster: {cluster_name}")

        # Get cluster info
        cluster = eks_client.describe_cluster(name=cluster_name)["cluster"]
        vpc_id = cluster["resourcesVpcConfig"]["vpcId"]
        subnet_ids = cluster["resourcesVpcConfig"]["subnetIds"]

        # Attach VPC to TGW
        attachment = aws.ec2transitgateway.VpcAttachment(
            f"tgw-attach-{cluster_name}",
            transit_gateway_id=tgw.id,
            vpc_id=vpc_id,
            subnet_ids=subnet_ids,
            tags={
                "Name": f"default-tgw-attach-{cluster_name}",
                "ClusterName": cluster_name,
                "ManagedBy": "Pulumi",
            }
        )

        print(f"✓ Cluster attached: {cluster_name}")
        return attachment

    except Exception as e:
        print(f"⚠ Could not attach {cluster_name}: {e}")
        return None

# Attach clusters
clusters = ["asg-plat-dev"]  # Add more as needed
for cluster_name in clusters:
    attach_eks_cluster(cluster_name)

# =============================================================================
# OUTPUTS (for peer stacks to reference)
# =============================================================================

pulumi.export("transit_gateway_id", tgw.id)
pulumi.export("transit_gateway_route_table_id", tgw_route_table.id)
pulumi.export("environment", environment)

print("\n✅ Core infrastructure ready")
print(f"   TGW ID: {tgw.id}")
print(f"   Route Table: {tgw_route_table.id}")
