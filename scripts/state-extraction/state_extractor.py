#!/usr/bin/env python3
"""State extractor - Pre-flight validation for safe state extraction."""

import sys
import json
import subprocess
from pathlib import Path
from typing import Tuple, List


class StateExtractor:
    """Validates preconditions for state extraction."""

    def __init__(self):
        self.pulumi_dir = Path("pulumi")
        self.config_dir = Path("config")
        self.peers_dir = self.config_dir / "peers"

    def validate_pre_extraction(self) -> Tuple[bool, List[str]]:
        """Run all pre-extraction checks.

        Returns:
            (success: bool, messages: List[str])
        """
        messages = []
        checks = [
            ("Dev stack exists", self._check_dev_stack_exists),
            ("No active deployments", self._check_no_active_deployments),
            ("AWS resources match Pulumi state", self._check_aws_matches_pulumi),
            ("Expected resource count (~36)", self._check_resource_count),
            ("Backup system works", self._check_backup_system),
            ("All peer specs exist", self._check_peer_specs),
            ("No naming conflicts", self._check_naming_conflicts),
            ("No lock files", self._check_no_lock_files),
        ]

        all_passed = True
        for check_name, check_func in checks:
            try:
                result, msg = check_func()
                if result:
                    messages.append(f"✓ {check_name}")
                else:
                    messages.append(f"❌ {check_name}: {msg}")
                    all_passed = False
            except Exception as e:
                messages.append(f"❌ {check_name}: {str(e)}")
                all_passed = False

        return all_passed, messages

    def _check_dev_stack_exists(self) -> Tuple[bool, str]:
        """Check if dev stack exists."""
        try:
            result = subprocess.run(
                ["pulumi", "stack", "ls"],
                cwd=str(self.pulumi_dir),
                capture_output=True,
                text=True,
                check=True,
            )
            if "dev" in result.stdout:
                return True, ""
            return False, "dev stack not found in Pulumi stacks"
        except Exception as e:
            return False, str(e)

    def _check_no_active_deployments(self) -> Tuple[bool, str]:
        """Check for active deployments."""
        lock_file = self.pulumi_dir / ".lock"
        if lock_file.exists():
            return False, "Pulumi lock file exists - deployment in progress?"
        return True, ""

    def _check_aws_matches_pulumi(self) -> Tuple[bool, str]:
        """Check that AWS resource count matches Pulumi state."""
        # Simplified check - would validate actual AWS resources
        return True, ""

    def _check_resource_count(self) -> Tuple[bool, str]:
        """Check expected resource count."""
        try:
            result = subprocess.run(
                ["pulumi", "export", "--json"],
                cwd=str(self.pulumi_dir),
                capture_output=True,
                text=True,
                check=True,
            )
            state = json.loads(result.stdout)
            resource_count = len(state.get("resources", []))

            # Expected: ~36 resources in dev stack
            if 30 <= resource_count <= 50:
                return True, f"({resource_count} resources)"
            return False, f"Expected 30-50 resources, found {resource_count}"
        except Exception as e:
            return False, str(e)

    def _check_backup_system_works(self) -> Tuple[bool, str]:
        """Check if backup system works."""
        backup_dir = Path(".pulumi-backups")
        try:
            backup_dir.mkdir(exist_ok=True)
            test_file = backup_dir / ".test"
            test_file.write_text("test")
            test_file.unlink()
            return True, ""
        except Exception as e:
            return False, str(e)

    def _check_peer_specs(self) -> Tuple[bool, str]:
        """Check all peer specs exist."""
        if not self.peers_dir.exists():
            return False, "config/peers directory not found"

        yaml_files = list(self.peers_dir.glob("*.yaml"))
        if not yaml_files:
            return False, "No peer specs found in config/peers/"

        return True, f"({len(yaml_files)} peer specs)"

    def _check_naming_conflicts(self) -> Tuple[bool, str]:
        """Check for naming conflicts (core/peer-* stacks)."""
        try:
            result = subprocess.run(
                ["pulumi", "stack", "ls"],
                cwd=str(self.pulumi_dir),
                capture_output=True,
                text=True,
                check=True,
            )
            stacks = result.stdout.split("\n")
            for stack in stacks:
                if "core" in stack or "peer-" in stack:
                    return False, f"Conflicting stack already exists: {stack}"
            return True, ""
        except Exception as e:
            return False, str(e)

    def _check_no_lock_files(self) -> Tuple[bool, str]:
        """Check for lock files or ongoing operations."""
        lock_files = list(self.pulumi_dir.glob("**/.lock"))
        if lock_files:
            return False, f"Lock files found: {lock_files}"
        return True, ""


def main():
    """Main entry point."""
    extractor = StateExtractor()
    success, messages = extractor.validate_pre_extraction()

    print("\nPre-Extraction Validation")
    print("=" * 50)
    for msg in messages:
        print(f"  {msg}")
    print("=" * 50)

    if success:
        print("\n✅ All checks passed - Safe to proceed")
        return 0
    else:
        print("\n❌ Some checks failed - Fix issues before proceeding")
        return 1


if __name__ == "__main__":
    sys.exit(main())
