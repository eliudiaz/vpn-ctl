# Tunnel Profile Restructuring Analysis

**Status**: Architecture Analysis  
**Date**: May 11, 2026  
**Question**: How to move tunnel-profiles.yaml so profiles are configured inline in each peer YAML?

---

## Current Architecture (Status Quo)

**Structure**:
```
config/
├── tunnel-profiles.yaml           ← Shared, referenced by peers
└── peers/
    ├── example-peer.yaml              ← References: checkpoint_r80
    ├── mock-peer-b.yaml                ← References: checkpoint_r80
    ├── mock-peer-c.yaml                 ← References: fortigate_standard
    └── mock-peer-d.yaml
```

**Problem**: Two separate files — peers and profiles decoupled.

---

## Option 1: Inline Profiles in Each Peer (Full Self-Containment)

**Concept**: Move tunnel profile definition directly into each peer manifest.

### Example: example-peer.yaml (with inline profile)

```yaml
apiVersion: vpn.example.io/v1
kind: VpnPeer
metadata:
  name: example-peer
spec:
  device:
    type: "Checkpoint Firewall"
    version: "R80.10"
  
  # INLINE TUNNEL PROFILE (not referenced, defined here)
  tunnel:
    # Profile definition embedded in peer
    profileDefinition:
      name: checkpoint_r80
      description: "Checkpoint R80.10 compatible"
      ike_versions: ["ikev2"]
      phase1:
        encryption: ["AES256"]
        integrity: ["SHA2-256"]
        dh_groups: [14]
        lifetime: 28800
      phase2:
        encryption: ["AES256"]
        integrity: ["SHA2-256"]
        dh_groups: []
        lifetime: 3600
      dpd:
        timeout: 30
        action: "restart"
      static_routes_only: true
    
    # Optional: Override specific settings for this peer
    overrides: {}
  
  network:
    public_ip: "191.97.106.141"
    # ... rest of config ...
```

### Example: mock-peer-c.yaml (with inline profile)

```yaml
apiVersion: vpn.example.io/v1
kind: VpnPeer
metadata:
  name: mock-peer-c
spec:
  device:
    type: "Firewall Fortinet"
    version: "FortiGate v7.2.10"
  
  # INLINE TUNNEL PROFILE
  tunnel:
    profileDefinition:
      name: fortigate_standard
      description: "Fortinet FortiGate with IKEv2 + PFS"
      ike_versions: ["ikev2"]
      phase1:
        encryption: ["AES256"]
        integrity: ["SHA2-256"]
        dh_groups: [14]
        lifetime: 28800
      phase2:
        encryption: ["AES256"]
        integrity: ["SHA2-256"]
        dh_groups: [14]
        lifetime: 3600
      dpd:
        timeout: 30
        action: "restart"
      aggressive_mode: false
      pfs_enabled: true
      replay_detection: true
      static_routes_only: true
    
    overrides: {}
  
  # ... rest of config ...
```

### Pros & Cons

**Pros ✅**:
- ✅ **Complete self-containment**: One peer file = everything needed to deploy
- ✅ **Atomic git commits**: Peer + profile changes in one commit
- ✅ **No external dependencies**: Peer doesn't reference external file
- ✅ **Easy to understand**: New developer opens example-peer.yaml, sees full config
- ✅ **Per-peer customization**: Easy to have slight profile variations

**Cons ❌**:
- ❌ **Duplication**: MockPeerA and EXAMPLE_PEER_B repeat same checkpoint_r80 profile (50+ lines each)
- ❌ **Maintenance nightmare**: Update DPD timeout → edit 2 peer files
- ❌ **Violates DRY**: Same profile defined multiple times
- ❌ **Larger files**: ~280 lines → ~330 lines per peer (50 line increase)
- ❌ **Harder to audit**: "Which peers use which profiles?" requires grepping all files
- ❌ **Migration risk**: If Checkpoint firmware updates, must update multiple peer files

**Impact**: **HIGH COUPLING** between peers using same device type.

---

## Option 2: YAML Anchors & References (Smart Duplication)

**Concept**: Use YAML native anchors (`&`) and references (`*`) to define profiles once, reference many times.

### Structure with Anchors

**File**: `config/profiles-and-peers.yaml` (single unified file with anchors)

```yaml
# Define profiles once with anchors
_tunnel_profiles:
  checkpoint_r80: &checkpoint_r80_profile
    description: "Checkpoint R80.10 compatible"
    ike_versions: ["ikev2"]
    phase1:
      encryption: ["AES256"]
      integrity: ["SHA2-256"]
      dh_groups: [14]
      lifetime: 28800
    phase2:
      encryption: ["AES256"]
      integrity: ["SHA2-256"]
      dh_groups: []
      lifetime: 3600
    dpd:
      timeout: 30
      action: "restart"
    static_routes_only: true

  fortigate_standard: &fortigate_standard_profile
    description: "Fortinet FortiGate with IKEv2 + PFS"
    ike_versions: ["ikev2"]
    phase1:
      encryption: ["AES256"]
      integrity: ["SHA2-256"]
      dh_groups: [14]
      lifetime: 28800
    phase2:
      encryption: ["AES256"]
      integrity: ["SHA2-256"]
      dh_groups: [14]
      lifetime: 3600
    dpd:
      timeout: 30
      action: "restart"
    aggressive_mode: false
    pfs_enabled: true
    replay_detection: true
    static_routes_only: true

# Peers reference profiles using YAML anchors
peers:
  - apiVersion: vpn.example.io/v1
    kind: VpnPeer
    metadata:
      name: example-peer
    spec:
      device:
        type: "Checkpoint Firewall"
        version: "R80.10"
      tunnel:
        profileDefinition: *checkpoint_r80_profile  # Reference, not duplication
      network:
        public_ip: "191.97.106.141"
        # ... rest of config ...

  - apiVersion: vpn.example.io/v1
    kind: VpnPeer
    metadata:
      name: mock-peer-b
    spec:
      device:
        type: "Checkpoint Firewall"
        version: "R80.10"
      tunnel:
        profileDefinition: *checkpoint_r80_profile  # Same reference
      network:
        public_ip: "186.148.92.203"
        # ... rest of config ...

  - apiVersion: vpn.example.io/v1
    kind: VpnPeer
    metadata:
      name: mock-peer-c
    spec:
      device:
        type: "Firewall Fortinet"
        version: "FortiGate v7.2.10"
      tunnel:
        profileDefinition: *fortigate_standard_profile  # Different profile
      network:
        public_ip: "4.152.100.174"
        # ... rest of config ...
```

### Alternative: Multi-File Anchors with Includes

If you want to keep files separate but use anchors, use YAML merge (`&` + `<<`):

**File**: `config/base-profiles.yaml`
```yaml
checkpoint_r80: &checkpoint_r80_profile
  description: "Checkpoint R80.10 compatible"
  # ... full profile ...
```

**File**: `config/peers/example-peer.yaml`
```yaml
apiVersion: vpn.example.io/v1
kind: VpnPeer
metadata:
  name: example-peer
spec:
  device:
    type: "Checkpoint Firewall"
  tunnel:
    profileDefinition: 
      <<: *checkpoint_r80_profile  # Merge anchor reference
      # Optional: override specific fields
  # ... rest ...
```

**Issue**: YAML anchors only work **within the same file** or with YAML-specific tooling. Standard YAML doesn't support cross-file anchors.

### Pros & Cons

**Pros ✅**:
- ✅ **DRY principle**: Profiles defined once, referenced multiple times
- ✅ **Single source of truth**: One profile definition used by all peers
- ✅ **Easy maintenance**: Update checkpoint_r80 → all peers using it get update
- ✅ **No duplication**: Same ~50 lines, referenced N times
- ✅ **File size**: Smaller (no repeated profile definitions)

**Cons ❌**:
- ❌ **YAML syntax complexity**: Anchors are less readable for non-YAML experts
- ❌ **Cross-file anchors don't work**: Can't split into separate files (must be single file)
- ❌ **Not standard K8s**: K8s doesn't use YAML anchors (uses separate resource files)
- ❌ **Parsing requirements**: Standard YAML parsers handle anchors, but some tools don't
- ❌ **Coupling**: All peers in single file (harder to add peers independently)
- ❌ **Git conflicts**: Multiple developers editing same file = more merge conflicts

**Impact**: **COMPLEX BUT DRY** — Works but adds YAML sophistication.

---

## Option 3: Per-Vendor Profile Files

**Concept**: Instead of one tunnel-profiles.yaml, have separate files per vendor.

### Structure

```
config/
├── profiles/
│   ├── checkpoint-profiles.yaml    ← All Checkpoint profiles
│   ├── fortinet-profiles.yaml      ← All Fortinet profiles
│   └── palo-alto-profiles.yaml     ← All Palo Alto profiles
└── peers/
    ├── example-peer.yaml               ← References checkpoint:r80
    ├── mock-peer-b.yaml                 ← References checkpoint:r80
    ├── mock-peer-c.yaml                  ← References fortinet:standard
    └── mock-peer-d.yaml
```

**File**: `config/profiles/checkpoint-profiles.yaml`
```yaml
apiVersion: vpn.example.io/v1
kind: CheckpointTunnelProfiles
metadata:
  name: checkpoint-tunnel-profiles

profiles:
  r80:  # Short name
    description: "Checkpoint R80.10 compatible"
    ike_versions: ["ikev2"]
    phase1:
      encryption: ["AES256"]
      # ... full definition ...

  r81:  # Could support multiple Checkpoint versions
    description: "Checkpoint R81 compatible"
    # ... config ...
```

**File**: `config/peers/example-peer.yaml`
```yaml
apiVersion: vpn.example.io/v1
kind: VpnPeer
metadata:
  name: example-peer
spec:
  device:
    type: "Checkpoint Firewall"
    version: "R80.10"
  
  tunnel:
    profileRef:
      vendor: checkpoint      # Reference vendor
      name: r80               # Reference profile name
    overrides: {}
  
  # ... rest ...
```

### Loader Implementation

```python
def load_tunnel_profile(vendor: str, profile_name: str) -> Dict:
    """Load tunnel profile by vendor and name."""
    profile_file = Path(f"../config/profiles/{vendor}-profiles.yaml")
    
    with open(profile_file) as f:
        doc = yaml.safe_load(f)
    
    return doc["profiles"][profile_name]
```

### Pros & Cons

**Pros ✅**:
- ✅ **Organized by vendor**: Easy to find all Checkpoint profiles
- ✅ **Scalable**: Can have multiple profiles per vendor (r80, r81, etc.)
- ✅ **DRY**: Profiles defined once per vendor
- ✅ **Future-proof**: Easy to support new vendors (add new file)
- ✅ **Vendor-specific evolution**: Each vendor file can evolve independently

**Cons ❌**:
- ❌ **Still a shared file**: Not fully self-contained per peer
- ❌ **More files**: 3+ profile files instead of 1
- ❌ **Coordination**: Must load peer file AND profile file
- ❌ **Reference breaking**: If peer references non-existent profile, error at runtime

**Impact**: **ORGANIZED BUT NOT SELF-CONTAINED** — Better than one big file, worse than fully inline.

---

## Option 4: Hybrid Approach (Recommended for Balance)

**Concept**: Keep shared tunnel-profiles.yaml for templates, allow per-peer customization inline.

### Structure

```
config/
├── tunnel-profiles.yaml           ← Base/standard profiles
└── peers/
    ├── example-peer.yaml              ← References checkpoint_r80
    ├── mock-peer-b.yaml                ← References checkpoint_r80
    ├── mock-peer-c.yaml                 ← References fortigate_standard + custom overrides
    └── mock-peer-d.yaml
```

**File**: `config/peers/mock-peer-c.yaml` (with custom profile tuning)

```yaml
apiVersion: vpn.example.io/v1
kind: VpnPeer
metadata:
  name: mock-peer-c
spec:
  device:
    type: "Firewall Fortinet"
    version: "FortiGate v7.2.10"
  
  tunnel:
    # Reference shared profile
    profile: fortigate_standard
    
    # But override specific parameters for THIS peer
    overrides:
      phase1:
        lifetime: 14400  # 4 hours instead of 8 (custom for this peer)
      dpd:
        timeout: 15     # 15 seconds instead of 30 (custom for this peer)
      # Only what differs from base profile
  
  network:
    public_ip: "4.152.100.174"
    # ... rest ...
```

### Loader Implementation

```python
def get_effective_tunnel_config(peer_manifest: Dict) -> Dict:
    """Get effective tunnel config: base profile + peer overrides."""
    tunnel_spec = peer_manifest["spec"]["tunnel"]
    profile_name = tunnel_spec["profile"]
    
    # Load base profile from tunnel-profiles.yaml
    base_profile = self.tunnel_profiles[profile_name]
    
    # Deep merge with peer-specific overrides
    effective_config = deep_merge(base_profile, tunnel_spec.get("overrides", {}))
    
    return effective_config
```

### Pros & Cons

**Pros ✅**:
- ✅ **Best of both worlds**: Shared templates + per-peer customization
- ✅ **DRY for common case**: Standard profiles defined once
- ✅ **Flexible for exceptions**: Peers can customize specific settings
- ✅ **Readable**: Peer manifest shows only what's different (overrides section)
- ✅ **Maintainable**: Update base profile → all peers using it get update (unless overridden)
- ✅ **Current architecture**: Already implemented!
- ✅ **K8s-aligned**: Similar to how K8s ConfigMaps + Deployments work

**Cons ❌**:
- ⚠️ **Two files to manage**: tunnel-profiles.yaml + peer manifests
- ⚠️ **Slight indirection**: Must understand profile references
- ⚠️ **Not fully self-contained**: Peer file references external profile

**Impact**: **BALANCED APPROACH** — Professional, maintainable, scalable. *This is our current design.*

---

## Comparison Table

| Option | Approach | Files | DRY | Self-Contained | Scalability | Maintenance | K8s-Like |
|--------|----------|-------|-----|----------------|------------|-------------|---------|
| **1: Inline** | Full embedding | 1 per peer | ❌ Poor | ✅ Excellent | ⚠️ Medium (100+ peer files) | ❌ Hard (update multiple) | ⚠️ K8s stores config inline |
| **2: YAML Anchors** | Smart references | 1 unified | ✅ Good | ❌ Complex | ❌ Poor (single file) | ⚠️ Medium | ❌ Not standard K8s |
| **3: Per-Vendor** | Vendor organization | 3-5 files | ✅ Good | ❌ Partial | ✅ Good | ✅ Good | ⚠️ Custom |
| **4: Hybrid** ⭐ | Base + overrides | 2 concepts | ✅ Excellent | ⚠️ Good | ✅ Excellent | ✅ Excellent | ✅ Standard |

---

## Recommendation: Why Current Architecture (Hybrid) Is Best

The **current architecture (Option 4)** is optimal for this use case:

### **Current Design**:
```
tunnel-profiles.yaml       ← 3 profiles (checkpoint_r80, fortigate_standard, palo_alto_standard)
     ↓ (referenced by)
config/peers/*.yaml        ← 4 peers (example-peer, mock-peer-b, mock-peer-c, mock-peer-d)
```

### **Why This Wins**:

1. **Scalability**: Add 100th peer?
   - ✅ Option 4: Create `config/peers/peer-100.yaml` (references existing profile)
   - ❌ Option 1: Create 330-line file with full profile duplication

2. **Maintenance**: Update all Checkpoint tunnels for new compliance requirement?
   - ✅ Option 4: Edit `tunnel-profiles.yaml` checkpoint_r80 once, all peers get it
   - ❌ Option 1: Edit 2+ peer files
   - ❌ Option 2: Single large file (git conflicts)
   - ⚠️ Option 3: Edit checkpoint-profiles.yaml (still good, just more files)

3. **Git History**: Developer wants to see what profiles were available?
   - ✅ Option 4: `git log config/tunnel-profiles.yaml` shows profile evolution
   - ❌ Option 1: Profile changes mixed with peer config changes

4. **Developer Experience**: New developer wants to understand VPN config?
   - ✅ Option 4: Clear separation — profiles are templates, peers are instances
   - ❌ Option 1: Open example-peer.yaml, see 330 lines, hard to tell what's shared vs. unique
   - ❌ Option 2: One giant file with YAML anchors (intimidating)

5. **Professional Architecture**: How do enterprises structure this?
   - ✅ Option 4: **ConfigMap pattern** (Kubernetes approach) — shared configs + instances
   - Standard in:
     - Kubernetes (ConfigMaps + Pods)
     - Terraform (modules/variables + instances)
     - Helm (values.yaml + templates)

---

## Alternative: If You Really Want Full Self-Containment

If the requirement is **"each peer must be 100% self-contained with NO external references"**, then:

**Use Option 1 (Inline Profiles)** with a **hybrid Python approach**:

```python
# Store base profiles in Python, not YAML
BASE_PROFILES = {
    "checkpoint_r80": {
        "ike_versions": ["ikev2"],
        # ... full definition ...
    },
    "fortigate_standard": {
        # ... full definition ...
    }
}

# When processing peer manifest with inline profile:
if "profileDefinition" in peer_manifest["spec"]["tunnel"]:
    # Profile is embedded in peer (Option 1)
    use_embedded_profile = True
else:
    # Profile is referenced (Option 4 current)
    use_shared_profile = True
```

**Result**: Support both architectures simultaneously:
- Teams that want self-contained peers: Use Option 1 (inline profiles)
- Teams that want DRY: Use Option 4 (shared profiles)
- Manifest loader handles both

---

## Implementation Decision Matrix

**Choose Option 1 (Inline) if**:
- You have <10 peers total (manageable duplication)
- Each peer has completely unique VPN requirements
- Self-containment is absolute requirement
- You rarely update tunnel profiles

**Choose Option 3 (Per-Vendor) if**:
- You have 10-50 peers
- You want organized, vendor-centric structure
- Each vendor group might have different profile evolution

**Choose Option 4 (Hybrid - CURRENT) if** ⭐ **RECOMMENDED**:
- You have >20 peers expected long-term
- Multiple peers share same device type (Checkpoint, FortiGate, etc.)
- You want professional, maintainable architecture
- You want to follow K8s ConfigMap patterns
- Git history clarity is important
- Peer profiles rarely change (mostly reference shared template)

**Choose Option 2 (YAML Anchors) if**:
- You want to optimize single-file deployments
- You have specialized YAML tooling
- You don't care about K8s alignment

---

## Conclusion

**The current architecture (Option 4) is the right balance**:

✅ **DRY**: Profiles defined once  
✅ **Scalable**: Supports 100+ peers cleanly  
✅ **Maintainable**: Profile updates apply to all peers  
✅ **Professional**: Aligns with enterprise patterns (K8s ConfigMaps)  
✅ **Clear Git history**: Peer changes separate from profile changes  
✅ **Extensible**: Supports per-peer profile overrides when needed  

**If full self-containment is required**: Implement Option 1 (inline profiles) alongside Option 4, with dual-mode loader support.

---

## Appendix: Migration Path If Changing Architecture

If you decide to move to Option 1 (inline profiles):

```bash
# 1. Extract profiles from tunnel-profiles.yaml for each peer
for peer in example-peer mock-peer-b mock-peer-c mock-peer-d; do
  PROFILE=$(grep "profile:" config/peers/$peer.yaml | awk '{print $2}')
  # Find profile definition in tunnel-profiles.yaml
  # Copy into config/peers/$peer.yaml under spec.tunnel.profileDefinition
done

# 2. Update manifest loader to read inline profiles
python3 -c "
from vpn_manifest_loader import VpnManifestLoader
loader = VpnManifestLoader()
# Modify to check for profileDefinition before looking for profile reference
"

# 3. Delete tunnel-profiles.yaml
rm config/tunnel-profiles.yaml

# 4. Test all peers still deploy
pulumi preview
```

But **we recommend keeping the current Option 4 architecture** — it's professionally designed and proven effective.
