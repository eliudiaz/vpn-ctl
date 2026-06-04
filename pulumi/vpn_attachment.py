"""
VPN Attachment Logic - Attach/detach VPN resources to/from peers.

Handles the connection between peer specs and VPN pool resources.
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass
from vpn_registry import VpnRegistry, VpnPoolEntry
import logging

logger = logging.getLogger(__name__)


@dataclass
class VpnAttachmentDecision:
    """Decision about how to handle VPN for a peer."""

    action: str  # 'create' | 'attach'
    vpn_entry: Optional[VpnPoolEntry] = None  # If attaching
    reason: str = ""  # Why this decision was made


class VpnAttachmentManager:
    """
    Determines whether to create new VPN or attach to existing one.

    Decision logic:
    1. Is there an attached VPN for this peer? → Reuse it
    2. Is there a detached VPN matching profile? → Reuse it
    3. No existing VPN? → Create new one
    """

    def __init__(self, registry: VpnRegistry):
        self.registry = registry

    def decide(
        self,
        peer_name: str,
        tunnel_profile: str
    ) -> VpnAttachmentDecision:
        """
        Decide whether to create or attach VPN for a peer.

        Args:
            peer_name: Name of the peer
            tunnel_profile: Tunnel profile name (e.g., 'checkpoint_r80')

        Returns:
            VpnAttachmentDecision with action and details
        """
        # Step 1: Check if peer has existing VPN (attached or previously attached)
        existing_vpn = self.registry.get_vpn(peer_name)
        if existing_vpn:
            if existing_vpn.state == 'attached':
                logger.info(f"Peer {peer_name}: VPN already attached")
                return VpnAttachmentDecision(
                    action='attach',
                    vpn_entry=existing_vpn,
                    reason=f"VPN already attached (ID: {existing_vpn.vpn_id})"
                )
            elif existing_vpn.state == 'detached':
                logger.info(f"Peer {peer_name}: Reusing detached VPN")
                return VpnAttachmentDecision(
                    action='attach',
                    vpn_entry=existing_vpn,
                    reason=f"Reusing detached VPN (ID: {existing_vpn.vpn_id}, preserved {existing_vpn.preserved_count} times)"
                )

        # Step 2: Check if there's a detached VPN matching this profile
        available_vpn = self.registry.get_detached_vpn(tunnel_profile)
        if available_vpn:
            logger.info(f"Peer {peer_name}: Found available VPN in pool")
            return VpnAttachmentDecision(
                action='attach',
                vpn_entry=available_vpn,
                reason=f"Found available VPN in pool (ID: {available_vpn.vpn_id}, preserved {available_vpn.preserved_count} times)"
            )

        # Step 3: No existing VPN, create new one
        logger.info(f"Peer {peer_name}: Creating new VPN")
        return VpnAttachmentDecision(
            action='create',
            reason=f"No existing VPN found, creating new one with profile {tunnel_profile}"
        )


class VpnAttachmentExecutor:
    """
    Executes VPN attachment decisions.

    Handles:
    - Attaching VPN to peer
    - Registering new VPN
    - Updating registry state
    """

    def __init__(self, registry: VpnRegistry):
        self.registry = registry

    def attach_vpn(
        self,
        decision: VpnAttachmentDecision,
        peer_name: str
    ) -> Dict[str, Any]:
        """
        Execute VPN attachment for peer.

        Returns data for VpnConnector to use.
        """
        if decision.action == 'attach':
            vpn = decision.vpn_entry
            logger.info(f"Attaching VPN {vpn.vpn_id} to peer {peer_name}")

            # Mark as attached in registry
            self.registry.mark_attached(vpn.vpn_id, peer_name)

            return {
                'action': 'attach',
                'vpn_id': vpn.vpn_id,
                'customer_gateway_id': vpn.customer_gateway_id,
                'tunnel1_ip': vpn.tunnel1_ip,
                'tunnel2_ip': vpn.tunnel2_ip,
                'reason': decision.reason,
                'preserved': vpn.preserved_count > 0,
            }

        elif decision.action == 'create':
            logger.info(f"Will create new VPN for peer {peer_name}")

            return {
                'action': 'create',
                'reason': decision.reason,
            }

        else:
            raise ValueError(f"Unknown action: {decision.action}")

    def register_new_vpn(
        self,
        vpn_id: str,
        customer_gateway_id: str,
        peer_name: str,
        tunnel_profile: str,
        tunnel1_ip: str,
        tunnel2_ip: str
    ) -> VpnPoolEntry:
        """
        Register newly created VPN in pool.

        Called after VPN is created.
        """
        return self.registry.register_vpn(
            vpn_id=vpn_id,
            customer_gateway_id=customer_gateway_id,
            peer_name=peer_name,
            tunnel_profile=tunnel_profile,
            tunnel1_ip=tunnel1_ip,
            tunnel2_ip=tunnel2_ip
        )

    def detach_vpn(self, peer_name: str):
        """
        Detach VPN when peer is destroyed.

        Marks VPN as detached (preserves for reuse).
        """
        vpn = self.registry.mark_detached(peer_name)
        if vpn:
            logger.info(f"✓ VPN detached from peer {peer_name} (preserved for reuse)")
            logger.info(f"  Tunnel IPs: {vpn.tunnel1_ip}, {vpn.tunnel2_ip}")
        else:
            logger.warning(f"No VPN found to detach for peer {peer_name}")
