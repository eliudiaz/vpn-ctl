"""Interactive wizard for creating VPN peer specifications."""

import click
import yaml
from pathlib import Path
from typing import Optional
from dataclasses import asdict

from .prompts import (
    prompt_peer_name,
    prompt_public_ip,
    prompt_bgp_asn,
    prompt_device_type,
    prompt_destination_cidrs,
    prompt_tunnel_profile,
    prompt_psk,
    prompt_contacts,
    prompt_health_check_targets,
    prompt_confirm,
)


class PeerWizard:
    """Interactive wizard for creating VPN peer specifications."""

    def __init__(self, specs_dir: str = "config/peers"):
        self.specs_dir = Path(specs_dir)
        self.specs_dir.mkdir(parents=True, exist_ok=True)

    def run(self) -> Optional[dict]:
        """Run wizard, return peer specification dict."""
        click.echo()
        click.secho("🔧 VPN Peer Configuration Wizard", fg='cyan', bold=True)
        click.echo()

        try:
            # Step 1: Basic Information
            click.secho("Step 1: Basic Information", fg='yellow')
            click.echo()
            peer_name = prompt_peer_name()
            public_ip = prompt_public_ip()
            bgp_asn = prompt_bgp_asn()

            # Step 2: Device Configuration
            click.echo()
            click.secho("Step 2: Device Configuration", fg='yellow')
            click.echo()
            device_type, device_version = prompt_device_type()
            tunnel_profile = prompt_tunnel_profile()

            # Step 3: Network Configuration
            click.echo()
            click.secho("Step 3: Network Configuration", fg='yellow')
            click.echo()
            destination_cidrs = prompt_destination_cidrs()

            # Step 4: Security Configuration
            click.echo()
            click.secho("Step 4: Security Configuration", fg='yellow')
            click.echo()
            psk1, psk2 = prompt_psk()

            # Step 5: Health Checks (Optional)
            click.echo()
            click.secho("Step 5: Health Checks (Optional)", fg='yellow')
            click.echo()
            health_check_targets = prompt_health_check_targets()

            # Step 6: Contact Information
            click.echo()
            click.secho("Step 6: Contact Information", fg='yellow')
            click.echo()
            contacts = prompt_contacts()

            # Build specification
            # Extract PSK values if they are objects with secure_value property
            psk1_value = psk1.secure_value if hasattr(psk1, 'secure_value') else psk1
            psk2_value = psk2.secure_value if hasattr(psk2, 'secure_value') else psk2

            spec = {
                'name': peer_name,
                'enabled': False,
                'device_type': device_type,
                'device_version': device_version,
                'public_ip': public_ip,
                'bgp_asn': bgp_asn,
                'destination_cidrs': destination_cidrs,
                'tunnel_profile': tunnel_profile,
                'psk_tunnel1': psk1_value,
                'psk_tunnel2': psk2_value,
                'health_check_targets': health_check_targets,
                'contacts': {k: v for k, v in contacts.items() if v},
            }

            # Review and confirm
            click.echo()
            click.secho("Step 7: Review", fg='yellow')
            self._display_review(spec)

            click.echo()
            if not prompt_confirm("Create peer specification?", default=True):
                click.echo("❌ Cancelled")
                return None

            # Save specification
            spec_file = self.specs_dir / f"{peer_name}.yaml"
            self._save_spec(spec, spec_file)

            click.echo()
            click.secho(f"✅ Peer specification created", fg='green')
            click.echo(f"   File: {spec_file}")

            return spec

        except KeyboardInterrupt:
            click.echo()
            click.secho("⚠️  Wizard cancelled", fg='yellow')
            return None
        except Exception as e:
            click.secho(f"❌ Error: {e}", fg='red')
            return None

    def _display_review(self, spec: dict) -> None:
        """Display review of peer specification."""
        click.echo()
        click.secho("Peer Specification Summary:", fg='cyan', bold=True)
        click.echo()
        click.echo(f"  Name:              {spec['name']}")
        click.echo(f"  Public IP:         {spec['public_ip']}")
        click.echo(f"  BGP ASN:           {spec['bgp_asn']}")
        click.echo(f"  Device:            {spec['device_type']} {spec['device_version']}")
        click.echo(f"  Tunnel Profile:    {spec['tunnel_profile']}")
        click.echo(f"  Destination CIDRs: {', '.join(spec['destination_cidrs'])}")
        click.echo(f"  PSK Tunnel 1:      {'*' * 16}")
        click.echo(f"  PSK Tunnel 2:      {'*' * 16}")

        if spec.get('health_check_targets'):
            click.echo(f"  Health Checks:     {', '.join(spec['health_check_targets'])}")

        if spec.get('contacts'):
            contact_info = []
            if spec['contacts'].get('name'):
                contact_info.append(spec['contacts']['name'])
            if spec['contacts'].get('email'):
                contact_info.append(f"({spec['contacts']['email']})")
            if contact_info:
                click.echo(f"  Contact:           {' '.join(contact_info)}")

    def _save_spec(self, spec: dict, spec_file: Path) -> None:
        """Save specification to YAML file."""
        # Remove sensitive data before saving
        spec_to_save = spec.copy()

        with open(spec_file, 'w') as f:
            yaml.dump(spec_to_save, f, default_flow_style=False, sort_keys=False)


__all__ = ['PeerWizard']
