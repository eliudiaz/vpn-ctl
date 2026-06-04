#!/usr/bin/env python3
"""State splitter - Split monolithic dev stack into per-peer stacks."""

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple


class StateSplitter:
    """Splits monolithic stack state into per-peer states."""

    def __init__(self):
        self.pulumi_dir = Path("pulumi")
        self.backup_dir = Path(".pulumi-backups")

    def split_state(self, dev_state: Dict) -> Tuple[Dict, Dict, Dict, Dict, Dict]:
        """Split dev stack state into per-peer states.

        Args:
            dev_state: Original monolithic dev stack state

        Returns:
            (core_state, vimenca_state, cibao_state, apap_state, vpn_legacy_state)
        """
        resources = dev_state.get("resources", [])

        core_resources = []
        vimenca_resources = []
        cibao_resources = []
        apap_resources = []
        vpn_legacy_resources = []

        # Categorize resources by peer
        for resource in resources:
            urn = resource.get("urn", "")
            name = resource.get("name", "").lower()

            if self._is_core_resource(urn, name):
                core_resources.append(resource)
            elif "vimenca" in name:
                vimenca_resources.append(resource)
            elif "cibao" in name:
                cibao_resources.append(resource)
            elif "apap" in name:
                apap_resources.append(resource)
            elif "default" in name or "legacy" in name:
                vpn_legacy_resources.append(resource)
            else:
                # Default to core (TGW routes, etc.)
                core_resources.append(resource)

        # Create per-peer states
        core_state = self._create_state(dev_state, core_resources, "core")
        vimenca_state = self._create_state(dev_state, vimenca_resources, "peer-vimenca")
        cibao_state = self._create_state(dev_state, cibao_resources, "peer-cibao")
        apap_state = self._create_state(dev_state, apap_resources, "peer-apap")
        vpn_legacy_state = self._create_state(
            dev_state, vpn_legacy_resources, "peer-internal-legacy-network"
        )

        return (
            core_state,
            vimenca_state,
            cibao_state,
            apap_state,
            vpn_legacy_state,
        )

    def _is_core_resource(self, urn: str, name: str) -> bool:
        """Check if resource is core (shared) infrastructure."""
        core_keywords = [
            "transitgateway",
            "tgw",
            "eks",
            "snat",
            "route53",
        ]
        return any(keyword in urn.lower() or keyword in name for keyword in core_keywords)

    def _create_state(
        self, template_state: Dict, resources: List[Dict], stack_name: str
    ) -> Dict:
        """Create a new state dict for a stack.

        Args:
            template_state: Template state to copy metadata from
            resources: Resources for this stack
            stack_name: Stack name

        Returns:
            New stack state
        """
        new_state = {
            "version": template_state.get("version", 3),
            "serial": template_state.get("serial", 0),
            "lineage": template_state.get("lineage", ""),
            "resources": resources,
        }
        return new_state

    def save_split_states(
        self, states: Tuple[Dict, Dict, Dict, Dict, Dict]
    ) -> Dict[str, Path]:
        """Save split states to files.

        Args:
            states: Tuple of (core, vimenca, cibao, apap, vpn_legacy) states

        Returns:
            Dict mapping stack name to file path
        """
        split_dir = self.backup_dir / "split-states"
        split_dir.mkdir(parents=True, exist_ok=True)

        state_files = {
            "core": split_dir / "core-state.json",
            "peer-vimenca": split_dir / "peer-vimenca-state.json",
            "peer-cibao": split_dir / "peer-cibao-state.json",
            "peer-apap": split_dir / "peer-apap-state.json",
            "peer-internal-legacy-network": split_dir / "peer-internal-legacy-network-state.json",
        }

        core, vimenca, cibao, apap, vpn_legacy = states

        for name, state in [
            ("core", core),
            ("peer-vimenca", vimenca),
            ("peer-cibao", cibao),
            ("peer-apap", apap),
            ("peer-internal-legacy-network", vpn_legacy),
        ]:
            with open(state_files[name], "w") as f:
                json.dump(state, f, indent=2)

        return state_files


def main():
    """Main entry point."""
    pulumi_dir = Path("pulumi")

    # Export current dev stack state
    import subprocess

    try:
        result = subprocess.run(
            ["pulumi", "export", "--json"],
            cwd=str(pulumi_dir),
            capture_output=True,
            text=True,
            check=True,
        )
        dev_state = json.loads(result.stdout)
    except Exception as e:
        print(f"Error exporting dev stack: {e}")
        return 1

    # Split state
    splitter = StateSplitter()
    states = splitter.split_state(dev_state)

    # Save split states
    state_files = splitter.save_split_states(states)

    print("\nState Splitting Complete")
    print("=" * 50)
    for name, path in state_files.items():
        with open(path) as f:
            resource_count = len(json.load(f).get("resources", []))
        print(f"  ✓ {name}: {resource_count} resources → {path}")
    print("=" * 50)

    return 0


if __name__ == "__main__":
    sys.exit(main())
