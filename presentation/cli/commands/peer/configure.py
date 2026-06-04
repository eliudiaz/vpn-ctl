"""Show peer configuration details for customer setup."""

import click
import yaml
from pathlib import Path
from datetime import datetime


@click.command()
@click.argument('peer_name')
@click.option('--format', type=click.Choice(['text', 'json', 'fortinet', 'checkpoint']),
              default='text', help='Output format')
@click.option('--show-psk', is_flag=True, help='Show pre-shared keys (secure)')
def configure(peer_name, format, show_psk):
    """
    Show peer network configuration for customer tunnel setup.

    Displays all encryption settings, IPs, and parameters needed for
    FortiGate, Checkpoint, Palo Alto, or other customer devices.
    """
    # Load peer configuration from main config
    config_file = Path("config/vpn-peers.yaml")
    if not config_file.exists():
        click.secho(f"❌ Config not found: {config_file}", fg='red')
        return

    with open(config_file) as f:
        config = yaml.safe_load(f)

    # Find peer
    peers = config.get('peers', [])
    peer = None
    for p in peers:
        if p['name'].lower() == peer_name.lower():
            peer = p
            break

    if not peer:
        click.secho(f"❌ Peer not found: {peer_name}", fg='red')
        return

    # Load tunnel profile
    tunnel_profiles = config.get('tunnel_profiles', {})
    profile_name = peer.get('tunnel_profile', 'unknown')
    profile = tunnel_profiles.get(profile_name, {})

    # Route output based on format
    if format == 'fortinet':
        _display_fortinet_config(peer, profile, show_psk)
    elif format == 'checkpoint':
        _display_checkpoint_config(peer, profile, show_psk)
    elif format == 'json':
        _display_json_config(peer, profile, show_psk)
    else:
        _display_text_config(peer, profile, show_psk)


def _display_text_config(peer, profile, show_psk):
    """Display full configuration in readable text format."""
    click.echo()
    click.secho(f"🔐 Peer Configuration: {peer['name']}", fg='cyan', bold=True)
    click.echo()

    # AWS Side Information
    click.secho("AWS INFRASTRUCTURE", fg='yellow', bold=True)
    click.echo(f"  Peer Name:              {peer['name']}")
    click.echo(f"  VPN Connection Type:    Site-to-Site VPN (IPSec)")
    click.echo(f"  AWS Region:             us-east-2")
    click.echo(f"  Transit Gateway:        tgw-0abc1234def5678")
    click.echo()

    # Customer Side Information
    click.secho("CUSTOMER SIDE (YOUR DEVICE)", fg='yellow', bold=True)
    click.echo(f"  Device Type:            {peer.get('device_type', 'Unknown')}")
    click.echo(f"  Device Version:         {peer.get('device_version', 'Unknown')}")
    click.echo(f"  Public IP Address:      {peer.get('public_ip')}")
    click.echo(f"  BGP ASN:                {peer.get('bgp_asn')}")
    click.echo()

    # Destination Networks
    click.secho("DESTINATION NETWORKS (Behind AWS)", fg='yellow', bold=True)
    cidrs = peer.get('destination_cidrs', [])
    for cidr in cidrs:
        click.echo(f"  • {cidr}")
    click.echo()

    # AWS Tunnel Endpoints
    click.secho("AWS TUNNEL ENDPOINTS", fg='yellow', bold=True)
    click.echo(f"  Tunnel 1 IP:            3.131.49.110")
    click.echo(f"  Tunnel 2 IP:            3.151.46.131")
    click.echo()

    # IKE Phase 1 Settings
    click.secho("PHASE 1 (IKE) SETTINGS", fg='yellow', bold=True)
    phase1 = profile.get('phase1', {})
    click.echo(f"  IKE Version:            {', '.join(profile.get('ike_versions', ['IKEv2']))}")
    click.echo(f"  Encryption:             {', '.join(phase1.get('encryption', ['AES256']))}")
    click.echo(f"  Integrity/Hash:         {', '.join(phase1.get('integrity', ['SHA2-256']))}")
    click.echo(f"  DH Group:               {', '.join(str(dh) for dh in phase1.get('dh_groups', [14]))}")
    click.echo(f"  Key Lifetime (Seconds): {phase1.get('lifetime', 28800)}")
    click.echo()

    # IKE Phase 2 Settings
    click.secho("PHASE 2 (IPSec) SETTINGS", fg='yellow', bold=True)
    phase2 = profile.get('phase2', {})
    click.echo(f"  Encryption:             {', '.join(phase2.get('encryption', ['AES256']))}")
    click.echo(f"  Integrity/Hash:         {', '.join(phase2.get('integrity', ['SHA2-256']))}")
    pfs_dh = phase2.get('dh_groups', [])
    pfs_enabled = profile.get('pfs_enabled', len(pfs_dh) > 0)
    click.echo(f"  PFS (Perfect Forward):  {'Yes' if pfs_enabled else 'No'}")
    if pfs_enabled:
        click.echo(f"  PFS DH Group:           {', '.join(str(dh) for dh in pfs_dh)}")
    click.echo(f"  SA Lifetime (Seconds):  {phase2.get('lifetime', 3600)}")
    click.echo()

    # DPD Settings
    click.secho("DPD (DEAD PEER DETECTION)", fg='yellow', bold=True)
    dpd = profile.get('dpd', {})
    click.echo(f"  Timeout (Seconds):      {dpd.get('timeout', 30)}")
    click.echo(f"  Action:                 {dpd.get('action', 'restart').upper()}")
    click.echo()

    # Pre-Shared Keys
    click.secho("AUTHENTICATION", fg='yellow', bold=True)
    if show_psk:
        psk = peer.get('psk', {}) or {}
        click.echo(f"  PSK Tunnel 1:           {psk.get('tunnel1', 'NOT PROVIDED')}")
        click.echo(f"  PSK Tunnel 2:           {psk.get('tunnel2', 'NOT PROVIDED')}")
    else:
        click.echo(f"  PSK Tunnel 1:           [REQUEST FROM AWS]")
        click.echo(f"  PSK Tunnel 2:           [REQUEST FROM AWS]")
        click.secho("  ℹ️  Use --show-psk flag to display PSK values", fg='blue')
    click.echo()

    # Advanced Settings
    click.secho("ADVANCED SETTINGS", fg='yellow', bold=True)
    click.echo(f"  Aggressive Mode:        {'Yes' if profile.get('aggressive_mode') else 'No'}")
    click.echo(f"  Replay Detection:       {'Yes' if profile.get('replay_detection') else 'No'}")
    click.echo(f"  Nat Traversal:          No")
    click.echo(f"  Local Identifier:       {peer.get('public_ip')}")
    click.echo()

    # Contact Information
    contacts = peer.get('contacts', [])
    if contacts:
        click.secho("CONTACT INFORMATION", fg='yellow', bold=True)
        if isinstance(contacts, list):
            for contact in contacts:
                click.echo(f"  Name:                   {contact.get('name', 'N/A')}")
                click.echo(f"  Email:                  {contact.get('email', 'N/A')}")
                click.echo(f"  Phone:                  {contact.get('phone', 'N/A')}")
        elif isinstance(contacts, dict):
            click.echo(f"  Name:                   {contacts.get('name', 'N/A')}")
            click.echo(f"  Email:                  {contacts.get('email', 'N/A')}")
            click.echo(f"  Phone:                  {contacts.get('phone', 'N/A')}")
        click.echo()

    click.secho("SETUP INSTRUCTIONS", fg='yellow', bold=True)
    device_type = peer.get('device_type', '').lower()
    if 'fortinet' in device_type or 'fortigate' in device_type:
        click.echo(f"  1. Log in to FortiGate console")
        click.echo(f"  2. Go to: Network → VPN → IPsec Tunnels")
        click.echo(f"  3. Create 2 tunnels (Tunnel 1 & Tunnel 2) with above settings")
        click.echo(f"  4. Configure Phase 1 & Phase 2 with values above")
        click.echo(f"  5. Create static routes or BGP for destination networks")
        click.echo(f"  6. Test connectivity and monitor tunnel status")
    elif 'checkpoint' in device_type:
        click.echo(f"  1. Log in to Checkpoint SmartDashboard")
        click.echo(f"  2. Create Site-to-Site VPN connection")
        click.echo(f"  3. Configure remote gateway: 3.131.49.110 (Tunnel 1)")
        click.echo(f"  4. Configure remote gateway: 3.151.46.131 (Tunnel 2)")
        click.echo(f"  5. Set encryption domains for destination networks")
        click.echo(f"  6. Apply policy and test tunnel")
    else:
        click.echo(f"  Refer to your device vendor's VPN configuration guide")
        click.echo(f"  Use the settings above to configure Site-to-Site IPSec VPN")
    click.echo()


def _display_fortinet_config(peer, profile, show_psk):
    """Display configuration in Fortinet CLI format."""
    click.echo()
    click.secho("🔐 Fortinet FortiGate Configuration", fg='cyan', bold=True)
    click.echo()
    click.echo("# Phase 1 Configuration")
    click.echo("config vpn ipsec phase1-interface")
    click.echo(f"  edit \"aws-tunnel-1\"")
    click.echo(f"    set interface \"port1\"")
    click.echo(f"    set peer 3.131.49.110")
    click.echo(f"    set psk-identity {peer.get('public_ip')}")

    if show_psk:
        psk = peer.get('psk', {}) or {}
        click.echo(f"    set psksecret \"{psk.get('tunnel1', '')}\"")
    else:
        click.echo(f"    set psksecret \"[PSK-TUNNEL-1]\"")

    phase1 = profile.get('phase1', {})
    click.echo(f"    set dpd enable")
    click.echo(f"    set dpd-retrycount 3")
    click.echo(f"    set ike-version 2")
    click.echo(f"    set encryption {phase1.get('encryption', ['AES256'])[0].lower()}")
    click.echo(f"    set authentication {phase1.get('integrity', ['SHA2-256'])[0].lower()}")
    click.echo(f"    set dhgrp 14")
    click.echo(f"    set lifetime {phase1.get('lifetime', 28800)}")
    click.echo(f"  next")
    click.echo("end")
    click.echo()

    click.echo("# Phase 2 Configuration")
    click.echo("config vpn ipsec phase2-interface")
    click.echo(f"  edit \"aws-tunnel-1\"")
    click.echo(f"    set phase1name \"aws-tunnel-1\"")
    phase2 = profile.get('phase2', {})
    click.echo(f"    set encryption {phase2.get('encryption', ['AES256'])[0].lower()}")
    click.echo(f"    set authentication {phase2.get('integrity', ['SHA2-256'])[0].lower()}")
    pfs_enabled = profile.get('pfs_enabled', False)
    if pfs_enabled:
        click.echo(f"    set pfs enable")
        click.echo(f"    set dhgrp 14")
    else:
        click.echo(f"    set pfs disable")
    click.echo(f"    set lifetime {phase2.get('lifetime', 3600)}")
    click.echo(f"  next")
    click.echo("end")
    click.echo()

    click.echo("# Static Routes Configuration")
    cidrs = peer.get('destination_cidrs', [])
    for cidr in cidrs:
        click.echo(f"config router static")
        click.echo(f"  edit 0")
        click.echo(f"    set dst {cidr}")
        click.echo(f"    set device \"aws-tunnel-1\"")
        click.echo(f"  next")
        click.echo(f"end")
    click.echo()


def _display_checkpoint_config(peer, profile, show_psk):
    """Display configuration in Checkpoint format."""
    click.echo()
    click.secho("🔐 Checkpoint Configuration", fg='cyan', bold=True)
    click.echo()
    click.echo("# Create Remote Gateway")
    click.echo(f"Remote Gateway Name:    {peer['name']}-AWS")
    click.echo(f"Remote Gateway IP:      {peer.get('public_ip')}")
    click.echo()

    click.echo("# IPSec Phase 1 Settings")
    phase1 = profile.get('phase1', {})
    click.echo(f"IKE Version:            IKEv2")
    click.echo(f"Encryption:             {phase1.get('encryption', ['AES256'])[0]}")
    click.echo(f"Integrity:              {phase1.get('integrity', ['SHA2-256'])[0]}")
    click.echo(f"DH Group:               14")
    click.echo(f"Lifetime:               {phase1.get('lifetime', 28800)} seconds")
    click.echo()

    click.echo("# IPSec Phase 2 Settings")
    phase2 = profile.get('phase2', {})
    click.echo(f"Encryption:             {phase2.get('encryption', ['AES256'])[0]}")
    click.echo(f"Integrity:              {phase2.get('integrity', ['SHA2-256'])[0]}")
    click.echo(f"Lifetime:               {phase2.get('lifetime', 3600)} seconds")
    click.echo()

    click.echo("# Encryption Domain")
    cidrs = peer.get('destination_cidrs', [])
    for cidr in cidrs:
        click.echo(f"  {cidr}")
    click.echo()


def _display_json_config(peer, profile, show_psk):
    """Display configuration as JSON."""
    import json

    config = {
        'peer_name': peer['name'],
        'device_type': peer.get('device_type', 'Unknown'),
        'device_version': peer.get('device_version', 'Unknown'),
        'customer_public_ip': peer.get('public_ip'),
        'bgp_asn': peer.get('bgp_asn'),
        'aws_infrastructure': {
            'region': 'us-east-2',
            'transit_gateway': 'tgw-0abc1234def5678',
            'tunnel_endpoints': [
                {'tunnel': 1, 'ip': '3.131.49.110'},
                {'tunnel': 2, 'ip': '3.151.46.131'}
            ]
        },
        'destination_networks': peer.get('destination_cidrs', []),
        'phase1': profile.get('phase1', {}),
        'phase2': profile.get('phase2', {}),
        'dpd': profile.get('dpd', {}),
        'advanced': {
            'aggressive_mode': profile.get('aggressive_mode', False),
            'replay_detection': profile.get('replay_detection', False),
            'pfs_enabled': profile.get('pfs_enabled', False)
        }
    }

    if show_psk:
        psk = peer.get('psk', {}) or {}
        config['authentication'] = {
            'psk_tunnel1': psk.get('tunnel1', 'NOT PROVIDED'),
            'psk_tunnel2': psk.get('tunnel2', 'NOT PROVIDED')
        }
    else:
        config['authentication'] = {
            'note': 'PSK values hidden. Use --show-psk to display.'
        }

    click.echo(json.dumps(config, indent=2))


__all__ = ['configure']
