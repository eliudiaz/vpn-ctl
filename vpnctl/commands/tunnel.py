"""vpnctl tunnel commands - Display and monitor VPN tunnel status and information."""

import click
import socket
import subprocess
from pathlib import Path
from typing import Optional, Tuple
from vpnctl.tunnel_info import show_tunnel_info

from domain.services.peer_spec_manager import PeerSpecManager
from domain.exceptions import DomainValidationError


@click.group()
def tunnel():
    """VPN tunnel operations and monitoring."""
    pass


@tunnel.command()
@click.option(
    '--config',
    type=click.Path(exists=False),
    help='Path to VPN config file (default: config/vpn-peers.yaml)'
)
def info(config):
    """
    Display comprehensive tunnel information for all VPN peers.

    Combines:
    - Current AWS public IPs and tunnel status
    - Tunnel profile encryption/DH/lifetime parameters
    - Peer configuration details

    Example:
      vpn-ctl tunnel info
      vpn-ctl tunnel info --config /path/to/vpn-peers.yaml
    """
    config_file = config
    if config_file is None:
        # Try to find config file
        config_file = "config/vpn-peers.yaml"
        if not Path(config_file).exists():
            # Try relative to vpnctl module
            config_file = str(Path(__file__).parent.parent.parent / "config" / "vpn-peers.yaml")

    if not Path(config_file).exists():
        click.secho(f"❌ Config file not found: {config_file}", fg='red')
        raise click.Abort()

    show_tunnel_info(config_file)


@tunnel.command('test')
@click.argument('peer_name')
@click.option('--protocol', default=None, help='Filter by protocol (ping/http/https/tcp/dns)')
@click.option('--timeout', type=int, default=5, help='Timeout per test in seconds')
def test_endpoints(peer_name, protocol, timeout):
    """Test all configured endpoints for a VPN peer."""
    try:
        spec_mgr = PeerSpecManager()
        endpoints = spec_mgr.list_test_endpoints(peer_name)

        if not endpoints:
            click.echo(f"No test endpoints configured for {peer_name}")
            return

        if protocol:
            endpoints = [ep for ep in endpoints if ep.protocol == protocol]
            if not endpoints:
                click.secho(f"No endpoints found with protocol {protocol}", fg='yellow')
                return

        click.echo(f"\n🧪 Testing {len(endpoints)} endpoint(s) for {peer_name}...")
        click.echo("=" * 80)

        results = []
        for ep in endpoints:
            status, message = _test_endpoint(ep.target, ep.protocol, ep.port, timeout)
            results.append((ep, status, message))

            status_icon = "✅" if status else "❌"
            port_str = f":{ep.port}" if ep.port else ""
            click.echo(f"{status_icon} {ep.target}{port_str} ({ep.protocol})")
            if message:
                click.echo(f"   └─ {message}")

        # Summary
        click.echo("=" * 80)
        passed = sum(1 for _, status, _ in results if status)
        total = len(results)
        click.echo(f"\n📊 Results: {passed}/{total} passed")

        if passed == total:
            click.secho("All tests passed!", fg='green')
        else:
            click.secho(f"{total - passed} test(s) failed", fg='red')

    except DomainValidationError as e:
        click.secho(f"❌ Error: {e}", fg='red')


def _test_endpoint(target: str, protocol: str, port: Optional[int], timeout: int) -> Tuple[bool, str]:
    """Test a single endpoint. Returns (success, message)."""

    if protocol == "ping":
        return _test_ping(target, timeout)
    elif protocol == "http":
        return _test_http(target, port or 80, timeout)
    elif protocol == "https":
        return _test_http(target, port or 443, timeout, use_https=True)
    elif protocol == "tcp":
        return _test_tcp(target, port or 443, timeout)
    elif protocol == "dns":
        return _test_dns(target, timeout)
    else:
        return False, f"Unknown protocol: {protocol}"


def _test_ping(target: str, timeout: int) -> Tuple[bool, str]:
    """Test connectivity with ping."""
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", str(timeout * 1000), target],
            capture_output=True,
            timeout=timeout + 2,
        )
        if result.returncode == 0:
            return True, "Reachable"
        else:
            return False, "No response"
    except subprocess.TimeoutExpired:
        return False, "Timeout"
    except Exception as e:
        return False, str(e)


def _test_http(target: str, port: int, timeout: int, use_https: bool = False) -> Tuple[bool, str]:
    """Test HTTP/HTTPS connectivity."""
    try:
        import http.client

        if use_https:
            conn = http.client.HTTPSConnection(target, port, timeout=timeout)
        else:
            conn = http.client.HTTPConnection(target, port, timeout=timeout)

        conn.request("GET", "/")
        response = conn.getresponse()
        conn.close()

        if 200 <= response.status < 400:
            return True, f"HTTP {response.status}"
        else:
            return False, f"HTTP {response.status}"

    except socket.timeout:
        return False, "Timeout"
    except Exception as e:
        return False, str(e)


def _test_tcp(target: str, port: int, timeout: int) -> Tuple[bool, str]:
    """Test TCP connectivity."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)

        result = sock.connect_ex((target, port))
        sock.close()

        if result == 0:
            return True, f"Port {port} open"
        else:
            return False, f"Port {port} closed"

    except socket.timeout:
        return False, "Timeout"
    except Exception as e:
        return False, str(e)


def _test_dns(target: str, timeout: int) -> Tuple[bool, str]:
    """Test DNS resolution."""
    try:
        socket.setdefaulttimeout(timeout)
        result = socket.getaddrinfo(target, None)

        if result:
            ips = [addr[4][0] for addr in result]
            return True, f"Resolves to {', '.join(ips)}"
        else:
            return False, "No DNS records found"

    except socket.timeout:
        return False, "Timeout"
    except socket.gaierror as e:
        return False, f"DNS error: {e}"
    except Exception as e:
        return False, str(e)
