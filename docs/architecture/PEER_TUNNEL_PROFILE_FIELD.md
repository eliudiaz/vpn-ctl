# Peer Tunnel Profile Field: Specification and Clarity

**Objective**: Make tunnel profile reference explicit and clear in peer manifests.

---

## Current State (Already Implemented ✅)

**Current peer manifest structure**:

```yaml
apiVersion: vpn.example.io/v1
kind: VpnPeer
metadata:
  name: example-peer
spec:
  tunnel:
    profile: checkpoint_r80        # ← Profile reference (clear but could be more explicit)
    overrides: {}
```

**This already works**, but we can enhance clarity with options below.

---

## Option A: Add Explicit Profile Metadata (RECOMMENDED)

**Make the profile reference MORE PROMINENT with additional metadata**:

```yaml
apiVersion: vpn.example.io/v1
kind: VpnPeer
metadata:
  name: example-peer
  labels:
    tunnel-profile: checkpoint_r80  # ← Explicit label for easier querying
    tunnel-vendor: checkpoint       # ← Quick vendor identification
spec:
  # Explicit tunnel profile section
  tunnel:
    # Which profile to use (required field)
    profileName: checkpoint_r80
    
    # Reference to the shared profile definition
    profileSource: config/tunnel-profiles.yaml
    
    # Profile version/date for documentation
    profileVersion: "1.0"           # Track profile evolution
    
    # Override specific fields from base profile
    overrides:
      dpd:
        timeout: 15                 # If Checkpoint device needs different DPD
```

**Benefits**:
- ✅ Explicit field naming (`profileName` is clearer than `profile`)
- ✅ Label-based querying (find all peers using checkpoint_r80)
- ✅ Profile source documented
- ✅ Version tracking for compliance/audit

---

## Option B: Enhanced Tunnel Section (More Metadata)

**Add validation and sourcing information**:

```yaml
spec:
  tunnel:
    # Profile reference (required)
    profile:
      name: checkpoint_r80          # Profile name
      vendor: checkpoint            # Device vendor
      version: R80.10               # Device version (informational)
      source: config/tunnel-profiles.yaml  # Where profile is defined
    
    # Validation
    validated: true                 # Profile exists and is valid
    lastValidated: "2026-05-12T10:30:00Z"
    
    # Overrides
    overrides:
      dpd:
        timeout: 15
```

**Benefits**:
- ✅ Structured profile reference (object instead of string)
- ✅ Vendor/version tracking
- ✅ Validation status visible
- ✅ Self-documenting

---

## Option C: Profile Reference with Link (K8s-Style)

**Use K8s-like reference pattern**:

```yaml
spec:
  tunnel:
    # Profile reference (K8s-style reference)
    profileRef:
      kind: TunnelProfile
      name: checkpoint_r80
      apiVersion: vpn.example.io/v1
      namespace: vpn-infrastructure
    
    # Overrides
    overrides: {}
```

**Benefits**:
- ✅ K8s-aligned pattern
- ✅ Explicit kind/namespace (future-proof for multiple profile types)
- ✅ Machine-readable format for tools

**Usage in loader**:
```python
def resolve_profile_ref(peer_manifest):
    profile_ref = peer_manifest["spec"]["tunnel"]["profileRef"]
    profile_name = profile_ref["name"]
    # Load from tunnel-profiles.yaml
    return tunnel_profiles[profile_name]
```

---

## Option D: Inline Profile Reference with Validation

**Current + add validation metadata**:

```yaml
spec:
  tunnel:
    # Profile reference
    profile: checkpoint_r80
    
    # Validation metadata
    profileMetadata:
      vendor: checkpoint
      description: "Checkpoint R80.10 compatible (MockPeerA standard)"
      ike_version: "IKEv2"
      encryption: "AES256"
      pfs: "disabled"
      dpdTimeout: 30
    
    # Overrides
    overrides: {}
```

**Benefits**:
- ✅ Quick reference without opening tunnel-profiles.yaml
- ✅ Validates profile is correctly referenced
- ✅ Self-documenting

---

## Recommended: Option A + Validation

**Combine clarity with practical validation**:

```yaml
apiVersion: vpn.example.io/v1
kind: VpnPeer
metadata:
  name: example-peer
  labels:
    tunnel-profile: checkpoint_r80  # For querying all peers with this profile
    tunnel-vendor: checkpoint
  annotations:
    tunnel-profile-description: "Checkpoint R80.10 standard IPsec/IKE config"

spec:
  device:
    type: "Checkpoint Firewall"
    version: "R80.10"
  
  # TUNNEL PROFILE SECTION (explicit and documented)
  tunnel:
    # Which tunnel profile to use from config/tunnel-profiles.yaml
    profileName: checkpoint_r80
    
    # Documentation: what this profile provides
    profileDescription: "IKEv2, AES256/SHA2-256, no PFS, DPD 30s, static routes"
    
    # Optional overrides for peer-specific customization
    overrides:
      # Example: if this peer needs different DPD timeout
      # dpd:
      #   timeout: 15

  network:
    public_ip: "191.97.106.141"
    # ... rest of config ...
```

**With validation in loader**:

```python
def validate_peer_tunnel_profile(peer_manifest):
    """Validate tunnel profile exists and is correctly referenced."""
    tunnel_spec = peer_manifest["spec"]["tunnel"]
    profile_name = tunnel_spec.get("profileName")
    
    if not profile_name:
        raise ValueError(f"Missing tunnel.profileName in peer {peer_name}")
    
    if profile_name not in self.tunnel_profiles:
        raise ValueError(
            f"Tunnel profile not found: {profile_name}\n"
            f"Available profiles: {list(self.tunnel_profiles.keys())}"
        )
    
    return True

# Usage
for peer in all_peers:
    validate_peer_tunnel_profile(peer)  # Catches missing/invalid profiles
```

---

## Query Examples (With Labels)

**With labels added to metadata, enable rich queries**:

```bash
# Find all peers using checkpoint_r80 profile
kubectl get peers -l tunnel-profile=checkpoint_r80

# Find all Checkpoint peers
kubectl get peers -l tunnel-vendor=checkpoint

# Find all peers that need tunnel profile update
vpn-ctl peer list --tunnel-profile=checkpoint_r80 --action=update-dpd
```

---

## Update All Peer Manifests

**Apply Option A (recommended) to all peers**:

### example-peer.yaml
```yaml
apiVersion: vpn.example.io/v1
kind: VpnPeer
metadata:
  name: example-peer
  labels:
    tunnel-profile: checkpoint_r80
    tunnel-vendor: checkpoint
  annotations:
    tunnel-profile-description: "Checkpoint R80.10 standard profile"

spec:
  tunnel:
    profileName: checkpoint_r80
    profileDescription: "IKEv2, AES256/SHA2-256, no PFS, DPD 30s"
    overrides: {}
  
  # ... rest of spec ...
```

### mock-peer-b.yaml
```yaml
apiVersion: vpn.example.io/v1
kind: VpnPeer
metadata:
  name: mock-peer-b
  labels:
    tunnel-profile: checkpoint_r80
    tunnel-vendor: checkpoint
  annotations:
    tunnel-profile-description: "Checkpoint R80.10 standard profile"

spec:
  tunnel:
    profileName: checkpoint_r80
    profileDescription: "IKEv2, AES256/SHA2-256, no PFS, DPD 30s"
    overrides: {}
  
  # ... rest of spec ...
```

### mock-peer-c.yaml
```yaml
apiVersion: vpn.example.io/v1
kind: VpnPeer
metadata:
  name: mock-peer-c
  labels:
    tunnel-profile: fortigate_standard
    tunnel-vendor: fortinet
  annotations:
    tunnel-profile-description: "Fortinet FortiGate standard profile with PFS"

spec:
  tunnel:
    profileName: fortigate_standard
    profileDescription: "IKEv2, AES256/SHA2-256, PFS Group 14, DPD 30s"
    overrides: {}
  
  # ... rest of spec ...
```

### mock-peer-d.yaml
```yaml
apiVersion: vpn.example.io/v1
kind: VpnPeer
metadata:
  name: mock-peer-d
  labels:
    tunnel-profile: checkpoint_r80
    tunnel-vendor: checkpoint
  annotations:
    tunnel-profile-description: "Checkpoint R80.10 standard profile"

spec:
  tunnel:
    profileName: checkpoint_r80
    profileDescription: "IKEv2, AES256/SHA2-256, no PFS, DPD 30s"
    overrides: {}
  
  # ... rest of spec ...
```

---

## Implementation: Updated Manifest Loader

**Update `vpn_manifest_loader.py` to handle enhanced profile field**:

```python
class VpnManifestLoader:
    def extract_vpn_config(self, peer_manifest: Dict[str, Any]) -> Dict[str, Any]:
        """Extract VPN config with enhanced profile validation."""
        tunnel_spec = peer_manifest["spec"]["tunnel"]
        
        # Support both old and new field names for backward compatibility
        profile_name = tunnel_spec.get("profileName") or tunnel_spec.get("profile")
        
        if not profile_name:
            raise ValueError(
                f"Peer {peer_manifest['metadata']['name']} missing tunnel profile\n"
                f"Required: spec.tunnel.profileName or spec.tunnel.profile"
            )
        
        # Validate profile exists
        if profile_name not in self.tunnel_profiles:
            raise ValueError(
                f"Profile not found: {profile_name}\n"
                f"Available: {list(self.tunnel_profiles.keys())}"
            )
        
        # Get base profile
        base_profile = self.tunnel_profiles[profile_name]
        
        # Apply peer-specific overrides
        effective_profile = self._deep_merge(
            base_profile,
            tunnel_spec.get("overrides", {})
        )
        
        return {
            "name": peer_manifest["metadata"]["name"],
            "tunnel_profile_name": profile_name,
            "tunnel_profile": effective_profile,
            # ... rest of config ...
        }
```

---

## Benefits of This Approach

✅ **Explicit**: Field name is clear (`profileName` not just `profile`)  
✅ **Queryable**: Labels enable `kubectl get peers -l tunnel-profile=checkpoint_r80`  
✅ **Documented**: `profileDescription` shows what this profile does  
✅ **Validated**: Loader checks profile exists  
✅ **Backward compatible**: Loader supports both `profile` and `profileName`  
✅ **Future-proof**: Can extend with versioning, constraints, etc.  

---

## Summary

**Current field**: `spec.tunnel.profile: checkpoint_r80` ✅ (works)

**Enhanced field**: 
```yaml
metadata:
  labels:
    tunnel-profile: checkpoint_r80
spec:
  tunnel:
    profileName: checkpoint_r80
    profileDescription: "IKEv2, AES256/SHA2-256, ..."
    overrides: {}
```

**Result**: 
- Explicit profile reference in peer spec
- Labels for querying
- Description for documentation
- Validation in loader
- Ready for future enhancements
