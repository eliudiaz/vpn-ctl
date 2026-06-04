#!/usr/bin/env python3
"""Check infrastructure state for each VPN peer after state extraction."""

import json
import subprocess
import os
from pathlib import Path
from datetime import datetime

def run_cmd(cmd, cwd=None):
    """Run command and return output."""
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, cwd=cwd
    )
    return result.stdout.strip(), result.returncode

def get_aws_resources(peer_name):
    """Get AWS resources for a peer."""
    peers_map = {
        'mock-peer-a': ['vpn-05ea9c12f40b67844', 'cgw-09e8da53ae18ef414'],
        'mock-peer-b': ['vpn-0e751eec94d5d4743', 'cgw-0badc5b6e98ccc9df'],
        'mock-peer-c': ['vpn-0603daac887e7abed', 'cgw-0bd99b5d30b39f86f'],
        'mock-peer-d': ['vpn-08a56c49f3c27a1cc', 'cgw-0c066cb9b8e9ca969'],
    }
    return peers_map.get(peer_name, [])

def check_vpn_connection(vpn_id):
    """Check VPN connection status."""
    cmd = f'aws ec2 describe-vpn-connections --vpn-connection-ids {vpn_id} --region us-east-2 --profile default'
    output, code = run_cmd(cmd)
    
    if code != 0:
        return {'status': 'NOT_FOUND', 'state': 'N/A'}
    
    try:
        data = json.loads(output)
        if data['VpnConnections']:
            vpn = data['VpnConnections'][0]
            return {
                'status': vpn.get('State', 'N/A'),
                'type': vpn.get('Type', 'N/A'),
                'tunnel1_state': vpn.get('VpnConnectionOptions', {}).get('TunnelOptions', [{}])[0].get('Phase1EncryptionAlgorithms', [{}])[0].get('Value', 'N/A'),
            }
    except:
        pass
    
    return {'status': 'ERROR', 'state': 'N/A'}

def check_customer_gateway(cgw_id):
    """Check customer gateway status."""
    cmd = f'aws ec2 describe-customer-gateways --customer-gateway-ids {cgw_id} --region us-east-2 --profile default'
    output, code = run_cmd(cmd)
    
    if code != 0:
        return {'status': 'NOT_FOUND'}
    
    try:
        data = json.loads(output)
        if data['CustomerGateways']:
            cgw = data['CustomerGateways'][0]
            return {
                'status': cgw.get('State', 'N/A'),
                'ip_address': cgw.get('IpAddress', 'N/A'),
                'type': cgw.get('Type', 'N/A'),
            }
    except:
        pass
    
    return {'status': 'ERROR'}

def main():
    os.chdir('/Users/eliudiaz/Documents/code/AFF/dev-ctx-asg2-core/asg-infra/aff-atg')
    
    peers = ['mock-peer-a', 'mock-peer-b', 'mock-peer-c', 'mock-peer-d']
    
    print()
    print("=" * 100)
    print("🏥 VPN PEER INFRASTRUCTURE HEALTH CHECK (POST-STATE-EXTRACTION)")
    print("=" * 100)
    print()
    
    results = {
        'timestamp': datetime.utcnow().isoformat(),
        'peers': {}
    }
    
    for peer in sorted(peers):
        print(f"\n📍 {peer.upper()}")
        print("-" * 100)
        
        aws_ids = get_aws_resources(peer)
        if not aws_ids:
            print(f"   ⚠️  No AWS resources mapped for {peer}")
            continue
        
        vpn_id, cgw_id = aws_ids
        
        # Check VPN Connection
        vpn_status = check_vpn_connection(vpn_id)
        print(f"   VPN Connection ({vpn_id}):")
        print(f"      Status: {vpn_status.get('status', 'N/A')}")
        
        # Check Customer Gateway
        cgw_status = check_customer_gateway(cgw_id)
        print(f"   Customer Gateway ({cgw_id}):")
        print(f"      Status: {cgw_status.get('status', 'N/A')}")
        print(f"      IP: {cgw_status.get('ip_address', 'N/A')}")
        
        results['peers'][peer] = {
            'vpn_id': vpn_id,
            'vpn_status': vpn_status,
            'cgw_id': cgw_id,
            'cgw_status': cgw_status
        }
    
    # Summary
    print()
    print("=" * 100)
    print("📊 SUMMARY")
    print("=" * 100)
    print()
    print(f"Peers checked: {len(peers)}")
    print(f"Timestamp: {results['timestamp']}")
    print()
    
    for peer, info in results['peers'].items():
        vpn_ok = info['vpn_status'].get('status') == 'available'
        cgw_ok = info['cgw_status'].get('status') == 'available'
        
        status = "✅" if (vpn_ok and cgw_ok) else ("⚠️" if (vpn_ok or cgw_ok) else "❌")
        print(f"   {status} {peer:30} | VPN: {info['vpn_status'].get('status'):12} | CGW: {info['cgw_status'].get('status'):12}")
    
    print()

if __name__ == '__main__':
    main()
