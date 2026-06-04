"""List available infrastructure providers."""

import click


@click.command()
def list_providers():
    """List available IaC providers."""
    click.echo("\n📦 Available Infrastructure Providers:\n")
    click.secho("  ✓ pulumi (current)", fg='green')
    click.echo("    Status: Production")
    click.echo("    Stacks: Fully supported")
    click.echo()

    click.echo("  📋 terraform (roadmap)")
    click.echo("    Status: Coming soon")
    click.echo("    Stacks: Will support state import")
    click.echo()

    click.echo("  📋 cloudformation (roadmap)")
    click.echo("    Status: Coming soon")
    click.echo("    Stacks: Will support stack migration")
    click.echo()

    click.echo("To switch providers: vpn-ctl provider switch")
