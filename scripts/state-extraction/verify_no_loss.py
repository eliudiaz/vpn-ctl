#!/usr/bin/env python3
"""Verify no data loss during state extraction."""

import json
import sys
from pathlib import Path
from typing import List, Tuple


class NoLossVerifier:
    """Verifies zero data loss during state extraction."""

    @staticmethod
    def verify_resource_count(original_count: int, split_counts: List[int]) -> Tuple[bool, str]:
        """Verify resource count matches before and after split.

        Args:
            original_count: Original resource count
            split_counts: List of resource counts in split states

        Returns:
            (success: bool, message: str)
        """
        total_split = sum(split_counts)
        if original_count == total_split:
            return True, f"✓ Resource count verified: {original_count} == {total_split}"
        else:
            return False, f"❌ Resource count mismatch: {original_count} != {total_split}"

    @staticmethod
    def verify_urns_preserved(original_urns: List[str], split_urns: List[str]) -> Tuple[bool, str]:
        """Verify all URNs are preserved in split states.

        Args:
            original_urns: Original URNs
            split_urns: URNs from split states

        Returns:
            (success: bool, message: str)
        """
        original_set = set(original_urns)
        split_set = set(split_urns)

        missing = original_set - split_set
        extra = split_set - original_set

        if missing:
            return False, f"❌ Missing URNs: {missing}"
        if extra:
            return False, f"❌ Extra URNs: {extra}"

        return True, f"✓ All {len(original_set)} URNs preserved"

    @staticmethod
    def verify_no_duplicates(split_urns: List[str]) -> Tuple[bool, str]:
        """Verify no duplicate URNs in split states.

        Args:
            split_urns: URNs from split states

        Returns:
            (success: bool, message: str)
        """
        unique = set(split_urns)
        total = len(split_urns)

        if len(unique) == total:
            return True, f"✓ No duplicate URNs ({total} unique)"
        else:
            duplicates = total - len(unique)
            return False, f"❌ {duplicates} duplicate URNs found"

    @staticmethod
    def verify_json_valid(state_files: dict) -> Tuple[bool, str]:
        """Verify all state files contain valid JSON.

        Args:
            state_files: Dict of {name: path}

        Returns:
            (success: bool, message: str)
        """
        invalid_files = []
        for name, path in state_files.items():
            try:
                with open(path) as f:
                    json.load(f)
            except Exception as e:
                invalid_files.append((name, str(e)))

        if invalid_files:
            msg = "; ".join([f"{name}: {error}" for name, error in invalid_files])
            return False, f"❌ Invalid JSON: {msg}"

        return True, f"✓ All {len(state_files)} state files valid JSON"


def main():
    """Main entry point."""
    backup_dir = Path(".pulumi-backups")

    # Load original state
    original_file = list(backup_dir.glob("dev-full-state-*.json"))
    if not original_file:
        print("❌ Original backup not found")
        return 1

    with open(original_file[0]) as f:
        original_state = json.load(f)

    original_resources = original_state.get("resources", [])
    original_urns = [r.get("urn") for r in original_resources]
    original_count = len(original_resources)

    # Load split states
    split_dir = backup_dir / "split-states"
    if not split_dir.exists():
        print("❌ Split states not found")
        return 1

    split_files = list(split_dir.glob("*.json"))
    split_states = {}
    split_urns = []
    split_counts = []

    for file in sorted(split_files):
        with open(file) as f:
            state = json.load(f)
        split_states[file.stem] = state
        resources = state.get("resources", [])
        split_counts.append(len(resources))
        split_urns.extend([r.get("urn") for r in resources])

    # Run verifications
    verifier = NoLossVerifier()
    checks = [
        ("Resource count", verifier.verify_resource_count(original_count, split_counts)),
        ("URNs preserved", verifier.verify_urns_preserved(original_urns, split_urns)),
        ("No duplicates", verifier.verify_no_duplicates(split_urns)),
        ("Valid JSON", verifier.verify_json_valid({file.stem: file for file in split_files})),
    ]

    print("\nData Loss Verification")
    print("=" * 70)
    all_passed = True
    for check_name, (passed, message) in checks:
        print(f"  {message}")
        if not passed:
            all_passed = False

    print("=" * 70)

    if all_passed:
        print(f"\n✅ ZERO DATA LOSS VERIFIED ({original_count} resources)")
        return 0
    else:
        print("\n❌ VERIFICATION FAILED - Do NOT proceed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
