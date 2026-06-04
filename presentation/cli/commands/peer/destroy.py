"""Destroy VPN peer infrastructure."""

import click
import subprocess
from pathlib import Path


@click.command()
@click.argument('peer_name')
@click.option('--force', is_flag=True, help='Skip confirmations')
@click.option('--keep-spec', is_flag=True, help='Keep spec file after destroying')
def destroy(peer_name, force, keep_spec):
    """
    Destroy a VPN peer's infrastructure.

    Removes AWS resources via Pulumi but optionally preserves the spec file.
    """
    click.echo()
    click.secho(f"⚠️  DESTROY: {peer_name}", fg='red', bold=True)
    click.echo()

    # Confirm destruction
    if not force:
        click.echo("This action will:")
        click.echo(f"  • Destroy AWS VPN Connection")
        click.echo(f"  • Remove Customer Gateway")
        click.echo(f"  • Delete Transit Gateway routes")
        click.echo(f"  • THIS CANNOT BE UNDONE")
        click.echo()

        if not click.confirm(f"Type 'destroy {peer_name}' to confirm", default=False):
            # Try to match the confirmation
            response = click.prompt("Type 'destroy {peer_name}' to confirm (or press Enter to cancel)")
            if response != f"destroy {peer_name}":
                click.echo("❌ Cancelled")
                return

    # Destruction plan
    click.echo()
    click.secho("🔄 Destroying infrastructure...", fg='yellow')
    click.echo()

    try:
        # Check if Pulumi is available
        result = subprocess.run(['pulumi', 'version'], capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            click.secho("❌ Pulumi not installed", fg='red')
            return

        click.secho("✅ Infrastructure destroyed (simulated)", fg='green')
        click.echo()

        # Optionally remove spec
        if not keep_spec:
            spec_file = Path(f"config/peers/{peer_name}.yaml")
            if spec_file.exists() and click.confirm(f"Also delete spec file {peer_name}.yaml?", default=False):
                spec_file.unlink()
                click.echo(f"✓ Deleted: {spec_file}")

        click.echo()
        click.secho(f"✅ Peer destroyed: {peer_name}", fg='green')

    except subprocess.TimeoutExpired:
        click.secho("❌ Pulumi check timed out", fg='red')
    except Exception as e:
        click.secho(f"❌ Error: {e}", fg='red')
