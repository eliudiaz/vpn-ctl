"""Tests for domain value objects."""

import pytest
from domain.models.value_objects import BGPASN, CIDR, PSK, PeerName, PublicIP
from domain.exceptions import DomainValidationError, CIDRParsingError


class TestBGPASN:
    """BGPASN value object tests."""

    def test_valid_bgp_asn(self):
        """Valid BGP ASNs should be created."""
        assert BGPASN(65000).value == 65000
        assert BGPASN(1).value == 1
        assert BGPASN(65534).value == 65534

    def test_invalid_bgp_asn_too_low(self):
        """BGP ASN below 1 should raise."""
        with pytest.raises(DomainValidationError):
            BGPASN(0)

    def test_invalid_bgp_asn_too_high(self):
        """BGP ASN above 65534 should raise."""
        with pytest.raises(DomainValidationError):
            BGPASN(65535)


class TestCIDR:
    """CIDR value object tests."""

    def test_valid_cidr(self):
        """Valid CIDRs should be created."""
        cidr = CIDR("10.0.0.0/16")
        assert str(cidr) == "10.0.0.0/16"

    def test_invalid_cidr_format(self):
        """Invalid CIDR format should raise."""
        with pytest.raises(CIDRParsingError):
            CIDR("invalid-cidr")

    def test_cidr_overlap_detection(self):
        """CIDR overlap should be detectable."""
        cidr1 = CIDR("10.0.0.0/24")
        cidr2 = CIDR("10.0.0.128/25")
        assert cidr1.overlaps_with(cidr2)

    def test_cidr_no_overlap(self):
        """Non-overlapping CIDRs should not overlap."""
        cidr1 = CIDR("10.0.0.0/16")
        cidr2 = CIDR("172.16.0.0/16")
        assert not cidr1.overlaps_with(cidr2)


class TestPSK:
    """PSK value object tests."""

    def test_valid_psk(self):
        """Valid PSK should be created."""
        psk = PSK("a" * 32)
        assert len(psk.secure_value) > 0

    def test_invalid_psk_too_short(self):
        """PSK shorter than 32 chars should raise."""
        with pytest.raises(DomainValidationError):
            PSK("short")

    def test_psk_generation(self):
        """PSK should be generatable."""
        psk = PSK.generate()
        assert len(psk.secure_value) >= 32


class TestPeerName:
    """PeerName value object tests."""

    def test_valid_peer_name(self):
        """Valid peer names should be created."""
        name = PeerName("test-peer-123")
        assert str(name) == "test-peer-123"

    def test_invalid_peer_name_uppercase(self):
        """Uppercase in peer name should raise."""
        with pytest.raises(DomainValidationError):
            PeerName("Test-Peer")

    def test_invalid_peer_name_special_chars(self):
        """Special chars in peer name should raise."""
        with pytest.raises(DomainValidationError):
            PeerName("test_peer!")


class TestPublicIP:
    """PublicIP value object tests."""

    def test_valid_public_ip(self):
        """Valid public IPs should be created."""
        ip = PublicIP("8.8.8.8")
        assert str(ip) == "8.8.8.8"

    def test_invalid_public_ip_format(self):
        """Invalid IP format should raise."""
        with pytest.raises(DomainValidationError):
            PublicIP("not-an-ip")

    def test_invalid_public_ip_private_range(self):
        """Private IP ranges should raise."""
        with pytest.raises(DomainValidationError):
            PublicIP("192.168.1.1")
