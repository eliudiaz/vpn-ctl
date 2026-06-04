#!/usr/bin/env python3
"""
ATG VPN Peer Verification Script
Purpose: Review current ATG instance, show peer status, and detect collision risks
Requires: AWS CLI credentials, boto3, pyyaml
"""

import sys
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import subprocess
import re

try:
    import yaml
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
except ImportError as e:
    print(f"❌ Missing required package: {e}")
    print("Install with: pip install boto3 pyyaml")
    sys.exit(1)


class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    RED = '\033[0;31m'
    BLUE = '\033[0;34m'
    BOLD = '\033[1m'
    NC = '\033[0m'


def print_status(status: str, message: str):
    """Print colored status message"""
    status_map = {
        'pass': f'{Colors.GREEN}✓{Colors.NC}',
        'fail': f'{Colors.RED}✗{Colors.NC}',
        'warn': f'{Colors.YELLOW}⚠{Colors.NC}',
        'info': f'{Colors.BLUE}ℹ{Colors.NC}',
    }
    print(f"{status_map.get(status, status)} {message}")


def print_header(title: str):
    """Print section header"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}=== {title} ==={Colors.NC}\n")


class ATGVerifier:
    """Verify ATG infrastructure and peer configurations"""

    def __init__(self, region: str = "us-east-2", registry_file: str = "vpn-peers-registry.yaml", profile: str = "default"):
        """Initialize verifier with AWS region and registry file"""
        self.region = region
        self.registry_file = registry_file
        self.profile = profile
        self.registry = {}
        self.ec2_client = None
        self.peers_from_aws = {}
        self.peers_from_registry = {}
        self.issues = []
        self.warnings = []
        self.checks_passed = 0
        self.checks_failed = 0

    def connect_aws(self) -> bool:
        """Connect to AWS using default profile"""
        try:
            session = boto3.Session(profile_name=self.profile)
            self.ec2_client = session.client('ec2', region_name=self.region)
            # Test connection
            self.ec2_client.describe_vpn_connections()
            print_status('pass', f'Connected to AWS region: {self.region}')
            return True
        except NoCredentialsError:
            print_status('fail', 'AWS credentials not found')
            return False
        except ClientError as e:
            print_status('fail', f'AWS connection error: {e}')
            return False

    def load_registry(self) -> bool:
        """Load vpn-peers-registry.yaml"""
        try:
            if not Path(self.registry_file).exists():
                print_status('fail', f'Registry not found: {self.registry_file}')
                return False

            with open(self.registry_file, 'r') as f:
                self.registry = yaml.safe_load(f)

            if not self.registry or 'peers' not in self.registry:
                print_status('fail', 'Invalid registry format')
                return False

            peer_count = len(self.registry.get('peers', {}))
            print_status('pass', f'Loaded registry with {peer_count} peers')
            return True
        except Exception as e:
            print_status('fail', f'Registry load error: {e}')
            return False

    def get_aws_peers(self) -> bool:
        """Query AWS for all VPN connections"""
        try:
            response = self.ec2_client.describe_vpn_connections()
            vpn_connections = response.get('VpnConnections', [])

            if not vpn_connections:
                print_status('warn', 'No VPN connections found in AWS')
                return True

            for vpn in vpn_connections:
                # Extract peer name from tags - prefer Customer tag, fallback to Name tag
                peer_name = vpn['VpnConnectionId']
                for tag in vpn.get('Tags', []):
                    if tag.get('Key') == 'Customer':
                        peer_name = tag.get('Value', vpn['VpnConnectionId'])
                        break
                    elif tag.get('Key') == 'Name':
                        # Fallback: extract peer name from VPN name (e.g., "company-partner-vpn" -> "Vimenca")
                        name_value = tag.get('Value', '').replace('vpn-', '').replace('-vpn', '')
                        peer_name = name_value.capitalize() if name_value else vpn['VpnConnectionId']

                # Extract tunnel information
                tunnel1_data = {}
                tunnel2_data = {}

                # Get outside IPs from VgwTelemetry
                for idx, telemetry in enumerate(vpn.get('VgwTelemetry', [])):
                    if idx == 0:
                        tunnel1_data['outside_ip'] = telemetry.get('OutsideIpAddress')
                        tunnel1_data['status'] = telemetry.get('Status', 'DOWN')
                        tunnel1_data['status_message'] = telemetry.get('StatusMessage', '')
                    elif idx == 1:
                        tunnel2_data['outside_ip'] = telemetry.get('OutsideIpAddress')
                        tunnel2_data['status'] = telemetry.get('Status', 'DOWN')
                        tunnel2_data['status_message'] = telemetry.get('StatusMessage', '')

                # Get customer gateway (peer) public IP
                peer_ip = None
                cg_response = self.ec2_client.describe_customer_gateways(
                    CustomerGatewayIds=[vpn['CustomerGatewayId']]
                )
                if cg_response['CustomerGateways']:
                    peer_ip = cg_response['CustomerGateways'][0].get('PublicIp')

                # Get BGP ASN
                bgp_asn = vpn.get('Options', {}).get('StaticRoutesOnly', False)

                self.peers_from_aws[peer_name] = {
                    'vpn_id': vpn['VpnConnectionId'],
                    'peer_ip': peer_ip,
                    'state': vpn.get('State', 'unknown'),
                    'customer_gateway_id': vpn.get('CustomerGatewayId'),
                    'tunnel1': tunnel1_data,
                    'tunnel2': tunnel2_data,
                    'destination_cidrs': vpn.get('Options', {}).get('StaticRoutes', []),
                    'tags': {tag['Key']: tag['Value'] for tag in vpn.get('Tags', [])},
                }

            print_status('pass', f'Found {len(self.peers_from_aws)} VPN connections in AWS')
            return True
        except ClientError as e:
            print_status('fail', f'AWS query error: {e}')
            return False

    def get_registry_peers(self):
        """Extract peer information from registry"""
        try:
            for peer_key, peer_data in self.registry.get('peers', {}).items():
                peer_name = peer_data.get('peer_name', peer_key)

                tunnel1_cidr = peer_data.get('tunnel_1', {}).get('inside_cidr')
                tunnel2_cidr = peer_data.get('tunnel_2', {}).get('inside_cidr')
                bgp_asn = peer_data.get('bgp', {}).get('peer_asn')
                peer_cidrs = peer_data.get('peer_cidrs', [])

                self.peers_from_registry[peer_name] = {
                    'key': peer_key,
                    'tunnel1_cidr': tunnel1_cidr,
                    'tunnel2_cidr': tunnel2_cidr,
                    'bgp_asn': bgp_asn,
                    'peer_cidrs': peer_cidrs,
                    'status': peer_data.get('status', 'unknown'),
                    'device_type': peer_data.get('peer_type'),
                }

            print_status('pass', f'Loaded {len(self.peers_from_registry)} peers from registry')
            return True
        except Exception as e:
            print_status('fail', f'Registry parsing error: {e}')
            return False

    def verify_peer_presence(self):
        """Check if all registered peers exist in AWS"""
        print_header('Peer Presence Verification')

        registry_names = set(self.peers_from_registry.keys())
        aws_names = set(self.peers_from_aws.keys())

        # Check for peers in registry but not in AWS
        missing_from_aws = registry_names - aws_names
        if missing_from_aws:
            for peer in missing_from_aws:
                msg = f'Peer "{peer}" registered but NOT deployed in AWS'
                print_status('warn', msg)
                self.warnings.append(msg)
                self.checks_failed += 1
        else:
            print_status('pass', 'All registered peers found in AWS')
            self.checks_passed += 1

        # Check for peers in AWS but not in registry
        extra_in_aws = aws_names - registry_names
        if extra_in_aws:
            for peer in extra_in_aws:
                msg = f'Peer "{peer}" deployed in AWS but NOT in registry'
                print_status('warn', msg)
                self.warnings.append(msg)
                self.checks_failed += 1
        else:
            print_status('pass', 'No unregistered peers in AWS')
            self.checks_passed += 1

    def verify_tunnel_status(self):
        """Check tunnel UP/DOWN status for all peers"""
        print_header('Tunnel Status Verification')

        for peer_name, aws_peer in self.peers_from_aws.items():
            tunnel1_status = aws_peer['tunnel1'].get('status', 'DOWN')
            tunnel2_status = aws_peer['tunnel2'].get('status', 'DOWN')

            both_up = tunnel1_status == 'UP' and tunnel2_status == 'UP'
            one_up = tunnel1_status == 'UP' or tunnel2_status == 'UP'

            if both_up:
                print_status('pass', f'{peer_name}: Both tunnels UP')
                self.checks_passed += 1
            elif one_up:
                msg = f'{peer_name}: Only {tunnel1_status} tunnel UP (redundancy degraded)'
                print_status('warn', msg)
                self.warnings.append(msg)
                self.checks_failed += 1
            else:
                msg = f'{peer_name}: Both tunnels DOWN'
                print_status('fail', msg)
                self.issues.append(msg)
                self.checks_failed += 1

            # Show tunnel details
            if aws_peer['tunnel1'].get('status_message'):
                print(f"    Tunnel 1: {aws_peer['tunnel1'].get('status_message')}")
            if aws_peer['tunnel2'].get('status_message'):
                print(f"    Tunnel 2: {aws_peer['tunnel2'].get('status_message')}")

    def verify_bgp_routes(self):
        """Check BGP route status from tunnel status messages"""
        print_header('BGP Route Verification')

        for peer_name, aws_peer in self.peers_from_aws.items():
            t1_msg = aws_peer['tunnel1'].get('status_message', '')
            t2_msg = aws_peer['tunnel2'].get('status_message', '')

            # Extract route counts from status message (format: "X BGP ROUTES")
            t1_routes = self._extract_route_count(t1_msg)
            t2_routes = self._extract_route_count(t2_msg)

            if t1_routes is not None or t2_routes is not None:
                total_routes = (t1_routes or 0) + (t2_routes or 0)
                if total_routes > 0:
                    print_status('pass', f'{peer_name}: {total_routes} BGP routes active')
                    self.checks_passed += 1
                else:
                    msg = f'{peer_name}: Tunnels UP but no BGP routes yet (still converging?)'
                    print_status('warn', msg)
                    self.warnings.append(msg)
                    self.checks_failed += 1
            else:
                msg = f'{peer_name}: Cannot determine BGP route status'
                print_status('warn', msg)
                self.warnings.append(msg)

    def _extract_route_count(self, message: str) -> Optional[int]:
        """Extract route count from AWS status message"""
        match = re.search(r'(\d+)\s+BGP\s+ROUTES', message)
        if match:
            return int(match.group(1))
        return None

    def verify_no_collisions(self):
        """Check for IP allocation collisions between peers"""
        print_header('Collision Detection Verification')

        all_tunnel1_cidrs = {}
        all_tunnel2_cidrs = {}
        all_asns = {}
        all_peer_cidrs = {}

        # Collect all allocations from registry
        for peer_name, peer_data in self.peers_from_registry.items():
            t1 = peer_data.get('tunnel1_cidr')
            t2 = peer_data.get('tunnel2_cidr')
            asn = peer_data.get('bgp_asn')
            cidrs = peer_data.get('peer_cidrs', [])

            # Check tunnel 1 collisions
            if t1:
                if t1 in all_tunnel1_cidrs:
                    collision = f'Tunnel 1 CIDR collision: {t1} (peers: {all_tunnel1_cidrs[t1]}, {peer_name})'
                    print_status('fail', collision)
                    self.issues.append(collision)
                    self.checks_failed += 1
                else:
                    all_tunnel1_cidrs[t1] = peer_name

            # Check tunnel 2 collisions
            if t2:
                if t2 in all_tunnel2_cidrs:
                    collision = f'Tunnel 2 CIDR collision: {t2} (peers: {all_tunnel2_cidrs[t2]}, {peer_name})'
                    print_status('fail', collision)
                    self.issues.append(collision)
                    self.checks_failed += 1
                else:
                    all_tunnel2_cidrs[t2] = peer_name

            # Check ASN collisions
            if asn:
                if asn in all_asns:
                    collision = f'BGP ASN collision: {asn} (peers: {all_asns[asn]}, {peer_name})'
                    print_status('fail', collision)
                    self.issues.append(collision)
                    self.checks_failed += 1
                else:
                    all_asns[asn] = peer_name

            # Check peer CIDR collisions
            for cidr in cidrs:
                if cidr in all_peer_cidrs:
                    collision = f'Peer CIDR collision: {cidr} (peers: {all_peer_cidrs[cidr]}, {peer_name})'
                    print_status('fail', collision)
                    self.issues.append(collision)
                    self.checks_failed += 1
                else:
                    all_peer_cidrs[cidr] = peer_name

        if not self.issues:
            print_status('pass', 'No IP allocation collisions detected')
            self.checks_passed += 1

    def verify_reserved_ranges(self):
        """Check for use of reserved IP ranges"""
        print_header('Reserved Range Verification')

        reserved_asns = [64512]  # AWS reserved

        collision_found = False

        for peer_name, peer_data in self.peers_from_registry.items():
            asn = peer_data.get('bgp_asn')

            if asn in reserved_asns:
                collision = f'{peer_name}: Uses reserved BGP ASN {asn} (AWS reserved)'
                print_status('fail', collision)
                self.issues.append(collision)
                self.checks_failed += 1
                collision_found = True

        if not collision_found:
            print_status('pass', 'No reserved ASN ranges used')
            self.checks_passed += 1

    def verify_tunnel_consistency(self):
        """Verify consistency between AWS and registry"""
        print_header('Tunnel Configuration Consistency')

        for peer_name in set(self.peers_from_aws.keys()) & set(self.peers_from_registry.keys()):
            aws_peer = self.peers_from_aws[peer_name]
            reg_peer = self.peers_from_registry[peer_name]

            # Check if AWS peer status matches expected deployment status
            aws_state = aws_peer.get('state', 'unknown')
            expected_status = reg_peer.get('status', 'production')

            if expected_status == 'production' and aws_state != 'available':
                msg = f'{peer_name}: Expected state "available" but found "{aws_state}"'
                print_status('warn', msg)
                self.warnings.append(msg)
                self.checks_failed += 1
            else:
                print_status('pass', f'{peer_name}: State is "{aws_state}" (expected for {expected_status})')
                self.checks_passed += 1

    def verify_vpn_connectivity_skill(self) -> bool:
        """Run skill-vpn-connectivity for detailed peer checks"""
        print_header('Deep Health Check (via skill-vpn-connectivity)')

        skill_path = Path('skill-vpn-connectivity')
        if not skill_path.exists():
            print_status('warn', 'skill-vpn-connectivity not found, skipping deep check')
            return True

        try:
            result = subprocess.run(
                [str(skill_path), '--deep'],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                # Parse output for health score
                if 'Score:' in result.stdout or '%' in result.stdout:
                    print_status('pass', 'Deep health check completed')
                    # Print relevant lines
                    for line in result.stdout.split('\n'):
                        if 'Score:' in line or 'Health:' in line or '%' in line:
                            print(f"  {line.strip()}")
                    self.checks_passed += 1
                    return True
            else:
                print_status('warn', 'Deep health check returned non-zero exit code')
                return True
        except subprocess.TimeoutExpired:
            print_status('warn', 'Deep health check timeout (>30s)')
            return True
        except Exception as e:
            print_status('warn', f'Deep health check error: {e}')
            return True

    def generate_summary(self):
        """Generate final summary report"""
        print_header('Verification Summary')

        total_checks = self.checks_passed + self.checks_failed
        pass_rate = (self.checks_passed / total_checks * 100) if total_checks > 0 else 0

        print(f"Checks Passed: {Colors.GREEN}{self.checks_passed}{Colors.NC}")
        print(f"Checks Failed: {Colors.RED}{self.checks_failed}{Colors.NC}")
        print(f"Pass Rate:    {pass_rate:.1f}%")
        print()

        if self.issues:
            print(f"{Colors.RED}CRITICAL ISSUES ({len(self.issues)}):{Colors.NC}")
            for issue in self.issues:
                print(f"  • {issue}")
            print()

        if self.warnings:
            print(f"{Colors.YELLOW}WARNINGS ({len(self.warnings)}):{Colors.NC}")
            for warning in self.warnings:
                print(f"  • {warning}")
            print()

        if not self.issues:
            print_status('pass', 'No critical issues detected')
        else:
            print_status('fail', f'{len(self.issues)} critical issue(s) found')

        # Overall health score
        if pass_rate >= 90:
            status_icon = f'{Colors.GREEN}✓{Colors.NC}'
            status_text = 'Healthy'
        elif pass_rate >= 70:
            status_icon = f'{Colors.YELLOW}⚠{Colors.NC}'
            status_text = 'Degraded'
        else:
            status_icon = f'{Colors.RED}✗{Colors.NC}'
            status_text = 'Critical'

        print(f"\n{Colors.BOLD}Overall Status: {status_icon} {status_text} ({pass_rate:.1f}% health){Colors.NC}")

    def generate_detailed_report(self):
        """Generate detailed peer-by-peer report"""
        print_header('Detailed Peer Status Report')

        print(f"{'Peer':<25} {'AWS State':<15} {'Tunnel1':<8} {'Tunnel2':<8} {'BGP ASN':<8} {'Status':<15}")
        print("-" * 95)

        for peer_name in sorted(set(self.peers_from_registry.keys()) | set(self.peers_from_aws.keys())):
            aws_peer = self.peers_from_aws.get(peer_name)
            reg_peer = self.peers_from_registry.get(peer_name)

            if aws_peer and reg_peer:
                aws_state = aws_peer.get('state', 'unknown')[:10]
                t1_status = aws_peer['tunnel1'].get('status', 'DOWN')[:3]
                t2_status = aws_peer['tunnel2'].get('status', 'DOWN')[:3]
                asn = str(reg_peer.get('bgp_asn', 'N/A'))[:6]

                # Determine overall status
                if t1_status == 'UP' and t2_status == 'UP':
                    status_color = Colors.GREEN
                    status = 'Healthy'
                elif t1_status == 'UP' or t2_status == 'UP':
                    status_color = Colors.YELLOW
                    status = 'Degraded'
                else:
                    status_color = Colors.RED
                    status = 'Down'

                print(f"{peer_name:<25} {aws_state:<15} {t1_status:<8} {t2_status:<8} {asn:<8} {status_color}{status}{Colors.NC:<15}")
            elif aws_peer:
                print(f"{peer_name:<25} {'DEPLOYED':<15} {'?':<8} {'?':<8} {'?':<8} {Colors.YELLOW}Unregistered{Colors.NC:<15}")
            elif reg_peer:
                print(f"{peer_name:<25} {'NOT DEPLOYED':<15} {'?':<8} {'?':<8} {'?':<8} {Colors.RED}Missing{Colors.NC:<15}")

    def run_verification(self) -> bool:
        """Run all verification checks"""
        print(f"\n{Colors.BOLD}{Colors.BLUE}ATG VPN Peer Verification Report{Colors.NC}")
        print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Region: {self.region}")

        # Connect and load data
        if not self.connect_aws():
            return False

        if not self.load_registry():
            return False

        if not self.get_aws_peers():
            return False

        if not self.get_registry_peers():
            return False

        # Run all verification checks
        self.verify_peer_presence()
        self.verify_tunnel_status()
        self.verify_bgp_routes()
        self.verify_no_collisions()
        self.verify_reserved_ranges()
        self.verify_tunnel_consistency()
        self.verify_vpn_connectivity_skill()

        # Generate reports
        self.generate_detailed_report()
        self.generate_summary()

        return len(self.issues) == 0


def main():
    parser = argparse.ArgumentParser(
        description='Verify ATG VPN peer configurations and detect collision risks'
    )
    parser.add_argument(
        '--region',
        default='us-east-2',
        help='AWS region (default: us-east-2)'
    )
    parser.add_argument(
        '--registry',
        default='vpn-peers-registry.yaml',
        help='Path to vpn-peers-registry.yaml (default: ./vpn-peers-registry.yaml)'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output results as JSON (for automation)'
    )
    parser.add_argument(
        '--profile',
        default='default',
        help='AWS CLI profile to use (default: default)'
    )

    args = parser.parse_args()

    verifier = ATGVerifier(region=args.region, registry_file=args.registry, profile=args.profile)
    success = verifier.run_verification()

    if args.json:
        # Output JSON for automation
        report = {
            'timestamp': datetime.now().isoformat(),
            'region': args.region,
            'checks_passed': verifier.checks_passed,
            'checks_failed': verifier.checks_failed,
            'issues': verifier.issues,
            'warnings': verifier.warnings,
            'peers_from_aws': {k: {
                'state': v['state'],
                'tunnel1_status': v['tunnel1'].get('status'),
                'tunnel2_status': v['tunnel2'].get('status'),
                'peer_ip': v['peer_ip'],
            } for k, v in verifier.peers_from_aws.items()},
            'peers_from_registry': {k: {
                'status': v['status'],
                'bgp_asn': v['bgp_asn'],
                'device_type': v['device_type'],
            } for k, v in verifier.peers_from_registry.items()},
        }
        print("\n" + json.dumps(report, indent=2))

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
