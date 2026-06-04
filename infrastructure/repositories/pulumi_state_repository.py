"""Pulumi state repository - IaC state management adapter."""

import json
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from domain.repositories import StateRepository
from domain.exceptions import DomainError


@dataclass
class StackResource:
    """Represents a resource in a Pulumi stack."""
    urn: str
    type: str
    logical_id: str
    physical_id: str
    outputs: Dict[str, Any]


class PulumiStateRepository(StateRepository):
    """
    Pulumi state repository - Manages IaC state via Pulumi stacks.

    Implements StateRepository interface for Pulumi, enabling:
    - Per-peer isolated stacks
    - Resource tracking and listing
    - State backup/restore
    - Multi-stack orchestration
    """

    def __init__(self, pulumi_dir: Path = Path("pulumi")):
        """
        Initialize Pulumi state repository.

        Args:
            pulumi_dir: Root directory for Pulumi projects (default: ./pulumi)
        """
        self.pulumi_dir = pulumi_dir
        if not pulumi_dir.exists():
            raise DomainError(f"Pulumi directory not found: {pulumi_dir}")

    def get_resource_count(self, peer_name: str) -> int:
        """Get resource count for a peer stack.

        Args:
            peer_name: Peer name (e.g., 'vimenca')

        Returns:
            Count of resources in peer-{peer_name} stack
        """
        try:
            stack_name = f"peer-{peer_name}"
            resources = self._list_stack_resources(stack_name)
            return len(resources)
        except Exception as e:
            raise DomainError(f"Failed to get resource count for {peer_name}: {e}")

    def list_resource_urns(self, peer_name: str) -> List[str]:
        """List all resource URNs for a peer stack.

        Args:
            peer_name: Peer name

        Returns:
            List of URNs in peer-{peer_name} stack
        """
        try:
            stack_name = f"peer-{peer_name}"
            resources = self._list_stack_resources(stack_name)
            return [r['urn'] for r in resources]
        except Exception as e:
            raise DomainError(f"Failed to list resources for {peer_name}: {e}")

    def get_stack_state(self, peer_name: str) -> Dict[str, Any]:
        """Get full state for a peer stack.

        Args:
            peer_name: Peer name

        Returns:
            Stack state dictionary
        """
        try:
            stack_name = f"peer-{peer_name}"
            state_file = self.pulumi_dir / ".pulumi" / "stacks" / f"{stack_name}.json"

            if not state_file.exists():
                raise DomainError(f"Stack state not found: {stack_name}")

            with open(state_file) as f:
                return json.load(f)
        except Exception as e:
            raise DomainError(f"Failed to get stack state for {peer_name}: {e}")

    def import_stack_state(self, peer_name: str, state: Dict[str, Any]) -> None:
        """Import state into a peer stack.

        Args:
            peer_name: Peer name
            state: State dictionary to import
        """
        try:
            stack_name = f"peer-{peer_name}"
            state_file = self.pulumi_dir / ".pulumi" / "stacks" / f"{stack_name}.json"
            state_file.parent.mkdir(parents=True, exist_ok=True)

            with open(state_file, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            raise DomainError(f"Failed to import stack state for {peer_name}: {e}")

    def backup_stack_state(self, peer_name: str, backup_dir: Path) -> Path:
        """Backup state for a peer stack.

        Args:
            peer_name: Peer name
            backup_dir: Directory to store backup

        Returns:
            Path to backup file
        """
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            stack_state = self.get_stack_state(peer_name)

            backup_file = backup_dir / f"peer-{peer_name}-backup.json"
            with open(backup_file, 'w') as f:
                json.dump(stack_state, f, indent=2)

            return backup_file
        except Exception as e:
            raise DomainError(f"Failed to backup stack state for {peer_name}: {e}")

    def restore_stack_state(self, peer_name: str, backup_file: Path) -> None:
        """Restore state for a peer stack from backup.

        Args:
            peer_name: Peer name
            backup_file: Backup file path
        """
        try:
            if not backup_file.exists():
                raise DomainError(f"Backup file not found: {backup_file}")

            with open(backup_file) as f:
                state = json.load(f)

            self.import_stack_state(peer_name, state)
        except Exception as e:
            raise DomainError(f"Failed to restore stack state for {peer_name}: {e}")

    def stack_exists(self, peer_name: str) -> bool:
        """Check if a peer stack exists.

        Args:
            peer_name: Peer name

        Returns:
            True if stack exists, False otherwise
        """
        try:
            stack_state = self.get_stack_state(peer_name)
            return stack_state is not None
        except DomainError:
            return False

    def create_stack(self, peer_name: str) -> None:
        """Create a new peer stack.

        Args:
            peer_name: Peer name
        """
        try:
            stack_name = f"peer-{peer_name}"
            self._run_pulumi_command("stack", "init", stack_name)
        except Exception as e:
            raise DomainError(f"Failed to create stack for {peer_name}: {e}")

    def delete_stack(self, peer_name: str, remove_config: bool = False) -> None:
        """Delete a peer stack.

        Args:
            peer_name: Peer name
            remove_config: If True, also remove stack config files
        """
        try:
            stack_name = f"peer-{peer_name}"
            cmd = ["stack", "rm", stack_name, "--yes"]
            if remove_config:
                cmd.append("--remove-config-file")
            self._run_pulumi_command(*cmd)
        except Exception as e:
            raise DomainError(f"Failed to delete stack for {peer_name}: {e}")

    def list_stacks(self) -> List[str]:
        """List all peer stacks.

        Returns:
            List of stack names
        """
        try:
            output = self._run_pulumi_command("stack", "ls", "--json")
            stacks = json.loads(output)
            return [s['name'] for s in stacks if s['name'].startswith('peer-')]
        except Exception as e:
            raise DomainError(f"Failed to list stacks: {e}")

    def _list_stack_resources(self, stack_name: str) -> List[Dict[str, Any]]:
        """List resources in a Pulumi stack.

        Args:
            stack_name: Stack name

        Returns:
            List of resource dictionaries
        """
        try:
            output = self._run_pulumi_command(
                "stack",
                "export",
                "--stack", stack_name,
                "--json"
            )
            state = json.loads(output)
            resources = []

            # Extract resources from state
            if 'resources' in state:
                for resource in state['resources']:
                    resources.append({
                        'urn': resource.get('urn', ''),
                        'type': resource.get('type', ''),
                        'logical_id': resource.get('logicalName', ''),
                        'physical_id': resource.get('physical_id', ''),
                        'outputs': resource.get('outputs', {}),
                    })

            return resources
        except Exception as e:
            raise DomainError(f"Failed to list stack resources: {e}")

    def _run_pulumi_command(self, *args: str) -> str:
        """Run a Pulumi CLI command in the pulumi directory.

        Args:
            *args: Command arguments

        Returns:
            Command stdout
        """
        try:
            cmd = ["pulumi"] + list(args)
            result = subprocess.run(
                cmd,
                cwd=str(self.pulumi_dir),
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            raise DomainError(f"Pulumi command failed: {e.stderr}")
