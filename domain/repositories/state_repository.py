"""State Repository Interface (Port)."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class StateRepository(ABC):
    """
    State Repository (Port)

    Abstract interface for Pulumi/IaC state operations.
    Implementations:
    - PulumiStateRepository
    - TerraformStateRepository
    - CloudFormationStateRepository

    Application logic depends on this interface, not concrete IaC tool.
    """

    @abstractmethod
    def get_resource_count(self, stack_name: str) -> int:
        """
        Get number of resources in a stack.

        Args:
            stack_name: Name of stack

        Returns:
            Number of resources
        """
        pass

    @abstractmethod
    def list_resource_urns(self, stack_name: str) -> List[str]:
        """
        List all resource URNs in a stack.

        Args:
            stack_name: Name of stack

        Returns:
            List of resource URNs
        """
        pass

    @abstractmethod
    def get_stack_state(self, stack_name: str) -> Dict[str, Any]:
        """
        Export stack state.

        Args:
            stack_name: Name of stack

        Returns:
            Stack state as dictionary
        """
        pass

    @abstractmethod
    def import_stack_state(self, stack_name: str, state: Dict[str, Any]) -> None:
        """
        Import stack state.

        Args:
            stack_name: Name of stack
            state: State dictionary to import

        Raises:
            StateError: If import fails
        """
        pass

    @abstractmethod
    def create_backup(self, stack_name: str, backup_file: str) -> None:
        """
        Create a backup of stack state.

        Args:
            stack_name: Name of stack
            backup_file: Path to backup file

        Raises:
            StateError: If backup fails
        """
        pass

    @abstractmethod
    def restore_backup(self, stack_name: str, backup_file: str) -> None:
        """
        Restore stack state from backup.

        Args:
            stack_name: Name of stack
            backup_file: Path to backup file

        Raises:
            StateError: If restore fails
        """
        pass

    @abstractmethod
    def stack_exists(self, stack_name: str) -> bool:
        """
        Check if stack exists.

        Args:
            stack_name: Name of stack

        Returns:
            True if stack exists, False otherwise
        """
        pass

    @abstractmethod
    def create_stack(self, stack_name: str) -> None:
        """
        Create a new stack.

        Args:
            stack_name: Name of stack

        Raises:
            StateError: If creation fails
        """
        pass

    @abstractmethod
    def delete_stack(self, stack_name: str, force: bool = False) -> None:
        """
        Delete a stack.

        Args:
            stack_name: Name of stack
            force: Force deletion without confirmation

        Raises:
            StateError: If deletion fails
        """
        pass

    @abstractmethod
    def list_stacks(self) -> List[str]:
        """
        List all stacks.

        Returns:
            List of stack names
        """
        pass
