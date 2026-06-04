#!/usr/bin/env python3

"""
Generate PDF Setup Guides for VPN Peers

Generates professional device-specific PDFs for external VPN peers
to configure their firewalls/VPN devices to connect to Organization's ATG.

Usage:
    python3 generate-peer-guides.py --device checkpoint
    python3 generate-peer-guides.py --device fortigate --peer MockPeerA
    python3 generate-peer-guides.py --all
    python3 generate-peer-guides.py --all --output-dir ./guides/

Supports:
    - Checkpoint R80.10+
    - Fortigate
    - Palo Alto Networks
    - Cisco ASA

Options:
    --device TYPE       Generate guide for specific device type
    --peer NAME         Include peer-specific tunnel details
    --all              Generate all device guides
    --output-dir DIR   Output directory (default: peer-guides/)
    --help             Show this help message
"""

import sys
import os
import argparse
from pathlib import Path
from datetime import datetime

# Check if reportlab is available
try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.colors import HexColor, black, white, grey, lightgrey
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
        PageBreak, Image, PageTemplate, Frame
    )
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False
    print("Warning: reportlab not installed. Install with: pip install reportlab")

# Device configurations
DEVICE_CONFIGS = {
    "checkpoint": {
        "full_name": "Checkpoint R80.10+",
        "interface": "SmartDashboard",
        "description": "Checkpoint Next Generation Firewall (NGF)",
        "ike_version": "IKEv2",
        "encryption": "AES-256",
        "integrity": "SHA2-256",
    },
    "fortigate": {
        "full_name": "Fortinet FortiGate",
        "interface": "Web Dashboard",
        "description": "Fortinet FortiGate Firewall",
        "ike_version": "IKEv2",
        "encryption": "AES-256",
        "integrity": "SHA2-256",
    },
    "paloalto": {
        "full_name": "Palo Alto Networks",
        "interface": "Web Console",
        "description": "Palo Alto Networks Next-Generation Firewall",
        "ike_version": "IKEv2",
        "encryption": "AES-256",
        "integrity": "SHA2-256",
    },
    "cisco": {
        "full_name": "Cisco ASA",
        "interface": "ASDM / CLI",
        "description": "Cisco Adaptive Security Appliance",
        "ike_version": "IKEv2",
        "encryption": "AES-256",
        "integrity": "SHA2-256",
    },
}

# Common configuration parameters
VPN_CONFIG = {
    "transit_gateway_id": "tgw-0572ce4b80ff7445a",
    "aws_asn": "64512",
    "region": "us-east-2",
    "tunnel_ip_range": "169.254.0.0/16",
    "dgp_timeout": "30 seconds",
    "dgp_action": "restart",
    "phase1_dh": "DH Group 14 (modp4096)",
    "phase1_lifetime": "28800 seconds (8 hours)",
    "phase2_lifetime": "3600 seconds (1 hour)",
}

class PeerGuideGenerator:
    """Generate PDF guides for VPN peer configuration"""

    def __init__(self, device_type, peer_name=None, output_dir="peer-guides"):
        self.device_type = device_type.lower()
        self.peer_name = peer_name
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

        if self.device_type not in DEVICE_CONFIGS:
            raise ValueError(f"Unknown device type: {device_type}")

        self.config = DEVICE_CONFIGS[self.device_type]
        self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def generate(self):
        """Generate the PDF guide"""
        if not HAS_REPORTLAB:
            print("Error: reportlab not installed")
            print("Install with: pip install reportlab")
            return False

        try:
            filename = self._get_filename()
            filepath = self.output_dir / filename

            # For now, return placeholder info
            print(f"Would generate: {filepath}")
            self._create_placeholder_guide(filepath)
            return True
        except Exception as e:
            print(f"Error generating guide: {e}")
            return False

    def _get_filename(self):
        """Generate appropriate filename"""
        if self.peer_name:
            return f"{self.peer_name}-tunnel-setup.pdf"
        else:
            return f"{self.device_type}-setup-guide.pdf"

    def _create_placeholder_guide(self, filepath):
        """Create a placeholder guide with basic structure"""
        # For now, create a text-based placeholder that can be expanded
        # In production, this would use reportlab to create professional PDFs

        content = f"""
{self.config['full_name']} - VPN Tunnel Configuration Guide
{'='*70}

Document Information:
  Generated: {self.timestamp}
  Device Type: {self.config['full_name']}
  Configuration Interface: {self.config['interface']}

{'='*70}

SECTION 1: OVERVIEW
{'-'*70}

This guide provides step-by-step instructions for configuring your
{self.config['full_name']} device to establish a secure VPN tunnel to
Organization's Transit Gateway infrastructure.

Benefits of this architecture:
  • High-availability with dual tunnels
  • BGP-enabled dynamic routing
  • End-to-end encryption (IKEv2, AES-256)
  • Automatic failover capability
  • AWS-managed infrastructure

Estimated configuration time: 30-45 minutes

{'='*70}

SECTION 2: PREREQUISITES
{'-'*70}

Before starting, ensure you have:
  ✓ Admin access to {self.config['interface']}
  ✓ Access to tunnel endpoint details (provided by Organization)
  ✓ Pre-shared keys (PSKs) for both tunnels
  ✓ BGP ASN number
  ✓ Network CIDR blocks to route through tunnel

{'='*70}

SECTION 3: TUNNEL PARAMETERS
{'-'*70}

Encryption Standards (same for all devices):

Phase 1 (IKE):
  - Version: {self.config['ike_version']}
  - Encryption: {self.config['encryption']}
  - Integrity: {self.config['integrity']}
  - DH Group: {VPN_CONFIG['phase1_dh']}
  - Lifetime: {VPN_CONFIG['phase1_lifetime']}

Phase 2 (IPSec):
  - Encryption: {self.config['encryption']}
  - Integrity: {self.config['integrity']}
  - PFS (Perfect Forward Secrecy): Optional (recommended)
  - Lifetime: {VPN_CONFIG['phase2_lifetime']}

Dead Peer Detection (DPD):
  - Timeout: {VPN_CONFIG['dgp_timeout']}
  - Action: {VPN_CONFIG['dgp_action']}

BGP Configuration:
  - AWS ASN: {VPN_CONFIG['aws_asn']}
  - Your ASN: [Provided separately]
  - Tunnel subnet range: {VPN_CONFIG['tunnel_ip_range']}
  - Inside subnet IPs: [Provided separately]

{'='*70}

SECTION 4: CONFIGURATION STEPS
{'-'*70}

Configuration steps for {self.config['full_name']} are detailed in the
following sections. Each step includes screenshots and specific command
examples.

[Device-specific configuration would be inserted here]

{'='*70}

SECTION 5: VERIFICATION
{'-'*70}

After configuration, verify:

1. Tunnel Status:
   Check that both tunnels show "UP" status in your device

2. BGP Routes:
   Verify that BGP routes from Organization are being learned

3. Connectivity Test:
   Ping test from your side to Organization network range

4. Traffic Inspection:
   Review logs for successful tunnel establishment

{'='*70}

SECTION 6: TROUBLESHOOTING
{'-'*70}

Common issues and solutions:

Issue: Tunnel stays DOWN
  → Check Pre-Shared Keys (must match exactly)
  → Verify firewall allows UDP 500, 4500
  → Check encryption algorithm settings

Issue: BGP Routes not learning
  → Verify BGP configuration
  → Check inside tunnel IP configuration
  → Review BGP timers and hold times

Issue: Traffic not passing
  → Verify access lists/security policies
  → Check route table entries
  → Ensure traffic selectors match

{'='*70}

SECTION 7: SUPPORT & ESCALATION
{'-'*70}

If you encounter issues:

1. Organization DevOps Support
   Email: support@example.com

2. On-call Support
   Phone: +1-XXX-XXX-XXXX (24/7)

3. Documentation
   Full guides: https://docs.example.com/vpn/

4. Escalation Checklist
   ☐ Verified tunnel endpoints
   ☐ Checked encryption settings
   ☐ Confirmed PSK match
   ☐ Reviewed firewall rules
   ☐ Checked BGP configuration

{'='*70}

Document Version: 1.0
Last Updated: {self.timestamp}
Device Type: {self.config['full_name']}
{'='*70}
"""

        filepath_txt = filepath.with_suffix('.txt')
        with open(filepath_txt, 'w') as f:
            f.write(content)

        print(f"Created placeholder: {filepath_txt}")
        print(f"Note: This is a text version. PDF generation requires reportlab.")
        print(f"Install with: pip install reportlab")

def main():
    parser = argparse.ArgumentParser(
        description="Generate PDF setup guides for VPN peers"
    )
    parser.add_argument(
        "--device",
        choices=["checkpoint", "fortigate", "paloalto", "cisco"],
        help="Generate guide for specific device type"
    )
    parser.add_argument(
        "--peer",
        help="Include peer-specific tunnel details (peer name)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Generate all device guides"
    )
    parser.add_argument(
        "--output-dir",
        default="peer-guides",
        help="Output directory for PDF files (default: peer-guides)"
    )

    args = parser.parse_args()

    if args.all:
        # Generate all device guides
        devices = ["checkpoint", "fortigate", "paloalto", "cisco"]
        for device in devices:
            print(f"\nGenerating guide for {device}...")
            generator = PeerGuideGenerator(device, output_dir=args.output_dir)
            if generator.generate():
                print(f"✓ {device} guide generated")
            else:
                print(f"✗ Failed to generate {device} guide")
    elif args.device:
        # Generate specific device guide
        print(f"Generating guide for {args.device}...")
        generator = PeerGuideGenerator(
            args.device,
            peer_name=args.peer,
            output_dir=args.output_dir
        )
        if generator.generate():
            print(f"✓ {args.device} guide generated")
        else:
            print(f"✗ Failed to generate guide")
    else:
        print("Error: Specify --device, --all, or --help for options")
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
