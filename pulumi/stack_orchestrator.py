"""
Stack Orchestration - Peer-Agnostic Infrastructure Deployment

Provides clean abstraction for deploying infrastructure based on stack type:
- CoreStackOrchestrator: dev/core stack (shared TGW, EKS, SNAT)
- PeerStackOrchestrator: peer-<name> stack (isolated peer resources)

Both orchestrators use the same domain classes - no branching logic in __main__.py
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Tuple
import pulumi
import pulumi_aws as aws
import logging
from dataclasses import dataclass

# Import VPN pool management
from vpn_registry import VpnRegistry
from vpn_attachment import VpnAttachmentManager, VpnAttachmentExecutor

logger = logging.getLogger(__name__)


# =============================================================================
# TRANSIT GATEWAY REFERENCE (Fixes ExistingTgwHub hack)
# =============================================================================

class TransitGatewayReference:
    """
    Proper abstraction for referencing existing Transit Gateway.

    Used by peer-specific stacks to reference TGW created by dev/core stack.
    NOT a full InfrastructureComponent because it doesn't create resources.
    """

    def __init__(self, tgw_id: str, tgw_rt_id: str):
        """
        Initialize reference to existing TGW.

        Args:
            tgw_id: Transit Gateway ID (e.g., tgw-0572ce4b80ff7445a)
            tgw_rt_id: Transit Gateway Route Table ID (e.g., tgw-rtb-079e9cb450e5355e6)
        """
        self._tgw_id = tgw_id
        self._tgw_rt_id = tgw_rt_id

        # Create a minimal proxy object that acts like TransitGatewayHub
        # for compatibility with VpnConnector and other classes
        class TgwProxy:
            def __init__(self, tgw_id_val, tgw_rt_id_val):
                self.id = tgw_id_val
                self.association_default_route_table_id = tgw_rt_id_val

        self.transit_gateway = TgwProxy(tgw_id, tgw_rt_id)

        logger.info(f"TransitGatewayReference initialized:")
        logger.info(f"  TGW ID: {tgw_id}")
        logger.info(f"  Route Table ID: {tgw_rt_id}")

    @property
    def id(self) -> str:
        """Return TGW ID (string, not Pulumi Output)."""
        return self._tgw_id

    def get_outputs(self) -> Dict[str, Any]:
        """Return reference outputs for export."""
        return {
            "transit_gateway_id": self._tgw_id,
            "transit_gateway_route_table_id": self._tgw_rt_id,
        }


# =============================================================================
# STACK ORCHESTRATOR PATTERN
# =============================================================================

class StackOrchestrator(ABC):
    """
    Abstract base for stack orchestration.

    Defines interface for deploying infrastructure based on stack type.
    Eliminates branching logic from __main__.py.
    """

    def __init__(self, stack_name: str, config_manager, vpc_connector_class):
        self.stack_name = stack_name
        self.config_manager = config_manager
        self.vpc_connector_class = vpc_connector_class

    @abstractmethod
    def create_tgw_hub(self) -> Any:
        """Create or reference Transit Gateway hub."""
        pass

    @abstractmethod
    def create_eks_connectors(self) -> Dict[str, Any]:
        """Create or skip EKS cluster connectors."""
        pass

    @abstractmethod
    def create_vpn_connectors(self) -> Dict[str, Any]:
        """Create VPN connectors (all or filtered)."""
        pass

    @abstractmethod
    def create_snat_instances(self, hub, cluster_connectors) -> Dict[str, Any]:
        """Create SNAT instances (shared or isolated)."""
        pass


class CoreStackOrchestrator(StackOrchestrator):
    """
    Orchestrates dev/core stack.

    Creates:
    - Transit Gateway Hub
    - EKS Cluster Connectors (optional, if shared infra needed)
    - ALL VPN Connectors
    - SNAT Instances (shared)
    """

    def __init__(self, stack_name: str, config_manager, vpc_connector_class):
        super().__init__(stack_name, config_manager, vpc_connector_class)
        self._hub = None  # Cache hub to avoid duplicate creation

    def create_tgw_hub(self):
        """Create new Transit Gateway Hub (cached to avoid duplicates)."""
        from __main__ import TransitGatewayHub  # Import from main module

        # Return cached hub if already created
        if self._hub is not None:
            logger.info("CoreStack: Using cached Transit Gateway Hub")
            return self._hub

        logger.info("CoreStack: Creating Transit Gateway Hub...")
        hub = TransitGatewayHub(
            name="affinity-hub",
            region=pulumi.Config("aws").get("region") or "us-east-2",
            description="Transit Gateway Hub for aff-atg (shared)",
            tags={"Environment": "production", "StackType": "core"}
        )
        logger.info("✓ Transit Gateway Hub created")

        # Cache for reuse
        self._hub = hub
        return hub

    def create_eks_connectors(self) -> Dict[str, Any]:
        """Create EKS cluster connectors using the hub."""
        from __main__ import EksClusterConnector  # Import from main module

        logger.info("CoreStack: Connecting EKS clusters...")
        connected_clusters = {}

        # Use cached hub (must have been created by create_tgw_hub() first)
        if self._hub is None:
            logger.warning("CoreStack: Hub not created yet, skipping EKS connectors")
            return connected_clusters

        # List of clusters to connect (configurable)
        eks_clusters = [
            {"name": "asg-plat-dev", "region": "us-east-2"},
        ]

        for cluster_cfg in eks_clusters:
            connector = EksClusterConnector(
                name=cluster_cfg["name"],
                hub=self._hub,
                region=cluster_cfg["region"],
                destination_cidrs=[],  # Will be populated later
                tags={"Environment": "dev"}
            )
            connected_clusters[cluster_cfg["name"]] = connector
            logger.info(f"✓ Connected cluster: {cluster_cfg['name']}")

        return connected_clusters

    def create_vpn_connectors(self) -> Dict[str, Any]:
        """Create all enabled VPN connectors."""
        logger.info("CoreStack: Creating VPN connectors for ALL enabled peers...")
        vpn_connectors = {}

        # Get ALL enabled peers
        all_peers = self.config_manager.get_peer_configs()

        for peer_config, tunnel_profile, tunnel1_psk, tunnel2_psk in all_peers:
            logger.info(f"  Creating VPN for {peer_config.name}...")
            # VpnConnector creation happens in main
            vpn_connectors[peer_config.name] = {
                "peer_config": peer_config,
                "tunnel_profile": tunnel_profile,
                "tunnel1_psk": tunnel1_psk,
                "tunnel2_psk": tunnel2_psk,
            }

        return vpn_connectors

    def create_snat_instances(self, hub, cluster_connectors) -> Dict[str, Any]:
        """Create SNAT instances for peers with provider_assigned_ip."""
        logger.info("CoreStack: Creating SNAT instances...")
        snat_instances = {}

        # Get all peers
        all_peers = self.config_manager.get_peer_configs()

        for peer_config, _, _, _ in all_peers:
            if peer_config.provider_assigned_ip:
                logger.info(f"  Creating SNAT for {peer_config.name}...")
                snat_instances[peer_config.name] = {
                    "peer_config": peer_config,
                    "hub": hub,
                    "cluster_connectors": cluster_connectors,
                }

        return snat_instances


class PeerStackOrchestrator(StackOrchestrator):
    """
    Orchestrates peer-<name> stack.

    Deploys ONLY a single peer's resources:
    - References existing Transit Gateway (no creation)
    - Skips EKS connectors (managed by core stack)
    - Creates ONLY this peer's VPN connector
    - Creates SNAT instance if peer has provider_assigned_ip
    """

    def __init__(self, peer_name: str, config_manager, vpc_connector_class):
        super().__init__(f"peer-{peer_name}", config_manager, vpc_connector_class)
        self.peer_name = peer_name.lower()

        # Get this peer's configuration
        all_peers = config_manager.get_peer_configs()
        peer_configs = [p for p in all_peers if p[0].name.lower() == self.peer_name]

        if not peer_configs:
            raise ValueError(f"Peer '{peer_name}' not found in configuration")

        self.peer_config, self.tunnel_profile, self.tunnel1_psk, self.tunnel2_psk = peer_configs[0]

    def create_tgw_hub(self):
        """Reference existing Transit Gateway (no creation)."""
        logger.info(f"PeerStack ({self.peer_name}): Referencing existing Transit Gateway...")

        config = pulumi.Config()
        tgw_id = config.get("transit_gateway_id")
        tgw_rt_id = config.get("transit_gateway_route_table_id")

        if not tgw_id or not tgw_rt_id:
            raise ValueError(
                "Peer-specific stack requires configuration:\n"
                "  pulumi config set transit_gateway_id <TGW_ID>\n"
                "  pulumi config set transit_gateway_route_table_id <TGW_RT_ID>"
            )

        hub = TransitGatewayReference(tgw_id, tgw_rt_id)
        logger.info(f"✓ Using existing TGW: {tgw_id}")
        return hub

    def create_eks_connectors(self) -> Dict[str, Any]:
        """Skip EKS connectors (managed by core stack)."""
        logger.info(f"PeerStack ({self.peer_name}): Skipping EKS connectors (managed by core)")
        return {}

    def create_vpn_connectors(self) -> Dict[str, Any]:
        """
        Create or attach VPN connector for this peer.

        Uses VPN pool to check if existing VPN can be reused.
        """
        logger.info(f"PeerStack ({self.peer_name}): Determining VPN action...")

        # Initialize VPN pool management
        vpn_registry = VpnRegistry()
        attachment_manager = VpnAttachmentManager(vpn_registry)
        attachment_executor = VpnAttachmentExecutor(vpn_registry)

        # Decide: create new or attach existing?
        decision = attachment_manager.decide(
            peer_name=self.peer_name,
            tunnel_profile=self.tunnel_profile.name
        )

        logger.info(f"  Decision: {decision.action}")
        logger.info(f"  Reason: {decision.reason}")

        # Execute decision and get attachment data
        attachment_data = attachment_executor.attach_vpn(decision, self.peer_name)

        # Return VPN connector data with attachment info
        return {
            self.peer_config.name: {
                "peer_config": self.peer_config,
                "tunnel_profile": self.tunnel_profile,
                "tunnel1_psk": self.tunnel1_psk,
                "tunnel2_psk": self.tunnel2_psk,
                "vpn_attachment_data": attachment_data,
            }
        }

    def create_snat_instances(self, hub, cluster_connectors) -> Dict[str, Any]:
        """Create SNAT instance ONLY if peer has provider_assigned_ip."""
        if self.peer_config.provider_assigned_ip:
            logger.info(f"PeerStack ({self.peer_name}): Creating SNAT instance...")
            return {
                self.peer_config.name: {
                    "peer_config": self.peer_config,
                    "hub": hub,
                    "cluster_connectors": cluster_connectors,
                }
            }
        else:
            logger.info(f"PeerStack ({self.peer_name}): No SNAT instance (no provider_assigned_ip)")
            return {}


def create_orchestrator(stack_name: str, config_manager, vpc_connector_class) -> StackOrchestrator:
    """Factory function to create appropriate orchestrator based on stack name."""

    if stack_name.startswith("peer-"):
        peer_name = stack_name[5:]  # Extract name from "peer-<name>"
        logger.info(f"🔹 Creating PeerStackOrchestrator for {peer_name}")
        return PeerStackOrchestrator(peer_name, config_manager, vpc_connector_class)
    else:
        logger.info(f"🔹 Creating CoreStackOrchestrator for {stack_name}")
        return CoreStackOrchestrator(stack_name, config_manager, vpc_connector_class)
