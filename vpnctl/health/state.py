"""VPN Health State Management.

Maintains current VPN state by comparing config specs with AWS reality.
Uses infra-config.json (resource IDs) via boto3 SDK, replaces AWS CLI subprocess calls.
"""

import json
import boto3
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import yaml
import logging

logger = logging.getLogger(__name__)


@dataclass
class PeerHealth:
    """Health status of a single VPN peer."""
    peer_name: str
    enabled: bool
    vpn_id: Optional[str] = None
    aws_state: Optional[str] = None
    tunnel1_ip: Optional[str] = None
    tunnel1_status: str = "UNKNOWN"
    tunnel2_ip: Optional[str] = None
    tunnel2_status: str = "UNKNOWN"
    config_drift: List[str] = None  # Differences between config and AWS
    health_status: str = "UNKNOWN"  # healthy, degraded, unhealthy, missing
    last_check: Optional[str] = None

    def __post_init__(self):
        if self.config_drift is None:
            self.config_drift = []
        if not self.last_check:
            self.last_check = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class VPNHealthState:
    """Manages VPN health state by comparing config with AWS reality using boto3 and infra-config resource IDs."""

    def __init__(self, infra_config: Optional[Dict[str, Any]] = None, aws_profile: str = "default", region: str = "us-east-2"):
        """
        Initialize health state manager.

        Args:
            infra_config: Infrastructure metadata with resource IDs (from infra-config.json)
            aws_profile: AWS profile to use (for boto3 session)
            region: AWS region
        """
        self.infra_config = infra_config or {}
        self.aws_profile = aws_profile
        self.region = region

        # Initialize boto3 session and EC2 client
        try:
            session = boto3.Session(profile_name=aws_profile, region_name=region)
            self.ec2 = session.client('ec2')
        except Exception as e:
            logger.warning(f"Failed to initialize boto3 session: {e}. Will retry on first health check.")
            self.ec2 = None

        self.peers: Dict[str, PeerHealth] = {}
        self.last_update: Optional[str] = None

    def load_config(self, config_file: str) -> Dict[str, Any]:
        """Load VPN configuration from YAML file."""
        try:
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
            return config or {}
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return {}

    def load_infra_config(self, infra_config_file: str) -> Dict[str, Any]:
        """Load infrastructure config from JSON file."""
        try:
            with open(infra_config_file, 'r') as f:
                config = json.load(f)
            return config or {}
        except Exception as e:
            logger.warning(f"Failed to load infra config from {infra_config_file}: {e}")
            return {}

    def _ensure_ec2_client(self) -> bool:
        """Ensure boto3 EC2 client is initialized."""
        if self.ec2:
            return True
        try:
            session = boto3.Session(profile_name=self.aws_profile, region_name=self.region)
            self.ec2 = session.client('ec2')
            return True
        except Exception as e:
            logger.error(f"Failed to initialize boto3 session: {e}")
            return False

    def _get_vpn_state_from_id(self, vpn_id: str) -> Dict[str, Any]:
        """Query specific VPN connection state by ID using boto3."""
        try:
            response = self.ec2.describe_vpn_connections(VpnConnectionIds=[vpn_id])
            vpn = response['VpnConnections'][0] if response['VpnConnections'] else None

            if not vpn:
                return {}

            telemetry = vpn.get('VgwTelemetry', [])
            return {
                "vpn_id": vpn['VpnConnectionId'],
                "state": vpn['State'],
                "tunnel1_ip": telemetry[0].get('OutsideIpAddress') if telemetry else None,
                "tunnel1_status": telemetry[0].get('Status', 'UNKNOWN').upper() if telemetry else 'UNKNOWN',
                "tunnel2_ip": telemetry[1].get('OutsideIpAddress') if len(telemetry) > 1 else None,
                "tunnel2_status": telemetry[1].get('Status', 'UNKNOWN').upper() if len(telemetry) > 1 else 'UNKNOWN',
            }
        except Exception as e:
            logger.error(f"Failed to query VPN {vpn_id}: {e}")
            return {}

    def _check_tgw_attachment_state(self, attachment_id: str) -> Optional[str]:
        """Check Transit Gateway attachment state."""
        try:
            response = self.ec2.describe_transit_gateway_attachments(
                TransitGatewayAttachmentIds=[attachment_id]
            )
            if response['TransitGatewayAttachments']:
                return response['TransitGatewayAttachments'][0]['State']
            return None
        except Exception as e:
            logger.debug(f"Failed to check TGW attachment {attachment_id}: {e}")
            return None

    def _check_tgw_routes_active(self, route_table_id: str, destination_cidrs: List[str]) -> bool:
        """Check if TGW routes are active for destination CIDRs."""
        try:
            response = self.ec2.search_transit_gateway_routes(
                TransitGatewayRouteTableId=route_table_id,
                Filters=[{'Name': 'state', 'Values': ['active']}]
            )
            active_routes = {r.get('DestinationCidrBlock') for r in response.get('Routes', [])}
            return any(cidr in active_routes for cidr in destination_cidrs)
        except Exception as e:
            logger.debug(f"Failed to check TGW routes for {route_table_id}: {e}")
            return False

    def get_aws_vpn_state(self) -> Dict[str, Dict[str, Any]]:
        """Query AWS for current VPN connection state using infra-config resource IDs and boto3."""
        if not self._ensure_ec2_client():
            return {}

        vpn_state = {}

        # Use resource IDs from infra_config instead of searching by tags
        for peer_name, peer_data in self.infra_config.get("peers", {}).items():
            peer_name_normalized = peer_name.lower().replace(" ", "-")
            aws_resources = peer_data.get("aws_resources", {})
            vpn_id = aws_resources.get("vpn_connection_id")

            if not vpn_id:
                logger.debug(f"No VPN ID in infra_config for peer {peer_name}")
                continue

            # Get VPN state by ID
            vpn_info = self._get_vpn_state_from_id(vpn_id)
            if vpn_info:
                vpn_state[peer_name_normalized] = vpn_info

                # Optionally check TGW attachment and routes
                attachment_id = aws_resources.get("tgw_attachment_id")
                if attachment_id and attachment_id != "not-attached":
                    attachment_state = self._check_tgw_attachment_state(attachment_id)
                    vpn_state[peer_name_normalized]["tgw_attachment_state"] = attachment_state

                # Check if routes are active
                route_table_id = aws_resources.get("tgw_route_table_id")
                destination_cidrs = peer_data.get("routes", {}).get("destination_cidrs", [])
                if route_table_id and destination_cidrs:
                    routes_active = self._check_tgw_routes_active(route_table_id, destination_cidrs)
                    vpn_state[peer_name_normalized]["routes_active"] = routes_active

        return vpn_state

    def detect_config_drift(self, peer_name: str, spec: Dict[str, Any], aws: Dict[str, Any]) -> List[str]:
        """Detect differences between config spec and AWS reality."""
        drift = []

        # Check VPN ID (should exist if AWS has it)
        if aws.get("vpn_id") and spec.get("vpn_id") != aws.get("vpn_id"):
            drift.append(f"VPN ID mismatch: spec={spec.get('vpn_id')} vs aws={aws.get('vpn_id')}")

        # Check tunnel IPs (should exist in AWS if enabled)
        if aws.get("tunnel1_ip") and spec.get("tunnel1_ip") != aws.get("tunnel1_ip"):
            drift.append(f"Tunnel 1 IP changed: spec={spec.get('tunnel1_ip')} vs aws={aws.get('tunnel1_ip')}")

        # Check device type
        if spec.get("device_type") and not aws.get("device_type"):
            drift.append(f"Device type in config but not in AWS: {spec.get('device_type')}")

        # Check public IP
        if spec.get("public_ip") and not aws.get("public_ip"):
            drift.append(f"Public IP in config but not in AWS: {spec.get('public_ip')}")

        return drift

    def determine_health_status(self, enabled: bool, aws: Dict[str, Any], drift: List[str]) -> str:
        """Determine overall health status based on state and drift."""
        if not enabled:
            return "disabled"

        if not aws or not aws.get("vpn_id"):
            return "missing"  # Not deployed yet

        if aws.get("state") != "available":
            return "unhealthy"  # AWS state is not available

        if aws.get("tunnel1_status") == "UP" or aws.get("tunnel2_status") == "UP":
            if drift:
                return "degraded"  # At least one tunnel up, but config drift
            return "healthy"

        if drift:
            return "degraded"

        return "unhealthy"  # Available but no tunnels UP

    def refresh(self, config_file: str, infra_config_file: Optional[str] = None) -> Dict[str, PeerHealth]:
        """
        Refresh health state by comparing config with AWS reality.

        Args:
            config_file: Path to vpn-peers.yaml
            infra_config_file: Optional path to infra-config.json (infrastructure state with resource IDs)
        """
        config = self.load_config(config_file)

        # Load infra config if provided
        if infra_config_file:
            self.infra_config = self.load_infra_config(infra_config_file)

        aws_state = self.get_aws_vpn_state()

        self.peers = {}

        # Process each peer in config
        for peer in config.get("peers", []):
            peer_name = peer["name"].lower().replace(" ", "-")
            enabled = peer.get("enabled", True)

            aws = aws_state.get(peer_name, {})
            drift = self.detect_config_drift(peer_name, peer, aws)
            health = self.determine_health_status(enabled, aws, drift)

            self.peers[peer_name] = PeerHealth(
                peer_name=peer_name,
                enabled=enabled,
                vpn_id=aws.get("vpn_id"),
                aws_state=aws.get("state"),
                tunnel1_ip=aws.get("tunnel1_ip"),
                tunnel1_status=aws.get("tunnel1_status", "UNKNOWN"),
                tunnel2_ip=aws.get("tunnel2_ip"),
                tunnel2_status=aws.get("tunnel2_status", "UNKNOWN"),
                config_drift=drift,
                health_status=health,
                last_check=datetime.utcnow().isoformat(),
            )

        # Process any AWS VPNs not in config (orphaned)
        for peer_name, aws in aws_state.items():
            if peer_name not in self.peers:
                self.peers[peer_name] = PeerHealth(
                    peer_name=peer_name,
                    enabled=False,
                    vpn_id=aws.get("vpn_id"),
                    aws_state=aws.get("state"),
                    tunnel1_ip=aws.get("tunnel1_ip"),
                    tunnel1_status=aws.get("tunnel1_status", "UNKNOWN"),
                    tunnel2_ip=aws.get("tunnel2_ip"),
                    tunnel2_status=aws.get("tunnel2_status", "UNKNOWN"),
                    config_drift=["Orphaned: exists in AWS but not in config"],
                    health_status="orphaned",
                    last_check=datetime.utcnow().isoformat(),
                )

        self.last_update = datetime.utcnow().isoformat()
        logger.info(f"Health check complete: {len(self.peers)} peers analyzed")
        return self.peers

    def get_summary(self) -> Dict[str, Any]:
        """Get health summary statistics."""
        statuses = {}
        for peer in self.peers.values():
            status = peer.health_status
            statuses[status] = statuses.get(status, 0) + 1

        return {
            "total_peers": len(self.peers),
            "healthy": statuses.get("healthy", 0),
            "degraded": statuses.get("degraded", 0),
            "unhealthy": statuses.get("unhealthy", 0),
            "missing": statuses.get("missing", 0),
            "orphaned": statuses.get("orphaned", 0),
            "disabled": statuses.get("disabled", 0),
            "last_update": self.last_update,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dictionary for JSON serialization."""
        return {
            "summary": self.get_summary(),
            "peers": {name: peer.to_dict() for name, peer in self.peers.items()},
        }
