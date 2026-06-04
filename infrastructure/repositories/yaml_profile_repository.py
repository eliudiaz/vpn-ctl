"""YAML-based Tunnel Profile Repository (Adapter)."""

from pathlib import Path
from typing import List, Optional
import yaml

from domain.models import TunnelProfile
from domain.repositories import TunnelProfileRepository
from domain.exceptions import DomainError


class YamlTunnelProfileRepository(TunnelProfileRepository):
    """Loads tunnel profiles from YAML file."""

    def __init__(self, profile_file: Path = None):
        """
        Initialize YAML profile repository.

        Args:
            profile_file: Path to tunnel-profiles.yaml
                         (default: config/tunnel-profiles.yaml)
        """
        self.profile_file = profile_file or Path("config/tunnel-profiles.yaml")
        self._profiles: Optional[dict] = None

    def _load_profiles(self):
        """Load all profiles from YAML file."""
        if self._profiles is not None:
            return  # Already loaded

        if not self.profile_file.exists():
            raise DomainError(f"Profile file not found: {self.profile_file}")

        try:
            with open(self.profile_file) as f:
                data = yaml.safe_load(f)

            self._profiles = {}
            for name, profile_data in data.get("profiles", {}).items():
                self._profiles[name] = TunnelProfile.from_dict(name, profile_data)
        except Exception as e:
            raise DomainError(f"Failed to load profiles: {e}")

    def save(self, profile: TunnelProfile) -> None:
        """Save profile to YAML file (not typically used)."""
        # Load existing
        self._load_profiles()

        # Update
        self._profiles[profile.name] = profile

        # Write back
        profiles_dict = {}
        for name, p in self._profiles.items():
            profiles_dict[name] = {
                "description": p.description,
                "ike_versions": p.ike_versions,
                "phase1": {
                    "encryption": p.phase1_encryption,
                    "integrity": p.phase1_integrity,
                    "dh_groups": p.phase1_dh_groups,
                    "lifetime": p.phase1_lifetime,
                },
                "phase2": {
                    "encryption": p.phase2_encryption,
                    "integrity": p.phase2_integrity,
                    "dh_groups": p.phase2_dh_groups,
                    "lifetime": p.phase2_lifetime,
                },
                "dpd": {
                    "timeout": p.dpd_timeout,
                    "action": p.dpd_action,
                },
                "static_routes_only": p.static_routes_only,
            }

        try:
            with open(self.profile_file, "w") as f:
                yaml.dump({"profiles": profiles_dict}, f, default_flow_style=False)
        except Exception as e:
            raise DomainError(f"Failed to save profiles: {e}")

    def get(self, name: str) -> Optional[TunnelProfile]:
        """Get profile by name."""
        self._load_profiles()
        return self._profiles.get(name)

    def get_all(self) -> List[TunnelProfile]:
        """Get all profiles."""
        self._load_profiles()
        return list(self._profiles.values())

    def delete(self, name: str) -> None:
        """Delete profile from YAML file."""
        self._load_profiles()

        if name in self._profiles:
            del self._profiles[name]
            self.save(list(self._profiles.values())[0] if self._profiles else None)

    def exists(self, name: str) -> bool:
        """Check if profile exists."""
        self._load_profiles()
        return name in self._profiles
