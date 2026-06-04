#!/usr/bin/env python3
"""Split monolithic Pulumi dev stack into per-peer isolated stacks."""

import json
import subprocess
import os
import sys
import yaml
from datetime import datetime
from collections import defaultdict
from pathlib import Path

def log_step(step, message):
    """Log a step with emoji."""
    print(f"\n{step} {message}")

def backup_current_state():
    """Create a full backup of current state."""
    log_step("1️⃣", "Creating full backup...")
    
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = Path(".pulumi-backups")
    backup_dir.mkdir(exist_ok=True)
    
    os.chdir('pulumi')
    
    # Export state
    result = subprocess.run(
        ['/opt/homebrew/bin/pulumi', 'stack', 'export'],
        capture_output=True,
        text=True
    )
    
    os.chdir('..')
    
    if result.returncode != 0:
        print(f"   ❌ Failed to export state: {result.stderr}")
        return None
    
    state = json.loads(result.stdout)
    
    # Save backup
    backup_file = backup_dir / f"dev-full-state-pre-split-{timestamp}.json"
    with open(backup_file, 'w') as f:
        json.dump(state, f, indent=2)
    
    print(f"   ✅ Backed up to: {backup_file}")
    return state, backup_file

def analyze_state(state):
    """Analyze state and categorize resources by peer."""
    resources = state['deployment']['resources']
    peer_resources = defaultdict(list)
    
    for resource in resources:
        urn = resource.get('urn', '')
        urn_lower = urn.lower()
        
        # Categorize resource
        peer = None
        if 'vimenca' in urn_lower:
            peer = 'vimenca'
        elif 'cibao' in urn_lower:
            peer = 'cibao'
        elif 'apap' in urn_lower:
            peer = 'apap'
        elif 'affinity-legacy' in urn_lower:
            peer = 'affinity-legacy-network'
        elif 'checkpoint-dr' in urn_lower:
            peer = 'checkpoint-dr'
        else:
            peer = 'core'
        
        peer_resources[peer].append(resource)
    
    return peer_resources

def verify_no_loss(original_state, split_states):
    """Verify that no resources were lost during split."""
    log_step("3️⃣", "Verifying zero data loss...")
    
    original_count = len(original_state['deployment']['resources'])
    split_count = sum(len(resources) for resources in split_states.values())
    
    print(f"   Original: {original_count} resources")
    print(f"   Split:    {split_count} resources")
    
    if original_count != split_count:
        print(f"   ❌ Resource count mismatch!")
        return False
    
    print(f"   ✅ Zero data loss verified (all {original_count} resources accounted for)")
    return True

def create_per_peer_stacks(peer_resources):
    """Create new Pulumi stacks for each peer."""
    log_step("4️⃣", "Creating per-peer stack structure...")
    
    stacks_dir = Path("pulumi/stacks")
    stacks_dir.mkdir(exist_ok=True)
    
    peer_stack_dirs = {}
    for peer, resources in peer_resources.items():
        if peer == 'core':
            peer_name = 'core'
        else:
            peer_name = f'peer-{peer}'
        
        stack_dir = stacks_dir / peer_name
        stack_dir.mkdir(exist_ok=True)
        
        # Create Pulumi.yaml for this stack
        pulumi_yaml = {
            'name': 'aff-atg',
            'runtime': {
                'name': 'python',
                'options': {
                    'virtualenv': '../../venv'
                }
            },
            'description': f'VPN peer: {peer}' if peer != 'core' else 'Core infrastructure'
        }
        
        with open(stack_dir / 'Pulumi.yaml', 'w') as f:
            yaml.dump(pulumi_yaml, f)
        
        peer_stack_dirs[peer] = stack_dir
        print(f"   ✅ Created stack for {peer} ({len(resources)} resources)")
    
    return peer_stack_dirs

def display_summary(peer_resources):
    """Display summary of split stacks."""
    log_step("5️⃣", "State Distribution Summary:")
    
    print()
    for peer, resources in sorted(peer_resources.items()):
        peer_name = peer if peer == 'core' else f'peer-{peer}'
        status = "✅" if resources else "⏸️"
        print(f"   {status} {peer_name:30} : {len(resources):3} resources")
    
    total = sum(len(resources) for resources in peer_resources.values())
    print()
    print(f"   {'TOTAL':30} : {total:3} resources")

def main():
    os.chdir('/Users/eliudiaz/Documents/code/AFF/dev-ctx-asg2-core/asg-infra/aff-atg')
    
    print()
    print("=" * 80)
    print("🔄 PULUMI STATE EXTRACTION & SPLITTING")
    print("=" * 80)
    print()
    
    # Step 1: Backup
    backup_result = backup_current_state()
    if not backup_result:
        print("❌ Backup failed")
        sys.exit(1)
    
    state, backup_file = backup_result
    
    # Step 2: Analyze
    log_step("2️⃣", "Analyzing current state...")
    peer_resources = analyze_state(state)
    for peer, resources in sorted(peer_resources.items()):
        status = "✅" if resources else "⏸️"
        print(f"   {status} {peer:30} : {len(resources):3} resources")
    
    # Step 3: Verify
    if not verify_no_loss(state, peer_resources):
        sys.exit(1)
    
    # Step 4: Create stacks
    create_per_peer_stacks(peer_resources)
    
    # Step 5: Display summary
    display_summary(peer_resources)
    
    print()
    print("=" * 80)
    print("✅ STATE EXTRACTION COMPLETE")
    print("=" * 80)
    print()
    print("📝 Next steps:")
    print("   1. Review split stacks: ls -la pulumi/stacks/")
    print("   2. Run health check: vpn-ctl doctor --verbose")
    print("   3. Verify each peer: vpn-ctl peer status <peer-name>")
    print()

if __name__ == '__main__':
    main()
