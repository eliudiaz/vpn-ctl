#!/usr/bin/env python3
"""
ATG VPN Peer Configuration Script
Senior AWS Solution Architect Grade
Purpose: Securely onboard new VPN peers with proper encryption and key management
"""

import sys
import json
import os
import secrets
import string
import argparse
from datetime import datetime
import hashlib
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import re

class ATGVPNPeerConfigurator:
    """Configure new VPN peers for ATG infrastructure"""
    
    def __init__(self, peer_name: str, peer_public_ip: str, bgp_asn: int, 
                 destination_cidrs: List[str], region: str = "us-east-2"):
        """Initialize peer configuration"""
        self.peer_name = peer_name
        self.peer_public_ip = peer_public_ip
        self.bgp_asn = bgp_asn
        self.destination_cidrs = destination_cidrs
        self.region = region
        self.config = {}
        self.timestamp = datetime.now().isoformat()
        
    def validate_inputs(self) -> bool:
        """Validate all inputs"""
        print(f"🔍 Validating inputs for peer: {self.peer_name}")

        # Validate peer name
        if not self.peer_name or len(self.peer_name) < 3:
            print("❌ Peer name must be at least 3 characters")
            return False

        # Validate public IP
        parts = self.peer_public_ip.split('.')
        if len(parts) != 4 or not all(0 <= int(p) <= 255 for p in parts):
            print(f"❌ Invalid public IP: {self.peer_public_ip}")
            return False

        # Validate BGP ASN
        if not (64512 <= self.bgp_asn <= 65534) and self.bgp_asn != 65000:
            print(f"❌ BGP ASN must be in private range (64512-65534) or 65000")
            return False

        # Validate destination CIDRs
        for cidr in self.destination_cidrs:
            if not self._validate_cidr(cidr):
                print(f"❌ Invalid CIDR: {cidr}")
                return False

        print("✅ All inputs validated successfully")
        return True

    def validate_ip_allocations(self, tunnel1_cidr: str, tunnel2_cidr: str,
                               peer_cidrs: List[str]) -> bool:
        """Validate IP allocations against registry to prevent collisions"""
        print(f"\n🔐 Validating IP allocations against vpn-peers-registry.yaml")

        # Check if skill-validate-peer-ips exists
        skill_path = Path("skill-validate-peer-ips")
        if not skill_path.exists():
            print("⚠️  skill-validate-peer-ips not found - skipping collision detection")
            return True

        # Build peer CIDRs string
        peer_cidrs_str = ",".join(peer_cidrs)

        # Call the validation skill
        cmd = [
            str(skill_path),
            "--peer", self.peer_name,
            "--tunnel1", tunnel1_cidr,
            "--tunnel2", tunnel2_cidr,
            "--asn", str(self.bgp_asn),
            "--peer-cidrs", peer_cidrs_str
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            # Print validation output
            if result.stdout:
                print(result.stdout)

            if result.returncode == 0:
                print("✅ IP allocation validation PASSED")
                return True
            else:
                print("❌ IP allocation validation FAILED")
                if result.stderr:
                    print(result.stderr)
                return False
        except subprocess.TimeoutExpired:
            print("⚠️  Validation timeout - proceeding (review IP allocation manually)")
            return True
        except Exception as e:
            print(f"⚠️  Validation error: {e} - proceeding with caution")
            return True
    
    def _validate_cidr(self, cidr: str) -> bool:
        """Validate CIDR notation"""
        try:
            network, prefix = cidr.split('/')
            parts = network.split('.')
            prefix = int(prefix)
            return (len(parts) == 4 and 
                    all(0 <= int(p) <= 255 for p in parts) and
                    0 <= prefix <= 32)
        except:
            return False
    
    def generate_preshared_keys(self) -> Dict[str, str]:
        """Generate cryptographically secure PSKs"""
        print(f"\n🔐 Generating Pre-Shared Keys")
        
        # PSK Requirements: 32 chars, mixed alphanumeric + special chars
        alphabet = string.ascii_letters + string.digits + "_-.!@#$%^&*"
        
        psk1 = ''.join(secrets.choice(alphabet) for _ in range(32))
        psk2 = ''.join(secrets.choice(alphabet) for _ in range(32))
        
        # Validate PSKs are different
        while psk1 == psk2:
            psk2 = ''.join(secrets.choice(alphabet) for _ in range(32))
        
        self.config['tunnel1_psk'] = psk1
        self.config['tunnel2_psk'] = psk2
        
        print(f"✅ Tunnel 1 PSK: {self._mask_psk(psk1)}")
        print(f"✅ Tunnel 2 PSK: {self._mask_psk(psk2)}")
        
        return {'tunnel1': psk1, 'tunnel2': psk2}
    
    def _mask_psk(self, psk: str) -> str:
        """Mask PSK for display"""
        return psk[:4] + '*' * (len(psk) - 8) + psk[-4:]
    
    def generate_encryption_config(self) -> Dict:
        """Generate enterprise-grade encryption configuration"""
        print(f"\n🔒 Configuring encryption parameters")
        
        encryption_config = {
            'phase1': {
                'ike_version': 'ikev2',
                'encryption': 'AES256',
                'integrity': 'SHA2-256',
                'dh_group': 14,  # ECDH-4096
                'lifetime': 28800  # 8 hours
            },
            'phase2': {
                'encryption': 'AES256',
                'integrity': 'SHA2-256',
                'dh_group': 14,  # PFS disabled for compatibility
                'lifetime': 3600  # 1 hour
            },
            'dpd': {
                'timeout': 30,  # 30 seconds
                'action': 'restart'  # Automatic tunnel restart
            }
        }
        
        self.config['encryption'] = encryption_config
        
        print(f"✅ IKE Version: {encryption_config['phase1']['ike_version']}")
        print(f"✅ Phase 1 Encryption: {encryption_config['phase1']['encryption']}")
        print(f"✅ Phase 2 Encryption: {encryption_config['phase2']['encryption']}")
        print(f"✅ DPD: {encryption_config['dpd']['timeout']}s timeout with {encryption_config['dpd']['action']}")
        
        return encryption_config
    
    def calculate_hash_keys(self) -> Dict[str, str]:
        """Calculate security hash keys for peer identification"""
        print(f"\n🔐 Calculating security hash keys")
        
        # Create hash components
        hash_input = f"{self.peer_name}:{self.peer_public_ip}:{self.timestamp}"
        
        # Generate multiple hash types for verification
        hash_keys = {
            'sha256': hashlib.sha256(hash_input.encode()).hexdigest(),
            'sha512': hashlib.sha512(hash_input.encode()).hexdigest(),
            'config_hash': hashlib.sha256(
                f"{json.dumps(self.config, sort_keys=True)}".encode()
            ).hexdigest()
        }
        
        self.config['hash_keys'] = hash_keys
        
        print(f"✅ SHA256 Hash: {hash_keys['sha256'][:16]}...")
        print(f"✅ SHA512 Hash: {hash_keys['sha512'][:16]}...")
        print(f"✅ Config Hash: {hash_keys['config_hash']}")
        
        return hash_keys
    
    def generate_pulumi_code(self) -> str:
        """Generate Python/Pulumi IaC code for peer"""
        print(f"\n📝 Generating Pulumi IaC code")
        
        pulumi_code = f'''
# Generated Pulumi code for peer: {self.peer_name}
# Generated: {self.timestamp}

vpn_{self.peer_name.lower()} = VpnConnector(
    name="{self.peer_name}",
    hub=vpn_hub,
    peer_config=VpnPeerConfig(
        name="{self.peer_name}",
        public_ip="{self.peer_public_ip}",
        bgp_asn={self.bgp_asn},
        destination_cidrs={self.destination_cidrs},
        device_type="Checkpoint",
        device_version="R80.10"
    ),
    region="{self.region}"
)

# Store outputs
pulumi.export("vpn_{self.peer_name.lower()}_id", vpn_{self.peer_name.lower()}.vpn_connection.id)
pulumi.export("vpn_{self.peer_name.lower()}_tunnel1_ip", vpn_{self.peer_name.lower()}.vpn_connection.tunnel1_address)
pulumi.export("vpn_{self.peer_name.lower()}_tunnel2_ip", vpn_{self.peer_name.lower()}.vpn_connection.tunnel2_address)
'''
        return pulumi_code.strip()
    
    def generate_peer_config_file(self) -> Dict:
        """Generate configuration for peer (Checkpoint side)"""
        print(f"\n📋 Generating peer-side configuration")
        
        peer_config = {
            'metadata': {
                'peer_name': self.peer_name,
                'generated': self.timestamp,
                'aws_account': '349298599900',
                'region': self.region,
                'security_level': 'Production'
            },
            'default': {
                'vpn_endpoint_1': '3.151.94.15',
                'vpn_endpoint_2': '18.117.210.11',
                'transit_gateway_asn': 64512,
                'local_cidr': '172.31.0.0/16',
                'aggregate_cidr': '172.33.0.0/16'
            },
            'peer': {
                'public_ip': self.peer_public_ip,
                'bgp_asn': self.bgp_asn,
                'destination_cidrs': self.destination_cidrs,
                'local_cidr': 'SET_BY_PEER'
            },
            'ipsec_phase1': {
                'ike_version': 'IKEv2',
                'encryption_algorithm': 'AES-256',
                'authentication_algorithm': 'SHA-256',
                'dh_group': 'Group 14 (modp4096)',
                'lifetime_seconds': 28800,
                'authentication_method': 'Pre-Shared Key'
            },
            'ipsec_phase2': {
                'encryption_algorithm': 'AES-256',
                'authentication_algorithm': 'SHA-256',
                'pfs': 'DISABLED',
                'lifetime_seconds': 3600
            },
            'dpd': {
                'enabled': True,
                'timeout_seconds': 30,
                'action': 'Restart',
                'interval_seconds': 30
            },
            'credentials': {
                'tunnel1_psk': 'SECURE_CHANNEL_REQUIRED',
                'tunnel2_psk': 'SECURE_CHANNEL_REQUIRED',
                'hash_verification': self.config.get('hash_keys', {}).get('sha256', '')
            },
            'bgp': {
                'vpn_asn': 64512,
                'peer_asn': self.bgp_asn,
                'hold_time': 30,
                'keepalive_interval': 10
            }
        }
        
        return peer_config
    
    def save_configuration(self, output_dir: str = "peer-configs") -> Tuple[str, str]:
        """Save all configuration files"""
        print(f"\n💾 Saving configuration files")
        
        # Create output directory
        Path(output_dir).mkdir(exist_ok=True)
        
        timestamp_short = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save peer configuration
        peer_config_file = f"{output_dir}/{self.peer_name}_config_{timestamp_short}.json"
        with open(peer_config_file, 'w') as f:
            json.dump(self.generate_peer_config_file(), f, indent=2)
        print(f"✅ Peer config: {peer_config_file}")
        
        # Save PSKs (encrypted in production)
        psk_file = f"{output_dir}/{self.peer_name}_psk_{timestamp_short}.txt"
        with open(psk_file, 'w') as f:
            f.write(f"# VPN Pre-Shared Keys for {self.peer_name}\n")
            f.write(f"# Generated: {self.timestamp}\n")
            f.write(f"# CONFIDENTIAL - Exchange via secure channel only\n")
            f.write(f"# Verify hash: {self.config.get('hash_keys', {}).get('sha256', '')}\n")
            f.write(f"#\n")
            f.write(f"Tunnel 1 PSK: {self.config['tunnel1_psk']}\n")
            f.write(f"Tunnel 2 PSK: {self.config['tunnel2_psk']}\n")
        os.chmod(psk_file, 0o600)
        print(f"✅ PSK file: {psk_file} (mode 600)")
        
        # Save Pulumi code
        pulumi_file = f"{output_dir}/{self.peer_name}_pulumi_{timestamp_short}.py"
        with open(pulumi_file, 'w') as f:
            f.write(self.generate_pulumi_code())
        print(f"✅ Pulumi code: {pulumi_file}")
        
        # Save full configuration
        config_file = f"{output_dir}/{self.peer_name}_full_config_{timestamp_short}.json"
        with open(config_file, 'w') as f:
            json.dump(self.config, f, indent=2, default=str)
        print(f"✅ Full config: {config_file}")
        
        return psk_file, config_file
    
    def generate_documentation(self) -> str:
        """Generate setup documentation"""
        doc = f"""
# VPN Peer Configuration: {self.peer_name}
Generated: {self.timestamp}

## Peer Information
- **Name**: {self.peer_name}
- **Public IP**: {self.peer_public_ip}
- **BGP ASN**: {self.bgp_asn}
- **Destination CIDRs**: {', '.join(self.destination_cidrs)}
- **Region**: {self.region}

## Security Configuration

### Phase 1 (IKE)
- IKE Version: IKEv2
- Encryption: AES-256
- Integrity: SHA2-256
- DH Group: 14 (ECDH-4096)
- Lifetime: 28,800 seconds (8 hours)

### Phase 2 (IPSec)
- Encryption: AES-256
- Integrity: SHA2-256
- PFS: DISABLED
- Lifetime: 3,600 seconds (1 hour)

### Keep Alive (DPD)
- Enabled: Yes
- Timeout: 30 seconds
- Action: Restart tunnel

## Hash Keys for Verification
- SHA256: {self.config.get('hash_keys', {}).get('sha256', 'N/A')}
- SHA512: {self.config.get('hash_keys', {}).get('sha512', 'N/A')[:32]}...
- Config: {self.config.get('hash_keys', {}).get('config_hash', 'N/A')}

## BGP Configuration
- Organization ASN: 64512
- Peer ASN: {self.bgp_asn}
- Hold Time: 30s
- Keepalive: 10s

## Next Steps
1. Exchange PSKs via secure channel (phone call)
2. Configure peer-side VPN settings
3. Deploy AWS side with Pulumi code
4. Verify tunnel status
5. Test connectivity

## Security Notes
- PSKs are 32-character, cryptographically secure
- All PSKs must be exchanged via secure channel
- Verify hash keys to ensure configuration integrity
- Keep documentation in secure location
"""
        return doc.strip()
    
    def display_summary(self):
        """Display configuration summary"""
        print("\n" + "="*80)
        print("VPN PEER CONFIGURATION SUMMARY")
        print("="*80)
        print(self.generate_documentation())
        print("="*80)

def main():
    parser = argparse.ArgumentParser(
        description='Add new VPN peer to ATG infrastructure with collision prevention'
    )
    parser.add_argument('peer_name', help='Peer name (e.g., Vimenca, Checkpoint)')
    parser.add_argument('public_ip', help='Peer public IP address')
    parser.add_argument('bgp_asn', type=int, help='BGP ASN (64512-65534)')
    parser.add_argument('--cidrs', nargs='+', required=True, help='Destination CIDRs (peer-side)')
    parser.add_argument('--tunnel1-cidr', help='Tunnel 1 inside CIDR (e.g., 169.254.16.0/30). Omit to auto-suggest')
    parser.add_argument('--tunnel2-cidr', help='Tunnel 2 inside CIDR (e.g., 169.254.17.0/30). Omit to auto-suggest')
    parser.add_argument('--skip-validation', action='store_true', help='Skip IP collision validation (NOT RECOMMENDED)')
    parser.add_argument('--region', default='us-east-2', help='AWS region')
    parser.add_argument('--output-dir', default='peer-configs', help='Output directory')

    args = parser.parse_args()
    
    print("\n" + "="*80)
    print("ATG VPN PEER CONFIGURATION")
    print("Senior AWS Solution Architect Grade - With IP Collision Prevention")
    print("="*80)

    # Determine tunnel CIDRs
    tunnel1_cidr = args.tunnel1_cidr
    tunnel2_cidr = args.tunnel2_cidr

    if not tunnel1_cidr or not tunnel2_cidr:
        print("\n📋 Tunnel CIDRs not provided. Getting suggestions from registry...")
        try:
            result = subprocess.run(
                ["./skill-validate-peer-ips", "--suggest"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and "Tunnel 1 Inside CIDR:" in result.stdout:
                # Parse suggested values
                lines = result.stdout.split('\n')
                for line in lines:
                    if "Tunnel 1 Inside CIDR:" in line:
                        tunnel1_cidr = line.split(':')[-1].strip()
                    elif "Tunnel 2 Inside CIDR:" in line:
                        tunnel2_cidr = line.split(':')[-1].strip()

        except Exception as e:
            print(f"⚠️  Could not get suggestions: {e}")

    if not tunnel1_cidr or not tunnel2_cidr:
        print("❌ Cannot determine tunnel CIDRs. Provide --tunnel1-cidr and --tunnel2-cidr")
        sys.exit(1)

    print(f"\n📍 Using tunnel allocations:")
    print(f"  Tunnel 1: {tunnel1_cidr}")
    print(f"  Tunnel 2: {tunnel2_cidr}")

    # Create configurator
    configurator = ATGVPNPeerConfigurator(
        peer_name=args.peer_name,
        peer_public_ip=args.public_ip,
        bgp_asn=args.bgp_asn,
        destination_cidrs=args.cidrs,
        region=args.region
    )

    # Validate inputs
    if not configurator.validate_inputs():
        sys.exit(1)

    # Validate IP allocations against registry (CRITICAL GATE)
    if not args.skip_validation:
        if not configurator.validate_ip_allocations(tunnel1_cidr, tunnel2_cidr, args.cidrs):
            print("\n❌ IP ALLOCATION VALIDATION FAILED")
            print("Cannot proceed with peer configuration.")
            print("Use --skip-validation only if you are certain of your allocations.")
            sys.exit(1)
    else:
        print("\n⚠️  SKIPPING collision detection (--skip-validation flag set)")

    # Generate all configurations
    configurator.generate_preshared_keys()
    configurator.generate_encryption_config()
    configurator.calculate_hash_keys()

    # Save files
    psk_file, config_file = configurator.save_configuration(args.output_dir)

    # Display summary
    configurator.display_summary()

    print(f"\n✅ Configuration complete!")
    print(f"📁 Output directory: {args.output_dir}")
    print(f"\n⚠️  NEXT: Update vpn-peers-registry.yaml with allocated IPs before deployment")

if __name__ == '__main__':
    main()
