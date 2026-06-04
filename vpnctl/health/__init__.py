"""VPN Health Monitoring System.

Monitors VPN peer state by:
1. Reading peer specs from config/vpn-peers.yaml (source of truth)
2. Querying AWS for current state
3. Detecting config changes automatically
4. Reporting health status and config drift
"""
