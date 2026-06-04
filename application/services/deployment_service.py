"""Deployment Service - Use case for deploying VPN peers."""

from typing import Dict, Any

from domain.models import VpnPeer, TunnelProfile
from domain.services import VpnPeerService
from domain.repositories import TunnelProfileRepository
from infrastructure.providers.interfaces import IInfrastructureProvider


class DeploymentService:
    """
    Deployment Service

    Orchestrates VPN peer deployment use case.
    Provider-injected: same code works with Pulumi, Terraform, CloudFormation.
    """

    def __init__(
        self,
        provider: IInfrastructureProvider,
        peer_service: VpnPeerService,
        profile_repo: TunnelProfileRepository,
    ):
        """
        Initialize deployment service with dependencies.

        Args:
            provider: Infrastructure provider (Pulumi, Terraform, etc)
            peer_service: VPN peer domain service
            profile_repo: Tunnel profile repository
        """
        self.provider = provider
        self.peer_service = peer_service
        self.profile_repo = profile_repo

    def deploy_peer(self, peer: VpnPeer) -> Dict[str, Any]:
        """
        Deploy a VPN peer.

        Args:
            peer: VpnPeer to deploy

        Returns:
            {
                'vpn_id': str,
                'tunnel1_ip': str,
                'tunnel2_ip': str,
                'cgw_id': str,
            }

        Raises:
            DeploymentError: If deployment fails
        """
        # Validate peer
        is_valid, errors = self.peer_service.validate_peer(peer)
        if not is_valid:
            raise ValueError(f"Peer invalid: {', '.join(errors)}")

        # Get tunnel profile
        profile = self.profile_repo.get(peer.tunnel_profile_name)
        if not profile:
            raise ValueError(f"Profile not found: {peer.tunnel_profile_name}")

        # Deploy via provider (could be Pulumi, Terraform, etc)
        result = self.provider.create_vpn_peer(peer, profile)

        return result

    def destroy_peer(self, peer_name: str) -> None:
        """
        Destroy a VPN peer.

        Args:
            peer_name: Name of peer to destroy

        Raises:
            DeploymentError: If destruction fails
        """
        self.provider.destroy_vpn_peer(peer_name)

    def get_peer_status(self, peer_name: str) -> Dict[str, Any]:
        """
        Get current peer status.

        Args:
            peer_name: Name of peer

        Returns:
            Status dictionary
        """
        return self.provider.get_peer_status(peer_name)

    def preview_deployment(self, peer: VpnPeer) -> Dict[str, Any]:
        """
        Preview deployment changes (dry-run).

        Args:
            peer: Peer to preview

        Returns:
            Preview summary
        """
        profile = self.profile_repo.get(peer.tunnel_profile_name)
        if not profile:
            raise ValueError(f"Profile not found: {peer.tunnel_profile_name}")

        return self.provider.preview_deployment(peer, profile)
