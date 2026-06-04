"""vpnctl health commands - VPN health monitoring and diagnostics."""

import click
import json
from pathlib import Path
from vpnctl.health.state import VPNHealthState


@click.group()
def health():
    """VPN health monitoring and diagnostics."""
    pass


@health.command()
@click.option(
    '--config',
    type=click.Path(exists=False),
    help='Path to VPN config file (default: config/vpn-peers.yaml)'
)
@click.option('--format', type=click.Choice(['table', 'json']), default='table', help='Output format')
def check(config, format):
    """
    Check VPN health status.

    Compares config specs with AWS reality, detects:
    - Missing VPN connections (not deployed)
    - Config drift (spec differs from AWS)
    - Tunnel status (UP/DOWN)
    - Orphaned resources (in AWS but not in config)

    Example:
      vpn-ctl health check
      vpn-ctl health check --format json
    """
    config_file = config
    if config_file is None:
        config_file = "config/vpn-peers.yaml"
        if not Path(config_file).exists():
            config_file = str(Path(__file__).parent.parent.parent / "config" / "vpn-peers.yaml")

    if not Path(config_file).exists():
        click.secho(f"❌ Config file not found: {config_file}", fg='red')
        raise click.Abort()

    click.echo(f"🔍 Checking VPN health from {config_file}...")

    state = VPNHealthState()
    state.refresh(config_file)
    summary = state.get_summary()

    if format == 'json':
        click.echo(json.dumps(state.to_dict(), indent=2))
        return

    # Table format
    click.echo()
    click.secho("=" * 100, fg='cyan')
    click.secho("VPN HEALTH SUMMARY", fg='cyan', bold=True)
    click.secho("=" * 100, fg='cyan')
    click.echo()

    click.echo(f"Total Peers:        {summary['total_peers']}")
    click.secho(f"✓ Healthy:          {summary['healthy']}", fg='green')
    click.secho(f"⚠ Degraded:         {summary['degraded']}", fg='yellow')
    click.secho(f"✗ Unhealthy:        {summary['unhealthy']}", fg='red')
    click.secho(f"❓ Missing:          {summary['missing']}", fg='blue')
    click.secho(f"🗑 Orphaned:         {summary['orphaned']}", fg='magenta')
    click.echo(f"⊘ Disabled:         {summary['disabled']}")
    click.echo(f"Last Update:        {summary['last_update']}")

    click.echo()
    click.secho("=" * 100, fg='cyan')
    click.secho("PEER STATUS", fg='cyan', bold=True)
    click.secho("=" * 100, fg='cyan')
    click.echo()

    # Sort peers by status
    status_order = {'healthy': 0, 'degraded': 1, 'unhealthy': 2, 'missing': 3, 'orphaned': 4, 'disabled': 5}
    sorted_peers = sorted(state.peers.values(), key=lambda p: status_order.get(p.health_status, 99))

    for peer in sorted_peers:
        status_color = {
            'healthy': 'green',
            'degraded': 'yellow',
            'unhealthy': 'red',
            'missing': 'blue',
            'orphaned': 'magenta',
            'disabled': 'white',
        }.get(peer.health_status, 'white')

        status_icon = {
            'healthy': '✓',
            'degraded': '⚠',
            'unhealthy': '✗',
            'missing': '❓',
            'orphaned': '🗑',
            'disabled': '⊘',
        }.get(peer.health_status, '?')

        click.secho(f"{status_icon} {peer.peer_name:<30}", fg=status_color, bold=True, nl=False)
        click.echo(f" | State: {peer.aws_state or 'N/A':<12} | ", nl=False)
        click.echo(f"T1: {peer.tunnel1_status:<7} | T2: {peer.tunnel2_status:<7}")

        if peer.config_drift:
            for drift in peer.config_drift:
                click.secho(f"    ⚠ {drift}", fg='yellow')

        if peer.vpn_id:
            click.echo(f"    VPN ID: {peer.vpn_id}")

    click.echo()
    click.secho("=" * 100, fg='cyan')


@health.command()
@click.option('--host', default='0.0.0.0', help='HTTP host to bind to')
@click.option('--port', type=int, default=8080, help='HTTP port to bind to')
@click.option('--config', type=click.Path(exists=False), help='Path to VPN config file')
def start(host, port, config):
    """
    Start VPN health monitoring service.

    Runs HTTP server that:
    - Watches config/vpn-peers.yaml for changes (auto-refresh)
    - Serves health status at http://localhost:8080/health
    - Accepts POST to /health/refresh to force update
    - Includes Kubernetes probes: /health/liveness, /health/readiness

    Example:
      vpn-ctl health start
      vpn-ctl health start --port 9000
    """
    from vpnctl.health.app import VPNHealthApp

    config_file = config
    if config_file is None:
        config_file = "config/vpn-peers.yaml"
        if not Path(config_file).exists():
            config_file = str(Path(__file__).parent.parent.parent / "config" / "vpn-peers.yaml")

    if not Path(config_file).exists():
        click.secho(f"❌ Config file not found: {config_file}", fg='red')
        raise click.Abort()

    click.secho(f"🚀 Starting VPN Health Service", fg='green')
    click.secho(f"   Config:  {config_file}", fg='cyan')
    click.secho(f"   HTTP:    http://{host}:{port}", fg='cyan')
    click.secho(f"   Health:  http://{host}:{port}/health", fg='cyan')
    click.secho(f"   Peers:   http://{host}:{port}/health/peers", fg='cyan')
    click.echo()

    app = VPNHealthApp(config_file=config_file)
    app.run(host=host, port=port, debug=False)


@health.command()
@click.option('--host', default='localhost', help='Health service host')
@click.option('--port', type=int, default=8080, help='Health service port')
def refresh(host, port):
    """
    Refresh VPN health status (requires running service).

    Triggers health check on running health service.

    Example:
      vpn-ctl health refresh
      vpn-ctl health refresh --host 10.0.0.5 --port 9000
    """
    import urllib.request
    import json

    url = f"http://{host}:{port}/health/refresh"

    try:
        click.echo(f"📡 Refreshing health on {url}...")
        req = urllib.request.Request(url, method='POST')
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            summary = data.get('summary', {})

            click.secho("✓ Health refreshed!", fg='green')
            click.echo()
            click.echo(f"Healthy:   {summary.get('healthy', 0)}")
            click.echo(f"Degraded:  {summary.get('degraded', 0)}")
            click.echo(f"Unhealthy: {summary.get('unhealthy', 0)}")
            click.echo(f"Missing:   {summary.get('missing', 0)}")

    except urllib.error.URLError as e:
        click.secho(f"❌ Failed to connect to health service at {url}", fg='red')
        click.secho(f"   Make sure: vpn-ctl health start is running", fg='yellow')
        click.secho(f"   Error: {e}", fg='red')
        raise click.Abort()
    except Exception as e:
        click.secho(f"❌ Error: {e}", fg='red')
        raise click.Abort()


@health.command()
def build():
    """
    Build VPN health app Docker image.

    Builds vpn-health:latest container image from Dockerfile.

    Example:
      vpn-ctl health build
    """
    import subprocess
    from pathlib import Path

    click.secho("🐳 Building VPN Health App Docker image", fg='green')
    click.echo()

    # Find Dockerfile
    dockerfile = Path("vpnctl/health/Dockerfile")
    if not dockerfile.exists():
        click.secho(f"❌ Dockerfile not found: {dockerfile}", fg='red')
        raise click.Abort()

    click.echo(f"Dockerfile: {dockerfile}")
    click.echo()

    # Build image
    click.echo("Building Docker image: vpn-health:latest")
    result = subprocess.run(
        ["docker", "build", "-f", str(dockerfile), "-t", "vpn-health:latest", "."],
        text=True
    )

    if result.returncode != 0:
        click.secho(f"❌ Docker build failed", fg='red')
        raise click.Abort()

    click.secho("✓ Docker image built successfully", fg='green')
    click.echo()
    click.echo("Next steps:")
    click.echo("  vpn-ctl health deploy          # Deploy health service")
    click.echo("  docker run vpn-health:latest   # Run container manually")


@health.command()
@click.option('--target', type=click.Choice(['helm', 'docker']), default='helm', help='Deployment target')
@click.option('--namespace', default='vpn-health', help='Kubernetes namespace')
@click.option('--release', default='vpn-health', help='Helm release name')
@click.option('--environment', type=click.Choice(['dev', 'qa', 'prod']), default='dev', help='Environment')
@click.option('--port', type=int, default=8080, help='HTTP port (docker only)')
@click.option('--ecr-registry', default='', help='ECR registry URL (e.g., 123456789.dkr.ecr.us-east-2.amazonaws.com)')
@click.option('--build/--no-build', default=True, help='Build image first')
@click.option('--push/--no-push', default=True, help='Push to ECR (helm only)')
@click.option('--verify/--no-verify', default=True, help='Verify deployment health')
def deploy(target, namespace, release, environment, port, ecr_registry, build, push, verify):
    """
    Deploy VPN health app to Kubernetes or Docker.

    Supports Helm deployment to K8s with full pipeline:
    1. Build Docker image
    2. Push to ECR
    3. Create K8s namespace & ConfigMaps
    4. Create IRSA ServiceAccount
    5. Helm install/upgrade
    6. Verify rollout status

    Example:
      vpn-ctl health deploy --target helm --environment prod
      vpn-ctl health deploy --target docker --port 9000
      vpn-ctl health deploy --target helm --no-push
    """
    import subprocess
    from pathlib import Path
    import os

    click.secho(f"🚀 Deploying VPN Health App ({target})", fg='green')
    click.echo()

    if target == 'helm':
        _deploy_helm(namespace, release, environment, ecr_registry, build, push, verify)
    else:
        _deploy_docker(port, build)


def _deploy_helm(namespace: str, release: str, environment: str, ecr_registry: str, build: bool, push: bool, verify: bool) -> None:
    """Deploy VPN health app to Kubernetes using Helm."""
    import subprocess
    from pathlib import Path
    import os

    click.secho("📋 Helm Deployment Pipeline", fg='cyan')
    click.echo()

    # Step 1: Build Docker image
    if build:
        click.echo("Step 1: Building Docker image...")
        # Use docker buildx to build for amd64 (K8s node architecture)
        result = subprocess.run(
            ["docker", "buildx", "build", "--platform=linux/amd64", "--load", "-f", "vpnctl/health/Dockerfile", "-t", "vpn-health:latest", "."],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            # Fallback to regular docker build
            click.echo("  (Using standard docker build)")
            result = subprocess.run(
                ["docker", "build", "-f", "vpnctl/health/Dockerfile", "-t", "vpn-health:latest", "."],
                capture_output=True,
                text=True
            )
        if result.returncode != 0:
            click.secho(f"❌ Build failed: {result.stderr}", fg='red')
            raise click.Abort()
        click.secho("✓ Image built: vpn-health:latest", fg='green')
        click.echo()

    # Step 2: Push to ECR
    if push:
        click.echo("Step 2: Pushing to ECR...")
        if not ecr_registry:
            # Try to infer from AWS account
            result = subprocess.run(
                ["aws", "sts", "get-caller-identity", "--query", "Account", "--output", "text", "--profile", "default"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                account_id = result.stdout.strip()
                ecr_registry = f"{account_id}.dkr.ecr.us-east-2.amazonaws.com"
            else:
                click.secho("❌ Could not determine ECR registry. Provide --ecr-registry", fg='red')
                raise click.Abort()

        image_uri = f"{ecr_registry}/vpn-health:latest"

        # Login to ECR
        result = subprocess.run(
            ["aws", "ecr", "get-login-password", "--region", "us-east-2", "--profile", "default"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            click.secho(f"❌ ECR login failed: {result.stderr}", fg='red')
            raise click.Abort()

        login_token = result.stdout.strip()
        result = subprocess.run(
            f"echo '{login_token}' | docker login --username AWS --password-stdin {ecr_registry}",
            shell=True,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            click.secho(f"❌ Docker ECR login failed: {result.stderr}", fg='red')
            raise click.Abort()

        # Tag and push
        subprocess.run(["docker", "tag", "vpn-health:latest", image_uri], check=True)
        result = subprocess.run(
            ["docker", "push", image_uri],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            click.secho(f"❌ Push to ECR failed: {result.stderr}", fg='red')
            raise click.Abort()

        click.secho(f"✓ Image pushed: {image_uri}", fg='green')
        click.echo()

    # Step 3: Create K8s namespace
    click.echo(f"Step 3: Creating Kubernetes namespace '{namespace}'...")
    result = subprocess.run(
        ["kubectl", "create", "namespace", namespace, "--dry-run=client", "-o", "yaml"],
        capture_output=True,
        text=True
    )
    if result.returncode == 0:
        subprocess.run(
            ["kubectl", "apply", "-f", "-"],
            input=result.stdout,
            text=True,
            capture_output=True
        )
        click.secho(f"✓ Namespace ready: {namespace}", fg='green')
    click.echo()

    # Step 4: Create ConfigMaps for vpn-peers.yaml and infra-config.json
    click.echo(f"Step 4: Creating ConfigMaps...")
    config_file = "config/vpn-peers.yaml"
    infra_config_file = "infra-config.json"

    if Path(config_file).exists():
        result = subprocess.run(
            ["kubectl", "create", "configmap", "vpn-peers-config", f"--from-file={config_file}",
             "-n", namespace, "--dry-run=client", "-o", "yaml"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            subprocess.run(
                ["kubectl", "apply", "-f", "-"],
                input=result.stdout,
                text=True,
                capture_output=True
            )
            click.secho(f"✓ ConfigMap created: vpn-peers-config", fg='green')

    if Path(infra_config_file).exists():
        result = subprocess.run(
            ["kubectl", "create", "configmap", "vpn-infra-config", f"--from-file={infra_config_file}",
             "-n", namespace, "--dry-run=client", "-o", "yaml"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            subprocess.run(
                ["kubectl", "apply", "-f", "-"],
                input=result.stdout,
                text=True,
                capture_output=True
            )
            click.secho(f"✓ ConfigMap created: vpn-infra-config", fg='green')
    click.echo()

    # Step 5: ServiceAccount will be created by Helm template
    click.echo(f"Step 5: ServiceAccount (managed by Helm)...")
    click.secho(f"✓ Will be created by Helm template", fg='green')
    click.echo()

    # Step 6: Helm install/upgrade
    click.echo(f"Step 6: Running Helm install/upgrade...")
    helm_chart_path = "vpnctl/health/helm/vpn-health"

    if not Path(helm_chart_path).exists():
        click.secho(f"⚠ Helm chart not found: {helm_chart_path}", fg='yellow')
        click.secho("  Creating minimal Helm chart...", fg='cyan')
        _create_helm_chart(helm_chart_path)

    values_file = f"{helm_chart_path}/values/{environment}.yaml"
    if not Path(values_file).exists():
        values_file = f"{helm_chart_path}/values.yaml"

    cmd = [
        "helm", "upgrade", "--install", release, helm_chart_path,
        "-n", namespace,
        "-f", values_file
    ]

    if push and ecr_registry:
        cmd.extend(["--set", f"image.repository={ecr_registry}/vpn-health"])
        cmd.extend(["--set", "image.tag=latest"])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        click.secho(f"❌ Helm install failed: {result.stderr}", fg='red')
        raise click.Abort()

    click.secho(f"✓ Helm install/upgrade complete", fg='green')
    click.echo()

    # Step 7: Verify deployment
    if verify:
        click.echo(f"Step 7: Verifying deployment...")
        result = subprocess.run(
            ["kubectl", "rollout", "status", "deployment/vpn-health", "-n", namespace, "--timeout=300s"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            click.secho(f"✓ Deployment healthy", fg='green')
        else:
            click.secho(f"⚠ Deployment status: {result.stdout}", fg='yellow')
        click.echo()

    # Summary
    click.secho("=" * 80, fg='cyan')
    click.secho("HELM DEPLOYMENT SUMMARY", fg='cyan', bold=True)
    click.secho("=" * 80, fg='cyan')
    click.echo()
    click.echo(f"Release:      {release}")
    click.echo(f"Namespace:    {namespace}")
    click.echo(f"Chart:        vpn-health")
    click.echo(f"Environment:  {environment}")
    if push and ecr_registry:
        click.echo(f"Image:        {ecr_registry}/vpn-health:latest")
    click.echo()
    click.secho("Useful Commands:", fg='cyan', bold=True)
    click.echo(f"  kubectl get pods -n {namespace}")
    click.echo(f"  kubectl logs -n {namespace} -l app=vpn-health -f")
    click.echo(f"  kubectl port-forward -n {namespace} svc/vpn-health 8080:8080")
    click.echo(f"  helm status {release} -n {namespace}")
    click.echo()


def _create_helm_chart(chart_path: str) -> None:
    """Create minimal Helm chart structure."""
    from pathlib import Path
    import yaml

    Path(chart_path).mkdir(parents=True, exist_ok=True)
    Path(f"{chart_path}/templates").mkdir(exist_ok=True)
    Path(f"{chart_path}/values").mkdir(exist_ok=True)

    # Chart.yaml
    chart_yaml = {
        'apiVersion': 'v2',
        'name': 'vpn-health',
        'description': 'VPN Health Monitoring Service',
        'type': 'application',
        'version': '0.1.0',
        'appVersion': '0.1.0'
    }
    with open(f"{chart_path}/Chart.yaml", 'w') as f:
        yaml.dump(chart_yaml, f)

    # values.yaml
    values_yaml = {
        'namespace': 'vpn-health',
        'image': {
            'repository': 'vpn-health',
            'pullPolicy': 'IfNotPresent',
            'tag': 'latest'
        },
        'service': {
            'type': 'ClusterIP',
            'port': 8080
        }
    }
    with open(f"{chart_path}/values.yaml", 'w') as f:
        yaml.dump(values_yaml, f)

    # values/dev.yaml
    with open(f"{chart_path}/values/dev.yaml", 'w') as f:
        yaml.dump({'replicas': 1}, f)

    click.secho(f"✓ Created Helm chart: {chart_path}", fg='green')


def _deploy_docker(port: int, build: bool) -> None:
    """Deploy VPN health app locally with Docker."""
    import subprocess
    from pathlib import Path

    click.secho("🐳 Docker Deployment", fg='cyan')
    click.echo()

    if build:
        click.echo("Building Docker image...")
        result = subprocess.run(
            ["docker", "build", "-f", "vpnctl/health/Dockerfile", "-t", "vpn-health:latest", "."],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            click.secho(f"❌ Build failed: {result.stderr}", fg='red')
            raise click.Abort()
        click.secho("✓ Image built", fg='green')
        click.echo()

    click.echo(f"Deploying to Docker...")
    subprocess.run(["docker", "stop", "vpn-health-app"], capture_output=True)
    subprocess.run(["docker", "rm", "vpn-health-app"], capture_output=True)

    config_path = Path("config").resolve()
    result = subprocess.run([
        "docker", "run",
        "-d",
        "--name", "vpn-health-app",
        "-p", f"{port}:8080",
        "-v", f"{config_path}:/app/config:ro",
        "-e", "AWS_PROFILE=default",
        "-e", "AWS_REGION=us-east-2",
        "-e", "PYTHONUNBUFFERED=1",
        "--restart", "unless-stopped",
        "vpn-health:latest"
    ], capture_output=True, text=True)

    if result.returncode != 0:
        click.secho(f"❌ Deployment failed: {result.stderr}", fg='red')
        raise click.Abort()

    click.secho(f"✓ Deployed to Docker on port {port}", fg='green')
    click.echo()
    click.echo(f"Test: curl http://localhost:{port}/health | jq")


@health.command()
@click.option('--lines', '-n', type=int, default=50, help='Number of lines to show')
def logs(lines):
    """
    View VPN health app logs.

    Shows recent logs from running health service.

    Example:
      vpn-ctl health logs
      vpn-ctl health logs -n 100
    """
    import subprocess

    click.secho("📋 VPN Health App Logs", fg='cyan')
    click.echo()

    # Try docker-compose first
    result = subprocess.run(
        ["docker-compose", "-f", "docker-compose.vpn-health.yml", "logs", "-n", str(lines), "vpn-health"],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        click.echo(result.stdout)
        return

    # Fallback to docker logs
    result = subprocess.run(
        ["docker", "logs", "--tail", str(lines), "vpn-health-app"],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        click.secho("❌ No running health service found", fg='red')
        click.secho("   Start with: vpn-ctl health deploy", fg='yellow')
        raise click.Abort()

    click.echo(result.stdout)
    if result.stderr:
        click.secho(result.stderr, fg='yellow')


@health.command()
def restart():
    """
    Restart VPN health service.

    Restarts the running health service container.

    Example:
      vpn-ctl health restart
    """
    import subprocess

    click.secho("🔄 Restarting VPN Health Service", fg='cyan')
    click.echo()

    # Try docker-compose first
    result = subprocess.run(
        ["docker-compose", "-f", "docker-compose.vpn-health.yml", "restart", "vpn-health"],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        click.secho("✓ Service restarted", fg='green')
        return

    # Fallback to docker
    result = subprocess.run(
        ["docker", "restart", "vpn-health-app"],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        click.secho("❌ Service not running", fg='red')
        click.secho("   Start with: vpn-ctl health deploy", fg='yellow')
        raise click.Abort()

    click.secho("✓ Service restarted", fg='green')


@health.command()
def stop():
    """
    Stop VPN health service.

    Stops the running health service container.

    Example:
      vpn-ctl health stop
    """
    import subprocess

    click.secho("⏹ Stopping VPN Health Service", fg='cyan')
    click.echo()

    # Try docker-compose first
    result = subprocess.run(
        ["docker-compose", "-f", "docker-compose.vpn-health.yml", "down"],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        click.secho("✓ Service stopped", fg='green')
        return

    # Fallback to docker
    result = subprocess.run(
        ["docker", "stop", "vpn-health-app"],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        click.secho("⚠ Service not running", fg='yellow')
        return

    click.secho("✓ Service stopped", fg='green')


@health.command()
def status():
    """
    Show VPN health service status.

    Shows running status, port, and recent health summary.

    Example:
      vpn-ctl health status
    """
    import subprocess
    import json
    import urllib.request

    click.secho("📊 VPN Health Service Status", fg='cyan')
    click.echo()

    # Check if container is running
    result = subprocess.run(
        ["docker", "ps", "-f", "name=vpn-health-app", "-q"],
        capture_output=True,
        text=True
    )

    if not result.stdout.strip():
        click.secho("⚠ Service not running", fg='yellow')
        click.secho("   Start with: vpn-ctl health deploy", fg='yellow')
        return

    click.secho("✓ Service Running", fg='green')
    click.echo()

    # Get container info
    result = subprocess.run(
        ["docker", "inspect", "vpn-health-app"],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        info = json.loads(result.stdout)[0]
        port_map = info['NetworkSettings']['Ports'].get('8080/tcp', [{}])[0]
        host_port = port_map.get('HostPort', '8080')

        click.echo(f"Container:    vpn-health-app")
        click.echo(f"Port:         {host_port}")
        click.echo(f"Status:       {info['State']['Status']}")
        click.echo()

        # Try to get health summary
        try:
            with urllib.request.urlopen(f'http://localhost:{host_port}/health', timeout=5) as response:
                data = json.loads(response.read().decode())
                summary = data.get('summary', {})
                click.secho("Health Summary:", fg='cyan', bold=True)
                click.echo(f"  Total Peers:   {summary.get('total_peers', 0)}")
                click.echo(f"  Healthy:       {summary.get('healthy', 0)}")
                click.echo(f"  Degraded:      {summary.get('degraded', 0)}")
                click.echo(f"  Unhealthy:     {summary.get('unhealthy', 0)}")
                click.echo(f"  Missing:       {summary.get('missing', 0)}")
                click.echo(f"  Last Update:   {summary.get('last_update', 'N/A')}")
        except Exception as e:
            click.secho(f"⚠ Could not reach service: {e}", fg='yellow')


@health.command()
@click.option('--config', type=click.Path(exists=False), help='Path to VPN config file')
def docker_old(config):
    """
    [DEPRECATED] Use 'vpn-ctl health deploy' instead.
    """
    click.secho("⚠ This command is deprecated", fg='yellow')
    click.secho("Use 'vpn-ctl health deploy' instead", fg='cyan')
    raise click.Abort()
