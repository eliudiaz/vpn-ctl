"""Integration tests for PeerSpecManager."""

import pytest
import tempfile
from pathlib import Path
import yaml

from domain.services.peer_spec_manager import PeerSpecManager
from domain.models.test_endpoint import TestEndpoint
from domain.exceptions import DomainValidationError


@pytest.fixture
def temp_config():
    """Create temporary config file for testing."""
    config = {
        'peers': [
            {
                'name': 'TestPeer',
                'public_ip': '192.168.1.1',
                'bgp_asn': 65000,
                'tunnel_profile': 'test_profile',
                'destination_cidrs': ['10.0.0.0/8'],
                'device_type': 'Firewall',
                'device_version': '1.0',
                'contacts': [
                    {'name': 'Test Admin', 'email': 'admin@test.com', 'phone': '555-1234'}
                ],
                'test_endpoints': [
                    {'target': '10.0.0.1', 'protocol': 'ping'},
                    {'target': 'api.test.local', 'protocol': 'http', 'port': 8080},
                ]
            },
            {
                'name': 'AnotherPeer',
                'public_ip': '192.168.1.2',
                'bgp_asn': 65001,
                'tunnel_profile': 'test_profile',
                'destination_cidrs': ['10.1.0.0/8'],
                'device_type': 'Firewall',
                'device_version': '1.0',
                'contacts': [
                    {'name': 'Another Admin', 'email': 'admin@another.com', 'phone': '555-5678'}
                ],
                'test_endpoints': []
            }
        ]
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_path = Path(f.name)

    yield temp_path

    # Cleanup
    temp_path.unlink()


class TestLoadPeerSpec:
    """Test loading peer specifications."""

    def test_load_existing_peer(self, temp_config):
        """Test loading existing peer."""
        mgr = PeerSpecManager(temp_config)
        spec = mgr.load_peer_spec('TestPeer')
        assert spec['name'] == 'TestPeer'
        assert spec['public_ip'] == '192.168.1.1'

    def test_load_peer_case_insensitive(self, temp_config):
        """Test loading peer is case-insensitive."""
        mgr = PeerSpecManager(temp_config)
        spec = mgr.load_peer_spec('testpeer')
        assert spec['name'] == 'TestPeer'

    def test_load_nonexistent_peer(self, temp_config):
        """Test loading non-existent peer."""
        mgr = PeerSpecManager(temp_config)
        with pytest.raises(DomainValidationError):
            mgr.load_peer_spec('NonExistent')

    def test_load_config_file_not_found(self):
        """Test error when config file not found."""
        mgr = PeerSpecManager(Path('/nonexistent/path.yaml'))
        with pytest.raises(DomainValidationError):
            mgr.load_peer_spec('TestPeer')


class TestListTestEndpoints:
    """Test listing test endpoints."""

    def test_list_existing_endpoints(self, temp_config):
        """Test listing endpoints for peer with endpoints."""
        mgr = PeerSpecManager(temp_config)
        endpoints = mgr.list_test_endpoints('TestPeer')
        assert len(endpoints) == 2
        assert all(isinstance(ep, TestEndpoint) for ep in endpoints)

    def test_list_empty_endpoints(self, temp_config):
        """Test listing endpoints for peer with no endpoints."""
        mgr = PeerSpecManager(temp_config)
        endpoints = mgr.list_test_endpoints('AnotherPeer')
        assert len(endpoints) == 0

    def test_endpoints_are_deserialized(self, temp_config):
        """Test endpoints are properly deserialized."""
        mgr = PeerSpecManager(temp_config)
        endpoints = mgr.list_test_endpoints('TestPeer')
        assert endpoints[0].target == '10.0.0.1'
        assert endpoints[0].protocol == 'ping'
        assert endpoints[1].target == 'api.test.local'
        assert endpoints[1].protocol == 'http'
        assert endpoints[1].port == 8080


class TestAddTestEndpoint:
    """Test adding test endpoints."""

    def test_add_endpoint_ping(self, temp_config):
        """Test adding ping endpoint."""
        mgr = PeerSpecManager(temp_config)
        endpoints = mgr.add_test_endpoint('AnotherPeer', '10.1.0.1', 'ping')
        assert len(endpoints) == 1
        assert endpoints[0].target == '10.1.0.1'
        assert endpoints[0].protocol == 'ping'

    def test_add_endpoint_http(self, temp_config):
        """Test adding HTTP endpoint with port."""
        mgr = PeerSpecManager(temp_config)
        endpoints = mgr.add_test_endpoint('AnotherPeer', 'api.example.com', 'http', 8080)
        assert len(endpoints) == 1
        assert endpoints[0].target == 'api.example.com'
        assert endpoints[0].protocol == 'http'
        assert endpoints[0].port == 8080

    def test_add_endpoint_persists_to_yaml(self, temp_config):
        """Test endpoint is persisted to YAML."""
        mgr = PeerSpecManager(temp_config)
        mgr.add_test_endpoint('AnotherPeer', '10.1.0.1', 'ping')

        # Reload from file
        with open(temp_config) as f:
            config = yaml.safe_load(f)

        peer = next(p for p in config['peers'] if p['name'] == 'AnotherPeer')
        assert len(peer['test_endpoints']) == 1
        assert peer['test_endpoints'][0]['target'] == '10.1.0.1'

    def test_add_duplicate_endpoint_fails(self, temp_config):
        """Test adding duplicate endpoint fails."""
        mgr = PeerSpecManager(temp_config)
        with pytest.raises(DomainValidationError):
            mgr.add_test_endpoint('TestPeer', '10.0.0.1', 'ping')

    def test_add_endpoint_invalid_protocol(self, temp_config):
        """Test adding endpoint with invalid protocol."""
        mgr = PeerSpecManager(temp_config)
        with pytest.raises(DomainValidationError):
            mgr.add_test_endpoint('AnotherPeer', '10.1.0.1', 'invalid_protocol')

    def test_add_endpoint_missing_port(self, temp_config):
        """Test adding HTTP endpoint without port."""
        mgr = PeerSpecManager(temp_config)
        with pytest.raises(DomainValidationError):
            mgr.add_test_endpoint('AnotherPeer', 'api.example.com', 'http')

    def test_add_endpoint_nonexistent_peer(self, temp_config):
        """Test adding endpoint to non-existent peer."""
        mgr = PeerSpecManager(temp_config)
        with pytest.raises(DomainValidationError):
            mgr.add_test_endpoint('NonExistent', '10.0.0.1', 'ping')


class TestRemoveTestEndpoint:
    """Test removing test endpoints."""

    def test_remove_endpoint(self, temp_config):
        """Test removing endpoint."""
        mgr = PeerSpecManager(temp_config)
        endpoints = mgr.remove_test_endpoint('TestPeer', '10.0.0.1')
        assert len(endpoints) == 1
        assert endpoints[0].target == 'api.test.local'

    def test_remove_endpoint_persists_to_yaml(self, temp_config):
        """Test removal is persisted to YAML."""
        mgr = PeerSpecManager(temp_config)
        mgr.remove_test_endpoint('TestPeer', '10.0.0.1')

        # Reload from file
        with open(temp_config) as f:
            config = yaml.safe_load(f)

        peer = next(p for p in config['peers'] if p['name'] == 'TestPeer')
        assert len(peer['test_endpoints']) == 1
        assert peer['test_endpoints'][0]['target'] == 'api.test.local'

    def test_remove_nonexistent_endpoint(self, temp_config):
        """Test removing non-existent endpoint."""
        mgr = PeerSpecManager(temp_config)
        with pytest.raises(DomainValidationError):
            mgr.remove_test_endpoint('TestPeer', '192.168.1.1')

    def test_remove_from_nonexistent_peer(self, temp_config):
        """Test removing from non-existent peer."""
        mgr = PeerSpecManager(temp_config)
        with pytest.raises(DomainValidationError):
            mgr.remove_test_endpoint('NonExistent', '10.0.0.1')


class TestYamlPersistence:
    """Test YAML persistence and formatting."""

    def test_yaml_format_preserved(self, temp_config):
        """Test YAML format is preserved after add/remove."""
        mgr = PeerSpecManager(temp_config)
        mgr.add_test_endpoint('AnotherPeer', '10.1.0.1', 'ping')

        # Check file is valid YAML
        with open(temp_config) as f:
            config = yaml.safe_load(f)

        assert 'peers' in config
        assert len(config['peers']) > 0

    def test_multiple_operations_consistency(self, temp_config):
        """Test multiple operations maintain consistency."""
        mgr = PeerSpecManager(temp_config)

        # Add endpoint
        mgr.add_test_endpoint('AnotherPeer', '10.1.0.1', 'ping')

        # List endpoints
        endpoints = mgr.list_test_endpoints('AnotherPeer')
        assert len(endpoints) == 1

        # Remove endpoint
        endpoints = mgr.remove_test_endpoint('AnotherPeer', '10.1.0.1')
        assert len(endpoints) == 0

        # Verify in file
        with open(temp_config) as f:
            config = yaml.safe_load(f)
        peer = next(p for p in config['peers'] if p['name'] == 'AnotherPeer')
        assert len(peer['test_endpoints']) == 0
