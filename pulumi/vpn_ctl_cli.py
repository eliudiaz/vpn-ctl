#!/usr/bin/env python3
"""
vpn-ctl: VPN Infrastructure Control Tool

K8s-style declarative infrastructure management wrapping Pulumi/Terraform/CloudFormation.
All operations through spec files - NEVER direct IaC commands.
"""

import sys
import argparse
from pathlib import Path
from typing import Dict, List, Any
import json
import subprocess
import os

# Add paths for imports
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vpnctl"))

from vpn_manifest_loader import VpnManifestLoader, VpnConfigLoader
from stack_orchestrator import CoreStackOrchestrator, PeerStackOrchestrator

try:
    from spec_runner import SpecRunner
except ImportError:
    SpecRunner = None


# =============================================================================
# SPEC-BASED HANDLERS (Primary interface)
# =============================================================================

def handle_apply(args):
    """Handle spec apply command (deploy infrastructure)."""
    try:
        if not SpecRunner:
            raise ImportError("spec_runner module not found")

        runner = SpecRunner(str(Path(__file__).parent.parent))

        if args.spec_file:
            print(f"📋 Applying spec: {args.spec_file}")
            runner.apply(args.spec_file, dry_run=args.dry_run)
        elif args.spec_dir:
            print(f"📋 Applying all specs in: {args.spec_dir}")
            spec_dir = Path(args.spec_dir)
            for spec_file in sorted(spec_dir.glob("*.yaml")):
                runner.apply(str(spec_file), dry_run=args.dry_run)
        else:
            print("❌ Error: Either --spec-file or --spec-dir required")
            sys.exit(1)

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


def handle_destroy(args):
    """Handle spec destroy command (destroy infrastructure)."""
    try:
        if not SpecRunner:
            raise ImportError("spec_runner module not found")

        runner = SpecRunner(str(Path(__file__).parent.parent))

        if not args.dry_run:
            response = input(f"\n⚠️  Destroy {args.spec_file}? (type 'DESTROY' to confirm): ")
            if response != "DESTROY":
                print("Destruction cancelled.")
                return

        runner.destroy(args.spec_file, dry_run=args.dry_run)

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


def handle_status(args):
    """Handle spec status command (check deployment status)."""
    try:
        if not SpecRunner:
            raise ImportError("spec_runner module not found")

        runner = SpecRunner(str(Path(__file__).parent.parent))
        status = runner.status(args.spec_file)

        print(f"\n📊 Status: {status['name']}")
        print(f"   Kind: {status['kind']}")
        print(f"   Provider: {status['provider']}")
        print(f"   Phase: {status['phase']}")
        if status['lastUpdate']:
            print(f"   Last Update: {status['lastUpdate']}")
        if status['message']:
            print(f"   Message: {status['message']}")

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


# =============================================================================
# LEGACY HANDLERS (Deprecated - use spec-based commands instead)
# =============================================================================

class VpnCtlPreviewService:
    """Generate dry-run preview of infrastructure changes."""

    def __init__(self, config_dir: str = "../config"):
        self.config_loader = VpnConfigLoader(config_dir)

    def preview_peer_deployment(self, peer_name: str) -> Dict[str, Any]:
        """
        Preview what infrastructure would be created for a peer deployment.

        Returns structure similar to Pulumi preview output.
        """
        # Load peer config
        peer_config = self.config_loader.load_peer(peer_name)
        if not peer_config:
            raise ValueError(f"Peer not found: {peer_name}")

        # Determine what resources would be created
        resources_to_create = self._plan_resources(peer_name, peer_config)

        return {
            "peer_name": peer_name,
            "stack": f"peer-{peer_name}",
            "preview_type": "peer_isolated",
            "resources": resources_to_create,
            "summary": self._generate_summary(resources_to_create),
        }

    def _plan_resources(self, peer_name: str, peer_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Plan what AWS resources would be created/modified."""
        resources = []
        # Note: peer_config is already flattened by extract_vpn_config, not nested
        public_ip = peer_config.get("public_ip")
        bgp_asn = peer_config.get("bgp_asn")
        destination_cidrs = peer_config.get("destination_cidrs", [])
        snat_enabled = peer_config.get("snat_enabled", False)

        # 1. Customer Gateway
        resources.append({
            "type": "aws:ec2/customerGateway:CustomerGateway",
            "name": f"affinity-{peer_name}-cgw",
            "operation": "create",
            "properties": {
                "bgpAsn": bgp_asn,
                "publicIp": public_ip,
                "type": "ipsec.1",
                "tags": {"Name": f"affinity-{peer_name}-cgw"},
            },
        })

        # 2. VPN Connection
        resources.append({
            "type": "aws:ec2/vpnConnection:VpnConnection",
            "name": f"affinity-{peer_name}-vpn",
            "operation": "create",
            "properties": {
                "customerGatewayId": "${aws_customer_gateway.affinity-" + peer_name + "-cgw.id}",
                "transitGatewayId": "${data.aws_ec2_transit_gateway.existing.id}",
                "type": "ipsec.1",
                "staticRoutesOnly": True,
                "tags": {"Name": f"affinity-{peer_name}-vpn"},
            },
        })

        # 3. Transit Gateway Routes (one per destination CIDR)
        for i, cidr in enumerate(destination_cidrs, 1):
            resources.append({
                "type": "aws:ec2transitgateway/route:Route",
                "name": f"affinity-{peer_name}-tgw-route-{i}",
                "operation": "create",
                "properties": {
                    "destinationCidrBlock": cidr,
                    "transitGatewayAttachmentId": "${aws_ec2_transit_gateway_vpc_attachment.vpn.id}",
                    "transitGatewayRouteTableId": "${data.aws_ec2_transit_gateway_route_table.vpn.id}",
                },
            })

        # 4. VPC Routes (one per destination CIDR)
        for i, cidr in enumerate(destination_cidrs, 1):
            resources.append({
                "type": "aws:ec2/route:Route",
                "name": f"affinity-{peer_name}-vpc-route-{i}",
                "operation": "create",
                "properties": {
                    "routeTableId": "${aws_route_table.cluster.id}",
                    "destinationCidrBlock": cidr,
                    "transitGatewayId": "${data.aws_ec2_transit_gateway.existing.id}",
                },
            })

        # 5. SNAT if enabled
        if snat_enabled:
            snat_type = peer_config.get("snat_type", "nat_instance")
            if snat_type == "nat_instance":
                resources.append({
                    "type": "aws:ec2/instance:Instance",
                    "name": f"affinity-{peer_name}-snat",
                    "operation": "create",
                    "properties": {
                        "ami": "${data.aws_ami.ubuntu.id}",
                        "instanceType": "t3.micro",
                        "subnetId": "${aws_subnet.private.id}",
                        "sourceDestCheck": False,
                        "tags": {"Name": f"affinity-{peer_name}-snat"},
                    },
                })

                # SNAT security group
                resources.append({
                    "type": "aws:ec2/securityGroup:SecurityGroup",
                    "name": f"affinity-{peer_name}-snat-sg",
                    "operation": "create",
                    "properties": {
                        "name": f"affinity-{peer_name}-snat-sg",
                        "vpcId": "${aws_vpc.main.id}",
                        "ingress": [
                            {"fromPort": 0, "toPort": 65535, "protocol": "-1", "cidrBlocks": ["0.0.0.0/0"]}
                        ],
                        "egress": [
                            {"fromPort": 0, "toPort": 65535, "protocol": "-1", "cidrBlocks": ["0.0.0.0/0"]}
                        ],
                    },
                })
            elif snat_type == "provider_assigned_ip":
                # Provider-assigned IP: no AWS resources needed, configured at peer
                pass

        return resources

    def _generate_summary(self, resources: List[Dict[str, Any]]) -> Dict[str, int]:
        """Generate summary of resource changes."""
        create_count = sum(1 for r in resources if r["operation"] == "create")
        update_count = sum(1 for r in resources if r["operation"] == "update")
        delete_count = sum(1 for r in resources if r["operation"] == "delete")

        return {
            "to_create": create_count,
            "to_update": update_count,
            "to_delete": delete_count,
            "total": len(resources),
        }


class VpnCtlFormatter:
    """Format preview output similar to Pulumi CLI."""

    @staticmethod
    def format_preview(preview: Dict[str, Any]) -> str:
        """Format preview as Pulumi-style output."""
        output = []
        output.append("")
        output.append(f"Previewing peer deployment: {preview['peer_name']}")
        output.append(f"Stack: {preview['stack']}")
        output.append("")
        output.append("Resources:")
        output.append("")

        for resource in preview["resources"]:
            icon = "+" if resource["operation"] == "create" else "~" if resource["operation"] == "update" else "-"
            output.append(f"  {icon} {resource['type']}::{resource['name']}")

        output.append("")
        summary = preview["summary"]
        output.append("Resources summary:")
        output.append(f"  + {summary['to_create']} to create")
        if summary["to_update"] > 0:
            output.append(f"  ~ {summary['to_update']} to update")
        if summary["to_delete"] > 0:
            output.append(f"  - {summary['to_delete']} to delete")
        output.append("")
        output.append(f"Plan: create {summary['to_create']} resources, " +
                     f"update {summary['to_update']} resources, " +
                     f"delete {summary['to_delete']} resources")
        output.append("")

        return "\n".join(output)

    @staticmethod
    def format_detailed_resources(preview: Dict[str, Any]) -> str:
        """Format detailed resource changes."""
        output = []
        output.append("")
        output.append("Detailed resource changes:")
        output.append("=" * 80)
        output.append("")

        for i, resource in enumerate(preview["resources"], 1):
            icon = "+" if resource["operation"] == "create" else "~" if resource["operation"] == "update" else "-"
            output.append(f"{icon} Resource {i}: {resource['name']}")
            output.append(f"  Type: {resource['type']}")
            output.append(f"  Operation: {resource['operation']}")
            output.append("  Properties:")
            for key, value in resource.get("properties", {}).items():
                if isinstance(value, (dict, list)):
                    output.append(f"    {key}: {json.dumps(value, indent=6)}")
                else:
                    output.append(f"    {key}: {value}")
            output.append("")

        return "\n".join(output)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="vpn-ctl: VPN Infrastructure Control Tool - K8s-style declarative IaC",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
SPEC-BASED OPERATIONS (Recommended):
  vpn-ctl apply --spec-file specs/core-stack.yaml
    Deploy core infrastructure from spec

  vpn-ctl apply --spec-file specs/peer-vimenca.yaml --dry-run
    Preview peer deployment

  vpn-ctl destroy --spec-file specs/peer-vimenca.yaml
    Destroy peer infrastructure from spec

  vpn-ctl status --spec-file specs/peer-vimenca.yaml
    Check deployment status

LEGACY PEER COMMANDS (Deprecated):
  vpn-ctl peer deploy vimenca
    (Internally uses specs)
""",
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # === SPEC-BASED COMMANDS (Primary) ===

    # apply command - Deploy from spec
    apply_parser = subparsers.add_parser("apply", help="Deploy infrastructure from spec file")
    apply_parser.add_argument("--spec-file", help="Path to spec file (e.g., specs/core-stack.yaml)")
    apply_parser.add_argument("--spec-dir", help="Path to spec directory (applies all specs)")
    apply_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without deploying",
    )

    # destroy command - Destroy from spec
    destroy_parser = subparsers.add_parser("destroy", help="Destroy infrastructure from spec file")
    destroy_parser.add_argument("--spec-file", required=True, help="Path to spec file")
    destroy_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview destruction without executing",
    )

    # status command - Check deployment status
    status_parser = subparsers.add_parser("status", help="Check infrastructure status")
    status_parser.add_argument("--spec-file", required=True, help="Path to spec file")

    # === LEGACY COMMANDS (Peer-specific, deprecated) ===

    # core command
    core_parser = subparsers.add_parser("core", help="Manage core infrastructure")
    core_subparsers = core_parser.add_subparsers(dest="core_command", help="Core commands")

    # core deploy command
    core_deploy_parser = core_subparsers.add_parser("deploy", help="Deploy core Transit Gateway infrastructure")
    core_deploy_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview infrastructure changes without deploying",
    )
    core_deploy_parser.add_argument(
        "--json",
        action="store_true",
        help="Output preview as JSON",
    )

    # peer command
    peer_parser = subparsers.add_parser("peer", help="Manage VPN peers")
    peer_subparsers = peer_parser.add_subparsers(dest="peer_command", help="Peer commands")

    # peer deploy command
    deploy_parser = peer_subparsers.add_parser("deploy", help="Deploy a VPN peer")
    deploy_parser.add_argument("peer_name", help="Name of the peer to deploy (e.g., vimenca, cibao, apap)")
    deploy_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview infrastructure changes without deploying",
    )
    deploy_parser.add_argument(
        "--detailed",
        action="store_true",
        help="Show detailed resource properties",
    )
    deploy_parser.add_argument(
        "--json",
        action="store_true",
        help="Output preview as JSON",
    )

    # peer config command
    config_parser = peer_subparsers.add_parser("config", help="Configure peer stack")
    config_subparsers = config_parser.add_subparsers(dest="config_command", help="Config commands")

    # peer config set command
    config_set_parser = config_subparsers.add_parser("set", help="Set peer configuration values")
    config_set_parser.add_argument("peer_name", help="Name of the peer (e.g., vimenca, cibao, apap)")
    config_set_parser.add_argument("key", help="Configuration key (e.g., transit_gateway_id)")
    config_set_parser.add_argument("value", help="Configuration value")

    args = parser.parse_args()

    # Route to command handler
    if args.command == "apply":
        handle_apply(args)
    elif args.command == "destroy":
        handle_destroy(args)
    elif args.command == "status":
        handle_status(args)
    elif args.command == "core" and args.core_command == "deploy":
        handle_core_deploy(args)
    elif args.command == "peer" and args.peer_command == "deploy":
        handle_peer_deploy(args)
    elif args.command == "peer" and args.peer_command == "config" and args.config_command == "set":
        handle_peer_config_set(args)
    else:
        parser.print_help()


def handle_core_deploy(args):
    """Handle core infrastructure deployment."""
    try:
        if not args.json:
            print("\n🔹 Core Infrastructure Deployment")
            print("=" * 60)
            print("\n📋 Resources to be created:")
            print("  • Transit Gateway Hub (shared)")
            print("  • EKS Cluster Connectors")
            print("  • Shared SNAT infrastructure (if configured)")
            print("")

        # If dry-run mode, stop here
        if args.dry_run:
            if not args.json:
                print("✅ Preview complete. No changes were made (--dry-run).")
            return

        # Actual deployment: execute pulumi up for core stack
        if not args.json:
            response = input(f"\n❓ Continue with core infrastructure deployment? [y/N]: ").lower()
            if response != 'y':
                print("Deployment cancelled.")
                return

        # Change to core stack directory
        script_dir = Path(__file__).parent
        core_stack_dir = script_dir / "stacks/core"
        if not core_stack_dir.exists():
            raise ValueError(f"Core stack directory not found: {core_stack_dir}")

        os.chdir(core_stack_dir)

        # Select the core stack
        print(f"\n📍 Selecting stack: vpn-ctl-stack (core)")
        result = subprocess.run(
            ["pulumi", "stack", "select", "vpn-ctl-stack"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to select stack: {result.stderr}")

        # Run pulumi up
        print(f"⏳ Running core infrastructure deployment...")
        result = subprocess.run(
            ["pulumi", "up", "--yes", "--skip-preview"],
            capture_output=False,
            text=True
        )

        if result.returncode != 0:
            raise RuntimeError(f"Deployment failed with exit code {result.returncode}")

        # After successful deployment, extract and display TGW ID
        print("\n📊 Extracting Transit Gateway configuration...")
        result = subprocess.run(
            ["pulumi", "stack", "output", "--json"],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            try:
                outputs = json.loads(result.stdout)
                tgw_id = outputs.get("transit_gateway_id", "")
                if tgw_id:
                    print(f"\n✅ Core infrastructure deployed!")
                    print(f"   Transit Gateway ID: {tgw_id}")
                    print(f"\n📝 Next steps:")
                    print(f"   1. Set TGW ID in peer stacks:")
                    print(f"      vpn-ctl peer config set transit_gateway_id {tgw_id}")
                    print(f"   2. Deploy peers:")
                    print(f"      vpn-ctl peer deploy vimenca")
                else:
                    print("\n✅ Core infrastructure deployed (TGW ID not exported)")
            except json.JSONDecodeError:
                print("\n✅ Core infrastructure deployed")
        else:
            print("\n✅ Core infrastructure deployed")

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


def handle_peer_config_set(args):
    """Handle peer config set command."""
    try:
        script_dir = Path(__file__).parent
        peer_stack_dir = script_dir / f"stacks/peer-{args.peer_name}"

        if not peer_stack_dir.exists():
            raise ValueError(f"Peer stack directory not found: {peer_stack_dir}")

        os.chdir(peer_stack_dir)

        # Select the peer stack
        print(f"📍 Selecting stack: peer-{args.peer_name}")
        result = subprocess.run(
            ["pulumi", "stack", "select", f"peer-{args.peer_name}"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to select stack: {result.stderr}")

        # Set config value
        print(f"⚙️  Setting {args.key} = {args.value}")
        result = subprocess.run(
            ["pulumi", "config", "set", f"aff-atg:{args.key}", args.value],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            raise RuntimeError(f"Failed to set config: {result.stderr}")

        print(f"✅ Config updated for peer-{args.peer_name}")

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


def handle_peer_deploy(args):
    """Handle peer deploy command."""
    try:
        # Load config - resolve relative to script location
        script_dir = Path(__file__).parent
        config_dir = (script_dir / "../config").resolve()
        preview_service = VpnCtlPreviewService(str(config_dir))

        # Generate preview (message to stderr for --json flag)
        if not args.json:
            print(f"\n🔍 Generating preview for peer: {args.peer_name}...\n")
        else:
            print(f"🔍 Generating preview for peer: {args.peer_name}...", file=sys.stderr)

        preview = preview_service.preview_peer_deployment(args.peer_name)

        # Format and output
        if args.json:
            print(json.dumps(preview, indent=2))
        else:
            print(VpnCtlFormatter.format_preview(preview))

            if args.detailed:
                print(VpnCtlFormatter.format_detailed_resources(preview))

        # If dry-run mode, stop here
        if args.dry_run:
            if not args.json:
                print("\n✅ Preview complete. No changes were made (--dry-run).")
            return

        # Actual deployment: execute pulumi up
        if not args.json:
            print(f"\n🚀 Deploying peer: {args.peer_name}...")
            response = input(f"\n❓ Continue with deployment? [y/N]: ").lower()
            if response != 'y':
                print("Deployment cancelled.")
                return

        # Change to peer stack directory
        peer_stack_dir = script_dir / f"stacks/peer-{args.peer_name}"
        if not peer_stack_dir.exists():
            raise ValueError(f"Peer stack directory not found: {peer_stack_dir}")

        os.chdir(peer_stack_dir)

        # Select the peer stack
        print(f"📍 Selecting stack: peer-{args.peer_name}")
        result = subprocess.run(
            ["pulumi", "stack", "select", f"peer-{args.peer_name}"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to select stack: {result.stderr}")

        # Run pulumi up
        print(f"⏳ Running deployment...")
        result = subprocess.run(
            ["pulumi", "up", "--yes", "--skip-preview"],
            capture_output=False,
            text=True
        )

        if result.returncode != 0:
            raise RuntimeError(f"Deployment failed with exit code {result.returncode}")

        if not args.json:
            print(f"\n✅ Deployment complete for peer: {args.peer_name}")

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
