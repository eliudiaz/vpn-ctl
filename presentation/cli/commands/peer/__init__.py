"""Peer management commands (add, deploy, destroy, status, list, refresh, state, configure, recreate)."""

import click
from .add import add
from .deploy import deploy
from .destroy import destroy
from .recreate import recreate
from .status import status
from .list_peers import list_peers
from .refresh import refresh
from .state import state
from .configure import configure


@click.group(name='peer')
def peer_group():
    """Manage VPN peers."""
    pass


peer_group.add_command(add)
peer_group.add_command(deploy)
peer_group.add_command(destroy)
peer_group.add_command(recreate)
peer_group.add_command(status)
peer_group.add_command(list_peers, name='list')
peer_group.add_command(refresh)
peer_group.add_command(state)
peer_group.add_command(configure)

__all__ = ['peer_group']
