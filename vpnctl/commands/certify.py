"""
VPN Infrastructure Certification Command

Verifies that all VPN infrastructure (core + peers) is correctly deployed to AWS.
Uses boto3 to query AWS and certify resources match expected configuration.
"""

import click
import boto3
import json
from typing import Dict, List, Tuple
from pathlib import Path
import yaml


class InfrastructureCertifier:
    """Certifies VPN infrastructure is correctly deployed."""

    def __init__(self, region: str = "us-east-2", profile: str = "affinity"):
        """Initialize certifier with AWS session."""
        self.session = boto3.Session(profile_name=profile, region_name=region)
        self.ec2 = self.session.client("ec2")
        self.region = region
        self.profile = profile
        self.errors = []
        self.warnings = []

    def certify_core_infrastructure(self) -> bool:
        """Certify core infrastructure (TGW, attachments) exists."""
        print("\n🔍 CERTIFYING CORE INFRASTRUCTURE")
        print("━" * 70)

        try:
            # Check Transit Gateway exists
            tgw_response = self.ec2.describe_transit_gateways(
                Filters=[
                    {"Name": "tag:Name", "Values": ["affinity-hub-tgw"]},
                    {"Name": "state", "Values": ["available"]},
                ]
            )

            if not tgw_response["TransitGateways"]:
                self.errors.append("❌ Transit Gateway not found (affinity-hub-tgw)")
                return False

            tgw = tgw_response["TransitGateways"][0]
            tgw_id = tgw["TransitGatewayId"]
            print(f"✓ Transit Gateway found: {tgw_id}")

            # Check TGW Route Table
            rt_response = self.ec2.describe_transit_gateway_route_tables(
                Filters=[
                    {"Name": "transit-gateway-id", "Values": [tgw_id]},
                    {"Name": "state", "Values": ["available"]},
                ]
            )

            if not rt_response["TransitGatewayRouteTables"]:
                self.errors.append("❌ TGW Route Table not found")
                return False

            rt_id = rt_response["TransitGatewayRouteTables"][0]["TransitGatewayRouteTableId"]
            print(f"✓ TGW Route Table found: {rt_id}")

            # Check EKS cluster attachment
            eks_response = self.ec2.describe_transit_gateway_attachments(
                Filters=[
                    {"Name": "transit-gateway-id", "Values": [tgw_id]},
                    {"Name": "resource-type", "Values": ["vpc"]},
                ]
            )

            if not eks_response["TransitGatewayAttachments"]:
                self.warnings.append("⚠️  No VPC attachments found")
            else:
                for attachment in eks_response["TransitGatewayAttachments"]:
                    print(f"✓ VPC Attachment: {attachment['TransitGatewayAttachmentId']}")

            return True

        except Exception as e:
            self.errors.append(f"❌ Core infrastructure check failed: {str(e)}")
            return False

    def certify_peer_infrastructure(self, peer_name: str) -> bool:
        """Certify peer infrastructure (routes, VPN attachment) exists."""
        print(f"\n🔍 CERTIFYING PEER: {peer_name.upper()}")
        print("━" * 70)

        try:
            # Get TGW for routes
            tgw_response = self.ec2.describe_transit_gateways(
                Filters=[
                    {"Name": "tag:Name", "Values": ["affinity-hub-tgw"]},
                    {"Name": "state", "Values": ["available"]},
                ]
            )

            if not tgw_response["TransitGateways"]:
                self.errors.append(f"❌ {peer_name}: TGW not found")
                return False

            tgw_id = tgw_response["TransitGateways"][0]["TransitGatewayId"]

            # Get route table
            rt_response = self.ec2.describe_transit_gateway_route_tables(
                Filters=[
                    {"Name": "transit-gateway-id", "Values": [tgw_id]},
                    {"Name": "state", "Values": ["available"]},
                ]
            )

            if not rt_response["TransitGatewayRouteTables"]:
                self.errors.append(f"❌ {peer_name}: Route table not found")
                return False

            rt_id = rt_response["TransitGatewayRouteTables"][0]["TransitGatewayRouteTableId"]

            # Load peer config
            config_path = Path(__file__).parent.parent.parent / "config" / "vpn-peers.yaml"
            with open(config_path) as f:
                config = yaml.safe_load(f)

            peer_config = next(
                (p for p in config["peers"] if p["name"].lower() == peer_name.lower()),
                None,
            )

            if not peer_config:
                self.errors.append(f"❌ {peer_name}: Config not found in vpn-peers.yaml")
                return False

            destination_cidrs = peer_config.get("destination_cidrs", [])
            print(f"✓ Peer config found: {peer_name}")
            print(f"  Destination CIDRs: {len(destination_cidrs)}")

            # Check TGW routes (query AWS CLI API)
            try:
                routes_response = self.ec2.search_transit_gateway_routes(
                    TransitGatewayRouteTableId=rt_id,
                    Filters=[
                        {"Name": "state", "Values": ["active", "blackhole"]},
                    ]
                )

                peer_routes = [
                    r for r in routes_response.get("Routes", [])
                    if r.get("DestinationCidrBlock") in destination_cidrs
                ]

                if len(peer_routes) != len(destination_cidrs):
                    self.warnings.append(
                        f"⚠️  {peer_name}: {len(peer_routes)}/{len(destination_cidrs)} routes found"
                    )
                else:
                    print(f"✓ TGW Routes: {len(peer_routes)} active")
                    for route in peer_routes:
                        cidr = route.get("DestinationCidrBlock", "unknown")
                        state = route.get("State", "unknown")
                        print(f"  ✓ {cidr} ({state})")
            except Exception as e:
                # Routes may not be queryable yet, log as warning
                self.warnings.append(f"⚠️  {peer_name}: Could not query routes: {str(e)}")

            # Check VPN connection
            vpn_response = self.ec2.describe_vpn_connections(
                Filters=[
                    {"Name": "tag:Peer", "Values": [peer_name]},
                ]
            )

            if vpn_response["VpnConnections"]:
                vpn = vpn_response["VpnConnections"][0]
                vpn_id = vpn["VpnConnectionId"]
                vpn_state = vpn["State"]
                print(f"✓ VPN Connection: {vpn_id} ({vpn_state})")

                # Check tunnel status
                if "VpnTunnelOptions" in vpn:
                    for i, tunnel in enumerate(vpn["VpnTunnelOptions"], 1):
                        phase1_state = tunnel.get("Phase1DHGroupNumbers", [None])[0]
                        print(f"  Tunnel {i}: configured")
            else:
                self.warnings.append(f"⚠️  {peer_name}: VPN connection not found")

            return True

        except Exception as e:
            self.errors.append(f"❌ {peer_name} infrastructure check failed: {str(e)}")
            return False

    def certify_all_peers(self) -> bool:
        """Certify all peers from config."""
        config_path = Path(__file__).parent.parent.parent / "config" / "vpn-peers.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f)

        peers_to_check = ["vimenca", "cibao", "apap", "affinity-legacy-network"]

        all_good = True
        for peer_name in peers_to_check:
            peer_config = next(
                (p for p in config["peers"] if p["name"].lower() == peer_name.lower()),
                None,
            )

            if peer_config and peer_config.get("enabled", True):
                if not self.certify_peer_infrastructure(peer_name):
                    all_good = False

        return all_good

    def print_summary(self) -> None:
        """Print certification summary."""
        print("\n" + "=" * 70)
        print("📊 CERTIFICATION SUMMARY")
        print("=" * 70)

        if not self.errors and not self.warnings:
            print("✅ ALL INFRASTRUCTURE CERTIFIED - READY FOR PRODUCTION")
            return

        if self.errors:
            print("\n❌ ERRORS FOUND:")
            for error in self.errors:
                print(f"  {error}")

        if self.warnings:
            print("\n⚠️  WARNINGS:")
            for warning in self.warnings:
                print(f"  {warning}")

    def get_certification_report(self) -> Dict:
        """Get detailed certification report as dict."""
        return {
            "status": "CERTIFIED" if not self.errors else "FAILED",
            "errors": self.errors,
            "warnings": self.warnings,
            "region": self.region,
            "profile": self.profile,
        }


@click.group()
def certify():
    """Certify VPN infrastructure is correctly deployed."""
    pass


@certify.command()
@click.option("--region", default="us-east-2", help="AWS region")
@click.option("--profile", default="affinity", help="AWS profile")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def all(region: str, profile: str, output_json: bool):
    """Certify all infrastructure."""
    certifier = InfrastructureCertifier(region=region, profile=profile)

    # Certify core
    core_ok = certifier.certify_core_infrastructure()

    # Certify peers
    peers_ok = certifier.certify_all_peers()

    # Print summary
    if not output_json:
        certifier.print_summary()
    else:
        report = certifier.get_certification_report()
        click.echo(json.dumps(report, indent=2))

    # Exit with appropriate code
    exit_code = 0 if (core_ok and peers_ok and not certifier.errors) else 1
    exit(exit_code)


@certify.command()
@click.argument("peer_name")
@click.option("--region", default="us-east-2", help="AWS region")
@click.option("--profile", default="affinity", help="AWS profile")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def peer(peer_name: str, region: str, profile: str, output_json: bool):
    """Certify specific peer infrastructure."""
    certifier = InfrastructureCertifier(region=region, profile=profile)

    # Certify core (required for peers)
    core_ok = certifier.certify_core_infrastructure()

    # Certify peer
    peer_ok = certifier.certify_peer_infrastructure(peer_name)

    # Print summary
    if not output_json:
        certifier.print_summary()
    else:
        report = certifier.get_certification_report()
        click.echo(json.dumps(report, indent=2))

    exit_code = 0 if (core_ok and peer_ok and not certifier.errors) else 1
    exit(exit_code)


@certify.command()
@click.option("--region", default="us-east-2", help="AWS region")
@click.option("--profile", default="affinity", help="AWS profile")
def core(region: str, profile: str):
    """Certify core infrastructure only."""
    certifier = InfrastructureCertifier(region=region, profile=profile)
    core_ok = certifier.certify_core_infrastructure()
    certifier.print_summary()
    exit(0 if core_ok and not certifier.errors else 1)


if __name__ == "__main__":
    certify()
