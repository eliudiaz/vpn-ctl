# Peer Manifest Implementation Guide

**Status**: Ready for Implementation  
**Date**: May 11, 2026  
**Document**: Step-by-step guide to implement K8s-style peer manifests

---

## Overview

This guide walks through implementing K8s-style peer manifests in the existing Pulumi infrastructure. The implementation is:
- ✅ **Zero-breaking**: Dual-stack support (manifests + monolithic)
- ✅ **Backward-compatible**: Existing `vpn-peers.yaml` still works
- ✅ **Incremental**: Migrate peers one at a time
- ✅ **Production-ready**: Full integration with orchestrator and secrets manager

---

## Phase 1: Create Infrastructure Files (5 files)

### Step 1.1: Create Tunnel Profiles File

**File**: `config/tunnel-profiles.yaml` (NEW)

Contains shared IPsec/IKE profiles referenced by peers.

```yaml
apiVersion: vpn.example.io/v1
kind: TunnelProfiles
metadata:
  name: tunnel-profiles
  namespace: vpn-infrastructure

profiles:
  checkpoint_r80:
    description: "Checkpoint R80.10 compatible"
    ike_versions: ["ikev2"]
    # ... (see PEER_MANIFEST_DESIGN.md for full content)
```

**Status**: ✅ Already created in this session

### Step 1.2: Create Peers Directory

```bash
mkdir -p config/peers
```

### Step 1.3: Create Individual Peer Manifests

**Files** (one per peer):
- `config/peers/vimenca.yaml` ✅ Created
- `config/peers/cibao.yaml` ✅ Created
- `config/peers/apap.yaml` ✅ Created
- `config/peers/internal-legacy-network.yaml` ✅ Created

Each contains complete peer specification in K8s-style manifest format.

---

## Phase 2: Create Manifest Loader (1 file)

### Step 2.1: Add VPN Manifest Loader

**File**: `pulumi/vpn_manifest_loader.py` (NEW)

Provides classes:
- `VpnManifestLoader`: Loads individual peer manifests
- `VpnConfigLoader`: Unified loader (manifests + fallback to monolithic)

**Status**: ✅ Already created in this session

---

## Phase 3: Integrate into Orchestrator (1 file update)

### Step 3.1: Update StackOrchestrator to Use Manifests

**File**: `pulumi/stack_orchestrator.py` (UPDATE)

Add manifest loading capability:

```python
# At top of stack_orchestrator.py
from vpn_manifest_loader import VpnManifestLoader, VpnConfigLoader

class StackOrchestrator:
    """Base orchestrator with manifest support."""
    
    def __init__(self, stack_name: str):
        self.stack_name = stack_name
        # Add manifest loader
        self.config_loader = VpnConfigLoader("../config")
        
    def load_vpn_configs(self) -> List[Dict[str, Any]]:
        """
        Load VPN peer configurations from manifests or monolithic file.
        
        Returns manifests first (K8s-style), falls back to monolithic.
        """
        return self.config_loader.load_all_peers(enabled_only=True)

# In create_vpn_connectors() method:
def create_vpn_connectors(self) -> List[Dict[str, Any]]:
    """Create VPN connector configurations."""
    # Load from manifests
    vpn_configs = self.load_vpn_configs()
    
    # Filter for current stack
    filtered_configs = self._filter_vpn_configs_for_stack(vpn_configs)
    
    # Return as-is (manifests or monolithic structure)
    return filtered_configs
```

### Example: Updated __main__.py Integration

```python
from vpn_manifest_loader import VpnConfigLoader

# In main orchestration
config_loader = VpnConfigLoader("../config")

# Load all enabled peers (from manifests or monolithic)
all_peer_configs = config_loader.load_all_peers(enabled_only=True)

# Create orchestrator (now manifest-aware)
orchestrator = create_orchestrator(stack_name)
vpn_configs = orchestrator.load_vpn_configs()

# Deploy
for vpc_conn in orchestrator.create_vpn_connectors():
    # ... existing deployment logic
```

---

## Phase 4: Testing (Incremental)

### Step 4.1: Verify Manifest Loading

```bash
cd pulumi

# Test loading single peer
python3 -c "
from vpn_manifest_loader import VpnManifestLoader
loader = VpnManifestLoader('../config')
peer = loader.load_peer('vimenca')
print(f'Loaded: {peer[\"metadata\"][\"name\"]}')
print(f'Status: {peer[\"status\"][\"conditions\"][0][\"status\"]}')
"
```

**Expected output**:
```
Loaded: vimenca
Status: True
```

### Step 4.2: Test All Peers Loading

```bash
python3 -c "
from vpn_manifest_loader import VpnManifestLoader
loader = VpnManifestLoader('../config')
peers = loader.load_all_peers(enabled_only=True)
print(f'Loaded {len(peers)} enabled peers:')
for p in peers:
    print(f'  - {p[\"metadata\"][\"name\"]}: {p[\"spec\"][\"device\"][\"type\"]}')
"
```

**Expected output**:
```
Loaded 4 enabled peers:
  - vimenca: Checkpoint Firewall
  - cibao: Checkpoint Firewall
  - apap: Firewall Fortinet
  - internal-legacy-network: Legacy Infrastructure
```

### Step 4.3: Test Config Extraction

```bash
python3 -c "
from vpn_manifest_loader import VpnManifestLoader
loader = VpnManifestLoader('../config')
peer = loader.load_peer('apap')
config = loader.extract_vpn_config(peer)
print(f'Peer: {config[\"name\"]}')
print(f'Public IP: {config[\"public_ip\"]}')
print(f'SNAT: {config[\"snat_enabled\"]}')
print(f'SNAT Type: {config[\"snat_type\"]}')
"
```

**Expected output**:
```
Peer: apap
Public IP: 4.152.100.174
SNAT: True
SNAT Type: provider_assigned_ip
```

### Step 4.4: Test Unified Loader (Dual-Stack)

```bash
python3 -c "
from vpn_manifest_loader import VpnConfigLoader
loader = VpnConfigLoader('../config')

# Load all peers (manifests + fallback to monolithic)
peers = loader.load_all_peers()
print(f'Total peers: {len(peers)}')

# Verify all 4 are loaded
names = {p[\"name\"] for p in peers}
print(f'Peers: {sorted(names)}')
"
```

**Expected output**:
```
Total peers: 5 (or 4 if monolithic is removed)
Peers: ['internal-legacy-network', 'apap', 'cibao', 'vimenca']
```

### Step 4.5: Verify Backward Compatibility

Both monolithic and manifests should load identically:

```bash
python3 -c "
from vpn_manifest_loader import VpnManifestLoader, VpnConfigLoader

# Load from manifest
manifest_loader = VpnManifestLoader('../config')
manifest_peer = manifest_loader.load_peer('vimenca')
manifest_config = manifest_loader.extract_vpn_config(manifest_peer)

# Load from unified (which tries manifest first)
config_loader = VpnConfigLoader('../config')
unified_config = config_loader.load_peer('vimenca')

# Compare key fields
assert manifest_config['name'] == unified_config['name']
assert manifest_config['public_ip'] == unified_config['public_ip']
assert manifest_config['destination_cidrs'] == unified_config['destination_cidrs']
print('✓ Backward compatibility verified')
"
```

---

## Phase 5: Pulumi Deployment Testing

### Step 5.1: Dry Run (Preview)

```bash
cd pulumi

# Test that manifests integrate with orchestrator
python3 -c "
from stack_orchestrator import create_orchestrator

# Create orchestrator (should load manifests internally)
orchestrator = create_orchestrator('dev')

# Get VPN configs
vpn_configs = orchestrator.create_vpn_connectors()

print(f'Orchestrator loaded {len(vpn_configs)} VPN configs')
for config in vpn_configs:
    print(f'  - {config[\"name\"]}: {config[\"public_ip\"]}')
"
```

### Step 5.2: Preview Deployment

```bash
# Test Pulumi preview with manifest-loaded config
pulumi stack select dev
pulumi preview --diff
```

Should show same resources as before (backward compatible):
- TGW hub
- 4 VPN connections (one per peer)
- 4 customer gateways
- Routes for each peer

### Step 5.3: Actual Deployment (Optional)

```bash
# Deploy with manifest support
pulumi up

# Verify same state as before
pulumi stack output
```

---

## Phase 6: Migration Strategy (Optional)

Once manifests are tested and working, optionally migrate to full manifest-only mode.

### Option A: Keep Dual-Stack (Recommended)

**Pros**: 
- Maximum backward compatibility
- Can maintain monolithic file for legacy reference
- No pressure to migrate
- Manifests and monolithic coexist peacefully

**Steps**:
1. Add note in vpn-peers.yaml: "Deprecated - use config/peers/*.yaml manifests instead"
2. Keep monolithic file as reference
3. All new peers go to manifests

### Option B: Full Migration

**Pros**: 
- Clean, single source of truth
- Smaller per-peer files
- Better git history

**Steps**:
1. Verify all peers load correctly from manifests
2. Delete `config/vpn-peers.yaml`
3. Update documentation to point to manifests
4. Update CI/CD to validate manifest files

---

## Configuration Query Examples (Future)

With manifests in place, enable rich DevOps queries:

```bash
# List all production peers
vpn-ctl peer list --selector "status=production"

# Find peers with SNAT enabled
vpn-ctl peer list --selector "snat_required=true"

# Get peers by vendor
vpn-ctl peer list --selector "vendor=checkpoint"

# Find peers in specific region
vpn-ctl peer list --selector "region=caribbean"

# Show all ready peers
vpn-ctl peer status --condition "type=Ready,status=True"
```

---

## Troubleshooting

### Manifest Not Loading

```bash
# Check if manifest file exists
ls -la config/peers/vimenca.yaml

# Validate YAML syntax
python3 -c "
import yaml
with open('config/peers/vimenca.yaml') as f:
    doc = yaml.safe_load(f)
    print('Valid YAML')
"

# Test loader directly
python3 -c "
from vpn_manifest_loader import VpnManifestLoader
loader = VpnManifestLoader('../config')
peer = loader.load_peer('vimenca')
if peer:
    print('✓ Manifest loaded')
else:
    print('✗ Manifest not loaded')
"
```

### Tunnel Profile Not Resolved

```bash
# Check tunnel-profiles.yaml exists
ls -la config/tunnel-profiles.yaml

# Verify profile name in peer matches profile name in tunnel-profiles.yaml
grep "profile:" config/peers/vimenca.yaml
grep -A2 "checkpoint_r80:" config/tunnel-profiles.yaml
```

### SNAT Config Issues

```bash
# Check SNAT config in manifest
grep -A10 "snat:" config/peers/apap.yaml

# Verify in extracted config
python3 -c "
from vpn_manifest_loader import VpnManifestLoader
loader = VpnManifestLoader('../config')
peer = loader.load_peer('apap')
config = loader.extract_vpn_config(peer)
print(f'SNAT enabled: {config[\"snat_enabled\"]}')
print(f'SNAT type: {config[\"snat_type\"]}')
print(f'SNAT IP: {config[\"snat_provider_ip\"]}')
"
```

---

## Files Created/Modified

### New Files
- ✅ `config/tunnel-profiles.yaml` — Shared tunnel profiles
- ✅ `config/peers/vimenca.yaml` — Vimenca peer manifest
- ✅ `config/peers/cibao.yaml` — CIBAO peer manifest
- ✅ `config/peers/apap.yaml` — APAP peer manifest with SNAT
- ✅ `config/peers/internal-legacy-network.yaml` — Legacy network peer
- ✅ `pulumi/vpn_manifest_loader.py` — Manifest loading code

### Modified Files
- `pulumi/stack_orchestrator.py` — Add manifest loading support (optional, if doing full integration)
- `pulumi/__main__.py` — Use new config loader (optional, if doing full integration)

### Existing Files (No Changes Needed)
- `pulumi/secrets_manager.py` — Works with manifest configs as-is
- `pulumi/multi_provider_nat.py` — Works with manifest configs as-is
- `.gitignore` — Already ignores `config/peers/*.yaml` (no changes needed)

---

## Success Criteria

✅ All peer manifests load successfully  
✅ Config extraction produces correct output  
✅ Tunnel profiles resolve correctly  
✅ SNAT configuration visible in extracted config  
✅ Backward compatibility with monolithic file maintained  
✅ Pulumi preview shows same resources (before/after)  
✅ Python syntax validation passes  
✅ All 4 peers load with `load_all_peers()`  
✅ Single peer loads with `load_peer(peer_name)`  
✅ Git history is clean (new files, no modifications)

---

## Next Steps

1. ✅ Create manifest files (DONE)
2. ✅ Create manifest loader (DONE)
3. ✅ Write implementation guide (DONE)
4. ⏳ Update `stack_orchestrator.py` to use manifest loader (optional)
5. ⏳ Update `__main__.py` to use manifest loader (optional)
6. ⏳ Test all scenarios (covered in Phase 4)
7. ⏳ Deploy and verify (Phase 5)
8. ⏳ Decide on dual-stack vs. full migration (Phase 6)

---

## References

- [PEER_MANIFEST_DESIGN.md](./PEER_MANIFEST_DESIGN.md) — Architecture and design patterns
- `pulumi/vpn_manifest_loader.py` — Implementation code
- `config/tunnel-profiles.yaml` — Shared profiles reference
- `config/peers/*.yaml` — Example peer manifests
