"""VPN Peer validation logic."""

from typing import List, Tuple
import re
import ipaddress

from domain.exceptions import DomainValidationError


class VpnPeerValidator:
    """Validates VPN peer specifications against schema and business rules."""

    @staticmethod
    def validate_spec(spec: dict) -> Tuple[bool, List[str]]:
        """
        Validate a VPN peer spec.

        Returns: (is_valid, list_of_errors)
        """
        errors = []

        # Required fields
        required = ['name', 'publicIp', 'bgpAsn', 'tunnelProfile', 'destinationCidrs']
        for field in required:
            if field not in spec:
                errors.append(f"Missing required field: {field}")

        if errors:
            return False, errors

        # Name validation
        if not re.match(r'^[a-z0-9-]{3,64}$', spec['name']):
            errors.append(
                f"Invalid name: {spec['name']} "
                f"(must be 3-64 lowercase alphanumeric + hyphen)"
            )

        # IP validation
        try:
            ip = ipaddress.ip_address(spec['publicIp'])
            if ip.version != 4:
                errors.append(f"Invalid IP: must be IPv4, got {spec['publicIp']}")
        except ValueError:
            errors.append(f"Invalid IP address: {spec['publicIp']}")

        # BGP ASN validation
        try:
            bgp_asn = int(spec['bgpAsn'])
            if not (1 <= bgp_asn <= 65534):
                errors.append(f"Invalid BGP ASN: {bgp_asn} (must be 1-65534)")
        except (ValueError, TypeError):
            errors.append(f"Invalid BGP ASN: {spec['bgpAsn']} (must be integer)")

        # Tunnel profile
        if not spec.get('tunnelProfile'):
            errors.append("Tunnel profile must be specified")

        # Destination CIDRs
        cidrs = spec.get('destinationCidrs', [])
        if not cidrs:
            errors.append("At least one destination CIDR required")
        else:
            for cidr in cidrs:
                try:
                    ipaddress.ip_network(cidr, strict=False)
                except ValueError:
                    errors.append(f"Invalid CIDR: {cidr}")

            # Check for overlaps with Organization reserved
            vpn_reserved = ipaddress.ip_network("172.33.0.0/16")
            for cidr in cidrs:
                try:
                    net = ipaddress.ip_network(cidr, strict=False)
                    if net.overlaps(vpn_reserved):
                        errors.append(
                            f"CIDR {cidr} overlaps with reserved Organization network"
                        )
                except ValueError:
                    pass  # Already reported above

        # PSK validation
        psk_config = spec.get('psk', {})
        for tunnel in ['tunnel1', 'tunnel2']:
            psk = psk_config.get(tunnel, '')
            if psk and len(psk) < 32:
                errors.append(
                    f"PSK {tunnel} too short: {len(psk)} chars "
                    f"(minimum 32)"
                )

        # Device info
        if not spec.get('deviceType'):
            errors.append("Device type must be specified")

        # Contacts
        contacts = spec.get('contacts', [])
        if not contacts:
            errors.append("At least one contact required")
        else:
            for i, contact in enumerate(contacts):
                if not contact.get('name'):
                    errors.append(f"Contact {i} missing name")
                if not contact.get('email'):
                    errors.append(f"Contact {i} missing email")

        return len(errors) == 0, errors

    @staticmethod
    def validate_name(name: str) -> Tuple[bool, str]:
        """Validate peer name format."""
        if not name:
            return False, "Name cannot be empty"
        if not re.match(r'^[a-z0-9-]{3,64}$', name):
            return False, (
                f"Invalid name: {name} "
                f"(must be 3-64 lowercase alphanumeric + hyphen)"
            )
        return True, ""

    @staticmethod
    def validate_cidr(cidr: str) -> Tuple[bool, str]:
        """Validate CIDR block."""
        try:
            ipaddress.ip_network(cidr, strict=False)
            return True, ""
        except ValueError as e:
            return False, f"Invalid CIDR: {cidr} - {e}"

    @staticmethod
    def validate_psk(psk: str) -> Tuple[bool, str]:
        """Validate PSK strength."""
        if not psk:
            return False, "PSK cannot be empty"
        if len(psk) < 32:
            return False, f"PSK too short: {len(psk)} chars (minimum 32)"
        return True, ""
