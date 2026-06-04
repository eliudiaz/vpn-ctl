"""Reusable prompt helpers for interactive CLI wizards."""

import click
import re
import ipaddress
import secrets
from typing import List, Tuple, Optional, Dict, Any


def prompt_peer_name() -> str:
    """Prompt for peer name with validation."""
    while True:
        name = click.prompt(
            "Peer Name",
            type=str,
            default=""
        ).strip().lower()

        if not name:
            click.secho("❌ Peer name required", fg='red')
            continue

        if not re.match(r'^[a-z0-9][a-z0-9\-]*[a-z0-9]$', name):
            click.secho(
                "❌ Invalid: start/end with letter or number, use a-z, 0-9, or hyphen",
                fg='red'
            )
            continue

        if len(name) < 3 or len(name) > 64:
            click.secho("❌ Name must be 3-64 characters", fg='red')
            continue

        return name


def prompt_public_ip() -> str:
    """Prompt for public IP address with validation."""
    while True:
        ip = click.prompt("Public IP Address", type=str).strip()

        try:
            ip_obj = ipaddress.ip_address(ip)

            if ip_obj.is_private:
                click.secho("❌ Must be public IP (not private range)", fg='red')
                continue

            if ip_obj.is_loopback:
                click.secho("❌ Cannot use loopback address", fg='red')
                continue

            return ip
        except ValueError:
            click.secho("❌ Invalid IP address format", fg='red')


def prompt_bgp_asn() -> int:
    """Prompt for BGP ASN with validation."""
    while True:
        try:
            asn_str = click.prompt("BGP ASN (1-65534)", type=str).strip()
            asn = int(asn_str)

            if asn < 1 or asn > 65534:
                click.secho("❌ BGP ASN must be 1-65534", fg='red')
                continue

            return asn
        except ValueError:
            click.secho("❌ BGP ASN must be a number", fg='red')


def prompt_device_type() -> Tuple[str, str]:
    """Prompt for device type and version."""
    device_types = {
        '1': ('checkpoint', 'Checkpoint'),
        '2': ('fortigate', 'Fortinet FortiGate'),
        '3': ('palo-alto', 'Palo Alto Networks'),
        '4': ('juniper', 'Juniper'),
        '5': ('cisco', 'Cisco'),
        '6': ('other', 'Other/Custom'),
    }

    click.echo("\nDevice Type:")
    for key, (_, display) in device_types.items():
        click.echo(f"  {key}. {display}")

    while True:
        choice = click.prompt("Select device type (1-6)", type=str).strip()
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(device_types):
                device_type = device_types[idx]
                version = click.prompt(f"{device_type.title()} version")
                return device_type, version
        except (ValueError, IndexError):
            pass
        click.secho("❌ Invalid choice", fg='red')


def prompt_destination_cidrs() -> List[str]:
    """Prompt for destination CIDRs with validation."""
    click.echo("\nDestination CIDRs (comma-separated):")
    click.echo("  Example: 10.0.0.0/16, 10.1.0.0/16, 192.168.0.0/24")

    while True:
        cidrs_input = click.prompt("CIDRs")
        cidrs = [c.strip() for c in cidrs_input.split(',')]

        try:
            for cidr in cidrs:
                ipaddress.ip_network(cidr, strict=False)
            return cidrs
        except ValueError as e:
            click.secho(f"❌ Invalid CIDR: {e}", fg='red')


def prompt_tunnel_profile() -> str:
    """Prompt for tunnel profile."""
    profiles = {
        'checkpoint_r80': 'Checkpoint R80+',
        'checkpoint_r77': 'Checkpoint R77.x',
        'fortigate_latest': 'FortiGate (Latest)',
        'palo_alto_pan': 'Palo Alto PAN-OS',
        'generic': 'Generic IPSec',
    }

    click.echo("\nTunnel Profile:")
    for i, (key, label) in enumerate(profiles.items(), 1):
        click.echo(f"  {i}. {label}")

    while True:
        choice = click.prompt("Select profile (1-5)")
        try:
            idx = int(choice) - 1
            profile_list = list(profiles.keys())
            if 0 <= idx < len(profile_list):
                return profile_list[idx]
        except (ValueError, IndexError):
            pass
        click.secho("❌ Invalid choice", fg='red')


def prompt_psk(auto_generate: bool = True) -> Tuple[str, str]:
    """Prompt for PSKs or auto-generate."""
    if auto_generate:
        response = click.confirm("Auto-generate PSKs?", default=True)
        if response:
            from domain.services.psk_service import PskService
            try:
                psk_svc = PskService()
                psk1 = psk_svc.generate_psk()
                psk2 = psk_svc.generate_psk()
                click.secho(f"✓ PSKs auto-generated", fg='green')
                return psk1, psk2
            except:
                click.secho("⚠️  Could not auto-generate, please enter manually", fg='yellow')

    # Manual entry
    psk1 = click.prompt("PSK Tunnel 1", hide_input=True)
    psk2 = click.prompt("PSK Tunnel 2", hide_input=True)

    if len(psk1) < 32 or len(psk2) < 32:
        click.secho("⚠️  Warning: PSKs less than 32 chars (weak security)", fg='yellow')

    return psk1, psk2


def prompt_contacts() -> Dict[str, Optional[str]]:
    """Prompt for contact information."""
    click.echo("\nContact Information (optional):")

    contact_name = click.prompt("Contact Name", type=str, default="").strip() or None
    contact_email = click.prompt("Contact Email", type=str, default="").strip() or None
    contact_phone = click.prompt("Contact Phone", type=str, default="").strip() or None

    return {
        'name': contact_name,
        'email': contact_email,
        'phone': contact_phone,
    }


def prompt_health_check_targets() -> List[str]:
    """Prompt for health check target IPs."""
    click.echo("\nHealth Check Targets (optional - comma-separated IPs):")
    click.echo("  Example: 10.0.1.1, 10.0.1.2")

    targets_input = click.prompt(
        "IPs (leave blank for defaults)",
        type=str,
        default=""
    ).strip()

    if not targets_input:
        return []

    targets = [ip.strip() for ip in targets_input.split(',') if ip.strip()]

    try:
        for target in targets:
            ipaddress.ip_address(target)
        return targets
    except ValueError as e:
        click.secho(f"❌ Invalid IP address: {e}", fg='red')
        return []


def prompt_confirmation(message: str, default: bool = True) -> bool:
    """Prompt for user confirmation."""
    return click.confirm(f"\n? {message}", default=default)


# Alias for backward compatibility
def prompt_confirm(message: str, default: bool = True) -> bool:
    """Alias for prompt_confirmation (backward compatible)."""
    return prompt_confirmation(message, default)


def prompt_confirm(message: str, default: bool = False) -> bool:
    """Prompt for confirmation."""
    return click.confirm(message, default=default)


__all__ = [
    'prompt_peer_name',
    'prompt_public_ip',
    'prompt_bgp_asn',
    'prompt_device_type',
    'prompt_destination_cidrs',
    'prompt_tunnel_profile',
    'prompt_psk',
    'prompt_contacts',
    'prompt_confirm',
]
