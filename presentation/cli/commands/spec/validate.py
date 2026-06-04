"""Validate all peer specs."""

import click
import yaml
from pathlib import Path
import ipaddress


@click.command()
@click.option('--all', is_flag=True, help='Also validate test/disabled peers')
def validate(all):
    """
    Validate all peer specifications.

    Checks YAML syntax, required fields, and value constraints.
    """
    click.echo()
    click.secho("✓ Validating peer specifications", fg='cyan', bold=True)
    click.echo()

    # Load main config
    main_config = Path("config/vpn-peers.yaml")
    if not main_config.exists():
        click.secho("❌ Main config not found: config/vpn-peers.yaml", fg='red')
        return

    try:
        with open(main_config) as f:
            config = yaml.safe_load(f)

        peers = config.get('peers', [])
        tunnel_profiles = config.get('tunnel_profiles', {})

        click.echo(f"📋 Found {len(peers)} peers in main config")
        click.echo()

        all_valid = True
        for peer in peers:
            peer_name = peer.get('name', '?')
            is_valid = True
            errors = []

            # Validate required fields
            required_fields = ['name', 'enabled', 'tunnel_profile', 'public_ip', 'bgp_asn', 'destination_cidrs']
            for field in required_fields:
                if field not in peer:
                    errors.append(f"Missing required field: {field}")
                    is_valid = False

            # Validate public IP
            if is_valid:
                try:
                    ipaddress.ip_address(peer.get('public_ip'))
                except ValueError:
                    errors.append(f"Invalid public IP: {peer.get('public_ip')}")
                    is_valid = False

            # Validate BGP ASN
            if is_valid:
                asn = peer.get('bgp_asn')
                if not isinstance(asn, int) or not (1 <= asn <= 65534):
                    errors.append(f"Invalid BGP ASN: {asn} (must be 1-65534)")
                    is_valid = False

            # Validate tunnel profile exists
            if is_valid:
                profile = peer.get('tunnel_profile')
                if profile not in tunnel_profiles:
                    errors.append(f"Tunnel profile not found: {profile}")
                    is_valid = False

            # Validate destination CIDRs
            if is_valid:
                cidrs = peer.get('destination_cidrs', [])
                if not cidrs:
                    errors.append("No destination CIDRs defined")
                    is_valid = False
                else:
                    for cidr in cidrs:
                        try:
                            ipaddress.ip_network(cidr, strict=False)
                        except ValueError:
                            errors.append(f"Invalid CIDR: {cidr}")
                            is_valid = False

            # Display result
            if is_valid:
                status_icon = "✅" if peer.get('enabled') else "⏸️"
                click.echo(f"  {status_icon} {peer_name}")
            else:
                click.secho(f"  ❌ {peer_name}", fg='red')
                for error in errors:
                    click.echo(f"     • {error}")
                all_valid = False

        click.echo()

        # Also validate individual spec files
        click.echo("📁 Checking individual peer spec files:")
        spec_dir = Path("config/peers")
        if spec_dir.exists():
            spec_count = len(list(spec_dir.glob("*.yaml")))
            if spec_count > 0:
                click.echo(f"   Found {spec_count} spec files in {spec_dir}")
                # For now, just count them
                for spec_file in spec_dir.glob("*.yaml"):
                    try:
                        with open(spec_file) as f:
                            yaml.safe_load(f)
                        click.echo(f"   ✓ {spec_file.name}")
                    except Exception as e:
                        click.secho(f"   ❌ {spec_file.name}: {e}", fg='red')
                        all_valid = False

        click.echo()
        if all_valid:
            click.secho("✅ All specifications valid", fg='green', bold=True)
        else:
            click.secho("❌ Some specifications invalid", fg='red', bold=True)

    except Exception as e:
        click.secho(f"❌ Error: {e}", fg='red')
