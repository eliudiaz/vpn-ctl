"""Tunnel profile validation logic."""

from typing import List, Tuple


class TunnelProfileValidator:
    """Validates tunnel profile specifications."""

    @staticmethod
    def validate_spec(spec: dict) -> Tuple[bool, List[str]]:
        """
        Validate a tunnel profile spec.

        Returns: (is_valid, list_of_errors)
        """
        errors = []

        # Required fields
        required = ['phase1', 'phase2', 'dpd']
        for field in required:
            if field not in spec:
                errors.append(f"Missing required section: {field}")

        if errors:
            return False, errors

        # Phase 1 validation
        phase1 = spec.get('phase1', {})
        for field in ['encryption', 'integrity', 'dh_groups', 'lifetime']:
            if field not in phase1:
                errors.append(f"Missing phase1.{field}")

        if phase1.get('lifetime', 0) < 600:
            errors.append("Phase 1 lifetime must be >= 600 seconds")

        # Phase 2 validation
        phase2 = spec.get('phase2', {})
        for field in ['encryption', 'integrity', 'lifetime']:
            if field not in phase2:
                errors.append(f"Missing phase2.{field}")

        if phase2.get('lifetime', 0) < 600:
            errors.append("Phase 2 lifetime must be >= 600 seconds")

        # DPD validation
        dpd = spec.get('dpd', {})
        if 'timeout' not in dpd:
            errors.append("Missing dpd.timeout")
        if 'action' not in dpd:
            errors.append("Missing dpd.action")

        if dpd.get('timeout', 0) < 10:
            errors.append("DPD timeout must be >= 10 seconds")

        valid_actions = {'restart', 'clear', 'hold', 'none'}
        if dpd.get('action') not in valid_actions:
            errors.append(
                f"Invalid DPD action: {dpd.get('action')} "
                f"(must be one of {valid_actions})"
            )

        return len(errors) == 0, errors
