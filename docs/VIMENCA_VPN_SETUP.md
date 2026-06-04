# VIMENCA VPN Configuration - Ready for Setup

**Status**: ✅ Organization infrastructure fully configured and ready for VIMENCA to connect

**Date Created**: 2026-04-08  
**VPN Connection ID**: vpn-0ab5476c1fcceac5b  
**Customer Gateway ID**: cgw-0a3695afcf8de0719

---

## Tunnel Endpoint Information for VIMENCA

Share the following tunnel endpoints with VIMENCA so they can configure their Checkpoint Firewall R80.10:

### Tunnel 1
- **Organization Tunnel IP**: `3.146.163.197`
- **Inside Tunnel CIDR**: `169.254.148.184/30`
- **Pre-Shared Key**: `y0XszfcaGD007Mc0DVEa`

### Tunnel 2
- **Organization Tunnel IP**: `16.58.137.104`
- **Inside Tunnel CIDR**: `169.254.220.92/30`
- **Pre-Shared Key**: `y0XszfcaGD007Mc0DVEa`

---

## IPsec Configuration Parameters

All the following parameters are already configured on Organization's side. VIMENCA must match these on their Checkpoint Firewall:

### Phase 1 (IKE)
- **IKE Version**: IKEv2 only
- **Encryption Algorithm**: AES256
- **Integrity Algorithm**: SHA2-256 (SHA-256)
- **DH Group**: 14
- **Lifetime**: 28800 seconds (8 hours)

### Phase 2 (IPsec)
- **Encryption Algorithm**: AES256
- **Integrity Algorithm**: SHA2-256 (SHA-256)
- **DH Group**: None (Perfect Forward Secrecy disabled)
- **Lifetime**: 3600 seconds (1 hour)

### Dead Peer Detection (DPD)
- **Timeout**: 30 seconds
- **Action**: Restart

### Routing
- **Mode**: Static routes only (no BGP dynamic routing)
- **Organization VPC CIDR**: 172.31.0.0/16 (source for traffic)

---

## Networks Accessible Through VIMENCA VPN

Once the tunnels are UP, VIMENCA can reach the following networks at Organization:

| Network | CIDR | Description |
|---------|------|-------------|
| Securities Services | 172.16.65.21/32 | HTTPS/HTTP services at VIMENCA endpoint |
| Securities Range | 172.16.70.0/24 | Full range for Securities infrastructure |
| Test Services | 172.16.82.0/24 | Test environment including 172.16.82.28:8088 |

---

## Connection Status Monitoring

### Expected Timeline
1. VIMENCA configures their Checkpoint Firewall with the tunnel endpoints
2. VIMENCA initiates the IKE handshake to both tunnel IPs
3. Organization's tunnels transition from **DOWN** → **UP** (typically 1-5 minutes)
4. Traffic begins flowing through the established tunnels
5. Static routes in Transit Gateway activate (change from blackhole → active)

### Current Status (as of 2026-04-08 15:57:41 UTC)
- Tunnel 1 (3.146.163.197): **DOWN** ⏳ Awaiting VIMENCA connection
- Tunnel 2 (16.58.137.104): **DOWN** ⏳ Awaiting VIMENCA connection
- VPN Connection State: **pending** → will become **available** when VIMENCA connects

### How to Monitor
Once VIMENCA connects, you can check tunnel status in AWS Console:
```bash
aws ec2 describe-vpn-connections --vpn-connection-ids vpn-0ab5476c1fcceac5b \
  --region us-east-2 --profile default | jq '.VpnConnections[0].VgwTelemetry'
```

---

## VIMENCA Contact Information (Organization Records)

- **Primary**: Eric Frias
  - Phone: 809-487-2679
  - Email: efrias@bv.com.do

- **Secondary**: Fermir Quezada
  - Phone: 809-487-2602
  - Email: fquezada@bv.com.do

---

## Organization Configuration Summary

| Parameter | Value |
|-----------|-------|
| **Organization Public IP** | 3.146.163.197 (Tunnel 1), 16.58.137.104 (Tunnel 2) |
| **VIMENCA Public IP** | 191.97.106.141 |
| **BGP ASN (VIMENCA)** | 65000 |
| **BGP ASN (Organization TGW)** | 64512 |
| **Transit Gateway ID** | tgw-0572ce4b80ff7445a |
| **VPN Type** | IPsec 1.0 |
| **Routing Mode** | Static routes only |
| **Device**: | Checkpoint Firewall R80.10 |

---

## Next Steps

1. **For VIMENCA**: Configure both tunnel endpoints on Checkpoint Firewall with provided credentials
2. **For Organization**: Monitor tunnel status for UP transition
3. **After Tunnels UP**: Verify end-to-end connectivity through VPN Health Monitor dashboard at https://vpn.assurehub.io/
4. **Testing**: VIMENCA can test connectivity to any IP in the accessible networks above

---

## Technical Reference

- VPN Configuration Source: `/aff-atg/config/vpn-peers.yaml`
- Tunnel Profile: `checkpoint_r80` (IPsec/IKEv2 standards-based)
- Infrastructure as Code: Pulumi (AWS provider)
- Deployed: 2026-04-08 15:57:41 UTC
