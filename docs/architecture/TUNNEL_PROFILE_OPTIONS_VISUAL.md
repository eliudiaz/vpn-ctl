# Tunnel Profile Options: Visual Comparison

Quick visual guide comparing 4 architectural approaches.

---

## Option 1: Inline Profiles (Full Self-Containment)

**Each peer contains its own tunnel profile definition.**

```
┌─ example-peer.yaml (330 lines)
│  ├─ metadata: { name: example-peer }
│  ├─ spec:
│  │  ├─ device: { type: Checkpoint... }
│  │  ├─ tunnel:
│  │  │  └─ profileDefinition:           ← Profile defined HERE
│  │  │     ├─ ike_versions: [ikev2]
│  │  │     ├─ phase1: { ... }
│  │  │     ├─ phase2: { ... }
│  │  │     └─ dpd: { ... }
│  │  └─ network: { ... }
│  └─ status: { ... }
│
└─ mock-peer-b.yaml (330 lines)
   ├─ metadata: { name: mock-peer-b }
   ├─ spec:
   │  ├─ device: { type: Checkpoint... }
   │  ├─ tunnel:
   │  │  └─ profileDefinition:           ← SAME profile, REPEATED!
   │  │     ├─ ike_versions: [ikev2]
   │  │     ├─ phase1: { ... }          (50 lines, duplicated)
   │  │     ├─ phase2: { ... }
   │  │     └─ dpd: { ... }
   │  └─ network: { ... }
   └─ status: { ... }

❌ DUPLICATION: Same checkpoint_r80 profile in both files
❌ MAINTENANCE: Update DPD timeout → edit 2 files
✅ SELF-CONTAINED: Each peer file is standalone
```

---

## Option 2: YAML Anchors (Smart Duplication)

**Profiles defined once with anchors, referenced multiple times in single file.**

```
config/profiles-and-peers.yaml (one file, ~800 lines)

_tunnel_profiles:
  checkpoint_r80: &checkpoint_r80_anchor
    ike_versions: [ikev2]
    phase1: { ... }
    phase2: { ... }
    dpd: { ... }

  fortigate_standard: &fortigate_standard_anchor
    ike_versions: [ikev2]
    phase1: { ... }
    phase2: { ... }
    dpd: { ... }

peers:
  - name: example-peer
    tunnel:
      profileDefinition: *checkpoint_r80_anchor  ← Reference anchor
  
  - name: mock-peer-b
    tunnel:
      profileDefinition: *checkpoint_r80_anchor  ← Same anchor
  
  - name: mock-peer-c
    tunnel:
      profileDefinition: *fortigate_standard_anchor  ← Different anchor

✅ DRY: Profiles defined once, referenced N times
✅ MAINTENANCE: Update anchor → all peers using it get update
❌ COUPLING: All peers in single file (git conflicts)
❌ K8S-UNLIKE: YAML anchors not standard in K8s
```

---

## Option 3: Per-Vendor Profile Files (Organized)

**Separate profile file per vendor, peers reference by vendor:name.**

```
config/
├─ profiles/
│  ├─ checkpoint-profiles.yaml
│  │  ├─ r80:                ← Checkpoint R80
│  │  │  ├─ ike_versions: [ikev2]
│  │  │  ├─ phase1: { ... }
│  │  │  └─ ...
│  │  └─ r81:                ← Checkpoint R81 (future)
│  │
│  ├─ fortinet-profiles.yaml
│  │  ├─ standard:           ← FortiGate standard
│  │  └─ advanced:           ← FortiGate advanced (future)
│  │
│  └─ palo-alto-profiles.yaml
│
└─ peers/
   ├─ example-peer.yaml
   │  └─ tunnel:
   │     └─ profileRef:
   │        ├─ vendor: checkpoint
   │        └─ name: r80    ← References external profile
   │
   ├─ mock-peer-b.yaml
   │  └─ tunnel:
   │     └─ profileRef:
   │        ├─ vendor: checkpoint
   │        └─ name: r80    ← Same reference
   │
   └─ mock-peer-c.yaml
      └─ tunnel:
         └─ profileRef:
            ├─ vendor: fortinet
            └─ name: standard

✅ DRY: Profiles organized by vendor
✅ SCALABLE: Can add new profiles per vendor
✅ ORGANIZED: Vendor-centric structure
❌ MULTI-FILE: Still need to coordinate vendor profiles + peers
❌ NOT SELF-CONTAINED: Peer references external profile
```

---

## Option 4: Hybrid (Current - RECOMMENDED ⭐)

**Base profiles in shared file, peers reference + optionally override.**

```
config/

├─ tunnel-profiles.yaml (5KB)
│  └─ profiles:
│     ├─ checkpoint_r80:      ← Defined ONCE
│     │  ├─ ike_versions: [ikev2]
│     │  ├─ phase1: { encryption: AES256, ... }
│     │  ├─ phase2: { encryption: AES256, ... }
│     │  └─ dpd: { timeout: 30, ... }
│     │
│     └─ fortigate_standard:   ← Defined ONCE
│        ├─ ike_versions: [ikev2]
│        ├─ phase1: { ... }
│        └─ phase2: { ... }
│
└─ peers/
   ├─ example-peer.yaml (280 lines)
   │  └─ spec:
   │     └─ tunnel:
   │        ├─ profile: checkpoint_r80  ← Reference
   │        └─ overrides: {}            ← No changes to base
   │
   ├─ mock-peer-b.yaml (280 lines)
   │  └─ spec:
   │     └─ tunnel:
   │        ├─ profile: checkpoint_r80  ← Same reference
   │        └─ overrides: {}
   │
   ├─ mock-peer-c.yaml (280 lines)
   │  └─ spec:
   │     └─ tunnel:
   │        ├─ profile: fortigate_standard  ← Different reference
   │        └─ overrides: {}
   │
   └─ mock-peer-d.yaml (280 lines)
      └─ spec:
         └─ tunnel:
            ├─ profile: checkpoint_r80
            └─ overrides: {}

      (If this peer needed custom DPD timeout:)
            ├─ profile: checkpoint_r80
            └─ overrides:
               └─ dpd:
                  └─ timeout: 15  ← Override just this value

✅ DRY: Profiles defined once
✅ SELF-CONTAINED: Peer file has everything + references
✅ MAINTAINABLE: Update profile → all peers get change
✅ FLEXIBLE: Peers can override specific settings
✅ SCALABLE: 100+ peers with ~10 profile lines each
✅ K8S-ALIGNED: Similar to K8s ConfigMaps + Pods
✅ GIT HISTORY: Profile changes tracked separately
```

---

## Workflow Comparison: Update Tunnel Settings

### Scenario: "All Checkpoint firewalls need DPD timeout: 15 seconds (urgent security patch)"

**Option 1 (Inline)**:
```bash
# Edit example-peer.yaml
# Change: dpd.timeout: 30 → 15
git add config/peers/example-peer.yaml

# Edit mock-peer-b.yaml
# Change: dpd.timeout: 30 → 15
git add config/peers/mock-peer-b.yaml

# Edit mock-peer-d.yaml
# Change: dpd.timeout: 30 → 15
git add config/peers/mock-peer-d.yaml

# Commit
git commit -m "fix: Update Checkpoint DPD timeout for security"
# ❌ Mixed peer + profile changes in one commit
# ❌ Hard to see it's the same change across peers
```

**Option 2 (YAML Anchors)**:
```bash
# Edit config/profiles-and-peers.yaml
# Change: checkpoint_r80_anchor.dpd.timeout: 30 → 15
git add config/profiles-and-peers.yaml

# Commit
git commit -m "fix: Update Checkpoint DPD timeout for security"
# ✅ Single change affects all peers using anchor
# ❌ But also modified 3 peer definitions in same commit
# ❌ Git blame might show peer changes even though peer didn't change
```

**Option 4 (Hybrid - CURRENT) ⭐**:
```bash
# Edit config/tunnel-profiles.yaml
# Change: checkpoint_r80.dpd.timeout: 30 → 15
git add config/tunnel-profiles.yaml

# Commit
git commit -m "fix: Update Checkpoint DPD timeout for security"
# ✅ Single file change
# ✅ Clear this is a profile update (affects all referencing peers)
# ✅ Peer files unchanged (they still reference checkpoint_r80)
# ✅ When viewing example-peer.yaml history, no unnecessary changes
# ✅ When viewing tunnel-profiles.yaml history, see all profile evolution
```

---

## Scaling Comparison: Adding 100th Peer

**Option 1 (Inline)**:
```yaml
# Create: config/peers/customer-100.yaml
apiVersion: vpn.example.io/v1
kind: VpnPeer
metadata:
  name: customer-100
spec:
  device:
    type: "Checkpoint Firewall"
  tunnel:
    profileDefinition:              ← Copy-paste 50 lines from another peer
      ike_versions: [ikev2]
      phase1: { ... }              (50 lines of duplication)
      phase2: { ... }
      dpd: { ... }
  network: { ... }
```
❌ **Duplication**: 50 lines copied from existing peer

**Option 4 (Hybrid)**:
```yaml
# Create: config/peers/customer-100.yaml
apiVersion: vpn.example.io/v1
kind: VpnPeer
metadata:
  name: customer-100
spec:
  device:
    type: "Checkpoint Firewall"
  tunnel:
    profile: checkpoint_r80        ← Just reference
    overrides: {}
  network: { ... }
```
✅ **DRY**: Just reference existing profile (3 lines)

---

## File Size Comparison (100 peers)

| Option | tunnel-profiles | peers/*.yaml | Total |
|--------|-----------------|--------------|-------|
| **1 (Inline)** | N/A | 100 × 330 lines = 33,000 | 33 KB |
| **2 (Anchors)** | 1 × 800 lines = 800 | All in 1 file | 0.8 KB |
| **3 (Per-Vendor)** | 5 × 300 = 1,500 | 100 × 260 = 26,000 | 27.5 KB |
| **4 (Hybrid)** | 1 × 300 = 300 | 100 × 280 = 28,000 | 28.3 KB |

---

## Git History Clarity

**What changed in the repo last week?**

**Option 1 (Inline)**:
```bash
$ git log --oneline -10
a1b2c3d Fix DPD timeout in example-peer
b2c3d4e Update EXAMPLE_PEER_C tunnel config
c3d4e5f Fix EXAMPLE_PEER_B network config
d4e5f6g Update example-peer device version
...
# ❌ Hard to tell what's profile change vs. peer config change
# ❌ Interdependent changes (same profile) look separate
```

**Option 4 (Hybrid)**:
```bash
$ git log --oneline -10
a1b2c3d fix: Update Checkpoint DPD timeout (affects 3 peers)
b2c3d4e feat: Add new Fortinet peer customer-50
c3d4e5f feat: Add new tunnel profile for Palo Alto
d4e5f6g fix: Update EXAMPLE_PEER_C SNAT config
...
# ✅ Clear separation: profile changes vs. peer changes
# ✅ Easy to see which peers are affected by profile updates
```

**Git log for specific peer**:
```bash
$ git log config/peers/example-peer.yaml
a1b2c3d Added example-peer peer (initial deployment)
# Shows only example-peer-specific changes, not every DPD timeout update
```

**Git log for profiles**:
```bash
$ git log config/tunnel-profiles.yaml
a1b2c3d fix: Update Checkpoint DPD timeout (affects example-peer, mock-peer-b, legacy)
b2c3d4e feat: Add new tunnel profile for Palo Alto
c3d4e5f fix: Fortinet DPD timeout update
# Shows all profile evolution without peer config noise
```

---

## Decision Grid

```
┌──────────────────┬──────┬──────┬────────┬──────────┐
│ Feature          │  1   │  2   │   3    │    4⭐   │
├──────────────────┼──────┼──────┼────────┼──────────┤
│ DRY              │ ❌❌ │ ✅✅ │  ✅✅  │  ✅✅✅  │
│ Self-Contained   │ ✅✅ │ ❌   │  ⚠️    │   ⚠️✅   │
│ Scalable         │ ❌   │ ❌   │  ✅    │  ✅✅✅  │
│ Maintainable     │ ❌   │ ⚠️   │  ✅    │  ✅✅✅  │
│ K8s-Aligned      │ ⚠️   │ ❌   │  ⚠️    │  ✅✅✅  │
│ Git History      │ ❌   │ ⚠️   │  ✅    │  ✅✅✅  │
│ File Size        │ 🔴   │ 🟢   │  🟡    │  🟡✅    │
│ Complexity       │ 🟢   │ 🔴   │  🟡    │  🟢✅    │
└──────────────────┴──────┴──────┴────────┴──────────┘

🟢 Good  🟡 OK  🔴 Poor  ✅ Excellent
```

---

## Recommendation Summary

| Use Case | Best Option |
|----------|------------|
| **<10 peers, each unique** | Option 1 (Inline) |
| **Single-file deployment** | Option 2 (YAML Anchors) |
| **10-50 peers, vendor-focused org** | Option 3 (Per-Vendor) |
| **20-1000+ peers, enterprise scale** ⭐ | **Option 4 (Hybrid/Current)** |
| **Maximum maintainability** ⭐ | **Option 4 (Hybrid/Current)** |
| **K8s-aligned architecture** ⭐ | **Option 4 (Hybrid/Current)** |

---

## Current Implementation

We are using **Option 4 (Hybrid)** because it provides:

✅ **Professional separation of concerns** — Profiles are templates, peers are instances  
✅ **Kubernetes-inspired architecture** — ConfigMap (tunnel-profiles) + Pod-like resources (peer manifests)  
✅ **Enterprise scalability** — Handles 100+ peers cleanly  
✅ **Clear git history** — Profile changes tracked separately from peer changes  
✅ **Flexible customization** — Peers can override specific profile settings when needed  
✅ **Maintainability** — Update base profile once, all peers get change (unless overridden)  

**This is the architecture used in production infrastructure at scale** (AWS, Google Cloud, Kubernetes, etc.).
