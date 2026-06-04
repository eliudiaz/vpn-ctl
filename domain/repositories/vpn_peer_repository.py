"""VPN Peer Repository Interface (Port)."""

from abc import ABC, abstractmethod
from typing import List, Optional

from domain.models import VpnPeer


class VpnPeerRepository(ABC):
    """
    VPN Peer Repository (Port)

    Abstract interface for VPN peer persistence.
    Can be implemented by:
    - YamlVpnPeerRepository (YAML files)
    - SqlVpnPeerRepository (SQL database)
    - S3VpnPeerRepository (AWS S3)

    Domain logic depends on this interface, NOT concrete implementations.
    """

    @abstractmethod
    def save(self, peer: VpnPeer) -> None:
        """
        Persist a VPN peer.

        Args:
            peer: VpnPeer to save

        Raises:
            DomainError: If save fails
        """
        pass

    @abstractmethod
    def get(self, name: str) -> Optional[VpnPeer]:
        """
        Load a peer by name.

        Args:
            name: Peer name

        Returns:
            VpnPeer if found, None otherwise
        """
        pass

    @abstractmethod
    def get_all(self) -> List[VpnPeer]:
        """
        Load all peers.

        Returns:
            List of VpnPeer objects
        """
        pass

    @abstractmethod
    def get_enabled(self) -> List[VpnPeer]:
        """
        Load all enabled peers.

        Returns:
            List of enabled VpnPeer objects
        """
        pass

    @abstractmethod
    def delete(self, name: str) -> None:
        """
        Delete a peer.

        Args:
            name: Peer name to delete

        Raises:
            DomainError: If delete fails
        """
        pass

    @abstractmethod
    def exists(self, name: str) -> bool:
        """
        Check if peer exists.

        Args:
            name: Peer name

        Returns:
            True if peer exists, False otherwise
        """
        pass
