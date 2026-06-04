# vpn-ctl CLI Guide

Complete reference for the vpn-ctl command-line interface.

## Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Or using make
make install
```

## Global Options

All commands support these options:

```bash
vpn-ctl --help              # Show help
vpn-ctl --version           # Show version
vpn-ctl -v                  # Verbose output (if supported)
```

---

## Peer Management

### peer add - Create a New Peer

Interactive wizard to create a VPN peer specification.

```bash
vpn-ctl peer add
```

**Prompts:**
- Peer name (e.g., `customer-x`)
- Public IP address (e.g., `203.0.113.50`)
- BGP ASN (1-65534, e.g., `65000`)
- Device type (`checkpoint`, `fortigate`, or `palo-alto`)
- Device version (e.g., `R80.10`)
- Tunnel profile (e.g., `checkpoint_r80`)
- Destination CIDRs (comma-separated, e.g., `10.0.0.0/16, 10.1.0.0/16`)
- Pre-shared keys (auto-generate recommended)
- Contact name
- Contact email
- Contact phone (optional)

**Output:**
```
✓ Peer spec saved: config/peers/customer-x.yaml
? Deploy now? [y/N]: y
✅ Deployed: customer-x (VPN ID: vpn-0abc1234...)
```

### peer deploy - Deploy a Peer

Deploy a peer to AWS VPN infrastructure.

```bash
vpn-ctl peer deploy customer-x
vpn-ctl peer deploy customer-x --dry-run    # Preview only
```

**Options:**
- `--dry-run` - Preview changes without deploying

**Output:**
```
🚀 Deploying customer-x...
✅ Deployed: customer-x
VPN ID: vpn-0abc1234def5678
Tunnel 1: 3.131.49.110
Tunnel 2: 3.151.46.131
```

### peer destroy - Destroy a Peer

Remove a peer from infrastructure (with confirmation).

```bash
vpn-ctl peer destroy customer-x
```

**Safety:**
- Requires confirmation before deletion
- Cannot be undone

**Output:**
```
? Destroy customer-x? This cannot be undone. [y/N]: y
✅ Destroyed: customer-x
```

### peer status - Show Peer Status

Display detailed status for a specific peer.

```bash
vpn-ctl peer status customer-x
```

**Output:**
```
📊 Peer Status: customer-x

Public IP: 203.0.113.50
BGP ASN: 65000
Device: checkpoint R80.10
Destination CIDRs: 10.0.0.0/16, 10.1.0.0/16

VPN State: available
Tunnel 1: UP
Tunnel 2: UP
```

### peer list - List All Peers

List all VPN peers in the system.

```bash
vpn-ctl peer list
```

**Output:**
```
📋 VPN Peers (4 total)

  • vimenca (191.97.106.141) - checkpoint
  • cibao (191.97.106.142) - checkpoint
  • apap (191.97.106.143) - fortigate
  • customer-x (203.0.113.50) - checkpoint
```

---

## Specification Management

### spec validate - Validate All Specs

Validate all peer specifications against schema.

```bash
vpn-ctl spec validate
```

**Output:**
```
✓ Validating 4 peers...

  ✓ vimenca
  ✓ cibao
  ✓ apap
  ✓ customer-x
✅ All specs valid
```

### spec sync - Synchronize Specs with State

Compare YAML specs with live infrastructure state and identify mismatches.

```bash
vpn-ctl spec sync                    # Show sync status and prompt for fixes
vpn-ctl spec sync --report-only      # Report only, no changes
vpn-ctl spec sync --auto-fix         # Automatically fix conflicts
```

**Options:**
- `--report-only` - Report status without making changes
- `--auto-fix` - Automatically resolve conflicts

**Output:**
```
📊 Comparing spec files with live state...

  ✓ vimenca: IN SYNC
  ✓ cibao: IN SYNC
  ✓ apap: OUT OF SYNC (PSK changed)
  ❓ customer-new: UNDEPLOYED (spec ready)

Summary:
  In sync: 2/4
  Out of sync: 1/4
  Undeployed: 1/4

? Auto-fix conflicts? [y/N]: y
  ✓ Synced: apap (PSK updated)
  ? customer-new - Deploy now? [y/N]: y
    ✓ Deploying customer-new...
✅ All specs synced with state!
```

---

## Tunnel Monitoring

### tunnel status - Show Tunnel Health

Display tunnel status for peers.

```bash
vpn-ctl tunnel status                 # All peers
vpn-ctl tunnel status customer-x      # Specific peer
```

**Output (all peers):**
```
🔗 Tunnel Status (All Peers)

┌────────────────────┬──────────┬──────────┐
│ Peer               │ Tunnel 1 │ Tunnel 2 │
├────────────────────┼──────────┼──────────┤
│ vimenca            │ UP ✓     │ UP ✓     │
│ cibao              │ UP ✓     │ UP ✓     │
│ apap               │ DOWN     │ DOWN     │
│ customer-x         │ DOWN     │ DOWN     │
└────────────────────┴──────────┴──────────┘

⚠️  Alerts:
  • apap: Both tunnels DOWN (6+ hours)
    → Check customer configuration
  • customer-x: Both tunnels DOWN (1+ hour)
    → Customer configuration pending
```

**Output (specific peer):**
```
🔗 Tunnel Status: customer-x

  Tunnel 1: DOWN
  Tunnel 2: DOWN
```

---

## Provider Management

### provider list - List Available Providers

Show available infrastructure providers.

```bash
vpn-ctl provider list
```

**Output:**
```
📦 Available Infrastructure Providers:

  ✓ pulumi (current)
    Status: Production
    Stacks: Fully supported

  📋 terraform (roadmap)
    Status: Coming soon
    Stacks: Will support state import

  📋 cloudformation (roadmap)
    Status: Coming soon
    Stacks: Will support stack migration

To switch providers: vpn-ctl provider switch
```

### provider switch - Switch Between Providers

Switch between infrastructure providers (future feature).

```bash
vpn-ctl provider switch
```

**Note:** This feature is under development and will enable switching between Pulumi, Terraform, and CloudFormation without re-creating infrastructure.

---

## Utility Commands

### version - Show Version

Display vpn-ctl version information.

```bash
vpn-ctl version
```

**Output:**
```
vpn-ctl v1.0.0
VPN Infrastructure Control Tool
```

### info - Show Platform Information

Display platform details and architecture.

```bash
vpn-ctl info
```

**Output:**
```
vpn-ctl v1.0.0 - VPN Infrastructure Control Tool

Architecture: 8-layer orthogonal design
Provider: Pulumi (Terraform/CloudFormation ready)
Config: YAML-based peer specifications

Commands:
  vpn-ctl peer add         Interactive wizard for new peer
  vpn-ctl peer deploy      Deploy peer to infrastructure
  vpn-ctl peer status      Show peer status
  vpn-ctl peer list        List all peers
  vpn-ctl spec validate    Validate all specs
  vpn-ctl spec sync        Sync specs with live state
  vpn-ctl tunnel status    Show tunnel health
  vpn-ctl provider list    List available providers

For help: vpn-ctl --help
```

---

## Examples

### Create and Deploy a New Peer

```bash
# 1. Create peer (interactive)
vpn-ctl peer add
# Follow prompts to create customer-x

# 2. (Optional) Check spec before deployment
vpn-ctl peer status customer-x

# 3. Deploy
vpn-ctl peer deploy customer-x

# 4. Verify tunnels
vpn-ctl tunnel status customer-x
```

### Manage Multiple Peers

```bash
# List all peers
vpn-ctl peer list

# Check all tunnel health
vpn-ctl tunnel status

# Validate all specs
vpn-ctl spec validate

# Sync all with infrastructure
vpn-ctl spec sync --report-only
```

### Troubleshoot a Peer

```bash
# Show peer details
vpn-ctl peer status vimenca

# Check tunnel status
vpn-ctl tunnel status vimenca

# Validate peer spec
vpn-ctl spec validate

# Check if peer is in sync
vpn-ctl spec sync --report-only
```

### Deploy with Dry-Run

```bash
# Preview changes before deployment
vpn-ctl peer deploy customer-x --dry-run

# If preview looks good, deploy
vpn-ctl peer deploy customer-x
```

---

## Configuration Files

### Peer Specifications
Location: `config/peers/{name}.yaml`

Example:
```yaml
apiVersion: v1
kind: VpnPeer
metadata:
  name: customer-x
  created: 2026-04-16T08:00:00Z
spec:
  publicIp: 203.0.113.50
  bgpAsn: 65000
  deviceType: checkpoint
  deviceVersion: R80.10
  tunnelProfile: checkpoint_r80
  destinationCidrs:
    - 10.0.0.0/16
    - 10.1.0.0/16
  contacts:
    - name: John Doe
      email: john@example.com
      phone: +1-555-1234
```

### Tunnel Profiles
Location: `config/tunnel-profiles.yaml`

---

## Troubleshooting

### Command Not Found

```bash
# Make sure vpn-ctl is installed
pip install -r requirements.txt

# Or add to PATH
export PATH="./bin:$PATH"
```

### Peer Validation Fails

```bash
# Check specific peer
vpn-ctl spec validate

# Common issues:
# - CIDR overlap with reserved ranges (172.33.0.0/16)
# - Invalid IP addresses
# - Missing tunnel profiles
# - Invalid peer names
```

### Deployment Fails

```bash
# Preview first to catch issues
vpn-ctl peer deploy customer-x --dry-run

# Check AWS credentials
aws sts get-caller-identity --profile affinity

# Check Pulumi stack
cd pulumi && pulumi stack select peer-customer-x && pulumi export
```

### Tunnels Not Coming Up

```bash
# Check peer status
vpn-ctl peer status customer-x

# Verify tunnel health
vpn-ctl tunnel status customer-x

# Common causes:
# - Customer hasn't configured their side yet
# - AWS security group blocking traffic
# - Firewall rules blocking port 500/4500 (IPsec)
# - PSK mismatch (unlikely if auto-generated)
```

---

## Help & Support

```bash
# Command help
vpn-ctl --help                # All commands
vpn-ctl peer --help           # Peer subcommands
vpn-ctl peer deploy --help    # Specific command

# Documentation
less ARCHITECTURE.md          # System design
less STATE_EXTRACTION.md      # Migration guide
less README.md                # Quick start
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Command syntax error |
| 3 | Validation error |
| 4 | Deployment error |
| 5 | Not found error |

