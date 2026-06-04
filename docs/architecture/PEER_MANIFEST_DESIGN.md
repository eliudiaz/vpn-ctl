# Peer Manifest Design: K8s-Style Per-Peer Specifications

**Status**: Proposed Architecture  
**Date**: May 11, 2026  
**Purpose**: Split vpn-peers.yaml into atomic, per-peer manifest files (K8s-style) with extensibility for peer-specific VPN parameters.

---

## Current State: Monolithic vpn-peers.yaml

**File**: `config/vpn-peers.yaml` (247 lines)

**Structure**:
```yaml
tunnel_profiles:      # Shared across all peers
  checkpoint_r80: { ... }
  fortigate_standard: { ... }
  palo_alto_standard: { ... }

peers:                # All peers mixed in one array
  - name: MockPeerA
    tunnel_profile: checkpoint_r80
    ...
  - name: MOCK_PEER_B
    tunnel_profile: checkpoint_r80
    ...
  - name: MOCK_PEER_C
    tunnel_profile: fortigate_standard
    ...
```

**Limitations**:
- ❌ All peers in single file (hard to manage at scale)
- ❌ Peer-specific overrides of tunnel profiles not supported
- ❌ Adding peer-specific VPN parameters requires modifying shared structure
- ❌ Difficult to version/audit individual peer changes
- ❌ No clear ownership per peer
- ❌ CI/CD cannot trigger per-peer updates (must update whole file)

---

## Proposed: K8s-Style Manifest Architecture

**Philosophy**: Treat each VPN peer like a Kubernetes resource — atomic, self-contained, versioned independently.

### Directory Structure

```
config/
├── tunnel-profiles.yaml          (Shared tunnel templates)
└── peers/
    ├── mock-peer-a.yaml             (MockPeerA specification)
    ├── mock-peer-b.yaml               (MOCK_PEER_B specification)
    ├── mock-peer-c.yaml                (MOCK_PEER_C specification)
    └── mock-peer-d.yaml  (Legacy network specification)
```

### File Format: K8s-Inspired Manifest

Each peer file follows Kubernetes resource pattern:

**`config/peers/mock-peer-a.yaml`** (Example):
```yaml
apiVersion: vpn.example.io/v1
kind: VpnPeer
metadata:
  name: mock-peer-a
  namespace: vpn-infrastructure
  labels:
    vendor: checkpoint
    status: production
    region: dominican-republic
  annotations:
    created-by: "Platform Engineering"
    last-reviewed: "2026-04-15"
spec:
  enabled: true
  device:
    type: "Checkpoint Firewall"
    version: "R80.10"
    vendor: "Checkpoint"
  network:
    public_ip: "191.97.106.141"
    bgp_asn: 65000
    destination_cidrs:
      - "172.16.70.0/24"
      - "172.16.65.21/32"
      - "172.16.82.0/24"
    imported_cidrs:  # Pre-existing in AWS, protected
      - "172.16.70.0/24"
      - "172.16.65.21/32"
  tunnel:
    profile: checkpoint_r80  # Reference to shared tunnel-profiles.yaml
    # Optional: Override specific tunnel parameters
    overrides:
      phase1:
        lifetime: 28800  # Custom lifetime if different from profile
      # ... other overrides
  security:
    psk:
      tunnel1: "y0XszfcaGD007Mc0DVEa"
      tunnel2: "y0XszfcaGD007Mc0DVEa"
      source: "vault"  # Where PSK is managed (vault, aws-secrets-manager, etc.)
  contacts:
    - name: "Eric Frias"
      phone: "809-487-2679"
      email: "efrias@bv.com.do"
      role: "Primary Contact"
    - name: "Fermir Quezada"
      phone: "809-487-2602"
      email: "fquezada@bv.com.do"
      role: "Secondary Contact"
  # Peer-specific VPN parameters (extensible)
  vpnSpecific:
    mss_clamping: 1436
    dpd_timeout_override: 30  # Override tunnel profile's DPD setting
    static_routes_only: true
    routing_protocol: "static"  # "static" or "bgp"
  # Custom peer parameters (vendor-specific)
  customParameters:
    checkpoint:
      encryption_domain: "172.16.0.0/16"
      automatic_negotiation: true
status:
  lastDeployed: "2026-04-16T14:35:22Z"
  vpnConnectionId: "vpn-05ea9c12f40b67844"
  tunnelStatus:
    tunnel1: "UP"
    tunnel2: "UP"
  routesActive: 3
  conditions:
    - type: "Ready"
      status: "True"
      lastTransitionTime: "2026-04-16T14:35:22Z"
      reason: "VpnConnected"
```

**`config/peers/mock-peer-c.yaml`** (SNAT Example):
```yaml
apiVersion: vpn.example.io/v1
kind: VpnPeer
metadata:
  name: mock-peer-c
  namespace: vpn-infrastructure
  labels:
    vendor: fortinet
    status: production
    snat_required: "true"
spec:
  enabled: true
  device:
    type: "Firewall Fortinet"
    version: "FortiGate v7.2.10"
    vendor: "Fortinet"
  network:
    public_ip: "4.152.100.174"
    bgp_asn: 64516
    destination_cidrs:
      - "172.33.50.0/30"
  tunnel:
    profile: fortigate_standard
  security:
    psk:
      tunnel1: "rb70BeeW9_uzZyDzGuc1wIkSkLkMPeUrJgZpH4Lm5177m09JelLvFbh95y2ziuoW"
      tunnel2: "oaVKn9YDRxkINDMvfX_wnlx1dyNLgBesOzzCt9hksynaHmYF5fxEX9Jr0DRIyYip"
      source: "vault"
  vpnSpecific:
    static_routes_only: true
    routing_protocol: "static"
    pfs_enabled: true
    replay_detection: true
  # SNAT-specific configuration
  snat:
    enabled: true
    type: "provider_assigned_ip"  # or "nat_instance"
    provider_assigned_ip: "203.0.113.99"  # MOCK_PEER_C provides this IP
    nat_instance_config:
      # Would be populated if using isolated NAT gateway
      instance_type: "t3.micro"
      availability_zone: "us-east-2a"
  contacts:
    - name: "MOCK_PEER_C Network Operations"
      phone: "TBD"
      email: "operations@mock-peer-c.local"
      role: "Network Administrator"
status:
  lastDeployed: "2026-04-16T08:22:33Z"
  vpnConnectionId: "vpn-0603daac887e7abed"
  tunnelStatus:
    tunnel1: "DOWN"
    tunnel2: "DOWN"
  routesActive: 0
  conditions:
    - type: "PendingCustomerConfiguration"
      status: "True"
      reason: "AwaitingCustomerSetup"
```

**`config/tunnel-profiles.yaml`** (Shared):
```yaml
apiVersion: vpn.example.io/v1
kind: TunnelProfiles
metadata:
  name: tunnel-profiles
  namespace: vpn-infrastructure
profiles:
  checkpoint_r80:
    description: "Checkpoint R80.10 compatible (MockPeerA standard)"
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
  
  fortigate_standard:
    description: "Fortinet FortiGate standard profile (IKEv2 with PFS)"
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
  
  palo_alto_standard:
    description: "Palo Alto Networks standard profile"
    ike_versions: ["ikev1", "ikev2"]
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
      timeout: 10
      action: "clear"
    static_routes_only: false
```

---

## Design Features

### 1. **Atomic Per-Peer Specifications**
- Each peer = one file = one git commit
- Changes to peer X don't affect peer Y
- Easy to audit history: `git log config/peers/mock-peer-c.yaml`

### 2. **Extensible Peer Parameters**

**`vpnSpecific`** section allows vendor-neutral VPN tuning:
```yaml
vpnSpecific:
  mss_clamping: 1436
  dpd_timeout_override: 30
  replay_detection: true
  anti_replay_window: 64
  rekey_margin: 540
  rekey_fuzz: 100
```

**`customParameters.<vendor>`** section for vendor-specific config:
```yaml
customParameters:
  checkpoint:
    encryption_domain: "172.16.0.0/16"
    automatic_negotiation: true
  fortinet:
    phase1_negotiation_mode: "aggressive"
    anti_replay_window: 128
```

### 3. **Profile Reference + Override Pattern**
- Peer references a tunnel profile (e.g., `checkpoint_r80`)
- Can override specific parameters in `overrides` section
- Maintains DRY principle while allowing flexibility

```yaml
tunnel:
  profile: checkpoint_r80
  overrides:
    phase1:
      lifetime: 14400  # 4 hours instead of 8
    dpd:
      timeout: 15  # 15 seconds instead of 30
```

### 4. **SNAT Configuration as Native Peer Property**
- SNAT is now first-class citizen in peer spec
- Supports multiple SNAT modes (provider_assigned_ip, nat_instance, etc.)
- MOCK_PEER_C-specific SNAT parameters co-located with peer definition

```yaml
snat:
  enabled: true
  type: "provider_assigned_ip"
  provider_assigned_ip: "203.0.113.99"
```

### 5. **Status + Conditions (K8s-Like)**
- `status` section tracks live state
- `conditions` array provides detailed status (Ready, PendingConfiguration, Error, etc.)
- Enables rich monitoring and health checks

```yaml
status:
  lastDeployed: "2026-04-16T14:35:22Z"
  vpnConnectionId: "vpn-05ea9c12f40b67844"
  tunnelStatus:
    tunnel1: "UP"
    tunnel2: "UP"
  conditions:
    - type: "Ready"
      status: "True"
      reason: "VpnConnected"
```

### 6. **Metadata + Labels for Organization**
- `labels`: Enable filtering, querying (e.g., vendor=checkpoint, status=production)
- `annotations`: Add operational context (reviewed_by, created_date, etc.)
- Enables rich queries: "all production Checkpoint peers" → filter by label

```yaml
metadata:
  labels:
    vendor: checkpoint
    status: production
    region: dominican-republic
  annotations:
    created-by: "Platform Engineering"
    last-reviewed: "2026-04-15"
```

---

## Python Integration: Loading Manifests

**`vpn_config_manager.py`** (Updated):

```python
from pathlib import Path
import yaml
from dataclasses import dataclass

class VpnManifestLoader:
    """Load K8s-style VPN peer manifests."""
    
    def __init__(self, peers_dir: str = "../config/peers"):
        self.peers_dir = Path(peers_dir)
        self.tunnel_profiles = self._load_tunnel_profiles()
    
    def _load_tunnel_profiles(self) -> dict:
        """Load shared tunnel profiles from config/tunnel-profiles.yaml."""
        profiles_file = self.peers_dir.parent / "tunnel-profiles.yaml"
        if profiles_file.exists():
            with open(profiles_file) as f:
                doc = yaml.safe_load(f)
                return doc.get("profiles", {})
        return {}
    
    def load_all_peers(self) -> list[dict]:
        """Load all peer manifests from config/peers/*.yaml."""
        peers = []
        for peer_file in sorted(self.peers_dir.glob("*.yaml")):
            with open(peer_file) as f:
                manifest = yaml.safe_load(f)
                # Resolve tunnel profile references
                if "profile" in manifest.get("spec", {}).get("tunnel", {}):
                    profile_name = manifest["spec"]["tunnel"]["profile"]
                    manifest["spec"]["tunnel"]["_resolved_profile"] = \
                        self.tunnel_profiles.get(profile_name)
                peers.append(manifest)
        return peers
    
    def load_peer(self, peer_name: str) -> dict:
        """Load single peer manifest by name."""
        peer_file = self.peers_dir / f"{peer_name}.yaml"
        if not peer_file.exists():
            raise FileNotFoundError(f"Peer manifest not found: {peer_file}")
        
        with open(peer_file) as f:
            manifest = yaml.safe_load(f)
        
        # Resolve tunnel profile
        if "profile" in manifest.get("spec", {}).get("tunnel", {}):
            profile_name = manifest["spec"]["tunnel"]["profile"]
            manifest["spec"]["tunnel"]["_resolved_profile"] = \
                self.tunnel_profiles.get(profile_name)
        
        return manifest

# Usage in __main__.py
loader = VpnManifestLoader("../config/peers")
all_peers = loader.load_all_peers()  # Load all peer manifests

for peer_manifest in all_peers:
    peer_name = peer_manifest["metadata"]["name"]
    peer_spec = peer_manifest["spec"]
    
    # Extract VPN configuration
    network_config = peer_spec["network"]
    tunnel_config = peer_spec["tunnel"]
    snat_config = peer_spec.get("snat", {})
    
    # Use in orchestrator
    vpn_connector_config = {
        "name": peer_name,
        "public_ip": network_config["public_ip"],
        "bgp_asn": network_config["bgp_asn"],
        "destination_cidrs": network_config["destination_cidrs"],
        "tunnel_profile": tunnel_config["profile"],
        "psk": peer_spec["security"]["psk"],
        "snat": snat_config,
        # ... etc
    }
    
    # Deploy
    vpn_connectors = orchestrator.create_vpn_connectors([vpn_connector_config])
```

---

## Migration Path

### Phase 1: Dual-Stack Support (Zero Breaking Changes)
Both `vpn-peers.yaml` and individual manifests work simultaneously.

```yaml
# config/vpn-peers.yaml (still works)
peers:
  - name: mock-peer-a
    tunnel_profile: checkpoint_r80
    ...

# config/peers/mock-peer-a.yaml (new, also works)
apiVersion: vpn.example.io/v1
kind: VpnPeer
metadata:
  name: mock-peer-a
...
```

**Loader strategy**: Try individual manifests first, fall back to monolithic file.

```python
def load_peer_config(peer_name):
    # Try individual manifest first
    manifest_file = Path(f"config/peers/{peer_name}.yaml")
    if manifest_file.exists():
        return load_manifest(manifest_file)
    
    # Fall back to monolithic file
    return load_monolithic_vpn_peers()[peer_name]
```

### Phase 2: Migrate to Manifests
Users gradually migrate peers to individual manifest files. Testing confirms equivalence before deleting from monolithic file.

### Phase 3: Full Manifest Mode
Deprecate `vpn-peers.yaml`, use only individual manifests and shared `tunnel-profiles.yaml`.

---

## Benefits

| Aspect | Monolithic | Manifests |
|--------|-----------|-----------|
| **Peer isolation** | ❌ All in one file | ✅ Atomic per-peer files |
| **Extensibility** | ⚠️ Requires schema changes | ✅ Free-form spec section |
| **Vendor specifics** | ❌ Not supported | ✅ customParameters.<vendor> |
| **SNAT config** | ⚠️ Boolean flag | ✅ Full SNAT object |
| **Version control** | ⚠️ Whole file commits | ✅ Per-peer git history |
| **Scaling** | ⚠️ 10+ peers = unwieldy | ✅ 100+ peers = easy |
| **CI/CD triggering** | ❌ Can't trigger per-peer | ✅ Trigger on peer file change |
| **Auditability** | ⚠️ Mixed changes | ✅ Clear per-peer lineage |
| **K8s-like patterns** | ❌ No | ✅ Yes (familiar to DevOps) |

---

## Implementation Checklist

- [ ] Create `config/tunnel-profiles.yaml` with shared profiles
- [ ] Create `config/peers/` directory
- [ ] Migrate mock-peer-a → `config/peers/mock-peer-a.yaml`
- [ ] Migrate mock-peer-b → `config/peers/mock-peer-b.yaml`
- [ ] Migrate mock-peer-c → `config/peers/mock-peer-c.yaml`
- [ ] Migrate mock-peer-d → `config/peers/mock-peer-d.yaml`
- [ ] Update `vpn_config_manager.py` to load manifests with fallback to monolithic
- [ ] Add dual-stack support in orchestrator
- [ ] Test: Each peer deploys identically via manifest vs. monolithic
- [ ] Add validation: schema validation for peer manifests
- [ ] Documentation: Update INSTALL.md with new manifest structure
- [ ] Deprecate monolithic `vpn-peers.yaml` (Phase 3)

---

## Example Queries (Future DevOps Capabilities)

Once manifests are in place, enable rich DevOps queries:

```bash
# List all production Checkpoint peers
vpn-ctl peer list --selector "vendor=checkpoint,status=production"

# Find peers with SNAT enabled
vpn-ctl peer list --selector "snat_required=true"

# Deploy all peers in dominican-republic region
vpn-ctl peer deploy --selector "region=dominican-republic"

# Show all peers ready for deployment
vpn-ctl peer status --condition "type=Ready,status=True"
```

---

## Conclusion

**K8s-style peer manifests** provide:
- ✅ Atomic, versioned peer specifications
- ✅ Freedom for peer-specific VPN parameters
- ✅ Clear extensibility (customParameters section)
- ✅ Familiar pattern for DevOps engineers
- ✅ Scalable to 100+ peers
- ✅ Rich monitoring and automation possibilities
- ✅ Zero-breaking-change migration path

**Recommended**: Implement Phase 1 (dual-stack) first, migrate gradually, then deprecate monolithic file in Phase 3.
