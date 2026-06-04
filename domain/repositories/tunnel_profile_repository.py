"""Tunnel Profile Repository Interface (Port)."""

from abc import ABC, abstractmethod
from typing import List, Optional

from domain.models import TunnelProfile


class TunnelProfileRepository(ABC):
    """
    Tunnel Profile Repository (Port)

    Abstract interface for tunnel profile persistence.
    Implementations:
    - YamlTunnelProfileRepository (YAML file)
    - SqlTunnelProfileRepository (SQL database)
    """

    @abstractmethod
    def save(self, profile: TunnelProfile) -> None:
        """
        Persist a tunnel profile.

        Args:
            profile: TunnelProfile to save

        Raises:
            DomainError: If save fails
        """
        pass

    @abstractmethod
    def get(self, name: str) -> Optional[TunnelProfile]:
        """
        Load a profile by name.

        Args:
            name: Profile name

        Returns:
            TunnelProfile if found, None otherwise
        """
        pass

    @abstractmethod
    def get_all(self) -> List[TunnelProfile]:
        """
        Load all profiles.

        Returns:
            List of TunnelProfile objects
        """
        pass

    @abstractmethod
    def delete(self, name: str) -> None:
        """
        Delete a profile.

        Args:
            name: Profile name to delete

        Raises:
            DomainError: If delete fails
        """
        pass

    @abstractmethod
    def exists(self, name: str) -> bool:
        """
        Check if profile exists.

        Args:
            name: Profile name

        Returns:
            True if profile exists, False otherwise
        """
        pass
