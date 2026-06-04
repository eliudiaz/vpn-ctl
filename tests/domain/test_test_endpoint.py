"""Unit tests for TestEndpoint value object."""

import pytest
from domain.models.test_endpoint import TestEndpoint
from domain.exceptions import DomainValidationError


class TestCreation:
    """Test creating TestEndpoint instances."""

    def test_ping_endpoint_with_ip(self):
        """Test creating ping endpoint with IPv4."""
        ep = TestEndpoint(target="192.168.1.1", protocol="ping")
        assert ep.target == "192.168.1.1"
        assert ep.protocol == "ping"
        assert ep.port is None

    def test_http_endpoint_with_url(self):
        """Test creating HTTP endpoint with hostname."""
        ep = TestEndpoint(target="api.example.com", protocol="http", port=8080)
        assert ep.target == "api.example.com"
        assert ep.protocol == "http"
        assert ep.port == 8080

    def test_https_endpoint_with_fqdn(self):
        """Test creating HTTPS endpoint with FQDN."""
        ep = TestEndpoint(target="api-internal.service.local", protocol="https", port=443)
        assert ep.target == "api-internal.service.local"
        assert ep.protocol == "https"
        assert ep.port == 443

    def test_tcp_endpoint_with_port(self):
        """Test creating TCP endpoint with port."""
        ep = TestEndpoint(target="10.0.0.1", protocol="tcp", port=5432)
        assert ep.target == "10.0.0.1"
        assert ep.protocol == "tcp"
        assert ep.port == 5432

    def test_dns_endpoint_with_hostname(self):
        """Test creating DNS endpoint."""
        ep = TestEndpoint(target="dns.example.com", protocol="dns")
        assert ep.target == "dns.example.com"
        assert ep.protocol == "dns"
        assert ep.port is None


class TestTargetValidation:
    """Test target validation."""

    def test_valid_ipv4(self):
        """Test valid IPv4 addresses."""
        valid_ips = [
            "192.168.1.1",
            "10.0.0.0",
            "172.16.0.1",
            "255.255.255.255",
        ]
        for ip in valid_ips:
            ep = TestEndpoint(target=ip, protocol="ping")
            assert ep.target == ip

    def test_invalid_ipv4(self):
        """Test invalid IPv4 addresses."""
        invalid_ips = [
            "256.1.1.1",
            "192.168.1",
            "192.168.1.1.1",
        ]
        for ip in invalid_ips:
            with pytest.raises(DomainValidationError):
                TestEndpoint(target=ip, protocol="ping")

    def test_valid_hostnames(self):
        """Test valid hostnames."""
        valid_hostnames = [
            "example.com",
            "api.example.com",
            "api-internal.service.local",
            "10-node-1.internal",
            "db_server.local",
            "host1",
            "192.168.a.1",  # Valid as a hostname (even if looks IP-like)
        ]
        for hostname in valid_hostnames:
            ep = TestEndpoint(target=hostname, protocol="ping")
            assert ep.target == hostname

    def test_invalid_hostnames(self):
        """Test invalid hostnames."""
        invalid_hostnames = [
            "-invalid.com",
            "invalid-.com",
            "invalid..com",
            "invalid@.com",
        ]
        for hostname in invalid_hostnames:
            with pytest.raises(DomainValidationError):
                TestEndpoint(target=hostname, protocol="ping")


class TestProtocolValidation:
    """Test protocol validation."""

    def test_valid_protocols(self):
        """Test all valid protocols."""
        valid_protocols = ["ping", "http", "https", "tcp", "dns"]
        for protocol in valid_protocols:
            # dns and ping don't require port
            if protocol in ["dns", "ping"]:
                ep = TestEndpoint(target="example.com", protocol=protocol)
                assert ep.protocol == protocol
            else:
                # http, https, tcp require port
                ep = TestEndpoint(target="example.com", protocol=protocol, port=443)
                assert ep.protocol == protocol

    def test_invalid_protocol(self):
        """Test invalid protocol."""
        with pytest.raises(DomainValidationError):
            TestEndpoint(target="example.com", protocol="ftp", port=21)


class TestPortValidation:
    """Test port validation."""

    def test_http_requires_port(self):
        """Test HTTP requires port."""
        with pytest.raises(DomainValidationError):
            TestEndpoint(target="example.com", protocol="http")

    def test_https_requires_port(self):
        """Test HTTPS requires port."""
        with pytest.raises(DomainValidationError):
            TestEndpoint(target="example.com", protocol="https")

    def test_tcp_requires_port(self):
        """Test TCP requires port."""
        with pytest.raises(DomainValidationError):
            TestEndpoint(target="example.com", protocol="tcp")

    def test_ping_does_not_require_port(self):
        """Test ping doesn't require port."""
        ep = TestEndpoint(target="example.com", protocol="ping")
        assert ep.port is None

    def test_dns_does_not_require_port(self):
        """Test DNS doesn't require port."""
        ep = TestEndpoint(target="example.com", protocol="dns")
        assert ep.port is None

    def test_valid_port_range(self):
        """Test valid port range."""
        for port in [1, 80, 443, 8080, 65535]:
            ep = TestEndpoint(target="example.com", protocol="http", port=port)
            assert ep.port == port

    def test_invalid_port_too_low(self):
        """Test port below valid range."""
        with pytest.raises(DomainValidationError):
            TestEndpoint(target="example.com", protocol="http", port=0)

    def test_invalid_port_too_high(self):
        """Test port above valid range."""
        with pytest.raises(DomainValidationError):
            TestEndpoint(target="example.com", protocol="http", port=65536)


class TestSerialization:
    """Test to_dict and from_dict methods."""

    def test_to_dict_with_port(self):
        """Test serialization with port."""
        ep = TestEndpoint(target="example.com", protocol="http", port=8080)
        data = ep.to_dict()
        assert data == {"target": "example.com", "protocol": "http", "port": 8080}

    def test_to_dict_without_port(self):
        """Test serialization without port."""
        ep = TestEndpoint(target="example.com", protocol="ping")
        data = ep.to_dict()
        assert data == {"target": "example.com", "protocol": "ping"}

    def test_from_dict_with_port(self):
        """Test deserialization with port."""
        data = {"target": "example.com", "protocol": "http", "port": 8080}
        ep = TestEndpoint.from_dict(data)
        assert ep.target == "example.com"
        assert ep.protocol == "http"
        assert ep.port == 8080

    def test_from_dict_without_port(self):
        """Test deserialization without port."""
        data = {"target": "example.com", "protocol": "ping"}
        ep = TestEndpoint.from_dict(data)
        assert ep.target == "example.com"
        assert ep.protocol == "ping"
        assert ep.port is None

    def test_roundtrip_serialization(self):
        """Test roundtrip serialization/deserialization."""
        original = TestEndpoint(target="api.service.local", protocol="https", port=443)
        data = original.to_dict()
        restored = TestEndpoint.from_dict(data)
        assert restored.target == original.target
        assert restored.protocol == original.protocol
        assert restored.port == original.port


class TestStringRepresentation:
    """Test __str__ and __repr__ methods."""

    def test_str_with_port(self):
        """Test string representation with port."""
        ep = TestEndpoint(target="example.com", protocol="http", port=8080)
        assert str(ep) == "example.com:8080 (http)"

    def test_str_without_port(self):
        """Test string representation without port."""
        ep = TestEndpoint(target="example.com", protocol="ping")
        assert str(ep) == "example.com (ping)"

    def test_repr(self):
        """Test repr representation."""
        ep = TestEndpoint(target="example.com", protocol="http", port=8080)
        assert "TestEndpoint" in repr(ep)
        assert "example.com" in repr(ep)
        assert "http" in repr(ep)
        assert "8080" in repr(ep)
