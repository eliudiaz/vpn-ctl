# VPN Pool Architecture Guide

## Overview

The VPN Pool is a refactored architecture that separates VPN resources from peer lifecycles, enabling **static tunnel IP preservation** and **VPN resource reuse**.

### Problem Solved

**Before (Coupled Architecture):**
```
Peer Stack Destroyed → VPN Deleted → Tunnel IPs Lost
Peer Redeployed → New VPN Created → New Tunnel IPs
Result: Customer firewall rules break ❌
```

**After (Decoupled Architecture):**
```
Peer Stack Destroyed → VPN Detached (preserved) → Tunnel IPs Preserved ✅
Peer Redeployed → VPN Reattached → Same Tunnel IPs ✅
Result: Customer firewall rules unaffected ✅
```

---

## Architecture

### Resource Organization

```
┌─────────────────────────────────────────────────────────┐
│ VPN POOL (Persistent)                                   │
├─────────────────────────────────────────────────────────┤
│                                                          │
│ Customer Gateway (CGW)  ──┐                             │
│ VPN Connection         ──┼─→ Tunnel IPs (preserved)    │
│ Tunnel Configuration   ──┘                              │
│                                                          │
│ State: attached | detached | orphaned                   │
│                                                          │
└─────────────────────────────────────────────────────────┘
                          ↕
┌─────────────────────────────────────────────────────────┐
│ PEER STACK (Ephemeral)                                  │
├─────────────────────────────────────────────────────────┤
│                                                          │
│ TGW Routes        (created/destroyed with peer)        │
│ VPC Routes        (created/destroyed with peer)        │
│ SNAT Instance     (created/destroyed with peer)        │
│ CloudWatch Alarms (created/destroyed with peer)        │
│                                                          │
│ Attaches to VPN Pool resources                         │
│ Detaches on destruction (doesn't delete)               │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### Key Components

| Component | File | Purpose |
|-----------|------|---------|
| **VpnRegistry** | `vpn_registry.py` | Persistent tracking of VPN state |
| **VpnAttachmentManager** | `vpn_attachment.py` | Decision logic: create vs attach |
| **VpnAttachmentExecutor** | `vpn_attachment.py` | Execute attachment decisions |
| **VpnPeerLifecycleManager** | `vpn_peer_lifecycle.py` | Track peer creation/destruction |
| **vpn-pool.yaml** | `config/vpn-pool.yaml` | YAML registry of VPN resources |

---

## Peer Lifecycle Flow

### 1. First Peer Creation (Create New VPN)

```
Peer Spec: example-peer.yaml
     ↓
Orchestrator: Check pool for existing VPN
     ↓ (not found)
Create new VPN + CGW
     ↓
Register in pool
     ↓
config/vpn-pool.yaml updated:
  example-peer:
    vpn_id: vpn-05ea9c12f40b67844
    state: attached
    tunnel1_ip: 3.131.49.110
    tunnel2_ip: 3.151.46.131
    preserved_count: 0
```

### 2. Peer Destruction (Detach, Preserve)

```
Destroy peer-example-peer stack
     ↓
Mark VPN as detached
     ↓
Delete routes (TGW/VPC)
Delete SNAT instance
Delete CloudWatch alarms
Delete peer stack state
     ↓
VPN REMAINS in pool ✅
config/vpn-pool.yaml updated:
  example-peer:
    vpn_id: vpn-05ea9c12f40b67844
    state: detached
    tunnel1_ip: 3.131.49.110 (PRESERVED)
    tunnel2_ip: 3.151.46.131 (PRESERVED)
    preserved_count: 0
```

### 3. Peer Redeployment (Reuse VPN)

```
Deploy new peer-example-peer stack
     ↓
Orchestrator: Check pool for existing VPN
     ↓ (found, detached)
Reattach existing VPN
     ↓
Create new routes
Create new SNAT instance
Create new CloudWatch alarms
     ↓
Same tunnel IPs as before ✅
config/vpn-pool.yaml updated:
  example-peer:
    vpn_id: vpn-05ea9c12f40b67844
    state: attached
    tunnel1_ip: 3.131.49.110 (SAME)
    tunnel2_ip: 3.151.46.131 (SAME)
    preserved_count: 1
```

---

## Usage Examples

### Deploy a Peer (Automatic VPN Management)

```bash
cd pulumi/stacks/peer-example-peer
pulumi up

# What happens:
# 1. Checks if VPN exists in pool
# 2. If yes (detached): Reattaches existing VPN
# 3. If no: Creates new VPN and registers in pool
# 4. Creates/updates routes and other peer resources
```

### Check VPN Pool Status

```python
from vpn_peer_lifecycle import VpnPeerLifecycleManager

mgr = VpnPeerLifecycleManager()
mgr.print_pool_status()

# Output:
# ================================================================================
# VPN POOL STATUS
# ================================================================================
# Total VPNs: 4
#   Attached: 3
#   Detached: 1
#   Orphaned: 0
# Total preservations: 2
# 
# 🟢 vpn-05ea9c12f40b67844 (example-peer)
#    Profile: checkpoint_r80
#    Tunnel IPs: 3.131.49.110, 3.151.46.131
#    Preserved: 0 times
# 
# 🟡 vpn-0603daac887e7abed (mock-peer-c)
#    Profile: fortigate_standard
#    Tunnel IPs: 3.156.78.90, 3.161.89.101
#    Preserved: 1 times
# ...
```

### Destroy a Peer (VPN Preserved)

```bash
cd pulumi/stacks/peer-example-peer
pulumi destroy

# What happens:
# 1. Deletes routes (TGW/VPC)
# 2. Deletes SNAT instance (if any)
# 3. Deletes peer stack state
# 4. Marks VPN as detached in pool
# 5. VPN remains in AWS for future reuse
#
# Cost: Still charged $36/month for preserved VPN
# Benefit: Instant redeploy with same tunnel IPs
```

### List Detached VPNs Available for Reuse

```python
from vpn_peer_lifecycle import VpnPeerLifecycleManager

mgr = VpnPeerLifecycleManager()
detached = mgr.list_vpns(state='detached')

for vpn in detached:
    print(f"{vpn.vpn_id}: {vpn.tunnel1_ip}, {vpn.tunnel2_ip}")
    print(f"  Profile: {vpn.tunnel_profile}")
    print(f"  Last detached: {vpn.detached_at}")
```

### Permanently Delete a VPN (Manual, Not Recommended)

```bash
# Only if you're sure the VPN won't be needed again!

# 1. Find VPN ID in pool
cat config/vpn-pool.yaml | grep vpn_id

# 2. Delete in AWS (use your preferred method)
aws ec2 delete-vpn-connection --vpn-connection-id vpn-0603daac887e7abed
aws ec2 delete-customer-gateway --customer-gateway-id cgw-xyz

# 3. Remove from registry (edit config/vpn-pool.yaml)
# - Delete the corresponding entry
# - Save file

# WARNING: Cannot undo this action!
```

---

## Registry File Format (config/vpn-pool.yaml)

```yaml
version: '1.0'
created_at: '2026-05-12T00:00:00'
updated_at: '2026-05-12T14:35:22'

vpns:
  # Entry for each VPN in pool
  - vpn_id: vpn-05ea9c12f40b67844
    customer_gateway_id: cgw-09e8da53ae18ef414
    peer_name: example-peer              # Which peer owns it (null if detached)
    state: attached|detached|orphaned
    tunnel_profile: checkpoint_r80    # Profile name for matching
    tunnel1_ip: 3.131.49.110          # AWS-assigned, preserved forever
    tunnel2_ip: 3.151.46.131          # AWS-assigned, preserved forever
    created_at: '2026-04-16T14:35:22' # When VPN was created
    attached_at: '2026-04-16T14:35:22' # Last time attached
    detached_at: null                  # Last time detached
    preserved_count: 0                 # How many times reused
```

---

## State Transitions

```
         ┌─────────┐
         │ CREATE  │  (New VPN created in AWS)
         └────┬────┘
              ↓
         ┌─────────────┐
         │  ATTACHED   │  (Peer using VPN)
         │ (example-peer)   │
         └────┬────────┘
              ↓
      ┌───────────────┐
      │   DETACH      │  (Peer destroyed)
      └───┬───────┬───┘
          ↓       ↓
      ┌────────────────────┐
      │   DETACHED         │  (VPN preserved)
      │  (reusable)        │
      └────┬───────────┬───┘
           ↓           ↓
    ┌────────────┐  ┌──────────────┐
    │  ATTACH    │  │  DELETE      │
    │(new peer)  │  │ (if never    │
    └────┬───────┘  │  needed)     │
         ↓          └──────────────┘
    ┌─────────────┐
    │  ATTACHED   │
    │ (new peer)  │
    └─────────────┘
```

---

## Cost Implications

| Scenario | Cost | Notes |
|----------|------|-------|
| **VPN Created** | +$36/month | Standard AWS VPN charge |
| **VPN Detached (Preserved)** | Still $36/month | VPN still exists in AWS |
| **VPN Reused** | Still $36/month | Same $36/month, same VPN |
| **VPN Deleted Permanently** | -$36/month | Only if manually deleted from AWS |

**Key Point:** Preserving a detached VPN costs $36/month but saves customer configuration disruption. This is worth it for production VPNs.

---

## Troubleshooting

### VPN Not Found in Pool

```
Error: No VPN found to detach for peer example-peer
```

**Cause:** Peer was created before pool was implemented.

**Solution:** 
1. Check if VPN exists in AWS
2. Add entry to config/vpn-pool.yaml manually
3. Match existing VPN ID and tunnel IPs

### Tunnel IPs Not Preserved After Redeploy

```
Before: 3.131.49.110, 3.151.46.131
After:  3.140.22.55, 3.145.33.77 ❌
```

**Cause:** New VPN was created instead of reusing existing.

**Check:**
1. Verify peer name matches exactly (case-sensitive)
2. Verify tunnel_profile matches in pool
3. Check registry state: `peer_name: null` should exist before redeploy

### Registry Out of Sync

If `config/vpn-pool.yaml` becomes out of sync with AWS:

```bash
# Query actual VPNs in AWS
aws ec2 describe-vpn-connections \
  --filters "Name=state,Values=available" \
  --query 'VpnConnections[*].[VpnConnectionId, State]'

# Manually update config/vpn-pool.yaml to match AWS
# Get tunnel IPs from AWS:
aws ec2 describe-vpn-connections --vpn-connection-ids vpn-xxx \
  --query 'VpnConnections[0].VgwTelemetry[*].OutsideIpAddress'
```

---

## Best Practices

### ✅ DO

- Preserve detached VPNs (default behavior)
- Deploy peers frequently without worrying about VPN impact
- Check pool status before major changes
- Keep config/vpn-pool.yaml committed to git
- Track tunnel IP changes in audit logs

### ❌ DON'T

- Manually delete VPNs from AWS without updating registry
- Edit tunnel IPs in config/vpn-pool.yaml (they're read-only)
- Delete peer stacks without verifying VPN state
- Change tunnel_profile after VPN is created
- Create manual VPN connections outside of orchestrator

---

## Migration from Old Architecture

If migrating existing VPNs to pool:

```python
from vpn_registry import VpnRegistry, VpnPoolEntry

registry = VpnRegistry()

# For each existing VPN, add to registry
registry.data['vpns'].append({
    'vpn_id': 'vpn-05ea9c12f40b67844',
    'customer_gateway_id': 'cgw-09e8da53ae18ef414',
    'peer_name': 'example-peer',
    'state': 'attached',
    'tunnel_profile': 'checkpoint_r80',
    'tunnel1_ip': '3.131.49.110',
    'tunnel2_ip': '3.151.46.131',
    'created_at': '2026-04-16T14:35:22',
    'attached_at': '2026-04-16T14:35:22',
    'detached_at': None,
    'preserved_count': 0,
})

registry._save_registry()
```

---

## Future Enhancements

1. **Automatic VPN Cleanup:** Delete detached VPNs after X days unused
2. **Cost Optimization:** Warn if detached VPNs exceed cost threshold
3. **Monitoring:** CloudWatch dashboard showing pool utilization
4. **Multi-Profile Support:** Share VPN pools across multiple tunnel profiles
5. **VPN Reuse Scheduler:** Auto-attach detached VPNs to new peers automatically

---

## Reference Documentation

- **VPN Registry API:** `vpn_registry.py`
- **Attachment Logic:** `vpn_attachment.py`
- **Lifecycle Hooks:** `vpn_peer_lifecycle.py`
- **Stack Orchestration:** `stack_orchestrator.py` (PeerStackOrchestrator.create_vpn_connectors)
