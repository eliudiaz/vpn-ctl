#!/usr/bin/env python3
"""
vpnctl tunnel info - Display comprehensive tunnel information for all VPN peers

Combines:
- Current AWS public IPs and tunnel status
- Tunnel profile encryption/DH/lifetime parameters
- Peer configuration details
"""

import subprocess
import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


@dataclass
class TunnelInfo:
    """Complete tunnel information."""
    peer_name: str
    vpn_id: str
    state: str
    tunnel1_ip: Optional[str]
    tunnel1_status: str
    tunnel2_ip: Optional[str]
    tunnel2_status: str
    profile_name: str
    profile_encryption: str
    profile_integrity: str
    profile_dh_group: str
    profile_lifetime: int
    public_ip: str
    device_type: str


class TunnelInfoCollector:
    """Collect tunnel information from AWS and specs."""

    def __init__(self, aws_profile: str = "affinity", region: str = "us-east-2"):
        self.aws_profile = aws_profile
        self.region = region

    def get_aws_tunnel_info(self) -> Dict[str, Dict[str, Any]]:
        """Get all VPN connections and tunnel details from AWS."""
        try:
            result = subprocess.run([
                "aws", "ec2", "describe-vpn-connections",
                "--profile", self.aws_profile,
                "--region", self.region,
                "--output", "json"
            ], capture_output=True, text=True, check=True)

            vpns = json.loads(result.stdout)
            tunnel_info = {}

            for vpn in vpns.get("VpnConnections", []):
                # Get peer name from tags
                peer_name = None
                vpn_name = None
                for tag in vpn.get("Tags", []):
                    if tag["Key"] == "Name":
                        vpn_name = tag["Value"]
                        # Extract peer name from VPN name (e.g., "affinity-vimenca-vpn" -> "vimenca")
                        if vpn_name.startswith("affinity-") and vpn_name.endswith("-vpn"):
                            # Remove first "affinity-" prefix and last "-vpn" suffix only
                            peer_name = vpn_name[9:]  # Remove "affinity-" (9 chars)
                            peer_name = peer_name[:-4]  # Remove "-vpn" (4 chars)
                            peer_name = peer_name.lower()
                            break

                if not peer_name:
                    continue

                telemetry = vpn.get("VgwTelemetry", [])
                tunnel_info[peer_name] = {
                    "vpn_id": vpn["VpnConnectionId"],
                    "state": vpn["State"],
                    "tunnel1_ip": telemetry[0].get("OutsideIpAddress") if telemetry else None,
                    "tunnel1_status": telemetry[0].get("Status", "UNKNOWN").upper() if telemetry else "UNKNOWN",
                    "tunnel2_ip": telemetry[1].get("OutsideIpAddress") if len(telemetry) > 1 else None,
                    "tunnel2_status": telemetry[1].get("Status", "UNKNOWN").upper() if len(telemetry) > 1 else "UNKNOWN",
                }

            return tunnel_info

        except Exception as e:
            logger.error(f"Failed to get AWS tunnel info: {e}")
            return {}

    def get_spec_tunnel_info(self, config_file: str) -> Dict[str, Dict[str, Any]]:
        """Get tunnel profile and peer info from VPN config."""
        try:
            import yaml
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)

            profiles = config.get("tunnel_profiles", {})
            tunnel_info = {}

            for peer in config.get("peers", []):
                if not peer.get("enabled", True):
                    continue

                profile_name = peer.get("tunnel_profile", "checkpoint_r80")
                profile = profiles.get(profile_name, {})

                # Normalize peer name to lowercase for matching with AWS
                peer_name_normalized = peer["name"].lower().replace(" ", "-")

                tunnel_info[peer_name_normalized] = {
                    "profile_name": profile_name,
                    "profile_encryption": profile.get("phase1", {}).get("encryption", ["N/A"])[0],
                    "profile_integrity": profile.get("phase1", {}).get("integrity", ["N/A"])[0],
                    "profile_dh_group": profile.get("phase1", {}).get("dh_groups", [0])[0],
                    "profile_lifetime": profile.get("phase1", {}).get("lifetime", 0),
                    "public_ip": peer.get("public_ip", "N/A"),
                    "device_type": peer.get("device_type", "Unknown"),
                }

            return tunnel_info

        except Exception as e:
            logger.error(f"Failed to load spec tunnel info: {e}")
            return {}

    def collect_all_tunnel_info(self, config_file: str) -> List[TunnelInfo]:
        """Combine AWS and spec data into complete tunnel info."""
        aws_info = self.get_aws_tunnel_info()
        spec_info = self.get_spec_tunnel_info(config_file)

        tunnel_infos = []

        # Merge AWS and spec data
        for peer_name in set(list(aws_info.keys()) + list(spec_info.keys())):
            aws = aws_info.get(peer_name, {})
            spec = spec_info.get(peer_name, {})

            info = TunnelInfo(
                peer_name=peer_name,
                vpn_id=aws.get("vpn_id", "N/A"),
                state=aws.get("state", "unknown"),
                tunnel1_ip=aws.get("tunnel1_ip", "N/A"),
                tunnel1_status=aws.get("tunnel1_status", "UNKNOWN"),
                tunnel2_ip=aws.get("tunnel2_ip", "N/A"),
                tunnel2_status=aws.get("tunnel2_status", "UNKNOWN"),
                profile_name=spec.get("profile_name", "N/A"),
                profile_encryption=spec.get("profile_encryption", "N/A"),
                profile_integrity=spec.get("profile_integrity", "N/A"),
                profile_dh_group=str(spec.get("profile_dh_group", "N/A")),
                profile_lifetime=spec.get("profile_lifetime", 0),
                public_ip=spec.get("public_ip", "N/A"),
                device_type=spec.get("device_type", "N/A"),
            )

            tunnel_infos.append(info)

        return sorted(tunnel_infos, key=lambda x: x.peer_name)

    def print_table(self, tunnel_infos: List[TunnelInfo]):
        """Print tunnel info in formatted table."""
        print("\n" + "="*180)
        print("VPN TUNNEL INFORMATION - All Peers")
        print("="*180)
        print()

        # Header
        print(f"{'Peer':<20} {'VPN ID':<25} {'State':<10} {'Tunnel 1 IP':<18} {'Status':<7} {'Tunnel 2 IP':<18} {'Status':<7}")
        print("-" * 180)

        for info in tunnel_infos:
            print(f"{info.peer_name:<20} {info.vpn_id:<25} {info.state:<10} {str(info.tunnel1_ip):<18} {info.tunnel1_status:<7} {str(info.tunnel2_ip):<18} {info.tunnel2_status:<7}")

        print()
        print("="*180)
        print("TUNNEL PROFILE DETAILS")
        print("="*180)
        print()

        # Profile details header
        print(f"{'Peer':<20} {'Profile':<20} {'Device':<30} {'Encryption':<12} {'Integrity':<12} {'DH Group':<10} {'Lifetime':<10} {'Peer IP':<18}")
        print("-" * 180)

        for info in tunnel_infos:
            print(f"{info.peer_name:<20} {info.profile_name:<20} {info.device_type:<30} {info.profile_encryption:<12} {info.profile_integrity:<12} {info.profile_dh_group:<10} {str(info.profile_lifetime):<10} {info.public_ip:<18}")

        print()
        print("="*180)
        print("LEGEND")
        print("="*180)
        print("""
  Peer:               VPN peer name (customer/branch)
  VPN ID:             AWS VPN Connection ID (vpn-xxxxx)
  State:              AWS VPN state (available, deleted, deleting, etc.)
  Tunnel 1/2 IP:      AWS public IP assigned to each tunnel (endpoint for customer config)
  Status:             Tunnel status (UP, DOWN, UNKNOWN)
  Profile:            IPsec tunnel profile name (checkpoint_r80, fortigate_standard, etc.)
  Device:             Peer device type (Checkpoint Firewall, Fortinet FortiGate, etc.)
  Encryption:         Phase 1 encryption algorithm (AES256, AES128, etc.)
  Integrity:          Phase 1 integrity algorithm (SHA2-256, SHA1, etc.)
  DH Group:           Diffie-Hellman group (14 = 2048-bit, etc.)
  Lifetime:           Phase 1 lifetime in seconds
  Peer IP:            Peer's public IP (customer-side VPN endpoint)
        """)


def show_tunnel_info(config_file: str = None):
    """Main command to show tunnel information."""
    if config_file is None:
        # Try to find config file
        config_file = "config/vpn-peers.yaml"
        if not Path(config_file).exists():
            # Try relative to vpnctl module
            config_file = str(Path(__file__).parent.parent / "config" / "vpn-peers.yaml")

    if not Path(config_file).exists():
        print(f"❌ Config file not found: {config_file}")
        return

    collector = TunnelInfoCollector()
    tunnel_infos = collector.collect_all_tunnel_info(config_file)

    if not tunnel_infos:
        print("❌ No tunnel information found")
        return

    collector.print_table(tunnel_infos)


if __name__ == "__main__":
    import sys
    config_file = sys.argv[1] if len(sys.argv) > 1 else None
    show_tunnel_info(config_file)
