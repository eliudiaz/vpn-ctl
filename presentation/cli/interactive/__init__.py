"""Interactive CLI components."""

from presentation.cli.commands.interactive import interactive
from .peer_wizard import PeerWizard
from .prompts import (
    prompt_peer_name,
    prompt_public_ip,
    prompt_bgp_asn,
    prompt_device_type,
    prompt_destination_cidrs,
    prompt_tunnel_profile,
    prompt_psk,
    prompt_contacts,
)

__all__ = [
    'interactive',
    'PeerWizard',
    'prompt_peer_name',
    'prompt_public_ip',
    'prompt_bgp_asn',
    'prompt_device_type',
    'prompt_destination_cidrs',
    'prompt_tunnel_profile',
    'prompt_psk',
    'prompt_contacts',
]
