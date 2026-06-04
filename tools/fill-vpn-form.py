#!/usr/bin/env python3
"""
VPN Form Filler - Reusable Script

Fills VPN configuration form with Affinity information.
Leaves Vimenca section blank for manual completion.

Usage:
    # Using JSON config file
    python3 fill-vpn-form.py --config vpn-config.json --output form-filled.docx

    # Using command line arguments
    python3 fill-vpn-form.py \\
        --affinity-ip 3.151.94.15 \\
        --affinity-device "AWS Transit Gateway" \\
        --output form-filled.docx

    # Using defaults from ATG
    python3 fill-vpn-form.py

Supported Input Formats:
    - JSON file with VPN configuration
    - Command line arguments
    - Interactive mode
    - Default ATG configuration
"""

import json
import argparse
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, List

# Try to import docx with better error handling
try:
    from docx import Document
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False
    print("ERROR: python-docx not installed. Install with:")
    print("  python3 -m venv venv-docx")
    print("  source venv-docx/bin/activate")
    print("  pip install python-docx")
    sys.exit(1)


class VPNFormFiller:
    """Fills VPN form with Affinity configuration data."""

    # ATG Default Configuration
    DEFAULT_CONFIG = {
        "affinity": {
            "company": "Affinity",
            "contact_primary": "Josué Ubico",
            "phone_primary": "809.274.0000",
            "phone_primary_alt": "(502) 4540-4017",
            "email_primary": "jubico@affinity.do",
            "contact_secondary": "Ricardo Peña",
            "phone_secondary": "809.274.0000",
            "email_secondary": "rpena@affinity.do",
            "contact_tertiary": "José Miguel Martínez",
            "phone_tertiary": "809.274.0000",
            "email_tertiary": "jmartinez@affinity.do",
            "vpn_ip": "3.151.94.15",
            "device_type": "AWS Transit Gateway",
            "device_version": "AWS Site-to-Site VPN",
            "source_cidr": "172.31.0.0/16",
            "ports": "80, 443, ICMP",
        },
        "vimenca": {
            "company": "Vimenca",
            "vpn_ip": "191.97.106.141",
            "device_type": "Checkpoint Firewall",
            "device_version": "R80.10",
            "dest_cidr": "172.16.70.0/24",
            "ports": "80, 443",
        },
        "ipsec": {
            "encryption_scheme": "IKE version 2",
            "encryption_algo": "AES256",
            "integrity_algo": "SHA256",
            "auth_method": "Pre-Shared Secret (Intercambiar telefónico)",
            "aggressive_mode": "Deshabilitado",
            "pfs": "Habilitado (Group 14)",
            "replay_detection": "Habilitado",
            "dh_phase1": "Group 14 (2048-bit)",
            "dh_phase2": "Group 14 (2048-bit)",
            "ike_renegotiate": "28800 Sec (480 Min)",
            "ipsec_renegotiate": "3600 Sec (60 Min)",
            "dpd": "Habilitado (30 sec interval)",
            "nat_traversal": "Habilitado",
            "auto_negotiate": "Disable",
            "autokey_keep_alive": "Disable",
        },
    }

    def __init__(self, template_path: str = None):
        """
        Initialize the form filler.

        Args:
            template_path: Path to the VPN form template (default: auto-detect)
        """
        if template_path:
            self.template_path = Path(template_path)
        else:
            # Try common locations
            possible_paths = [
                Path.home() / "Downloads" / "Form_VPN_Affinity-Vimenca_V1.docx",
                Path("/Users/eliudiaz/Downloads/Form_VPN_Affinity-Vimenca_V1.docx"),
                Path("Form_VPN_Affinity-Vimenca_V1.docx"),
            ]

            self.template_path = None
            for path in possible_paths:
                if path.exists():
                    self.template_path = path
                    break

        if not self.template_path or not self.template_path.exists():
            raise FileNotFoundError(
                f"VPN form template not found. Searched:\n"
                f"  - ~/Downloads/Form_VPN_Affinity-Vimenca_V1.docx\n"
                f"  - ./Form_VPN_Affinity-Vimenca_V1.docx"
            )

        self.doc = Document(self.template_path)

    def load_config(self, config_path: str) -> Dict:
        """Load configuration from JSON file."""
        with open(config_path, 'r') as f:
            return json.load(f)

    def fill_contacts_table(self, affinity_data: Dict, vimenca_data: Dict = None) -> None:
        """
        Fill the contacts table (Table 0).

        Affinity data: Column 1
        Vimenca data: Column 2 (left blank if not provided)
        """
        table = self.doc.tables[0]

        # Row 0: Company
        table.rows[0].cells[1].text = affinity_data.get("company", "Affinity")

        # Row 1: Primary Contact
        table.rows[1].cells[1].text = affinity_data.get("contact_primary", "")

        # Row 2: Primary Phone
        phones = affinity_data.get("phone_primary", "")
        if affinity_data.get("phone_primary_alt"):
            phones = f"{phones} - {affinity_data.get('phone_primary_alt')}"
        table.rows[2].cells[1].text = phones

        # Row 3: Primary Email
        table.rows[3].cells[1].text = affinity_data.get("email_primary", "")

        # Row 4: Secondary Contact
        table.rows[4].cells[1].text = affinity_data.get("contact_secondary", "")

        # Row 5: Secondary Phone
        table.rows[5].cells[1].text = affinity_data.get("phone_secondary", "")

        # Row 6: Secondary Email
        table.rows[6].cells[1].text = affinity_data.get("email_secondary", "")

        # Row 7: Tertiary Contact
        table.rows[7].cells[1].text = affinity_data.get("contact_tertiary", "")

        # Row 8: Tertiary Phone
        table.rows[8].cells[1].text = affinity_data.get("phone_tertiary", "")

        # Row 9: Tertiary Email
        table.rows[9].cells[1].text = affinity_data.get("email_tertiary", "")

        # Leave Vimenca column (index 2) blank for manual entry
        if vimenca_data:
            table.rows[0].cells[2].text = vimenca_data.get("company", "")

    def fill_vpn_device_table(self, affinity_data: Dict, vimenca_data: Dict = None) -> None:
        """
        Fill the VPN device information table (Table 1).

        Affinity data: Column 1
        Vimenca data: Column 2 (left blank if not provided)
        """
        table = self.doc.tables[1]

        # Row 1: VPN IP Address
        table.rows[1].cells[1].text = affinity_data.get("vpn_ip", "")

        # Row 2: Device Type
        table.rows[2].cells[1].text = affinity_data.get("device_type", "")

        # Row 3: Device Version
        table.rows[3].cells[1].text = affinity_data.get("device_version", "")

        # Row 4: Source/Destination CIDR
        table.rows[4].cells[1].text = affinity_data.get("source_cidr", "")

        # Row 5: Services/Ports
        table.rows[5].cells[1].text = affinity_data.get("ports", "")

        # Leave Vimenca column blank for manual entry
        if vimenca_data:
            table.rows[1].cells[2].text = vimenca_data.get("vpn_ip", "")
            table.rows[2].cells[2].text = vimenca_data.get("device_type", "")
            table.rows[3].cells[2].text = vimenca_data.get("device_version", "")
            table.rows[4].cells[2].text = vimenca_data.get("dest_cidr", "")
            table.rows[5].cells[2].text = vimenca_data.get("ports", "")

    def fill_ipsec_properties_table(self, ipsec_data: Dict) -> None:
        """Fill the IPSec tunnel properties table (Table 2)."""
        table = self.doc.tables[2]

        properties = [
            ("encryption_scheme", 0),
            ("encryption_algo", 1),
            ("integrity_algo", 2),
            ("auth_method", 3),
            ("aggressive_mode", 4),
            ("pfs", 5),
            ("replay_detection", 6),
            ("dh_phase1", 7),
            ("dh_phase2", 8),
            ("ike_renegotiate", 9),
            ("ipsec_renegotiate", 10),
            ("auto_negotiate", 11),
            ("autokey_keep_alive", 12),
        ]

        for key, row_idx in properties:
            if key in ipsec_data:
                table.rows[row_idx].cells[1].text = ipsec_data[key]

    def fill_form(
        self,
        affinity_data: Dict = None,
        vimenca_data: Dict = None,
        ipsec_data: Dict = None,
    ) -> None:
        """
        Fill all form sections.

        Args:
            affinity_data: Affinity VPN configuration
            vimenca_data: Vimenca VPN configuration (optional)
            ipsec_data: IPSec tunnel properties
        """
        # Use defaults if not provided
        affinity_data = affinity_data or self.DEFAULT_CONFIG["affinity"]
        vimenca_data = vimenca_data or self.DEFAULT_CONFIG["vimenca"]
        ipsec_data = ipsec_data or self.DEFAULT_CONFIG["ipsec"]

        print("Filling form with Affinity configuration...")

        # Fill contacts
        self.fill_contacts_table(affinity_data, vimenca_data)
        print("  ✓ Contacts table filled")

        # Fill VPN device info
        self.fill_vpn_device_table(affinity_data, vimenca_data)
        print("  ✓ VPN device information filled")

        # Fill IPSec properties
        self.fill_ipsec_properties_table(ipsec_data)
        print("  ✓ IPSec properties filled")

    def save(self, output_path: str = None) -> str:
        """
        Save the filled form.

        Args:
            output_path: Output file path (default: form_VPN_filled_<timestamp>.docx)

        Returns:
            Path to saved file
        """
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"Form_VPN_Filled_{timestamp}.docx"

        output_path = Path(output_path)
        self.doc.save(output_path)
        print(f"✓ Form saved: {output_path}")

        return str(output_path)

    @staticmethod
    def load_atg_config() -> Dict:
        """Load ATG configuration from vpn-config.json."""
        config_path = Path("secrets/vpn-config.json")

        if not config_path.exists():
            print(f"Warning: ATG config not found at {config_path}")
            return None

        with open(config_path, 'r') as f:
            atg_config = json.load(f)

        return atg_config


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Fill VPN Configuration Form - Reusable Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use defaults (ATG configuration)
  python3 fill-vpn-form.py

  # Use ATG configuration from secrets/vpn-config.json
  python3 fill-vpn-form.py --use-atg

  # Use custom JSON configuration
  python3 fill-vpn-form.py --config my-vpn-config.json

  # Specify custom output file
  python3 fill-vpn-form.py --output my-form.docx

  # Use custom template
  python3 fill-vpn-form.py --template Form_VPN_Template.docx --output form.docx
        """,
    )

    parser.add_argument(
        "--template",
        help="Path to VPN form template",
    )

    parser.add_argument(
        "--config",
        help="Path to JSON configuration file",
    )

    parser.add_argument(
        "--output",
        help="Output file path (default: Form_VPN_Filled_<timestamp>.docx)",
    )

    parser.add_argument(
        "--use-atg",
        action="store_true",
        help="Load ATG configuration from secrets/vpn-config.json",
    )

    parser.add_argument(
        "--affinity-ip",
        help="Affinity VPN IP address",
    )

    parser.add_argument(
        "--affinity-device",
        help="Affinity VPN device type",
    )

    parser.add_argument(
        "--affinity-cidr",
        help="Affinity source CIDR",
    )

    args = parser.parse_args()

    try:
        # Create filler
        filler = VPNFormFiller(template_path=args.template)
        print(f"✓ Form template loaded: {filler.template_path}\n")

        # Determine configuration source
        affinity_data = None
        vimenca_data = None
        ipsec_data = None

        if args.use_atg:
            print("Loading ATG configuration...")
            atg_config = VPNFormFiller.load_atg_config()
            if atg_config:
                affinity_data = {
                    **filler.DEFAULT_CONFIG["affinity"],
                    "vpn_ip": atg_config.get("tunnel1_address", ""),
                }
                vimenca_data = {
                    **filler.DEFAULT_CONFIG["vimenca"],
                    "vpn_ip": atg_config.get("customer_ip", ""),
                }
                ipsec_data = filler.DEFAULT_CONFIG["ipsec"]
                print("✓ ATG configuration loaded\n")

        elif args.config:
            print(f"Loading configuration from {args.config}...")
            config = filler.load_config(args.config)
            affinity_data = config.get("affinity")
            vimenca_data = config.get("vimenca")
            ipsec_data = config.get("ipsec")
            print("✓ Configuration loaded\n")

        else:
            # Use defaults with CLI overrides
            affinity_data = filler.DEFAULT_CONFIG["affinity"].copy()
            vimenca_data = filler.DEFAULT_CONFIG["vimenca"].copy()
            ipsec_data = filler.DEFAULT_CONFIG["ipsec"].copy()

            # Apply CLI overrides
            if args.affinity_ip:
                affinity_data["vpn_ip"] = args.affinity_ip
            if args.affinity_device:
                affinity_data["device_type"] = args.affinity_device
            if args.affinity_cidr:
                affinity_data["source_cidr"] = args.affinity_cidr

        # Fill the form
        print("Filling form with configuration...\n")
        filler.fill_form(affinity_data, vimenca_data, ipsec_data)

        # Save the form
        print()
        output_file = filler.save(args.output)

        # Print summary
        print("\n" + "=" * 80)
        print("FORM FILLED SUCCESSFULLY")
        print("=" * 80)
        print(f"✓ Output file: {output_file}")
        print("\nVimenca Section: BLANK (ready for manual completion)")
        print("Affinity Section: FILLED with configuration\n")

    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
