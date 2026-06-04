"""
VPN Pool Registry - Manages persistent state of VPN resources.

Tracks VPN resources as a reusable pool:
- VPN ownership and attachment state
- Tunnel IP persistence
- Preservation count (reuse tracking)
- Peer attachment history

Registry is stored in config/vpn-pool.yaml for version control visibility.
"""

from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path
import yaml
import logging

logger = logging.getLogger(__name__)


@dataclass
class VpnPoolEntry:
    """Single VPN resource in the pool."""

    vpn_id: str                           # AWS VPN Connection ID
    customer_gateway_id: str              # AWS Customer Gateway ID
    peer_name: Optional[str] = None       # Which peer attached (None = detached)
    state: str = "detached"               # attached | detached | orphaned
    tunnel_profile: str = "checkpoint_r80"  # Which profile (for matching)
    tunnel1_ip: Optional[str] = None      # AWS tunnel 1 IP (preserved)
    tunnel2_ip: Optional[str] = None      # AWS tunnel 2 IP (preserved)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    attached_at: Optional[str] = None     # When last attached
    detached_at: Optional[str] = None     # When last detached
    preserved_count: int = 0              # How many times reused

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for YAML serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'VpnPoolEntry':
        """Create from dict (YAML deserialization)."""
        return cls(**data)


class VpnRegistry:
    """
    Manages VPN pool as persistent YAML file.

    Responsibilities:
    - Track which VPNs exist and their state
    - Attach/detach VPNs to/from peers
    - Query for available VPNs by profile
    - Persist state across deployments
    """

    def __init__(self, registry_file: str = "config/vpn-pool.yaml"):
        """
        Initialize registry, creating file if needed.

        Args:
            registry_file: Path to YAML registry file
        """
        self.registry_path = Path(registry_file)
        self.data = self._load_registry()

    def _load_registry(self) -> Dict[str, Any]:
        """Load registry from YAML file, create if not exists."""
        if not self.registry_path.exists():
            logger.info(f"Creating new VPN registry: {self.registry_path}")
            initial_data = {
                'version': '1.0',
                'created_at': datetime.utcnow().isoformat(),
                'vpns': []
            }
            self._save_registry(initial_data)
            return initial_data

        try:
            with open(self.registry_path, 'r') as f:
                data = yaml.safe_load(f) or {'vpns': []}
                return data
        except Exception as e:
            logger.error(f"Failed to load VPN registry: {e}")
            return {'vpns': []}

    def _save_registry(self, data: Optional[Dict[str, Any]] = None):
        """Save registry to YAML file."""
        if data is None:
            data = self.data

        data['updated_at'] = datetime.utcnow().isoformat()

        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.registry_path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

        logger.debug(f"VPN registry saved: {self.registry_path}")

    def get_vpn(self, peer_name: str) -> Optional[VpnPoolEntry]:
        """
        Get VPN entry for peer (attached or previously attached).

        Args:
            peer_name: Name of the peer

        Returns:
            VpnPoolEntry if found, None otherwise
        """
        for vpn_dict in self.data.get('vpns', []):
            vpn = VpnPoolEntry.from_dict(vpn_dict)
            if vpn.peer_name == peer_name:
                return vpn
        return None

    def get_vpn_by_id(self, vpn_id: str) -> Optional[VpnPoolEntry]:
        """Get VPN entry by AWS VPN Connection ID."""
        for vpn_dict in self.data.get('vpns', []):
            vpn = VpnPoolEntry.from_dict(vpn_dict)
            if vpn.vpn_id == vpn_id:
                return vpn
        return None

    def get_detached_vpn(self, tunnel_profile: str) -> Optional[VpnPoolEntry]:
        """
        Get any detached VPN ready for reuse (matching profile).

        Used when creating new peer that matches an existing profile.
        Returns the oldest detached VPN (FIFO reuse).

        Args:
            tunnel_profile: Which profile to match (e.g., 'checkpoint_r80')

        Returns:
            VpnPoolEntry if available, None otherwise
        """
        detached = [
            VpnPoolEntry.from_dict(v)
            for v in self.data.get('vpns', [])
            if v.get('state') == 'detached' and v.get('tunnel_profile') == tunnel_profile
        ]

        if detached:
            # Return oldest detached (longest waiting for reuse)
            return sorted(detached, key=lambda v: v.detached_at or '')[0]

        return None

    def get_attached_vpns(self) -> List[VpnPoolEntry]:
        """Get all currently attached VPNs."""
        return [
            VpnPoolEntry.from_dict(v)
            for v in self.data.get('vpns', [])
            if v.get('state') == 'attached'
        ]

    def get_all_vpns(self) -> List[VpnPoolEntry]:
        """Get all VPNs in registry."""
        return [
            VpnPoolEntry.from_dict(v)
            for v in self.data.get('vpns', [])
        ]

    def register_vpn(
        self,
        vpn_id: str,
        customer_gateway_id: str,
        peer_name: str,
        tunnel_profile: str,
        tunnel1_ip: str,
        tunnel2_ip: str
    ) -> VpnPoolEntry:
        """
        Register new VPN in pool.

        Called when a new VPN connection is created.
        """
        entry = VpnPoolEntry(
            vpn_id=vpn_id,
            customer_gateway_id=customer_gateway_id,
            peer_name=peer_name,
            state='attached',
            tunnel_profile=tunnel_profile,
            tunnel1_ip=tunnel1_ip,
            tunnel2_ip=tunnel2_ip,
            attached_at=datetime.utcnow().isoformat()
        )

        self.data['vpns'].append(entry.to_dict())
        self._save_registry()

        logger.info(f"✓ Registered VPN in pool: {vpn_id} (peer: {peer_name})")
        logger.info(f"  Tunnel 1: {tunnel1_ip}")
        logger.info(f"  Tunnel 2: {tunnel2_ip}")

        return entry

    def mark_attached(self, vpn_id: str, peer_name: str):
        """
        Mark VPN as attached to peer.

        Called when reusing a detached VPN.
        Increments preserved_count to track reuse.
        """
        vpn = self.get_vpn_by_id(vpn_id)
        if not vpn:
            logger.error(f"VPN not found in registry: {vpn_id}")
            return

        # Update in data list
        for vpn_dict in self.data.get('vpns', []):
            if vpn_dict.get('vpn_id') == vpn_id:
                vpn_dict['peer_name'] = peer_name
                vpn_dict['state'] = 'attached'
                vpn_dict['attached_at'] = datetime.utcnow().isoformat()
                vpn_dict['preserved_count'] = vpn_dict.get('preserved_count', 0) + 1
                break

        self._save_registry()

        logger.info(f"✓ Attached VPN to peer: {vpn_id} → {peer_name}")
        logger.info(f"  Preserved count: {vpn.preserved_count + 1}")

    def mark_detached(self, peer_name: str) -> Optional[VpnPoolEntry]:
        """
        Mark VPN as detached (peer destroyed).

        Preserves VPN and tunnel IPs for future reuse.
        """
        vpn = self.get_vpn(peer_name)
        if not vpn:
            logger.warning(f"No VPN found for peer: {peer_name}")
            return None

        # Update in data list
        for vpn_dict in self.data.get('vpns', []):
            if vpn_dict.get('vpn_id') == vpn.vpn_id:
                vpn_dict['peer_name'] = None
                vpn_dict['state'] = 'detached'
                vpn_dict['detached_at'] = datetime.utcnow().isoformat()
                break

        self._save_registry()

        logger.info(f"✓ Detached VPN from peer: {vpn.vpn_id}")
        logger.info(f"  Tunnel IPs preserved: {vpn.tunnel1_ip}, {vpn.tunnel2_ip}")
        logger.info(f"  Ready for reuse by another peer")

        return vpn

    def get_stats(self) -> Dict[str, int]:
        """Get pool statistics."""
        vpns = self.data.get('vpns', [])
        return {
            'total': len(vpns),
            'attached': sum(1 for v in vpns if v.get('state') == 'attached'),
            'detached': sum(1 for v in vpns if v.get('state') == 'detached'),
            'orphaned': sum(1 for v in vpns if v.get('state') == 'orphaned'),
            'total_preservations': sum(v.get('preserved_count', 0) for v in vpns),
        }
