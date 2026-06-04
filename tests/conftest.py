"""Pytest configuration and shared fixtures."""

import pytest
from pathlib import Path
import tempfile

from domain.models import VpnPeer, TunnelProfile
from domain.models.value_objects import BGPASN, CIDR, PSK, PeerName, PublicIP
from infrastructure.repositories import YamlVpnPeerRepository, YamlTunnelProfileRepository


@pytest.fixture
def temp_config_dir():
    """Create temporary config directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir) / "config"
        config_dir.mkdir()
        (config_dir / "peers").mkdir()
        yield config_dir


@pytest.fixture
def sample_peer():
    """Create a sample VPN peer for testing."""
    return VpnPeer(
        name=PeerName("test-peer"),
        public_ip=PublicIP("203.0.113.50"),
        bgp_asn=BGPASN(65000),
        destination_cidrs=frozenset([CIDR("10.0.0.0/16"), CIDR("10.1.0.0/16")]),
        tunnel_profile_name="checkpoint_r80",
        device_type="checkpoint",
        device_version="R80.10",
        psk_tunnel1=PSK("a" * 32),
        psk_tunnel2=PSK("b" * 32),
        contacts=[{'name': 'John Doe', 'email': 'john@example.com', 'phone': '+1-555-1234'}],
        enabled=True,
    )


@pytest.fixture
def sample_tunnel_profile():
    """Create a sample tunnel profile for testing."""
    return TunnelProfile(
        name="checkpoint_r80",
        device_vendor="checkpoint",
        ike_version=2,
        phase1_encryption="aes-256",
        phase1_integrity="sha2-256",
        phase1_dh_group="group14",
        phase1_lifetime_seconds=28800,
        phase2_encryption="aes-256",
        phase2_integrity="sha2-256",
        phase2_lifetime_seconds=3600,
        dpd_action="restart",
        dpd_interval_seconds=10,
        dpd_timeout_seconds=30,
    )


@pytest.fixture
def peer_repository(temp_config_dir):
    """Create a peer repository with temporary directory."""
    peers_dir = temp_config_dir / "peers"
    return YamlVpnPeerRepository(peers_dir)


# Fixtures for IaC provider testing

@pytest.fixture(autouse=True)
def cleanup_providers():
    """Clean up registered providers after each test."""
    yield
    from infrastructure.iac_providers import IacProviderFactory
    # Unregister test providers
    for provider_name in ['test-pulumi', 'test-pulumi-preview', 'prov1', 'prov2', 'simple-mock', 'mock', 'test-provider']:
        try:
            IacProviderFactory.unregister(provider_name)
        except:
            pass


@pytest.fixture
def mock_config_manager():
    """Create a mock configuration manager."""
    from unittest.mock import Mock
    manager = Mock()
    manager.get_peer_config.return_value = {'iac_provider': 'mock'}
    return manager


@pytest.fixture
def mock_event_publisher():
    """Create a mock event publisher."""
    from unittest.mock import Mock
    publisher = Mock()
    publisher.publish = Mock()
    return publisher


@pytest.fixture
def simple_mock_provider():
    """Create a simple mock IaC provider for testing."""
    from infrastructure.iac_providers import IacProvider, OperationStatus, OperationResult, DiffResult

    class SimpleMockProvider(IacProvider):
        def __init__(self, peer_name, config):
            super().__init__(peer_name, config)
            self.routes = []
            self.deployed = False

        def get_provider_name(self):
            return "simple-mock"

        def add_route(self, cidr):
            self.routes.append(cidr)
            return OperationResult(
                status=OperationStatus.SUCCESS,
                message=f"Route {cidr} added",
                details={"cidr": cidr},
                provider_name="simple-mock"
            )

        def remove_route(self, cidr):
            if cidr in self.routes:
                self.routes.remove(cidr)
            return OperationResult(
                status=OperationStatus.SUCCESS,
                message=f"Route {cidr} removed",
                details={"cidr": cidr},
                provider_name="simple-mock"
            )

        def update_routes(self, cidrs):
            self.routes = cidrs
            return OperationResult(
                status=OperationStatus.SUCCESS,
                message="Routes updated",
                details={"cidrs": cidrs},
                provider_name="simple-mock"
            )

        def set_health_checks(self, target_ips):
            return OperationResult(
                status=OperationStatus.SUCCESS,
                message="Health checks set",
                details={},
                provider_name="simple-mock"
            )

        def set_bgp_metric(self, metric):
            return OperationResult(
                status=OperationStatus.SUCCESS,
                message=f"BGP metric set to {metric}",
                details={"metric": metric},
                provider_name="simple-mock"
            )

        def set_tunnel_preference(self, preferred_tunnel):
            return OperationResult(
                status=OperationStatus.SUCCESS,
                message=f"Tunnel preference set to {preferred_tunnel}",
                details={"preferred_tunnel": preferred_tunnel},
                provider_name="simple-mock"
            )

        def rotate_psk(self):
            return OperationResult(
                status=OperationStatus.SUCCESS,
                message="PSK rotated",
                details={},
                provider_name="simple-mock"
            )

        def get_current_state(self):
            from unittest.mock import Mock
            return Mock()

        def diff(self):
            return DiffResult(
                added=[],
                removed=[],
                modified=[],
                in_sync=True
            )

        def refresh(self):
            return OperationResult(
                status=OperationStatus.SUCCESS,
                message="State refreshed",
                details={},
                provider_name="simple-mock"
            )

        def deploy(self, preview_only=False):
            if not preview_only:
                self.deployed = True
            return OperationResult(
                status=OperationStatus.SUCCESS,
                message="Deployment complete" if not preview_only else "Preview complete",
                details={"deployed": self.deployed},
                provider_name="simple-mock"
            )

        def rollback(self, target_state):
            return OperationResult(
                status=OperationStatus.SUCCESS,
                message="Rolled back",
                details={},
                provider_name="simple-mock"
            )

        def destroy(self):
            self.deployed = False
            return OperationResult(
                status=OperationStatus.SUCCESS,
                message="Destroyed",
                details={},
                provider_name="simple-mock"
            )

        def verify_tunnel_ips(self, expected_ips):
            return OperationResult(
                status=OperationStatus.SUCCESS,
                message="Tunnel IPs verified",
                details={"ips": expected_ips},
                provider_name="simple-mock"
            )

        def verify_vpn_connection(self, expected_vpn_id):
            return OperationResult(
                status=OperationStatus.SUCCESS,
                message="VPN verified",
                details={"vpn_id": expected_vpn_id},
                provider_name="simple-mock"
            )

        def get_immutable_resources(self):
            from unittest.mock import Mock
            return Mock()

        def validate_config(self):
            return OperationResult(
                status=OperationStatus.SUCCESS,
                message="Config valid",
                details={},
                provider_name="simple-mock"
            )

        def export_state(self, format="json"):
            import json
            return json.dumps({"routes": self.routes, "deployed": self.deployed})

    return SimpleMockProvider


@pytest.fixture
def register_simple_mock(simple_mock_provider):
    """Register the simple mock provider for testing."""
    from infrastructure.iac_providers import IacProviderFactory
    IacProviderFactory.register('simple-mock', simple_mock_provider)
    yield simple_mock_provider
    IacProviderFactory.unregister('simple-mock')
