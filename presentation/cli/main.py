"""Main entry point for vpn-ctl CLI."""

import click
from presentation.cli.splash import display_splash_if_needed
from presentation.cli.commands.doctor import doctor
from presentation.cli.commands.peer import peer_group
from presentation.cli.commands.interactive import interactive
from presentation.cli.commands.spec import spec_group
from presentation.cli.commands.tunnel import tunnel_group


@click.group(context_settings={'help_option_names': ['-h', '--help']})
@click.version_option(version='1.0.0', prog_name='vpnctl')
def cli():
    """vpnctl - VPN Infrastructure Control Tool

    Enterprise-grade VPN infrastructure platform with 8-layer orthogonal
    architecture, provider agnosticism, and per-peer isolation.

    Quick start:
        vpnctl peer list          # List all peers
        vpnctl interactive        # Interactive menu
        vpnctl peer status NAME   # Check peer status
        vpnctl doctor             # System health check
    """
    # Display splash on first run
    display_splash_if_needed()


# Register commands
cli.add_command(doctor)
cli.add_command(peer_group)
cli.add_command(spec_group)
cli.add_command(tunnel_group)
cli.add_command(interactive, name='interactive')


def main():
    """Entry point for setup.py or module execution."""
    cli()


if __name__ == '__main__':
    main()
