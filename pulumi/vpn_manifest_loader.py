"""
VPN Manifest Loader - K8s-Style Peer Specifications

Loads VPN peer configurations from K8s-inspired YAML manifest files.
Each peer is a self-contained manifest with complete specification.

Usage:
    loader = VpnManifestLoader("../config")
    peer = loader.load_peer("vimenca")  # Load single peer
    all_peers = loader.load_all_peers()  # Load all peer manifests
"""

from pathlib import Path
from typing import Dict, List, Optional, Any
import yaml
import logging

logger = logging.getLogger(__name__)


class VpnManifestLoader:
    """Load K8s-style VPN peer manifests with tunnel profile resolution."""

    def __init__(self, config_dir: str = "../config", peers_subdir: str = "peers"):
        """
        Initialize manifest loader.

        Args:
            config_dir: Base config directory (default: ../config)
            peers_subdir: Subdirectory containing peer manifests (default: peers)
        """
        self.config_dir = Path(config_dir)
        self.peers_dir = self.config_dir / peers_subdir
        self.tunnel_profiles = {}

        # Load shared tunnel profiles
        self._load_tunnel_profiles()

        if not self.peers_dir.exists():
            logger.warning(f"Peers directory not found: {self.peers_dir}")
            logger.warning("Falling back to monolithic vpn-peers.yaml")

    def _load_tunnel_profiles(self) -> None:
        """Load shared tunnel profiles from tunnel-profiles.yaml."""
        profiles_file = self.config_dir / "tunnel-profiles.yaml"

        if not profiles_file.exists():
            logger.warning(f"Tunnel profiles file not found: {profiles_file}")
            return

        try:
            with open(profiles_file, "r") as f:
                doc = yaml.safe_load(f)
                if doc and "profiles" in doc:
                    self.tunnel_profiles = doc["profiles"]
                    logger.info(f"Loaded {len(self.tunnel_profiles)} tunnel profiles")
        except Exception as e:
            logger.error(f"Error loading tunnel profiles: {e}")

    def load_all_peers(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
        """
        Load all peer manifests from peers/ directory.

        Args:
            enabled_only: If True, only return peers with enabled=True

        Returns:
            List of peer manifest dictionaries
        """
        peers = []

        if not self.peers_dir.exists():
            logger.error(f"Peers directory not found: {self.peers_dir}")
            return peers

        for peer_file in sorted(self.peers_dir.glob("*.yaml")):
            try:
                peer = self.load_peer_from_file(peer_file)
                if peer:
                    # Filter by enabled flag if requested
                    if enabled_only and not peer.get("spec", {}).get("enabled", True):
                        logger.debug(f"Skipping disabled peer: {peer_file.name}")
                        continue

                    peers.append(peer)
            except Exception as e:
                logger.error(f"Error loading peer from {peer_file}: {e}")
                continue

        logger.info(f"Loaded {len(peers)} peer manifests")
        return peers

    def load_peer(
        self, peer_name: str, resolve_profile: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Load single peer manifest by name.

        Args:
            peer_name: Name of the peer (e.g., "vimenca", "apap")
            resolve_profile: If True, resolve tunnel profile references

        Returns:
            Peer manifest dictionary or None if not found
        """
        peer_file = self.peers_dir / f"{peer_name}.yaml"

        if not peer_file.exists():
            logger.error(f"Peer manifest not found: {peer_file}")
            return None

        return self.load_peer_from_file(peer_file, resolve_profile)

    def load_peer_from_file(
        self, peer_file: Path, resolve_profile: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Load peer manifest from file.

        Handles multi-document YAML files (K8s-style with spec and status).
        Extracts the spec document (first document).

        Args:
            peer_file: Path to peer manifest file
            resolve_profile: If True, resolve tunnel profile references

        Returns:
            Peer manifest dictionary or None on error
        """
        try:
            with open(peer_file, "r") as f:
                # Use safe_load_all to handle multi-document YAML (spec + status)
                docs = list(yaml.safe_load_all(f))

            if not docs or not docs[0]:
                logger.error(f"Empty peer manifest: {peer_file}")
                return None

            # Extract spec document (first document)
            manifest = docs[0]

            # If there's a status document (second document), store it for reference
            if len(docs) > 1 and docs[1]:
                manifest["_status"] = docs[1].get("status", {})

            # Validate basic structure
            if not self._validate_manifest(manifest):
                logger.error(f"Invalid peer manifest structure: {peer_file}")
                return None

            # Resolve tunnel profile reference
            if resolve_profile:
                self._resolve_profile(manifest)

            return manifest

        except Exception as e:
            logger.error(f"Error loading peer manifest {peer_file}: {e}")
            return None

    def _validate_manifest(self, manifest: Dict[str, Any]) -> bool:
        """Validate manifest has required fields."""
        required_fields = ["apiVersion", "kind", "metadata", "spec"]
        for field in required_fields:
            if field not in manifest:
                logger.error(f"Missing required field: {field}")
                return False

        # Validate kind
        if manifest.get("kind") != "VpnPeer":
            logger.error(f"Invalid kind: {manifest.get('kind')} (expected VpnPeer)")
            return False

        # Validate metadata has name
        if not manifest.get("metadata", {}).get("name"):
            logger.error("Missing metadata.name in manifest")
            return False

        return True

    def _resolve_profile(self, manifest: Dict[str, Any]) -> None:
        """Resolve tunnel profile reference in manifest."""
        tunnel_config = manifest.get("spec", {}).get("tunnel", {})

        # Support both old "profile" and new "profileName" field names
        profile_name = tunnel_config.get("profileName") or tunnel_config.get("profile")

        if not profile_name:
            peer_name = manifest.get("metadata", {}).get("name", "unknown")
            logger.warning(f"No tunnel profile specified for peer: {peer_name}")
            return

        if profile_name in self.tunnel_profiles:
            # Store resolved profile in manifest
            tunnel_config["_resolved_profile"] = self.tunnel_profiles[profile_name]
            logger.debug(f"Resolved tunnel profile: {profile_name}")
        else:
            peer_name = manifest.get("metadata", {}).get("name", "unknown")
            available = list(self.tunnel_profiles.keys())
            logger.error(
                f"Tunnel profile not found for peer {peer_name}: {profile_name}\n"
                f"Available profiles: {available}"
            )

    def extract_vpn_config(self, peer_manifest: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract VPN configuration from peer manifest.

        Converts manifest structure into flat dictionary suitable for
        use with orchestrator and Pulumi resources.

        Args:
            peer_manifest: Peer manifest dictionary

        Returns:
            VPN configuration dictionary
        """
        metadata = peer_manifest.get("metadata", {})
        spec = peer_manifest.get("spec", {})

        name = metadata.get("name")
        network_config = spec.get("network", {})
        tunnel_config = spec.get("tunnel", {})
        security_config = spec.get("security", {})
        snat_config = spec.get("snat", {})
        vpn_specific = spec.get("vpnSpecific", {})
        custom_params = spec.get("customParameters", {})

        return {
            # Basic peer info
            "name": name,
            "enabled": spec.get("enabled", True),
            # Device info
            "device_type": spec.get("device", {}).get("type"),
            "device_version": spec.get("device", {}).get("version"),
            "device_vendor": spec.get("device", {}).get("vendor"),
            # Network config
            "public_ip": network_config.get("public_ip"),
            "bgp_asn": network_config.get("bgp_asn"),
            "destination_cidrs": network_config.get("destination_cidrs", []),
            "imported_cidrs": network_config.get("imported_cidrs", []),
            # Tunnel config
            "tunnel_profile_name": tunnel_config.get("profile"),
            "tunnel_profile": tunnel_config.get("_resolved_profile"),
            "tunnel_overrides": tunnel_config.get("overrides", {}),
            # Security
            "psk_tunnel1": security_config.get("psk", {}).get("tunnel1"),
            "psk_tunnel2": security_config.get("psk", {}).get("tunnel2"),
            "psk_source": security_config.get("psk", {}).get("source", "plaintext"),
            # SNAT
            "snat_enabled": snat_config.get("enabled", False),
            "snat_type": snat_config.get("type"),
            "snat_provider_ip": snat_config.get("provider_assigned_ip"),
            # VPN-specific tuning
            "mss_clamping": vpn_specific.get("mss_clamping"),
            "static_routes_only": vpn_specific.get("static_routes_only", True),
            "routing_protocol": vpn_specific.get("routing_protocol", "static"),
            "replay_detection": vpn_specific.get("replay_detection", False),
            # Custom parameters by vendor
            "custom_parameters": custom_params,
            # Contacts
            "contacts": spec.get("contacts", []),
            # Full manifests for reference
            "_manifest": peer_manifest,
            "_spec": spec,
        }

    def get_enabled_peers(self) -> List[Dict[str, Any]]:
        """Get all enabled peer manifests."""
        all_peers = self.load_all_peers()
        return [p for p in all_peers if p.get("spec", {}).get("enabled", True)]

    def get_peers_by_label(
        self, label_name: str, label_value: str
    ) -> List[Dict[str, Any]]:
        """
        Get peers matching a specific label.

        Args:
            label_name: Label key (e.g., "vendor", "status")
            label_value: Label value (e.g., "checkpoint", "production")

        Returns:
            List of matching peer manifests
        """
        all_peers = self.load_all_peers()
        matching = []

        for peer in all_peers:
            labels = peer.get("metadata", {}).get("labels", {})
            if labels.get(label_name) == label_value:
                matching.append(peer)

        return matching

    def get_peer_names(self, enabled_only: bool = True) -> List[str]:
        """
        Get list of all peer names.

        Args:
            enabled_only: If True, only return enabled peers

        Returns:
            List of peer names
        """
        peers = self.get_enabled_peers() if enabled_only else self.load_all_peers()
        return [p.get("metadata", {}).get("name") for p in peers if p]


# Backward compatibility: Unified loader that tries manifests first, falls back to monolithic
class VpnConfigLoader:
    """
    Unified VPN configuration loader.

    Tries to load peer specs from K8s-style manifests first,
    falls back to monolithic vpn-peers.yaml for backward compatibility.
    """

    def __init__(self, config_dir: str = "../config"):
        self.config_dir = Path(config_dir)
        self.manifest_loader = VpnManifestLoader(config_dir)
        self.monolithic_path = self.config_dir / "vpn-peers.yaml"

    def load_peer(self, peer_name: str) -> Optional[Dict[str, Any]]:
        """
        Load single peer configuration.

        Tries manifest first, falls back to monolithic file.

        Args:
            peer_name: Name of the peer (e.g., "vimenca", "apap")

        Returns:
            Peer configuration dictionary
        """
        # Try manifest first
        peer_manifest = self.manifest_loader.load_peer(peer_name)
        if peer_manifest:
            return self.manifest_loader.extract_vpn_config(peer_manifest)

        # Fall back to monolithic file
        logger.info(f"Manifest not found for {peer_name}, trying monolithic vpn-peers.yaml")
        return self._load_from_monolithic(peer_name)

    def load_all_peers(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
        """
        Load all peer configurations.

        Prefers manifests, falls back to monolithic for missing peers.

        Args:
            enabled_only: If True, only return enabled peers

        Returns:
            List of peer configurations
        """
        peers = []

        # Load from manifests
        manifest_peers = self.manifest_loader.load_all_peers(enabled_only)
        for manifest in manifest_peers:
            config = self.manifest_loader.extract_vpn_config(manifest)
            peers.append(config)

        # Load any missing peers from monolithic file
        monolithic_peers = self._load_all_from_monolithic(enabled_only)
        existing_names = {p.get("name") for p in peers}

        for peer in monolithic_peers:
            if peer.get("name") not in existing_names:
                peers.append(peer)

        return peers

    def _load_from_monolithic(self, peer_name: str) -> Optional[Dict[str, Any]]:
        """Load single peer from monolithic vpn-peers.yaml."""
        if not self.monolithic_path.exists():
            return None

        try:
            with open(self.monolithic_path, "r") as f:
                doc = yaml.safe_load(f)

            peers = doc.get("peers", [])
            for peer in peers:
                if peer.get("name") == peer_name:
                    return peer

        except Exception as e:
            logger.error(f"Error loading from monolithic file: {e}")

        return None

    def _load_all_from_monolithic(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
        """Load all peers from monolithic vpn-peers.yaml."""
        if not self.monolithic_path.exists():
            return []

        try:
            with open(self.monolithic_path, "r") as f:
                doc = yaml.safe_load(f)

            peers = doc.get("peers", [])
            if enabled_only:
                return [p for p in peers if p.get("enabled", True)]
            return peers

        except Exception as e:
            logger.error(f"Error loading from monolithic file: {e}")

        return []
