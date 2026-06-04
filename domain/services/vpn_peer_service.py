"""VPN Peer Domain Service."""

from typing import List

from domain.models import VpnPeer, TunnelProfile
from domain.repositories import VpnPeerRepository, TunnelProfileRepository
from domain.exceptions import (
    DomainValidationError,
    PeerNotFoundError,
    DuplicatePeerError,
    ProfileNotFoundError,
)


class VpnPeerService:
    """
    VPN Peer Domain Service

    Orchestrates business logic for VPN peer lifecycle.
    Provider-agnostic: works with any infrastructure backend.
    """

    def __init__(
        self,
        peer_repo: VpnPeerRepository,
        profile_repo: TunnelProfileRepository,
    ):
        self.peer_repo = peer_repo
        self.profile_repo = profile_repo

    def create_peer(
        self,
        name: str,
        public_ip: str,
        bgp_asn: int,
        tunnel_profile_name: str,
        destination_cidrs: list,
        **kwargs,
    ) -> VpnPeer:
        """
        Create a new VPN peer.

        Args:
            name: Peer name
            public_ip: Public IP address
            bgp_asn: BGP AS number
            tunnel_profile_name: Tunnel profile to use
            destination_cidrs: Destination CIDR blocks
            **kwargs: Additional peer attributes

        Returns:
            Created VpnPeer

        Raises:
            DomainValidationError: If peer data is invalid
            DuplicatePeerError: If peer already exists
            ProfileNotFoundError: If profile not found
        """
        # Check if peer already exists
        if self.peer_repo.exists(name):
            raise DuplicatePeerError(f"Peer already exists: {name}")

        # Validate profile exists
        profile = self.profile_repo.get(tunnel_profile_name)
        if not profile:
            raise ProfileNotFoundError(
                f"Tunnel profile not found: {tunnel_profile_name}"
            )

        # Create peer entity (validation in __post_init__)
        peer = VpnPeer(
            name=name,
            public_ip=public_ip,
            bgp_asn=bgp_asn,
            tunnel_profile_name=tunnel_profile_name,
            destination_cidrs=frozenset(destination_cidrs),
            **kwargs,
        )

        # Persist
        self.peer_repo.save(peer)

        return peer

    def get_peer(self, name: str) -> VpnPeer:
        """
        Load a peer by name.

        Args:
            name: Peer name

        Returns:
            VpnPeer

        Raises:
            PeerNotFoundError: If peer not found
        """
        peer = self.peer_repo.get(name)
        if not peer:
            raise PeerNotFoundError(f"Peer not found: {name}")
        return peer

    def get_all_peers(self) -> List[VpnPeer]:
        """
        Get all peers.

        Returns:
            List of VpnPeer objects
        """
        return self.peer_repo.get_all()

    def get_enabled_peers(self) -> List[VpnPeer]:
        """
        Get all enabled peers.

        Returns:
            List of enabled VpnPeer objects
        """
        return self.peer_repo.get_enabled()

    def delete_peer(self, name: str) -> None:
        """
        Delete a peer.

        Args:
            name: Peer name

        Raises:
            PeerNotFoundError: If peer not found
        """
        if not self.peer_repo.exists(name):
            raise PeerNotFoundError(f"Peer not found: {name}")

        self.peer_repo.delete(name)

    def validate_peer(self, peer: VpnPeer) -> tuple[bool, List[str]]:
        """
        Validate a peer against business rules.

        Args:
            peer: VpnPeer to validate

        Returns:
            (is_valid, list_of_errors)
        """
        errors = []

        # Check tunnel profile exists
        if not self.profile_repo.exists(peer.tunnel_profile_name):
            errors.append(f"Tunnel profile not found: {peer.tunnel_profile_name}")

        # Check peer name uniqueness (if updating)
        if self.peer_repo.exists(peer.name):
            errors.append(f"Peer already exists: {peer.name}")

        return len(errors) == 0, errors

    def peer_exists(self, name: str) -> bool:
        """
        Check if peer exists.

        Args:
            name: Peer name

        Returns:
            True if exists, False otherwise
        """
        return self.peer_repo.exists(name)

    def get_profile(self, name: str) -> TunnelProfile:
        """
        Get tunnel profile by name.

        Args:
            name: Profile name

        Returns:
            TunnelProfile

        Raises:
            ProfileNotFoundError: If profile not found
        """
        profile = self.profile_repo.get(name)
        if not profile:
            raise ProfileNotFoundError(f"Profile not found: {name}")
        return profile
