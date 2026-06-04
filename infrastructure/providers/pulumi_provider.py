"""Pulumi Infrastructure Provider (Adapter)."""

from typing import Dict, Any
import subprocess
import json
from pathlib import Path

from infrastructure.providers.interfaces import IInfrastructureProvider
from domain.models import VpnPeer, TunnelProfile


class PulumiProvider(IInfrastructureProvider):
    """
    Pulumi Infrastructure Provider Implementation

    This is the ONLY place Pulumi code lives.
    Completely swappable with TerraformProvider, CloudFormationProvider, etc.
    """

    def __init__(self, stack_name: str, pulumi_dir: Path = None):
        """
        Initialize Pulumi provider.

        Args:
            stack_name: Name of Pulumi stack (e.g., 'core', 'peer-vimenca')
            pulumi_dir: Path to Pulumi directory (default: pulumi/)
        """
        self.stack_name = stack_name
        self.pulumi_dir = pulumi_dir or Path("pulumi")

    def _run_pulumi(self, *args: str) -> subprocess.CompletedProcess:
        """Run pulumi command in pulumi directory."""
        cmd = ["pulumi"] + list(args) + ["--stack", self.stack_name]
        result = subprocess.run(
            cmd,
            cwd=str(self.pulumi_dir),
            capture_output=True,
            text=True,
        )
        return result

    def create_vpn_peer(
        self,
        peer: VpnPeer,
        tunnel_profile: TunnelProfile,
    ) -> Dict[str, Any]:
        """
        Deploy VPN peer using Pulumi.

        Delegates to existing __main__.py VpnConnector logic.
        """
        # Run pulumi up
        result = self._run_pulumi("up", "--yes")

        if result.returncode != 0:
            raise RuntimeError(f"Pulumi deployment failed: {result.stderr}")

        # Query outputs
        try:
            vpn_id_result = self._run_pulumi("stack", "output", f"vpn_{peer.name}_id")
            tunnel1_result = self._run_pulumi("stack", "output", f"vpn_{peer.name}_tunnel1")
            tunnel2_result = self._run_pulumi("stack", "output", f"vpn_{peer.name}_tunnel2")

            return {
                "vpn_id": vpn_id_result.stdout.strip(),
                "tunnel1_ip": tunnel1_result.stdout.strip(),
                "tunnel2_ip": tunnel2_result.stdout.strip(),
                "cgw_id": f"vpn-{peer.name}-cgw",  # From naming convention
            }
        except Exception as e:
            raise RuntimeError(f"Failed to get deployment outputs: {e}")

    def destroy_vpn_peer(self, peer_name: str) -> None:
        """Destroy peer using Pulumi."""
        result = self._run_pulumi("destroy", "--yes", "--remove")

        if result.returncode != 0:
            raise RuntimeError(f"Pulumi destruction failed: {result.stderr}")

    def get_peer_status(self, peer_name: str) -> Dict[str, Any]:
        """Get peer status from Pulumi + AWS."""
        try:
            # Get VPN ID from Pulumi
            vpn_id_result = self._run_pulumi("stack", "output", f"vpn_{peer_name}_id")
            vpn_id = vpn_id_result.stdout.strip()

            # Query AWS for tunnel status
            import boto3

            ec2 = boto3.client("ec2", region_name="us-east-2")
            response = ec2.describe_vpn_connections(VpnConnectionIds=[vpn_id])

            vpn = response["VpnConnections"][0]
            tunnels = vpn.get("VgwTelemetry", [])

            return {
                "state": vpn["State"],
                "tunnel1_status": tunnels[0]["Status"] if len(tunnels) > 0 else "UNKNOWN",
                "tunnel2_status": tunnels[1]["Status"] if len(tunnels) > 1 else "UNKNOWN",
                "tunnel1_last_change": str(tunnels[0]["LastStatusChange"]) if len(tunnels) > 0 else None,
                "tunnel2_last_change": str(tunnels[1]["LastStatusChange"]) if len(tunnels) > 1 else None,
            }
        except Exception as e:
            raise RuntimeError(f"Failed to get peer status: {e}")

    def list_resources(self, peer_name: str) -> list:
        """List all resources for peer."""
        result = self._run_pulumi("stack", "--show-urns")

        if result.returncode != 0:
            raise RuntimeError(f"Failed to list resources: {result.stderr}")

        # Filter to peer-specific resources
        resources = []
        for line in result.stdout.split("\n"):
            if f"vpn-{peer_name}-" in line or f"{peer_name.lower()}-" in line:
                resources.append(line.strip())

        return resources

    def preview_deployment(self, peer: VpnPeer, tunnel_profile: TunnelProfile) -> Dict[str, Any]:
        """Preview deployment changes."""
        result = self._run_pulumi("preview", "--json")

        if result.returncode != 0:
            raise RuntimeError(f"Preview failed: {result.stderr}")

        try:
            preview_data = json.loads(result.stdout)
            return {
                "changes": f"{preview_data.get('summary', {}).get('same', 0)} unchanged, "
                          f"{preview_data.get('summary', {}).get('create', 0)} to create, "
                          f"{preview_data.get('summary', {}).get('replace', 0)} to replace, "
                          f"{preview_data.get('summary', {}).get('delete', 0)} to delete",
                "resource_count": len(preview_data.get("steps", [])),
                "estimated_monthly_cost": 36.0,  # Placeholder
            }
        except Exception as e:
            raise RuntimeError(f"Failed to parse preview: {e}")
