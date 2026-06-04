"""
VPN Peer Lifecycle Management - Handle peer creation/destruction with VPN pool.

Provides hooks to:
- Mark VPN as detached when peer is destroyed
- Clean up peer-specific resources (routes, SNAT, monitoring)
- Track peer creation/destruction history
"""

from vpn_registry import VpnRegistry
from vpn_attachment import VpnAttachmentExecutor
import logging

logger = logging.getLogger(__name__)


class VpnPeerLifecycleManager:
    """
    Manages VPN lifecycle during peer creation and destruction.

    Responsibilities:
    - On peer creation: Register VPN in pool
    - On peer destruction: Mark VPN as detached (preserve for reuse)
    """

    def __init__(self):
        self.vpn_registry = VpnRegistry()
        self.vpn_executor = VpnAttachmentExecutor(self.vpn_registry)

    def on_peer_created(self, peer_name: str, vpn_id: str):
        """
        Called when peer is successfully created.

        Ensures VPN is registered in pool.
        """
        vpn = self.vpn_registry.get_vpn_by_id(vpn_id)
        if vpn:
            logger.info(f"✓ Peer {peer_name} created with VPN {vpn_id}")
            logger.info(f"  Tunnel IPs: {vpn.tunnel1_ip}, {vpn.tunnel2_ip}")
        else:
            logger.warning(f"VPN {vpn_id} not found in registry after peer creation")

    def on_peer_destroyed(self, peer_name: str):
        """
        Called when peer is about to be destroyed.

        Marks VPN as detached so it can be reused by another peer.
        """
        logger.info(f"Peer destruction hook: {peer_name}")
        vpn = self.vpn_executor.detach_vpn(peer_name)
        if vpn:
            logger.info(f"✓ VPN {vpn.vpn_id} preserved for reuse")
            logger.info(f"  Can be reused by peers with profile: {vpn.tunnel_profile}")
        return vpn

    def get_pool_stats(self) -> dict:
        """Get current pool statistics."""
        return self.vpn_registry.get_stats()

    def list_vpns(self, state: str = None) -> list:
        """
        List VPNs in pool.

        Args:
            state: Filter by state ('attached', 'detached', 'orphaned'), or None for all

        Returns:
            List of VPN pool entries
        """
        vpns = self.vpn_registry.get_all_vpns()

        if state:
            vpns = [v for v in vpns if v.state == state]

        return vpns

    def print_pool_status(self):
        """Print current pool status to logger."""
        vpns = self.vpn_registry.get_all_vpns()
        stats = self.vpn_registry.get_stats()

        logger.info("=" * 80)
        logger.info("VPN POOL STATUS")
        logger.info("=" * 80)
        logger.info(f"Total VPNs: {stats['total']}")
        logger.info(f"  Attached: {stats['attached']}")
        logger.info(f"  Detached: {stats['detached']}")
        logger.info(f"  Orphaned: {stats['orphaned']}")
        logger.info(f"Total preservations: {stats['total_preservations']}")
        logger.info("")

        for vpn in sorted(vpns, key=lambda v: v.peer_name or ""):
            state_icon = "🟢" if vpn.state == "attached" else "🟡" if vpn.state == "detached" else "🔴"
            peer = vpn.peer_name or "(detached)"
            logger.info(f"{state_icon} {vpn.vpn_id} ({peer})")
            logger.info(f"   Profile: {vpn.tunnel_profile}")
            logger.info(f"   Tunnel IPs: {vpn.tunnel1_ip}, {vpn.tunnel2_ip}")
            logger.info(f"   Preserved: {vpn.preserved_count} times")
            logger.info("")

        logger.info("=" * 80)


def log_pool_cleanup_guide():
    """Print guide for manual VPN cleanup (if needed)."""
    guide = """
MANUAL VPN CLEANUP (Optional)
=============================

If you need to permanently delete a detached VPN (to save on monthly costs):

1. List detached VPNs:
   vpc_peer_lifecycle = VpnPeerLifecycleManager()
   detached = vpc_peer_lifecycle.list_vpns(state='detached')

2. Delete VPN permanently (CAREFUL - cannot undo!):
   # In Pulumi, manually: pulumi destroy peer-[name] --remove
   # Then manually delete VPN in AWS console or via AWS CLI:
   aws ec2 delete-vpn-connection --vpn-connection-id vpn-xxx
   aws ec2 delete-customer-gateway --customer-gateway-id cgw-xxx

3. Remove from registry:
   registry = VpnRegistry()
   registry.data['vpns'] = [v for v in registry.data['vpns'] if v['vpn_id'] != 'vpn-xxx']
   registry._save_registry()

Note: Deleted VPNs cannot be reused. Only delete if you're sure the VPN won't be needed again.
"""
    logger.info(guide)
