#!/usr/bin/env python3
"""
vpn-ctl - VPN Infrastructure Control Tool

Provider-agnostic K8s-style declarative VPN infrastructure management.
Wraps Pulumi/Terraform/CloudFormation with professional DevOps workflows.

Usage:
  vpn-ctl --help
  vpn-ctl tunnel info
  vpn-ctl apply --spec spec.yaml
  vpn-ctl destroy --spec spec.yaml
"""

import click
import logging
from vpnctl.commands.tunnel import tunnel
from vpnctl.commands.health import health
from vpnctl.commands.certify import certify
from vpnctl.commands.peer import peer
from vpnctl.commands.infra import infra

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


@click.group()
@click.version_option(version='0.1.0')
def cli():
    """vpn-ctl - VPN Infrastructure Control Tool.

    Provider-agnostic K8s-style declarative VPN infrastructure management.
    """
    pass


# Register command groups
cli.add_command(tunnel)
cli.add_command(health)
cli.add_command(certify)
cli.add_command(peer)
cli.add_command(infra)


if __name__ == '__main__':
    cli()
