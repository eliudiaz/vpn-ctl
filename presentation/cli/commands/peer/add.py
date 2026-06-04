"""Add a new VPN peer."""

import click
from pathlib import Path
from presentation.cli.interactive.peer_wizard import PeerWizard


@click.command()
@click.option('--interactive', is_flag=True, default=True, help='Interactive mode')
@click.option('--dry-run', is_flag=True, default=False, help='Preview only')
def add(interactive, dry_run):
    """
    Add a new VPN peer.

    Interactive mode: Guided wizard for all details.
    Creates spec file and optionally prepares for deployment.
    """
    if interactive:
        wizard = PeerWizard()
        peer_spec = wizard.run()

        if peer_spec is None:
            return

        # Display next steps
        click.echo()
        click.secho("Next Steps:", fg='cyan', bold=True)
        click.echo(f"  1. Review spec file: config/peers/{peer_spec['name']}.yaml")
        click.echo(f"  2. Deploy peer: vpn-ctl peer deploy {peer_spec['name']}")
        click.echo(f"  3. Check status: vpn-ctl peer status {peer_spec['name']}")
        click.echo()
