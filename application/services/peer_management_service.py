"""Peer management application service (provider-agnostic).

Uses IaC provider abstraction - works with any provider (Pulumi, Terraform, CloudFormation).
Orchestrates peer operations at the application level.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from infrastructure.iac_providers import IacProviderFactory
from domain.models import VpnPeer, CIDR
from domain.validators.vpn_peer_validator import VpnPeerValidator
from observability.logging import get_logger


logger = get_logger(__name__)


@dataclass
class PeerOperationResult:
    """Result of a peer management operation."""
    success: bool
    message: str
    details: Dict[str, Any]
    provider_name: str
    error: Optional[Exception] = None


class PeerManagementService:
    """
    Application service for peer management.

    Uses IaC provider abstraction - provider-agnostic.
    All vpnctl peer commands route through here.
    """

    def __init__(self, config_manager, event_publisher=None):
        """Initialize service.

        Args:
            config_manager: Configuration manager
            event_publisher: Optional event publisher for audit trail
        """
        self.config_manager = config_manager
        self.event_publisher = event_publisher
        self.validator = VpnPeerValidator()

    # ========================================================================
    # ROUTE MANAGEMENT
    # ========================================================================

    def add_destination_cidr(self, peer_name: str, cidr: str) -> PeerOperationResult:
        """Add destination CIDR to peer (provider-agnostic).

        Works with any IaC provider (Pulumi, Terraform, CloudFormation).

        Args:
            peer_name: Peer name
            cidr: Destination CIDR

        Returns:
            PeerOperationResult with status
        """
        try:
            # Get peer config
            config = self.config_manager.get_peer_config(peer_name)
            if not config:
                return PeerOperationResult(
                    success=False,
                    message=f"Peer {peer_name} not found",
                    details={},
                    provider_name="unknown"
                )

            # Validate CIDR (domain logic - provider-agnostic)
            try:
                cidr_obj = CIDR(cidr)
            except Exception as e:
                return PeerOperationResult(
                    success=False,
                    message=f"Invalid CIDR: {str(e)}",
                    details={"cidr": cidr},
                    provider_name="unknown",
                    error=e
                )

            # Get active provider (could be Pulumi, Terraform, etc.)
            provider = IacProviderFactory.get_active_provider(peer_name, config)

            # Add via provider (provider-specific implementation)
            result = provider.add_route(cidr)

            # Publish event for audit trail
            if result.is_success and self.event_publisher:
                self.event_publisher.publish({
                    "event": "cidr_added",
                    "peer": peer_name,
                    "cidr": cidr,
                    "provider": provider.get_provider_name(),
                    "timestamp": result.timestamp
                })

            return PeerOperationResult(
                success=result.is_success,
                message=result.message,
                details=result.details,
                provider_name=provider.get_provider_name(),
                error=result.error
            )

        except Exception as e:
            logger.error(f"Failed to add CIDR {cidr} to {peer_name}: {str(e)}")

            return PeerOperationResult(
                success=False,
                message=f"Failed to add CIDR: {str(e)}",
                details={"exception": str(e)},
                provider_name="unknown",
                error=e
            )

    def remove_destination_cidr(self, peer_name: str, cidr: str) -> PeerOperationResult:
        """Remove destination CIDR from peer."""
        try:
            config = self.config_manager.get_peer_config(peer_name)
            if not config:
                return PeerOperationResult(
                    success=False,
                    message=f"Peer {peer_name} not found",
                    details={},
                    provider_name="unknown"
                )

            provider = IacProviderFactory.get_active_provider(peer_name, config)

            result = provider.remove_route(cidr)

            if result.is_success and self.event_publisher:
                self.event_publisher.publish({
                    "event": "cidr_removed",
                    "peer": peer_name,
                    "cidr": cidr,
                    "provider": provider.get_provider_name(),
                    "timestamp": result.timestamp
                })

            return PeerOperationResult(
                success=result.is_success,
                message=result.message,
                details=result.details,
                provider_name=provider.get_provider_name(),
                error=result.error
            )

        except Exception as e:
            logger.error(f"Failed to remove CIDR {cidr} from {peer_name}: {str(e)}")

            return PeerOperationResult(
                success=False,
                message=f"Failed to remove CIDR: {str(e)}",
                details={"exception": str(e)},
                provider_name="unknown",
                error=e
            )

    def update_destination_cidrs(
        self,
        peer_name: str,
        cidrs: List[str]
    ) -> PeerOperationResult:
        """Update all destination CIDRs for peer."""
        try:
            config = self.config_manager.get_peer_config(peer_name)
            if not config:
                return PeerOperationResult(
                    success=False,
                    message=f"Peer {peer_name} not found",
                    details={},
                    provider_name="unknown"
                )

            # Validate all CIDRs
            for cidr in cidrs:
                try:
                    CIDR(cidr)
                except Exception as e:
                    return PeerOperationResult(
                        success=False,
                        message=f"Invalid CIDR {cidr}: {str(e)}",
                        details={"cidr": cidr},
                        provider_name="unknown",
                        error=e
                    )

            provider = IacProviderFactory.get_active_provider(peer_name, config)

            result = provider.update_routes(cidrs)

            if result.is_success and self.event_publisher:
                self.event_publisher.publish({
                    "event": "routes_updated",
                    "peer": peer_name,
                    "cidr_count": len(cidrs),
                    "provider": provider.get_provider_name(),
                    "timestamp": result.timestamp
                })

            return PeerOperationResult(
                success=result.is_success,
                message=result.message,
                details=result.details,
                provider_name=provider.get_provider_name(),
                error=result.error
            )

        except Exception as e:
            logger.error(f"Failed to update routes for {peer_name}: {str(e)}")

            return PeerOperationResult(
                success=False,
                message=f"Failed to update routes: {str(e)}",
                details={"exception": str(e)},
                provider_name="unknown",
                error=e
            )

    # ========================================================================
    # DEPLOYMENT OPERATIONS
    # ========================================================================

    def deploy_peer(self, peer_name: str, preview_only: bool = False) -> PeerOperationResult:
        """Deploy peer to infrastructure (provider-agnostic).

        Works with any IaC provider configured.

        Args:
            peer_name: Peer to deploy
            preview_only: If True, show what would happen (dry-run)

        Returns:
            PeerOperationResult with deployment result
        """
        try:
            config = self.config_manager.get_peer_config(peer_name)
            if not config:
                return PeerOperationResult(
                    success=False,
                    message=f"Peer {peer_name} not found",
                    details={},
                    provider_name="unknown"
                )

            provider = IacProviderFactory.get_active_provider(peer_name, config)

            # Validate configuration
            validation = provider.validate_config()
            if not validation.is_success:
                return PeerOperationResult(
                    success=False,
                    message=validation.message,
                    details=validation.details,
                    provider_name=provider.get_provider_name(),
                    error=validation.error
                )

            # Safety check: verify tunnel IPs won't change
            tunnel_check = provider.verify_tunnel_ips(config.get('tunnel_ips', []))
            if not tunnel_check.is_success:
                return PeerOperationResult(
                    success=False,
                    message=tunnel_check.message,
                    details=tunnel_check.details,
                    provider_name=provider.get_provider_name(),
                    error=tunnel_check.error
                )

            # Deploy
            result = provider.deploy(preview_only=preview_only)

            if result.is_success and self.event_publisher:
                self.event_publisher.publish({
                    "event": "peer_deployed",
                    "peer": peer_name,
                    "preview_only": preview_only,
                    "provider": provider.get_provider_name(),
                    "timestamp": result.timestamp
                })

            return PeerOperationResult(
                success=result.is_success,
                message=result.message,
                details=result.details,
                provider_name=provider.get_provider_name(),
                error=result.error
            )

        except Exception as e:
            logger.error(f"Failed to deploy {peer_name}: {str(e)}")

            return PeerOperationResult(
                success=False,
                message=f"Deployment failed: {str(e)}",
                details={"exception": str(e)},
                provider_name="unknown",
                error=e
            )

    # ========================================================================
    # STATE & INSPECTION
    # ========================================================================

    def show_peer_diff(self, peer_name: str) -> Dict[str, Any]:
        """Show what would change if deployed (provider-agnostic)."""
        try:
            config = self.config_manager.get_peer_config(peer_name)
            if not config:
                return {"success": False, "error": f"Peer {peer_name} not found"}

            provider = IacProviderFactory.get_active_provider(peer_name, config)

            diff = provider.diff()

            return {
                "success": True,
                "in_sync": diff.in_sync,
                "added": diff.added,
                "removed": diff.removed,
                "modified": diff.modified,
                "provider": provider.get_provider_name()
            }

        except Exception as e:
            logger.error(f"Failed to show diff for {peer_name}: {str(e)}")

            return {
                "success": False,
                "error": str(e)
            }

    def get_peer_state(self, peer_name: str) -> Dict[str, Any]:
        """Get peer state snapshot."""
        try:
            config = self.config_manager.get_peer_config(peer_name)
            if not config:
                return {"success": False, "error": f"Peer {peer_name} not found"}

            provider = IacProviderFactory.get_active_provider(peer_name, config)

            state = provider.get_current_state()

            return {
                "success": True,
                "peer_name": state.peer_name,
                "timestamp": state.timestamp,
                "provider": provider.get_provider_name(),
                "routes": state.routes,
                "tunnel_ips": state.tunnel_ips,
                "health_checks": state.health_checks
            }

        except Exception as e:
            logger.error(f"Failed to get state for {peer_name}: {str(e)}")

            return {
                "success": False,
                "error": str(e)
            }

    # ========================================================================
    # CONFIGURATION
    # ========================================================================

    def validate_peer_config(self, peer_name: str) -> PeerOperationResult:
        """Validate peer configuration."""
        try:
            config = self.config_manager.get_peer_config(peer_name)
            if not config:
                return PeerOperationResult(
                    success=False,
                    message=f"Peer {peer_name} not found",
                    details={},
                    provider_name="unknown"
                )

            provider = IacProviderFactory.get_active_provider(peer_name, config)

            result = provider.validate_config()

            return PeerOperationResult(
                success=result.is_success,
                message=result.message,
                details=result.details,
                provider_name=provider.get_provider_name(),
                error=result.error
            )

        except Exception as e:
            logger.error(f"Failed to validate config for {peer_name}: {str(e)}")

            return PeerOperationResult(
                success=False,
                message=f"Validation failed: {str(e)}",
                details={"exception": str(e)},
                provider_name="unknown",
                error=e
            )
