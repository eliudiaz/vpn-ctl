"""Domain repository interfaces (ports)."""

from domain.repositories.vpn_peer_repository import VpnPeerRepository
from domain.repositories.tunnel_profile_repository import TunnelProfileRepository
from domain.repositories.state_repository import StateRepository

__all__ = [
    "VpnPeerRepository",
    "TunnelProfileRepository",
    "StateRepository",
]
