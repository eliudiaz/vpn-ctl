"""Pulumi-specific implementation of IaC provider.

Handles all Pulumi CLI operations and state management.
Implements the IacProvider interface for Pulumi.
"""

import subprocess
import json
import yaml
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

from .abstract_provider import (
    IacProvider,
    OperationStatus,
    OperationResult,
    DiffResult,
    StateSnapshot,
    ImmutableResources,
)
from observability.logging import get_logger


logger = get_logger(__name__)


class PulumiCommandResult:
    """Result from executing a Pulumi CLI command."""

    def __init__(self, return_code: int, stdout: str, stderr: str):
        self.return_code = return_code
        self.stdout = stdout
        self.stderr = stderr
        self.is_success = return_code == 0
        self.output = stdout if self.is_success else stderr


class PulumiCommandExecutor:
    """Executes Pulumi CLI commands in a stack directory."""

    def __init__(self, stack_dir: Path):
        self.stack_dir = Path(stack_dir)

    def run_command(self, command: List[str]) -> PulumiCommandResult:
        """Run a Pulumi command.

        Args:
            command: List of command parts (e.g., ['pulumi', 'up', '--yes'])

        Returns:
            PulumiCommandResult with output
        """
        try:
            result = subprocess.run(
                command,
                cwd=str(self.stack_dir),
                capture_output=True,
                text=True,
                timeout=600
            )

            logger.debug(
                f"Executed: {' '.join(command)} "
                f"(exit code: {result.returncode})"
            )

            return PulumiCommandResult(
                return_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr
            )

        except subprocess.TimeoutExpired as e:
            logger.error(f"Command timed out: {' '.join(command)}")
            return PulumiCommandResult(1, "", str(e))

        except Exception as e:
            logger.error(f"Command failed: {' '.join(command)} - {str(e)}")
            return PulumiCommandResult(1, "", str(e))

    def run_pulumi_up(self) -> PulumiCommandResult:
        """Run pulumi up (deploy)."""
        return self.run_command(['pulumi', 'up', '--yes', '--skip-preview'])

    def run_pulumi_preview(self) -> PulumiCommandResult:
        """Run pulumi preview (dry-run)."""
        return self.run_command(['pulumi', 'preview', '--json'])

    def run_pulumi_refresh(self) -> PulumiCommandResult:
        """Run pulumi refresh (sync state with AWS)."""
        return self.run_command(['pulumi', 'refresh', '--yes'])

    def run_pulumi_destroy(self) -> PulumiCommandResult:
        """Run pulumi destroy (delete infrastructure)."""
        return self.run_command(['pulumi', 'destroy', '--yes'])

    def run_pulumi_export(self) -> PulumiCommandResult:
        """Export stack state as JSON."""
        return self.run_command(['pulumi', 'stack', 'export'])

    def run_git_commit(self, message: str) -> PulumiCommandResult:
        """Commit changes to git (audit trail)."""
        return self.run_command(['git', 'add', '-A'])

        commit_cmd = ['git', 'commit', '-m', message]
        return self.run_command(commit_cmd)


class PulumiProvider(IacProvider):
    """Pulumi-specific implementation of IaC provider.

    Manages infrastructure via Pulumi CLI and state files.
    All Pulumi-specific logic is contained here.
    """

    def __init__(self, peer_name: str, config: Dict[str, Any]):
        super().__init__(peer_name, config)

        self.stack_name = f"peer-{peer_name}"
        self.stack_dir = Path(f"pulumi/stacks/peers/{peer_name}")
        self.config_file = self.stack_dir / f"Pulumi.{peer_name}.yaml"
        self.executor = PulumiCommandExecutor(self.stack_dir)

    # ========================================================================
    # PROVIDER IDENTITY
    # ========================================================================

    def get_provider_name(self) -> str:
        return "pulumi"

    # ========================================================================
    # CONFIGURATION MANAGEMENT
    # ========================================================================

    def _load_config(self) -> Dict[str, Any]:
        """Load Pulumi configuration from YAML."""
        if not self.config_file.exists():
            raise FileNotFoundError(f"Config not found: {self.config_file}")

        with open(self.config_file) as f:
            return yaml.safe_load(f) or {}

    def _save_config(self, config: Dict[str, Any]) -> None:
        """Save Pulumi configuration to YAML."""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)

        with open(self.config_file, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    def _compute_config_hash(self, config: Dict[str, Any]) -> str:
        """Compute SHA256 hash of config for change detection."""
        config_str = json.dumps(config, sort_keys=True)
        return hashlib.sha256(config_str.encode()).hexdigest()

    # ========================================================================
    # MUTABLE RESOURCE OPERATIONS
    # ========================================================================

    def add_route(self, cidr: str) -> OperationResult:
        """Add destination CIDR (idempotent)."""
        start_time = datetime.now()

        try:
            config = self._load_config()

            # Idempotency: check if already exists
            existing_cidrs = config.get('destination_cidrs', [])
            if cidr in existing_cidrs:
                return OperationResult(
                    status=OperationStatus.SKIPPED,
                    message=f"CIDR {cidr} already exists",
                    details={},
                    duration_ms=0,
                    provider_name="pulumi"
                )

            # Add CIDR
            if 'destination_cidrs' not in config:
                config['destination_cidrs'] = []

            config['destination_cidrs'].append(cidr)
            self._save_config(config)

            # Deploy
            result = self.executor.run_pulumi_up()

            if result.is_success:
                self._commit_to_git(f"feat: Add route {cidr} to {self.peer_name}")

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            return OperationResult(
                status=OperationStatus.SUCCESS if result.is_success else OperationStatus.FAILED,
                message=f"Route {cidr} added" if result.is_success else f"Failed to add route",
                details={"cidr": cidr},
                duration_ms=duration,
                provider_name="pulumi",
                error=Exception(result.stderr) if not result.is_success else None
            )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error(f"Failed to add route {cidr}: {str(e)}")

            return OperationResult(
                status=OperationStatus.FAILED,
                message=f"Failed to add route: {str(e)}",
                details={"exception": str(e)},
                duration_ms=duration,
                provider_name="pulumi",
                error=e
            )

    def remove_route(self, cidr: str) -> OperationResult:
        """Remove destination CIDR."""
        start_time = datetime.now()

        try:
            config = self._load_config()

            if cidr not in config.get('destination_cidrs', []):
                return OperationResult(
                    status=OperationStatus.SKIPPED,
                    message=f"CIDR {cidr} not found",
                    details={},
                    duration_ms=0,
                    provider_name="pulumi"
                )

            config['destination_cidrs'].remove(cidr)
            self._save_config(config)

            result = self.executor.run_pulumi_up()

            if result.is_success:
                self._commit_to_git(f"fix: Remove route {cidr} from {self.peer_name}")

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            return OperationResult(
                status=OperationStatus.SUCCESS if result.is_success else OperationStatus.FAILED,
                message=f"Route {cidr} removed" if result.is_success else "Failed to remove route",
                details={"cidr": cidr},
                duration_ms=duration,
                provider_name="pulumi",
                error=Exception(result.stderr) if not result.is_success else None
            )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error(f"Failed to remove route {cidr}: {str(e)}")

            return OperationResult(
                status=OperationStatus.FAILED,
                message=f"Failed to remove route: {str(e)}",
                details={"exception": str(e)},
                duration_ms=duration,
                provider_name="pulumi",
                error=e
            )

    def update_routes(self, cidrs: List[str]) -> OperationResult:
        """Update routes to EXACTLY match cidr list."""
        start_time = datetime.now()

        try:
            config = self._load_config()
            current_cidrs = set(config.get('destination_cidrs', []))
            desired_cidrs = set(cidrs)

            to_add = desired_cidrs - current_cidrs
            to_remove = current_cidrs - desired_cidrs

            if not to_add and not to_remove:
                return OperationResult(
                    status=OperationStatus.SKIPPED,
                    message="Routes already match desired state",
                    details={},
                    duration_ms=0,
                    provider_name="pulumi"
                )

            config['destination_cidrs'] = sorted(list(desired_cidrs))
            self._save_config(config)

            result = self.executor.run_pulumi_up()

            if result.is_success:
                self._commit_to_git(
                    f"refactor: Update routes for {self.peer_name}\n\n"
                    f"Added: {to_add}\nRemoved: {to_remove}"
                )

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            return OperationResult(
                status=OperationStatus.SUCCESS if result.is_success else OperationStatus.FAILED,
                message=f"Routes updated (added {len(to_add)}, removed {len(to_remove)})",
                details={"added": list(to_add), "removed": list(to_remove)},
                duration_ms=duration,
                provider_name="pulumi"
            )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error(f"Failed to update routes: {str(e)}")

            return OperationResult(
                status=OperationStatus.FAILED,
                message=f"Failed to update routes: {str(e)}",
                details={"exception": str(e)},
                duration_ms=duration,
                provider_name="pulumi",
                error=e
            )

    def set_health_checks(self, target_ips: List[str]) -> OperationResult:
        """Set health check targets."""
        start_time = datetime.now()

        try:
            config = self._load_config()
            config['health_check_targets'] = sorted(list(set(target_ips)))
            self._save_config(config)

            result = self.executor.run_pulumi_up()

            if result.is_success:
                self._commit_to_git(f"feat: Update health checks for {self.peer_name}")

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            return OperationResult(
                status=OperationStatus.SUCCESS if result.is_success else OperationStatus.FAILED,
                message=f"Health checks updated ({len(target_ips)} targets)",
                details={"targets": target_ips},
                duration_ms=duration,
                provider_name="pulumi"
            )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error(f"Failed to set health checks: {str(e)}")

            return OperationResult(
                status=OperationStatus.FAILED,
                message=f"Failed to set health checks: {str(e)}",
                details={"exception": str(e)},
                duration_ms=duration,
                provider_name="pulumi",
                error=e
            )

    # ========================================================================
    # BGP & TUNNEL CONFIGURATION
    # ========================================================================

    def set_bgp_metric(self, metric: int) -> OperationResult:
        """Update BGP metric."""
        start_time = datetime.now()

        try:
            if not (0 <= metric <= 65535):
                raise ValueError(f"BGP metric must be 0-65535, got {metric}")

            config = self._load_config()
            if 'bgp_settings' not in config:
                config['bgp_settings'] = {}

            config['bgp_settings']['metric'] = metric
            self._save_config(config)

            result = self.executor.run_pulumi_up()

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            return OperationResult(
                status=OperationStatus.SUCCESS if result.is_success else OperationStatus.FAILED,
                message=f"BGP metric set to {metric}",
                details={"metric": metric},
                duration_ms=duration,
                provider_name="pulumi"
            )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error(f"Failed to set BGP metric: {str(e)}")

            return OperationResult(
                status=OperationStatus.FAILED,
                message=f"Failed to set BGP metric: {str(e)}",
                details={"exception": str(e)},
                duration_ms=duration,
                provider_name="pulumi",
                error=e
            )

    def set_tunnel_preference(self, preferred_tunnel: int) -> OperationResult:
        """Set preferred tunnel (1 or 2)."""
        start_time = datetime.now()

        try:
            if preferred_tunnel not in (1, 2):
                raise ValueError(f"Preferred tunnel must be 1 or 2, got {preferred_tunnel}")

            config = self._load_config()
            if 'tunnel_settings' not in config:
                config['tunnel_settings'] = {}

            config['tunnel_settings']['preferred_tunnel'] = preferred_tunnel
            self._save_config(config)

            result = self.executor.run_pulumi_up()

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            return OperationResult(
                status=OperationStatus.SUCCESS if result.is_success else OperationStatus.FAILED,
                message=f"Tunnel preference set to {preferred_tunnel}",
                details={"preferred_tunnel": preferred_tunnel},
                duration_ms=duration,
                provider_name="pulumi"
            )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error(f"Failed to set tunnel preference: {str(e)}")

            return OperationResult(
                status=OperationStatus.FAILED,
                message=f"Failed to set tunnel preference: {str(e)}",
                details={"exception": str(e)},
                duration_ms=duration,
                provider_name="pulumi",
                error=e
            )

    # ========================================================================
    # PSK MANAGEMENT
    # ========================================================================

    def rotate_psk(self) -> OperationResult:
        """Rotate Pre-Shared Keys (security operation)."""
        start_time = datetime.now()

        try:
            from domain.services.security import PskGenerator
            from infrastructure.config.secrets_manager import SecretsManager

            psk_gen = PskGenerator()
            new_psk1 = psk_gen.generate()
            new_psk2 = psk_gen.generate()

            secrets = SecretsManager()
            secrets.put_secret(
                secret_id=f"vpn/{self.peer_name}/psk",
                data={
                    "tunnel1": new_psk1,
                    "tunnel2": new_psk2,
                    "rotated_at": datetime.now().isoformat()
                }
            )

            config = self._load_config()
            config['psk_reference'] = f"arn:aws:secretsmanager:us-east-2:xxx:secret:vpn/{self.peer_name}/psk"
            config['psk_rotation'] = {
                'last_rotated': datetime.now().isoformat(),
            }
            self._save_config(config)

            result = self.executor.run_pulumi_up()

            if result.is_success:
                self._commit_to_git(f"security: Rotate PSK for {self.peer_name}")

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            return OperationResult(
                status=OperationStatus.SUCCESS if result.is_success else OperationStatus.FAILED,
                message="PSK rotated successfully",
                details={
                    "tunnel1_psk": "***" + new_psk1[-4:],
                    "tunnel2_psk": "***" + new_psk2[-4:]
                },
                duration_ms=duration,
                provider_name="pulumi"
            )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error(f"Failed to rotate PSK: {str(e)}")

            return OperationResult(
                status=OperationStatus.FAILED,
                message=f"Failed to rotate PSK: {str(e)}",
                details={"exception": str(e)},
                duration_ms=duration,
                provider_name="pulumi",
                error=e
            )

    # ========================================================================
    # STATE & DIFF OPERATIONS
    # ========================================================================

    def get_current_state(self) -> StateSnapshot:
        """Get current state snapshot from Pulumi."""
        result = self.executor.run_pulumi_export()

        state_data = {}
        routes = []
        tunnel_ips = []
        health_checks = []

        if result.is_success:
            try:
                state_data = json.loads(result.output)

                for resource in state_data.get('resources', []):
                    urn = resource.get('urn', '')
                    if 'transitGatewayRoute' in urn:
                        cidr = resource.get('outputs', {}).get('destinationCidrBlock')
                        if cidr:
                            routes.append(cidr)
                    elif 'vpnConnection' in urn:
                        outputs = resource.get('outputs', {})
                        ip1 = outputs.get('vpnGatewayAddress')
                        ip2 = outputs.get('vpnGatewayAddress2')
                        if ip1:
                            tunnel_ips.append(ip1)
                        if ip2:
                            tunnel_ips.append(ip2)
                    elif 'healthCheck' in urn:
                        ip = resource.get('outputs', {}).get('ipAddress')
                        if ip:
                            health_checks.append(ip)

            except json.JSONDecodeError:
                logger.warning("Failed to parse Pulumi state JSON")

        config = self._load_config()
        config_hash = self._compute_config_hash(config)

        return StateSnapshot(
            peer_name=self.peer_name,
            timestamp=datetime.now().isoformat(),
            provider_name="pulumi",
            resources=state_data,
            routes=routes,
            tunnel_ips=tunnel_ips,
            health_checks=health_checks,
            config_hash=config_hash
        )

    def diff(self) -> DiffResult:
        """Compare config vs AWS state."""
        result = self.executor.run_pulumi_preview()

        added = []
        removed = []
        modified = []
        in_sync = True

        if result.is_success:
            try:
                changes = json.loads(result.output)
                in_sync = len(changes.get('changes', [])) == 0

                for change in changes.get('changes', []):
                    change_type = change.get('type')
                    resource = change.get('resource', {})

                    if change_type == 'create':
                        added.append(resource)
                    elif change_type == 'delete':
                        removed.append(resource)
                    elif change_type == 'modify':
                        modified.append(resource)

            except json.JSONDecodeError:
                logger.warning("Failed to parse Pulumi preview output")

        return DiffResult(
            added=added,
            removed=removed,
            modified=modified,
            in_sync=in_sync
        )

    def refresh(self) -> OperationResult:
        """Refresh provider state from AWS."""
        start_time = datetime.now()

        try:
            result = self.executor.run_pulumi_refresh()

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            return OperationResult(
                status=OperationStatus.SUCCESS if result.is_success else OperationStatus.FAILED,
                message="State refreshed from AWS",
                details={},
                duration_ms=duration,
                provider_name="pulumi"
            )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error(f"Failed to refresh state: {str(e)}")

            return OperationResult(
                status=OperationStatus.FAILED,
                message=f"Failed to refresh state: {str(e)}",
                details={"exception": str(e)},
                duration_ms=duration,
                provider_name="pulumi",
                error=e
            )

    # ========================================================================
    # DEPLOYMENT & ROLLBACK
    # ========================================================================

    def deploy(self, preview_only: bool = False) -> OperationResult:
        """Deploy configuration to AWS."""
        start_time = datetime.now()

        try:
            tunnel_check = self.verify_tunnel_ips(self.config.get('tunnel_ips', []))
            if not tunnel_check.is_success:
                return tunnel_check

            if preview_only:
                result = self.executor.run_pulumi_preview()
                message = "Deployment preview generated"
            else:
                result = self.executor.run_pulumi_up()
                message = "Deployment successful"

                if result.is_success:
                    self._commit_to_git(f"deploy: Update {self.peer_name} infrastructure")

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            return OperationResult(
                status=OperationStatus.SUCCESS if result.is_success else OperationStatus.FAILED,
                message=message,
                details={},
                duration_ms=duration,
                provider_name="pulumi"
            )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error(f"Deployment failed: {str(e)}")

            return OperationResult(
                status=OperationStatus.FAILED,
                message=f"Deployment failed: {str(e)}",
                details={"exception": str(e)},
                duration_ms=duration,
                provider_name="pulumi",
                error=e
            )

    def rollback(self, target_state: StateSnapshot) -> OperationResult:
        """Rollback to previous state."""
        start_time = datetime.now()

        try:
            if not target_state.resources:
                raise ValueError("Target state has no resources")

            self._save_config(target_state.resources)

            result = self.executor.run_pulumi_up()

            if result.is_success:
                self._commit_to_git(f"revert: Rollback {self.peer_name} to previous state")

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            return OperationResult(
                status=OperationStatus.SUCCESS if result.is_success else OperationStatus.FAILED,
                message="Rollback successful",
                details={},
                duration_ms=duration,
                provider_name="pulumi"
            )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error(f"Rollback failed: {str(e)}")

            return OperationResult(
                status=OperationStatus.FAILED,
                message=f"Rollback failed: {str(e)}",
                details={"exception": str(e)},
                duration_ms=duration,
                provider_name="pulumi",
                error=e
            )

    def destroy(self) -> OperationResult:
        """Destroy all peer infrastructure."""
        start_time = datetime.now()

        try:
            result = self.executor.run_pulumi_destroy()

            if result.is_success:
                self._commit_to_git(f"remove: Destroy {self.peer_name} infrastructure")

            duration = int((datetime.now() - start_time).total_seconds() * 1000)

            return OperationResult(
                status=OperationStatus.SUCCESS if result.is_success else OperationStatus.FAILED,
                message="Infrastructure destroyed",
                details={},
                duration_ms=duration,
                provider_name="pulumi"
            )

        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error(f"Destroy failed: {str(e)}")

            return OperationResult(
                status=OperationStatus.FAILED,
                message=f"Destroy failed: {str(e)}",
                details={"exception": str(e)},
                duration_ms=duration,
                provider_name="pulumi",
                error=e
            )

    # ========================================================================
    # IMMUTABLE RESOURCE PROTECTION
    # ========================================================================

    def verify_tunnel_ips(self, expected_ips: List[str]) -> OperationResult:
        """CRITICAL: Verify tunnel IPs haven't changed."""
        try:
            state = self.get_current_state()
            actual_ips = state.tunnel_ips

            if set(actual_ips) != set(expected_ips):
                return OperationResult(
                    status=OperationStatus.FAILED,
                    message="CRITICAL: Tunnel IPs have changed!",
                    details={
                        "expected": expected_ips,
                        "actual": actual_ips,
                        "alert": "VPN connection may have been recreated. Do NOT proceed."
                    },
                    duration_ms=0,
                    provider_name="pulumi",
                    error=Exception("Tunnel IP mismatch")
                )

            return OperationResult(
                status=OperationStatus.SUCCESS,
                message="Tunnel IPs verified",
                details={"ips": expected_ips},
                duration_ms=0,
                provider_name="pulumi"
            )

        except Exception as e:
            logger.error(f"Failed to verify tunnel IPs: {str(e)}")

            return OperationResult(
                status=OperationStatus.FAILED,
                message=f"Failed to verify tunnel IPs: {str(e)}",
                details={"exception": str(e)},
                duration_ms=0,
                provider_name="pulumi",
                error=e
            )

    def verify_vpn_connection(self, expected_vpn_id: str) -> OperationResult:
        """Verify VPN connection ID is correct."""
        try:
            config = self._load_config()
            actual_vpn_id = config.get('vpn_id')

            if actual_vpn_id != expected_vpn_id:
                return OperationResult(
                    status=OperationStatus.FAILED,
                    message="CRITICAL: VPN connection ID has changed!",
                    details={
                        "expected": expected_vpn_id,
                        "actual": actual_vpn_id
                    },
                    duration_ms=0,
                    provider_name="pulumi",
                    error=Exception("VPN ID mismatch")
                )

            return OperationResult(
                status=OperationStatus.SUCCESS,
                message="VPN connection verified",
                details={"vpn_id": expected_vpn_id},
                duration_ms=0,
                provider_name="pulumi"
            )

        except Exception as e:
            logger.error(f"Failed to verify VPN connection: {str(e)}")

            return OperationResult(
                status=OperationStatus.FAILED,
                message=f"Failed to verify VPN connection: {str(e)}",
                details={"exception": str(e)},
                duration_ms=0,
                provider_name="pulumi",
                error=e
            )

    def get_immutable_resources(self) -> ImmutableResources:
        """Get immutable resource IDs."""
        config = self._load_config()

        return ImmutableResources(
            vpn_id=config.get('vpn_id', ''),
            customer_gateway_id=config.get('customer_gateway_id', ''),
            tgw_attachment_id=config.get('tgw_attachment_id', ''),
            tunnel_ips=config.get('tunnel_ips', [])
        )

    # ========================================================================
    # CONFIGURATION & METADATA
    # ========================================================================

    def get_config(self) -> Dict[str, Any]:
        return self._load_config()

    def validate_config(self) -> OperationResult:
        """Validate configuration."""
        try:
            config = self._load_config()

            if not config.get('destination_cidrs'):
                raise ValueError("No destination CIDRs configured")

            if not config.get('vpn_id'):
                raise ValueError("VPN ID not configured")

            return OperationResult(
                status=OperationStatus.SUCCESS,
                message="Configuration valid",
                details={},
                duration_ms=0,
                provider_name="pulumi"
            )

        except Exception as e:
            logger.error(f"Configuration validation failed: {str(e)}")

            return OperationResult(
                status=OperationStatus.FAILED,
                message=f"Configuration invalid: {str(e)}",
                details={"exception": str(e)},
                duration_ms=0,
                provider_name="pulumi",
                error=e
            )

    def export_state(self, format: str = "json") -> str:
        """Export state for backup."""
        result = self.executor.run_pulumi_export()

        if not result.is_success:
            raise Exception(f"Failed to export state: {result.stderr}")

        if format == "json":
            return result.output

        elif format == "yaml":
            data = json.loads(result.output)
            return yaml.dump(data, default_flow_style=False)

        else:
            raise ValueError(f"Unsupported format: {format}")

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    def _commit_to_git(self, message: str) -> None:
        """Commit changes to git (audit trail)."""
        try:
            subprocess.run(
                ['git', 'add', '-A'],
                cwd=str(self.stack_dir.parent.parent),
                capture_output=True,
                timeout=30
            )

            subprocess.run(
                ['git', 'commit', '-m', message],
                cwd=str(self.stack_dir.parent.parent),
                capture_output=True,
                timeout=30
            )

            logger.debug(f"Committed: {message}")

        except Exception as e:
            logger.warning(f"Failed to commit to git: {str(e)}")
