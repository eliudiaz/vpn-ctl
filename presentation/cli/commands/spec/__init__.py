"""Spec management commands (validate, sync, generate)."""

import click
from .validate import validate
from .sync import sync


@click.group(name='spec')
def spec_group():
    """Manage peer specifications."""
    pass


spec_group.add_command(validate)
spec_group.add_command(sync)

__all__ = ['spec_group']
