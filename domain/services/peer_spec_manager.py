"""
Peer Spec Manager

Manages reading and writing peer specifications to YAML files.
Handles test endpoint management with persistence to config/vpn-peers.yaml.
"""

from pathlib import Path
from typing import List, Optional
import yaml

from domain.models.test_endpoint import TestEndpoint
from domain.exceptions import DomainValidationError


class PeerSpecManager:
    """Manages peer specifications in YAML format."""

    def __init__(self, config_path: Path = None):
        """Initialize with path to vpn-peers.yaml config file."""
        if config_path is None:
            config_path = Path("config/vpn-peers.yaml")
        self.config_path = config_path

    def load_peer_spec(self, peer_name: str) -> dict:
        """Load peer specification from YAML."""
        if not self.config_path.exists():
            raise DomainValidationError(f"Config file not found: {self.config_path}")

        with open(self.config_path) as f:
            config = yaml.safe_load(f) or {}

        peers = config.get('peers', [])
        for peer in peers:
            if peer['name'].lower() == peer_name.lower():
                return peer

        raise DomainValidationError(f"Peer not found: {peer_name}")

    def list_test_endpoints(self, peer_name: str) -> List[TestEndpoint]:
        """List all test endpoints for a peer."""
        spec = self.load_peer_spec(peer_name)
        endpoints = []

        for ep_data in spec.get('test_endpoints', []):
            endpoints.append(TestEndpoint.from_dict(ep_data))

        return endpoints

    def add_test_endpoint(
        self,
        peer_name: str,
        target: str,
        protocol: str,
        port: Optional[int] = None,
    ) -> List[TestEndpoint]:
        """Add test endpoint to peer and persist to YAML."""
        # Validate endpoint
        endpoint = TestEndpoint(target=target, protocol=protocol, port=port)

        # Load config
        with open(self.config_path) as f:
            config = yaml.safe_load(f) or {'peers': []}

        # Find and update peer
        peers = config.get('peers', [])
        peer_found = False

        for peer in peers:
            if peer['name'].lower() == peer_name.lower():
                peer_found = True

                # Initialize test_endpoints if not present
                if 'test_endpoints' not in peer:
                    peer['test_endpoints'] = []

                # Check if endpoint already exists
                for existing in peer['test_endpoints']:
                    if existing['target'] == target:
                        raise DomainValidationError(
                            f"Test endpoint {target} already exists for peer {peer_name}"
                        )

                # Add endpoint
                peer['test_endpoints'].append(endpoint.to_dict())
                break

        if not peer_found:
            raise DomainValidationError(f"Peer not found: {peer_name}")

        # Write back to YAML
        self._write_config(config)

        # Return updated list
        return self.list_test_endpoints(peer_name)

    def remove_test_endpoint(self, peer_name: str, target: str) -> List[TestEndpoint]:
        """Remove test endpoint from peer and persist to YAML."""
        # Load config
        with open(self.config_path) as f:
            config = yaml.safe_load(f) or {'peers': []}

        # Find and update peer
        peers = config.get('peers', [])
        peer_found = False
        endpoint_found = False

        for peer in peers:
            if peer['name'].lower() == peer_name.lower():
                peer_found = True

                if 'test_endpoints' in peer:
                    original_count = len(peer['test_endpoints'])
                    peer['test_endpoints'] = [
                        ep for ep in peer['test_endpoints']
                        if ep['target'] != target
                    ]
                    endpoint_found = original_count > len(peer['test_endpoints'])

                break

        if not peer_found:
            raise DomainValidationError(f"Peer not found: {peer_name}")

        if not endpoint_found:
            raise DomainValidationError(
                f"Test endpoint {target} not found for peer {peer_name}"
            )

        # Write back to YAML
        self._write_config(config)

        # Return updated list
        return self.list_test_endpoints(peer_name)

    def _write_config(self, config: dict) -> None:
        """Write configuration back to YAML file, preserving format."""
        with open(self.config_path, 'w') as f:
            yaml.dump(
                config,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )
