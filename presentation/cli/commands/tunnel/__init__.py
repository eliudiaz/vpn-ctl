"""Tunnel monitoring commands (status, test)."""

import click
from .status import status
from .test import test


@click.group(name='tunnel')
def tunnel_group():
    """Monitor and test VPN tunnels."""
    pass


tunnel_group.add_command(status)
tunnel_group.add_command(test)

__all__ = ['tunnel_group']
