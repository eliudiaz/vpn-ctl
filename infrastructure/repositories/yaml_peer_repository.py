"""YAML-based VPN Peer Repository (Adapter)."""

from pathlib import Path
from typing import List, Optional
import yaml

from domain.models import VpnPeer
from domain.repositories import VpnPeerRepository
from domain.exceptions import DomainError


class YamlVpnPeerRepository(VpnPeerRepository):
    """Loads/saves VPN peers from/to YAML spec files."""

    def __init__(self, peers_dir: Path = None):
        """
        Initialize YAML peer repository.

        Args:
            peers_dir: Directory containing peer YAML files
                      (default: config/peers/)
        """
        self.peers_dir = peers_dir or Path("config/peers")
        self.peers_dir.mkdir(parents=True, exist_ok=True)

    def save(self, peer: VpnPeer) -> None:
        """Save peer to YAML file."""
        spec_file = self.peers_dir / f"{peer.name}.yaml"

        spec = {
            "apiVersion": "aff-atg/v1",
            "kind": "VpnPeer",
            "metadata": {
                "name": str(peer.name),
                "labels": peer.tags,
            },
            "spec": {
                "enabled": True,
                "publicIp": str(peer.public_ip),
                "bgpAsn": int(peer.bgp_asn),
                "deviceType": peer.device_type,
                "deviceVersion": peer.device_version,
                "tunnelProfile": peer.tunnel_profile_name,
                "destinationCidrs": [str(c) for c in peer.destination_cidrs],
                "importedCidrs": [str(c) for c in peer.imported_cidrs],
                "psk": {
                    "tunnel1": peer.psk_tunnel1.secure_value,
                    "tunnel2": peer.psk_tunnel2.secure_value,
                },
                "contacts": [
                    {
                        "name": c.name,
                        "email": c.email,
                        "phone": c.phone,
                    }
                    for c in peer.contacts
                ],
            },
        }

        try:
            with open(spec_file, "w") as f:
                yaml.dump(spec, f, default_flow_style=False, sort_keys=False)
        except Exception as e:
            raise DomainError(f"Failed to save peer {peer.name}: {e}")

    def get(self, name: str) -> Optional[VpnPeer]:
        """Load peer from YAML file."""
        spec_file = self.peers_dir / f"{name}.yaml"

        if not spec_file.exists():
            return None

        try:
            with open(spec_file) as f:
                data = yaml.safe_load(f)

            spec = data["spec"]
            return VpnPeer.from_dict(
                name=data["metadata"]["name"],
                spec=spec,
                psk_tunnel1=spec.get("psk", {}).get("tunnel1"),
                psk_tunnel2=spec.get("psk", {}).get("tunnel2"),
            )
        except Exception as e:
            raise DomainError(f"Failed to load peer {name}: {e}")

    def get_all(self) -> List[VpnPeer]:
        """Load all peer YAML files."""
        peers = []

        for spec_file in self.peers_dir.glob("*.yaml"):
            # Skip template file
            if spec_file.name == "_template.yaml":
                continue

            try:
                peer_name = spec_file.stem
                peer = self.get(peer_name)
                if peer:
                    peers.append(peer)
            except Exception as e:
                print(f"Warning: Failed to load {spec_file.name}: {e}")

        return sorted(peers, key=lambda p: str(p.name))

    def get_enabled(self) -> List[VpnPeer]:
        """Get all enabled peers."""
        # All loaded peers are considered enabled (can add flag later)
        return self.get_all()

    def delete(self, name: str) -> None:
        """Delete peer YAML file."""
        spec_file = self.peers_dir / f"{name}.yaml"

        try:
            if spec_file.exists():
                spec_file.unlink()
        except Exception as e:
            raise DomainError(f"Failed to delete peer {name}: {e}")

    def exists(self, name: str) -> bool:
        """Check if peer spec file exists."""
        return (self.peers_dir / f"{name}.yaml").exists()
