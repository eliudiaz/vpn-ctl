"""Infrastructure Provider Interface (Port)."""

from abc import ABC, abstractmethod
from typing import Dict, Any

from domain.models import VpnPeer, TunnelProfile


class IInfrastructureProvider(ABC):
    """
    Infrastructure Provider Interface (Port)

    Abstract interface for deploying VPN infrastructure.
    Implementations:
    - PulumiProvider
    - TerraformProvider
    - CloudFormationProvider

    Application logic depends on this interface, not concrete IaC tools.
    """

    @abstractmethod
    def create_vpn_peer(
        self,
        peer: VpnPeer,
        tunnel_profile: TunnelProfile,
    ) -> Dict[str, Any]:
        """
        Deploy VPN peer infrastructure.

        Args:
            peer: VpnPeer to deploy
            tunnel_profile: Tunnel profile for peer

        Returns:
            {
                'vpn_id': str,
                'tunnel1_ip': str,
                'tunnel2_ip': str,
                'cgw_id': str,
            }

        Raises:
            InfrastructureError: If deployment fails
        """
        pass

    @abstractmethod
    def destroy_vpn_peer(self, peer_name: str) -> None:
        """
        Destroy VPN peer infrastructure.

        Args:
            peer_name: Name of peer to destroy

        Raises:
            InfrastructureError: If destruction fails
        """
        pass

    @abstractmethod
    def get_peer_status(self, peer_name: str) -> Dict[str, Any]:
        """
        Query current peer status.

        Args:
            peer_name: Name of peer

        Returns:
            {
                'state': str,
                'tunnel1_status': str,
                'tunnel2_status': str,
                'tunnel1_last_change': datetime,
                'tunnel2_last_change': datetime,
            }

        Raises:
            InfrastructureError: If query fails
        """
        pass

    @abstractmethod
    def list_resources(self, peer_name: str) -> list:
        """
        List all resources for peer.

        Args:
            peer_name: Name of peer

        Returns:
            List of resource IDs/names

        Raises:
            InfrastructureError: If listing fails
        """
        pass

    @abstractmethod
    def preview_deployment(self, peer: VpnPeer, tunnel_profile: TunnelProfile) -> Dict[str, Any]:
        """
        Preview (dry-run) deployment changes.

        Args:
            peer: VpnPeer to preview
            tunnel_profile: Tunnel profile for peer

        Returns:
            {
                'changes': str,
                'resource_count': int,
                'estimated_monthly_cost': float,
            }

        Raises:
            InfrastructureError: If preview fails
        """
        pass
