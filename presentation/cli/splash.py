"""ASCII splash screen for vpn-ctl CLI startup."""

import click
from datetime import datetime


def show_splash():
    """Display the vpn-ctl splash screen on first launch."""
    splash = r"""

    ╔══════════════════════════════════════════════════════════════════════════════╗
    ║                                                                              ║
    ║                                                                              ║
    ║                 ██╗   ██╗██████╗ ███╗   ██╗      ██████╗████████╗██╗       ║
    ║                 ██║   ██║██╔══██╗████╗  ██║     ██╔════╝╚══██╔══╝██║       ║
    ║                 ██║   ██║██████╔╝██╔██╗ ██║     ██║        ██║   ██║       ║
    ║                 ╚██╗ ██╔╝██╔═══╝ ██║╚██╗██║     ██║        ██║   ██║       ║
    ║                  ╚████╔╝ ██║     ██║ ╚████║     ╚██████╗   ██║   ███████╗  ║
    ║                   ╚═══╝  ╚═╝     ╚═╝  ╚═══╝      ╚═════╝   ╚═╝   ╚══════╝  ║
    ║                                                                              ║
    ║            VPN Infrastructure Control Tool | Enterprise Grade              ║
    ║                                                                              ║
    ║  8-Layer Orthogonal Architecture • Provider Agnostic • Per-Peer Isolation  ║
    ║                                                                              ║
    ║               🔐 Created by Eliu Diaz - AI / Cloud / Software Architect 🔐           ║
    ║                                                                              ║
    ║                                                                              ║
    ╚══════════════════════════════════════════════════════════════════════════════╝

    """

    click.echo(splash, color=True)

    # Show version and build info
    version_info = f"""
  ┌─────────────────────────────────────────────────────────────────────────┐
  │                                                                         │
  │  Version:        1.0.0                                                  │
  │  Architecture:   8-Layer Orthogonal Design                             │
  │  Provider:       Pulumi (Terraform/CloudFormation Ready)               │
  │  Status:         Production Ready                                       │
  │  Released:       April 2026                                             │
  │  Creator:        Eliu Diaz - AI / Cloud / Software Architect            │
  │                                                                         │
  │  🚀 Quick Start:  vpnctl peer add                                       │
  │  📚 Help:        vpnctl --help                                          │
  │  📖 Docs:        vpnctl info                                            │
  │                                                                         │
  └─────────────────────────────────────────────────────────────────────────┘

    """

    click.secho(version_info, fg='cyan')

    # Show powered by message
    powered_by = """  ⚡ Powered by D&DD Tech / dyddtech.com

  """
    click.secho(powered_by, fg='green')


def show_splash_compact():
    """Display a compact version of the splash screen."""
    splash_compact = r"""
╔════════════════════════════════════════════════════════════════════╗
║                                                                    ║
║       ██╗   ██╗██████╗ ███╗   ██╗      ██████╗████████╗██╗        ║
║       ██║   ██║██╔══██╗████╗  ██║     ██╔════╝╚══██╔══╝██║        ║
║       ██║   ██║██████╔╝██╔██╗ ██║     ██║        ██║   ██║        ║
║       ╚██╗ ██╔╝██╔═══╝ ██║╚██╗██║     ██║        ██║   ██║        ║
║        ╚████╔╝ ██║     ██║ ╚████║     ╚██████╗   ██║   ███████╗   ║
║         ╚═══╝  ╚═╝     ╚═╝  ╚═══╝      ╚═════╝   ╚═╝   ╚══════╝   ║
║                                                                    ║
║       Created by Eliu Diaz | AI / Cloud / Software Architect | v1.0.0  ║
║                                                                    ║
╚════════════════════════════════════════════════════════════════════╝
    """
    click.echo(splash_compact)


def show_splash_minimal():
    """Display a minimal splash screen for non-terminal use."""
    minimal = """
╔════════════════════════════════════════════════════════╗
║  vpn-ctl v1.0.0 - Created by Eliu Diaz - AI / Cloud / Software Architect   ║
║  VPN Infrastructure Control Tool                     ║
╚════════════════════════════════════════════════════════╝
    """
    click.echo(minimal)


def should_show_splash() -> bool:
    """Determine if splash screen should be shown.

    Returns:
        True if this is the first run or splash should be shown
    """
    import os
    splash_file = os.path.expanduser('~/.vpnctl/.splash_shown')

    if not os.path.exists(os.path.dirname(splash_file)):
        return True

    if not os.path.exists(splash_file):
        return True

    return False


def mark_splash_shown():
    """Mark that the splash screen has been shown."""
    import os
    splash_file = os.path.expanduser('~/.vpnctl/.splash_shown')

    os.makedirs(os.path.dirname(splash_file), exist_ok=True)

    with open(splash_file, 'w') as f:
        f.write(f"First run splash shown on: {datetime.now().isoformat()}\n")


def display_splash_if_needed():
    """Display splash screen on first run."""
    if should_show_splash():
        show_splash()
        mark_splash_shown()


__all__ = [
    'show_splash',
    'show_splash_compact',
    'show_splash_minimal',
    'should_show_splash',
    'mark_splash_shown',
    'display_splash_if_needed',
]
