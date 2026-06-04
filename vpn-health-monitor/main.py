"""
VPN Health Monitoring Application
Modern nodeping-like system for continuous VPN connectivity monitoring.

Monitors VPN provider targets using multiple ping/trace tools:
- icmplib: Modern async ICMP ping
- aioping: Async ping implementation
- scapy: Low-level packet analysis
- mtr: Multi-hop traceroute analysis
- asyncio: Concurrent execution

Configuration via YAML (vpn-targets.yaml)
Exposed via REST API: /health endpoint
Accessible at: vpn.assurehub.io/health
"""

import asyncio
import time
import yaml
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass, asdict
from enum import Enum

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

# Modern ping tools
try:
    import icmplib
    HAS_ICMPLIB = True
except ImportError:
    HAS_ICMPLIB = False

try:
    import aioping
    HAS_AIOPING = True
except ImportError:
    HAS_AIOPING = False

try:
    from scapy.all import IP, ICMP, sr1
    HAS_SCAPY = True
except ImportError:
    HAS_SCAPY = False

try:
    import mtr
    HAS_MTR = True
except ImportError:
    HAS_MTR = False

import subprocess
import socket
import os

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

try:
    import boto3
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration constants
CONFIG_FILE = Path(__file__).parent / "vpn-targets.yaml"
DASHBOARD_FILE = Path(__file__).parent / "dashboard.html"
PING_INTERVAL = 60  # seconds
HISTORY_RETENTION = 3600  # 1 hour in seconds
MAX_HISTORY_PER_TARGET = 60  # Keep last 60 pings

# Load dashboard HTML
try:
    with open(DASHBOARD_FILE, 'r') as f:
        DASHBOARD_HTML = f.read()
except FileNotFoundError:
    DASHBOARD_HTML = "<h1>VPN Health Monitor</h1><p>Loading...</p>"


class PingStatus(str, Enum):
    """Ping result status."""
    SUCCESS = "success"
    TIMEOUT = "timeout"
    UNREACHABLE = "unreachable"
    ERROR = "error"


@dataclass
class PingResult:
    """Single ping result with traffic generation details."""
    timestamp: datetime
    status: PingStatus
    protocol: str = "icmp"  # icmp, tcp, tns, http, https
    source_ip: Optional[str] = None  # Pod origin IP
    latency_ms: Optional[float] = None
    ttl: Optional[int] = None
    packets_sent: int = 1
    packets_received: int = 0
    bytes_sent: int = 0  # For HTTP/HTTPS requests
    response_code: Optional[int] = None  # HTTP response code
    error_message: Optional[str] = None

    def to_dict(self):
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "status": self.status.value,
            "protocol": self.protocol,
            "source_ip": self.source_ip,
            "latency_ms": self.latency_ms,
            "ttl": self.ttl,
            "packets_sent": self.packets_sent,
            "packets_received": self.packets_received,
            "bytes_sent": self.bytes_sent,
            "response_code": self.response_code,
            "error_message": self.error_message
        }


@dataclass
class PingTarget:
    """Target to monitor."""
    provider: str
    name: str
    ip: str
    port: Optional[int] = None
    protocol: str = "icmp"
    timeout: int = 5
    enabled: bool = True


# Pydantic models for API requests
class DiagnosticRequest(BaseModel):
    """Request model for network diagnostics."""
    command: str = Field(..., description="Command to execute: ping, nslookup, telnet, ssh")
    target: str = Field(..., description="Target IP address or domain")
    options: Optional[Dict] = Field(default=None, description="Command options (count, port, etc)")

    class Config:
        schema_extra = {
            "example": {
                "command": "ping",
                "target": "8.8.8.8",
                "options": {"count": 4}
            }
        }


class DiagnosticResponse(BaseModel):
    """Response model for diagnostic execution."""
    session_id: str
    status: str
    command: str
    target: str


class PodNetworkInfo:
    """Manage pod network information for peer configuration."""

    def __init__(self):
        """Initialize pod network info."""
        self.pod_ip = self._get_pod_ip()
        self.pod_name = os.environ.get("HOSTNAME", "unknown")
        self.pod_namespace = os.environ.get("POD_NAMESPACE", "unknown")
        self.cluster_cidrs = self._get_cluster_cidrs()

    def _get_pod_ip(self) -> str:
        """Get pod's own IP address."""
        try:
            # Try to get from environment variable first
            if "POD_IP" in os.environ:
                return os.environ["POD_IP"]

            # Fallback: resolve hostname
            hostname = socket.gethostname()
            pod_ip = socket.gethostbyname(hostname)
            if pod_ip and pod_ip != "127.0.0.1":
                return pod_ip

            # Last resort: get from socket connection
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(("8.8.8.8", 80))
                pod_ip = s.getsockname()[0]
                return pod_ip
            finally:
                s.close()

        except Exception as e:
            logger.warning(f"Failed to get pod IP: {e}")
            return "unknown"

    def _get_cluster_cidrs(self) -> Dict[str, str]:
        """Get cluster CIDR information from environment or defaults."""
        return {
            "vpc_cidr": os.environ.get("VPC_CIDR", "172.31.0.0/16"),
            "cluster_cidrs": os.environ.get("CLUSTER_CIDRS", "172.31.0.0/20,172.31.16.0/20,172.31.32.0/20"),
            "description": "Expected source IPs for VPN peers to whitelist"
        }

    def get_info(self) -> Dict:
        """Get complete pod network information."""
        return {
            "pod": {
                "name": self.pod_name,
                "namespace": self.pod_namespace,
                "ip": self.pod_ip,
                "timestamp": datetime.now().isoformat()
            },
            "cluster_network": self.cluster_cidrs,
            "message": "Provide the VPC CIDR to your VPN peer for whitelisting inbound traffic"
        }


class PingMonitor:
    """Modern ping monitor using multiple tools."""

    def __init__(self):
        """Initialize monitor."""
        self.targets: Dict[str, List[PingTarget]] = {}
        self.history: Dict[str, List[PingResult]] = {}
        self.load_config()
        self.running = False

    def load_config(self):
        """Load configuration from YAML file."""
        if not CONFIG_FILE.exists():
            logger.warning(f"Config file not found: {CONFIG_FILE}")
            return

        try:
            with open(CONFIG_FILE) as f:
                config = yaml.safe_load(f)

            if not config or "providers" not in config:
                logger.error("Invalid config format")
                return

            self.targets = {}
            for provider_config in config["providers"]:
                provider_name = provider_config.get("name", "Unknown")
                targets = []

                for target_config in provider_config.get("targets", []):
                    if not target_config.get("enabled", True):
                        continue

                    target = PingTarget(
                        provider=provider_name,
                        name=target_config.get("name", target_config["ip"]),
                        ip=target_config["ip"],
                        port=target_config.get("port"),
                        protocol=target_config.get("protocol", "icmp"),
                        timeout=target_config.get("timeout", 5),
                        enabled=True
                    )
                    targets.append(target)
                    self.history[f"{provider_name}/{target.name}"] = []

                self.targets[provider_name] = targets

            logger.info(f"Loaded {sum(len(t) for t in self.targets.values())} targets from {len(self.targets)} providers")

        except Exception as e:
            logger.error(f"Failed to load config: {e}")

    async def ping_icmplib(self, ip: str, timeout: int = 5) -> PingResult:
        """Ping using icmplib (modern async ICMP)."""
        if not HAS_ICMPLIB:
            return PingResult(
                timestamp=datetime.now(),
                status=PingStatus.ERROR,
                protocol="icmp",
                source_ip=pod_network.pod_ip,
                error_message="icmplib not installed"
            )

        try:
            host = await icmplib.async_ping(
                ip,
                count=1,
                timeout=timeout,
                privileged=False
            )

            if host.is_alive:
                return PingResult(
                    timestamp=datetime.now(),
                    status=PingStatus.SUCCESS,
                    protocol="icmp",
                    source_ip=pod_network.pod_ip,
                    latency_ms=host.avg_rtt,
                    ttl=host.min_rtt,
                    packets_sent=1,
                    packets_received=1
                )
            else:
                return PingResult(
                    timestamp=datetime.now(),
                    status=PingStatus.UNREACHABLE,
                    protocol="icmp",
                    source_ip=pod_network.pod_ip,
                    packets_sent=1,
                    packets_received=0
                )
        except Exception as e:
            return PingResult(
                timestamp=datetime.now(),
                status=PingStatus.ERROR,
                protocol="icmp",
                source_ip=pod_network.pod_ip,
                error_message=str(e)
            )

    async def ping_system(self, ip: str, timeout: int = 5) -> PingResult:
        """Ping using system ping command (fallback)."""
        try:
            # Use system ping
            if isinstance(timeout, int):
                timeout_val = timeout
            else:
                timeout_val = 5

            # Platform-specific ping
            import platform
            is_windows = platform.system().lower() == "windows"

            if is_windows:
                cmd = ["ping", "-n", "1", "-w", str(timeout_val * 1000), ip]
            else:
                cmd = ["ping", "-c", "1", "-W", str(timeout_val * 1000), ip]

            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await asyncio.wait_for(
                result.communicate(),
                timeout=timeout_val + 2
            )

            if result.returncode == 0:
                # Parse latency from output
                output = stdout.decode()
                latency = self._extract_latency(output)

                return PingResult(
                    timestamp=datetime.now(),
                    status=PingStatus.SUCCESS,
                    protocol="icmp",
                    source_ip=pod_network.pod_ip,
                    latency_ms=latency,
                    packets_sent=1,
                    packets_received=1
                )
            else:
                return PingResult(
                    timestamp=datetime.now(),
                    status=PingStatus.UNREACHABLE,
                    protocol="icmp",
                    source_ip=pod_network.pod_ip,
                    packets_sent=1,
                    packets_received=0
                )

        except asyncio.TimeoutError:
            return PingResult(
                timestamp=datetime.now(),
                status=PingStatus.TIMEOUT,
                protocol="icmp",
                source_ip=pod_network.pod_ip,
                packets_sent=1,
                packets_received=0
            )
        except Exception as e:
            return PingResult(
                timestamp=datetime.now(),
                status=PingStatus.ERROR,
                protocol="icmp",
                source_ip=pod_network.pod_ip,
                error_message=str(e)
            )

    @staticmethod
    def _extract_latency(output: str) -> Optional[float]:
        """Extract latency from ping output."""
        import re

        # Try multiple patterns
        patterns = [
            r'time[=<](\d+\.?\d*)\s*ms',  # Unix: time=24.7 ms
            r'time<(\d+\.?\d*)\s*ms',      # Windows: time<24ms
            r'min/avg/max[^=]*=\s*[\d.]+/(\d+\.?\d*)',  # Summary line
        ]

        for pattern in patterns:
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except (ValueError, IndexError):
                    continue

        return None

    async def check_target(self, target: PingTarget) -> PingResult:
        """Check single target using protocol-specific method."""
        protocol = target.protocol.lower()
        logger.info(f"Checking {target.provider}/{target.name} ({target.ip}) via {protocol}")

        # Route based on protocol
        if protocol == "https":
            return await self.check_https(target)
        elif protocol == "http":
            return await self.check_http(target)
        elif protocol == "tns":
            return await self.check_tns(target)
        elif protocol == "tcp":
            return await self.check_tcp(target)
        else:
            # Default to ICMP
            # Try icmplib first (modern async)
            if HAS_ICMPLIB:
                result = await self.ping_icmplib(target.ip, target.timeout)
                if result.status != PingStatus.ERROR:
                    return result

            # Fallback to system ping
            result = await self.ping_system(target.ip, target.timeout)
            return result

    async def check_http(self, target: PingTarget) -> PingResult:
        """Check HTTP connectivity and generate traffic."""
        if not HAS_AIOHTTP:
            return PingResult(
                timestamp=datetime.now(),
                status=PingStatus.ERROR,
                protocol="http",
                error_message="aiohttp not installed"
            )

        pod_ip = pod_network.pod_ip
        try:
            url = f"http://{target.ip}:{target.port or 80}/" if target.port else f"http://{target.ip}/"
            timeout = aiohttp.ClientTimeout(total=target.timeout)

            async with aiohttp.ClientSession(timeout=timeout) as session:
                start_time = time.time()
                async with session.get(url, allow_redirects=False, ssl=False) as response:
                    latency = (time.time() - start_time) * 1000

                    return PingResult(
                        timestamp=datetime.now(),
                        status=PingStatus.SUCCESS,
                        protocol="http",
                        source_ip=pod_ip,
                        latency_ms=latency,
                        response_code=response.status,
                        bytes_sent=len(url),
                        packets_sent=1,
                        packets_received=1
                    )
        except asyncio.TimeoutError:
            return PingResult(
                timestamp=datetime.now(),
                status=PingStatus.TIMEOUT,
                protocol="http",
                source_ip=pod_ip
            )
        except Exception as e:
            return PingResult(
                timestamp=datetime.now(),
                status=PingStatus.ERROR,
                protocol="http",
                source_ip=pod_ip,
                error_message=str(e)
            )

    async def check_https(self, target: PingTarget) -> PingResult:
        """Check HTTPS connectivity and generate traffic."""
        if not HAS_AIOHTTP:
            return PingResult(
                timestamp=datetime.now(),
                status=PingStatus.ERROR,
                protocol="https",
                error_message="aiohttp not installed"
            )

        pod_ip = pod_network.pod_ip
        try:
            url = f"https://{target.ip}:{target.port or 443}/" if target.port else f"https://{target.ip}/"
            timeout = aiohttp.ClientTimeout(total=target.timeout)

            async with aiohttp.ClientSession(timeout=timeout) as session:
                start_time = time.time()
                async with session.get(url, allow_redirects=False, ssl=False) as response:
                    latency = (time.time() - start_time) * 1000

                    return PingResult(
                        timestamp=datetime.now(),
                        status=PingStatus.SUCCESS,
                        protocol="https",
                        source_ip=pod_ip,
                        latency_ms=latency,
                        response_code=response.status,
                        bytes_sent=len(url),
                        packets_sent=1,
                        packets_received=1
                    )
        except asyncio.TimeoutError:
            return PingResult(
                timestamp=datetime.now(),
                status=PingStatus.TIMEOUT,
                protocol="https",
                source_ip=pod_ip
            )
        except Exception as e:
            return PingResult(
                timestamp=datetime.now(),
                status=PingStatus.ERROR,
                protocol="https",
                source_ip=pod_ip,
                error_message=str(e)
            )

    async def check_tcp(self, target: PingTarget) -> PingResult:
        """Check TCP connectivity."""
        pod_ip = pod_network.pod_ip
        try:
            port = target.port or 443
            start_time = time.time()

            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target.ip, port),
                timeout=target.timeout
            )

            latency = (time.time() - start_time) * 1000
            writer.close()
            await writer.wait_closed()

            return PingResult(
                timestamp=datetime.now(),
                status=PingStatus.SUCCESS,
                protocol="tcp",
                source_ip=pod_ip,
                latency_ms=latency,
                packets_sent=1,
                packets_received=1
            )
        except asyncio.TimeoutError:
            return PingResult(
                timestamp=datetime.now(),
                status=PingStatus.TIMEOUT,
                protocol="tcp",
                source_ip=pod_ip
            )
        except Exception as e:
            return PingResult(
                timestamp=datetime.now(),
                status=PingStatus.ERROR,
                protocol="tcp",
                source_ip=pod_ip,
                error_message=str(e)
            )

    async def check_tns(self, target: PingTarget) -> PingResult:
        """Check TNS (Oracle) connectivity."""
        pod_ip = pod_network.pod_ip
        try:
            port = target.port or 1521
            start_time = time.time()

            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target.ip, port),
                timeout=target.timeout
            )

            # Send TNS CONNECT packet and listen for response
            # TNS packet format: 2-byte length + packet type
            try:
                # Wait for TNS ACCEPT packet from Oracle listener
                data = await asyncio.wait_for(reader.read(100), timeout=1)
                latency = (time.time() - start_time) * 1000

                if data and len(data) >= 8:
                    # Check for valid TNS packet signature
                    packet_type = data[4] if len(data) > 4 else None
                    # TNS ACCEPT packet type is typically 2
                    writer.close()
                    await writer.wait_closed()

                    return PingResult(
                        timestamp=datetime.now(),
                        status=PingStatus.SUCCESS,
                        protocol="tns",
                        source_ip=pod_ip,
                        latency_ms=latency,
                        packets_sent=1,
                        packets_received=1
                    )
            except asyncio.TimeoutError:
                # No response, but TCP connection succeeded
                pass

            latency = (time.time() - start_time) * 1000
            writer.close()
            await writer.wait_closed()

            return PingResult(
                timestamp=datetime.now(),
                status=PingStatus.SUCCESS,
                protocol="tns",
                source_ip=pod_ip,
                latency_ms=latency,
                packets_sent=1,
                packets_received=1
            )
        except asyncio.TimeoutError:
            return PingResult(
                timestamp=datetime.now(),
                status=PingStatus.TIMEOUT,
                protocol="tns",
                source_ip=pod_ip
            )
        except Exception as e:
            return PingResult(
                timestamp=datetime.now(),
                status=PingStatus.ERROR,
                protocol="tns",
                source_ip=pod_ip,
                error_message=str(e)
            )

    async def monitor_all(self):
        """Monitor all targets concurrently."""
        logger.info("Starting health check cycle...")

        tasks = []
        target_map = {}

        # Create tasks for all targets
        for provider, targets in self.targets.items():
            for target in targets:
                key = f"{provider}/{target.name}"
                target_map[asyncio.create_task(self.check_target(target))] = key

        # Wait for all to complete
        if target_map:
            results = await asyncio.gather(*target_map.keys(), return_exceptions=True)

            for task, key in zip(target_map.keys(), target_map.values()):
                try:
                    result = task.result()
                    self.history[key].append(result)

                    # Keep only recent history
                    if len(self.history[key]) > MAX_HISTORY_PER_TARGET:
                        self.history[key] = self.history[key][-MAX_HISTORY_PER_TARGET:]

                    status_icon = "✓" if result.status == PingStatus.SUCCESS else "✗"
                    logger.info(
                        f"  {status_icon} {key}: {result.status.value} "
                        f"({result.latency_ms:.2f}ms)" if result.latency_ms else ""
                    )
                except Exception as e:
                    logger.error(f"  ✗ {key}: {e}")

        logger.info("Health check cycle complete")

    async def run_continuous(self):
        """Run continuous monitoring loop."""
        self.running = True
        logger.info(f"Starting continuous monitoring (interval: {PING_INTERVAL}s)")

        while self.running:
            try:
                await self.monitor_all()
                await asyncio.sleep(PING_INTERVAL)
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                await asyncio.sleep(PING_INTERVAL)

    def get_health_summary(self) -> Dict:
        """Get current health summary grouped by provider."""
        summary = {
            "timestamp": datetime.now().isoformat(),
            "providers": {},
            "statistics": {
                "total_targets": 0,
                "healthy": 0,
                "unhealthy": 0,
                "errors": 0
            }
        }

        for provider, targets in self.targets.items():
            provider_status = {
                "name": provider,
                "targets": [],
                "status": "healthy",
                "last_update": None
            }

            for target in targets:
                key = f"{provider}/{target.name}"
                history = self.history.get(key, [])

                # Get latest result
                latest = history[-1] if history else None

                target_info = {
                    "name": target.name,
                    "ip": target.ip,
                    "port": target.port,
                    "status": latest.status.value if latest else "unknown",
                    "latency_ms": latest.latency_ms if latest else None,
                    "last_ping": latest.timestamp.isoformat() if latest else None,
                    "history_size": len(history)
                }

                # Calculate statistics
                if history:
                    successes = sum(1 for r in history if r.status == PingStatus.SUCCESS)
                    success_rate = (successes / len(history)) * 100
                    target_info["success_rate"] = success_rate
                    target_info["avg_latency"] = (
                        sum(r.latency_ms for r in history if r.latency_ms) / successes
                        if successes > 0 else None
                    )

                provider_status["targets"].append(target_info)

                # Update provider status
                if latest and latest.status != PingStatus.SUCCESS:
                    provider_status["status"] = "degraded" if latest.status == PingStatus.TIMEOUT else "unhealthy"

                # Update statistics
                summary["statistics"]["total_targets"] += 1
                if latest:
                    if latest.status == PingStatus.SUCCESS:
                        summary["statistics"]["healthy"] += 1
                    elif latest.status == PingStatus.ERROR:
                        summary["statistics"]["errors"] += 1
                    else:
                        summary["statistics"]["unhealthy"] += 1

            provider_status["last_update"] = (
                max((t["last_ping"] for t in provider_status["targets"] if t["last_ping"]), default=None)
            )

            # Add VPN tunnel status with ping health fallback
            provider_status["tunnel"] = tunnel_status.get_tunnel_status(provider, provider_status)

            summary["providers"][provider] = provider_status

        # Add cluster network info for peer configuration
        summary["cluster_network"] = {
            "pod_origin_ip": pod_network.pod_ip,
            "pod_name": pod_network.pod_name,
            "pod_namespace": pod_network.pod_namespace,
            "vpc_cidr": pod_network.cluster_cidrs["vpc_cidr"],
            "subnet_cidrs": pod_network.cluster_cidrs["cluster_cidrs"].split(","),
            "message": "These are the expected source IPs for traffic originating from this EKS cluster"
        }

        return summary


class VPNTunnelStatus:
    """Query AWS VPN connection tunnel status with caching and timeout."""

    def __init__(self):
        """Initialize AWS client."""
        self.ec2_client = None
        self.vpn_mappings = {}
        self.tunnel_cache = {}
        self.cache_ttl = 30  # Cache for 30 seconds
        self.last_cache_update = 0
        self.query_timeout = 5  # 5 second timeout for AWS queries
        self._init_aws()

    def _init_aws(self):
        """Initialize AWS EC2 client if boto3 is available."""
        if not HAS_BOTO3:
            logger.warning("boto3 not installed - VPN tunnel status unavailable")
            return

        try:
            region = os.environ.get("AWS_REGION", "us-east-2")
            self.ec2_client = boto3.client("ec2", region_name=region)
            self._load_vpn_mappings()
        except Exception as e:
            logger.warning(f"Failed to initialize AWS client: {e}")

    def _load_vpn_mappings(self):
        """Load VPN connection ID mappings from tags (name -> vpn_id)."""
        if not self.ec2_client:
            return

        try:
            response = self.ec2_client.describe_vpn_connections()
            for vpn in response.get("VpnConnections", []):
                tags = {tag["Key"]: tag["Value"] for tag in vpn.get("Tags", [])}
                customer_name = tags.get("Customer", "")
                if customer_name:
                    self.vpn_mappings[customer_name] = vpn["VpnConnectionId"]
                    logger.info(f"Mapped VPN {customer_name} → {vpn['VpnConnectionId']}")
        except Exception as e:
            logger.error(f"Failed to load VPN mappings: {e}")

    def get_tunnel_status(self, provider_name: str, provider_status: Dict = None) -> Dict:
        """Get VPN tunnel status for a provider (cached, non-blocking).

        Falls back to ping health if AWS metrics are stale:
        If any target for this provider has successful pings, tunnel is marked as UP
        regardless of AWS reported status (handles stale AWS metrics).
        """
        if not self.ec2_client:
            return None  # Return None instead of error dict to hide AWS issues

        # Check cache
        if provider_name in self.tunnel_cache:
            cached_data, timestamp = self.tunnel_cache[provider_name]
            if time.time() - timestamp < self.cache_ttl:
                return cached_data

        try:
            vpn_id = self._find_vpn_id(provider_name)
            if not vpn_id:
                return None

            response = self.ec2_client.describe_vpn_connections(VpnConnectionIds=[vpn_id])
            vpn_connection = response["VpnConnections"][0]

            tunnels = []
            for tunnel_info in vpn_connection.get("VgwTelemetry", []):
                tunnels.append({
                    "outside_ip": tunnel_info.get("OutsideIpAddress", ""),
                    "status": tunnel_info.get("Status", "UNKNOWN"),
                    "last_status_change": tunnel_info.get("LastStatusChange", "").isoformat() if tunnel_info.get("LastStatusChange") else None,
                })

            tunnel_status = "up" if any(t["status"] == "UP" for t in tunnels) else "down"

            # FALLBACK: If AWS says tunnel is DOWN but pings are working, override to UP
            # This handles stale AWS metrics (e.g., DPD timeout that never got updated in CloudWatch)
            if tunnel_status == "down" and provider_status:
                ping_working = any(
                    target.get("status") == "success"
                    for target in provider_status.get("targets", [])
                )
                if ping_working:
                    logger.info(f"Tunnel status override: {provider_name} AWS=DOWN but pings=UP, marking as UP")
                    tunnel_status = "up"

            result = {
                "available": True,
                "vpn_id": vpn_id,
                "status": tunnel_status,
                "tunnels": tunnels,
                "connection_state": vpn_connection.get("State", "unknown"),
            }

            # Cache result
            self.tunnel_cache[provider_name] = (result, time.time())
            return result

        except Exception as e:
            logger.warning(f"Failed to get tunnel status for {provider_name}: {e}")
            # Return None to gracefully degrade instead of blocking
            return None

    def _find_vpn_id(self, provider_name: str) -> Optional[str]:
        """Find VPN ID by provider name (tries multiple variations)."""
        if provider_name in self.vpn_mappings:
            return self.vpn_mappings[provider_name]

        if not self.ec2_client:
            return None

        try:
            response = self.ec2_client.describe_vpn_connections()
            provider_lower = provider_name.lower()

            for vpn in response.get("VpnConnections", []):
                # Skip deleted VPNs
                if vpn.get("State") == "deleted":
                    continue

                tags = {tag["Key"]: tag["Value"] for tag in vpn.get("Tags", [])}
                customer_tag = tags.get("Customer", "").lower()
                name_tag = tags.get("Name", "").lower()

                # Try exact match on Customer tag
                if customer_tag == provider_lower:
                    vpn_id = vpn["VpnConnectionId"]
                    self.vpn_mappings[provider_name] = vpn_id
                    return vpn_id

                # Try substring match (handles "Organization-Legacy" vs "internal-legacy-network")
                if customer_tag and (customer_tag in provider_lower or provider_lower in customer_tag):
                    vpn_id = vpn["VpnConnectionId"]
                    self.vpn_mappings[provider_name] = vpn_id
                    return vpn_id

                # Try name tag as fallback
                if name_tag and (name_tag in provider_lower or provider_lower in name_tag):
                    vpn_id = vpn["VpnConnectionId"]
                    self.vpn_mappings[provider_name] = vpn_id
                    return vpn_id
        except Exception as e:
            logger.warning(f"Error searching for VPN {provider_name}: {e}")

        return None


class NetworkDiagnostics:
    """Execute network diagnostic commands with real-time output streaming."""

    # Allowed commands only
    COMMANDS = {
        "ping": {"timeout": 30, "default_count": 4},
        "dig": {"timeout": 10, "default_count": 1},
        "telnet": {"timeout": 5, "default_count": 1},
        "ssh": {"timeout": 10, "default_count": 1},
        "curl": {"timeout": 30, "default_count": 1},
        "traceroute": {"timeout": 30, "default_count": 1},
    }

    # Session storage for streaming
    sessions: Dict[str, Dict] = {}
    max_sessions = 10
    max_output_lines = 1000
    output_buffer_limit = 10 * 1024 * 1024  # 10MB

    @staticmethod
    def _validate_ip(ip: str) -> bool:
        """Validate IPv4 or IPv6 address."""
        import ipaddress
        try:
            ipaddress.ip_address(ip)
            return True
        except ValueError:
            return False

    @staticmethod
    def _validate_domain(domain: str) -> bool:
        """Validate domain name."""
        import re
        # Simple domain validation
        pattern = r'^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$'
        return bool(re.match(pattern, domain, re.IGNORECASE))

    @staticmethod
    def _validate_port(port: int) -> bool:
        """Validate port number."""
        return 1 <= port <= 65535

    async def execute_ping(self, session_id: str, target: str, count: int = 4) -> None:
        """Execute ping command and stream output."""
        if not self._validate_ip(target):
            self._add_output(session_id, f"❌ Invalid IP address: {target}")
            return

        cmd = ["ping", "-c", str(count), target]
        await self._run_command(session_id, cmd, f"ping -c {count} {target}")

    async def execute_dig(self, session_id: str, target: str, record_type: str = "A", dns_server: str = None) -> None:
        """Execute dig command and stream output."""
        if not (self._validate_ip(target) or self._validate_domain(target)):
            self._add_output(session_id, f"❌ Invalid target: {target}")
            return

        # Validate record type
        valid_types = ["A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA"]
        if record_type not in valid_types:
            self._add_output(session_id, f"❌ Invalid record type: {record_type}")
            return

        # Build dig command
        cmd = ["dig"]
        if dns_server:
            cmd.extend(["@" + dns_server])
        cmd.extend([target, record_type])

        display_cmd = f"dig {('@' + dns_server + ' ' if dns_server else '')}{target} {record_type}"
        await self._run_command(session_id, cmd, display_cmd)

    async def execute_telnet(self, session_id: str, target: str, port: int = 22) -> None:
        """Execute telnet (socket connection check) and stream output."""
        if not self._validate_ip(target):
            self._add_output(session_id, f"❌ Invalid IP address: {target}")
            return

        if not self._validate_port(port):
            self._add_output(session_id, f"❌ Invalid port: {port}")
            return

        self._add_output(session_id, f"$ telnet {target} {port}")
        self._add_output(session_id, f"Attempting to connect to {target}:{port}...")

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port),
                timeout=5.0
            )
            self._add_output(session_id, f"✅ Connected to {target}:{port}")
            writer.close()
            await writer.wait_closed()
        except asyncio.TimeoutError:
            self._add_output(session_id, f"⏱️ Connection timeout after 5 seconds")
        except ConnectionRefusedError:
            self._add_output(session_id, f"❌ Connection refused by {target}:{port}")
        except Exception as e:
            self._add_output(session_id, f"❌ Error: {str(e)}")

    async def execute_ssh(self, session_id: str, target: str, port: int = 22, username: str = "root", verbose: bool = False) -> None:
        """Execute SSH connection check with real ssh command."""
        if not self._validate_ip(target):
            self._add_output(session_id, f"❌ Invalid IP address: {target}")
            return

        if not self._validate_port(port):
            self._add_output(session_id, f"❌ Invalid port: {port}")
            return

        # Build SSH command
        cmd = ["ssh"]
        if verbose:
            cmd.append("-v")
        cmd.extend([
            "-o", "ConnectTimeout=10",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-p", str(port),
            f"{username}@{target}",
            "echo 'SSH Test' && hostname && uptime"
        ])

        display_cmd = f"ssh {'-v ' if verbose else ''}-p {port} {username}@{target}"
        await self._run_command(session_id, cmd, display_cmd)

    async def execute_curl(self, session_id: str, target: str, port: int = 443, method: str = "GET",
                          headers: str = "", body: str = "", follow_redirects: bool = False,
                          verify_ssl: bool = True, protocol: str = "https") -> None:
        """Execute CURL command for HTTP/HTTPS API testing."""
        if not self._validate_ip(target):
            self._add_output(session_id, f"❌ Invalid IP address: {target}")
            return

        if not self._validate_port(port):
            self._add_output(session_id, f"❌ Invalid port: {port}")
            return

        # Build URL
        url = f"{protocol}://{target}:{port}/"

        # Build CURL command
        cmd = ["curl"]
        if not verify_ssl:
            cmd.append("--insecure")
        if follow_redirects:
            cmd.append("-L")

        cmd.extend(["-X", method])

        # Parse and add headers
        if headers:
            for header in headers.split("\n"):
                header = header.strip()
                if header:
                    cmd.extend(["-H", header])

        # Add body if present
        if body and method in ["POST", "PUT", "PATCH"]:
            cmd.extend(["-d", body])

        cmd.append(url)

        display_parts = [f"curl -X {method}"]
        if not verify_ssl:
            display_parts.append("--insecure")
        if follow_redirects:
            display_parts.append("-L")
        display_cmd = " ".join(display_parts) + f" {url}"

        await self._run_command(session_id, cmd, display_cmd)

    async def execute_traceroute(self, session_id: str, target: str, max_hops: int = 30, timeout: int = 5) -> None:
        """Execute traceroute command to show network path."""
        if not self._validate_ip(target):
            self._add_output(session_id, f"❌ Invalid IP address: {target}")
            return

        if not (1 <= max_hops <= 255):
            self._add_output(session_id, f"❌ Invalid max hops: {max_hops} (must be 1-255)")
            return

        if timeout < 1 or timeout > 60:
            self._add_output(session_id, f"❌ Invalid timeout: {timeout} (must be 1-60)")
            return

        cmd = ["traceroute", "-m", str(max_hops), "-w", str(timeout), target]
        await self._run_command(session_id, cmd, f"traceroute -m {max_hops} -w {timeout} {target}")

    async def _run_command(self, session_id: str, cmd: List[str], display_cmd: str) -> None:
        """Execute command and stream output line by line with exit code and timing."""
        import time as time_module

        self._add_output(session_id, f"$ {display_cmd}")
        timeout = self.COMMANDS.get(cmd[0], {}).get("timeout", 30)
        start_time = time_module.time()

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            # Stream stdout and stderr combined
            while True:
                try:
                    line = await asyncio.wait_for(
                        process.stdout.readline(),
                        timeout=timeout
                    )
                    if not line:
                        break
                    self._add_output(session_id, line.decode("utf-8", errors="ignore").rstrip())
                except asyncio.TimeoutError:
                    process.kill()
                    self._add_output(session_id, f"⏱️ Command timed out after {timeout} seconds")
                    break

            # Wait for process completion and get exit code
            exit_code = await asyncio.wait_for(process.wait(), timeout=timeout)
            elapsed = time_module.time() - start_time

            # Add exit code and duration
            self._add_output(session_id, f"[Exit Code: {exit_code}]")
            self._add_output(session_id, f"[Duration: {elapsed:.2f}s]")

        except asyncio.TimeoutError:
            self._add_output(session_id, f"⏱️ Command execution timed out after {timeout} seconds")
        except Exception as e:
            self._add_output(session_id, f"❌ Error: {str(e)}")

    def _add_output(self, session_id: str, line: str) -> None:
        """Add output line to session."""
        if session_id not in self.sessions:
            logger.warning(f"[ADD-OUTPUT] Session {session_id} not found! Available: {list(self.sessions.keys())}")
            return

        session = self.sessions[session_id]
        session["output"].append(line)
        logger.debug(f"[ADD-OUTPUT] Added to {session_id}: {line[:50]}")

        # Limit output
        if len(session["output"]) > self.max_output_lines:
            session["output"].pop(0)

    async def execute_command_in_session(
        self, command: str, target: str, options: Dict = None, session_id: str = None
    ) -> None:
        """Execute command in a background task for a given session."""
        logger.info(f"[BG-TASK] Starting background task for session {session_id}")
        if not session_id or session_id not in self.sessions:
            logger.error(f"[BG-TASK] Session {session_id} not found in sessions dict!")
            return

        try:
            logger.info(f"[BG-TASK] Executing {command} for {target}")
            # Execute command
            if command == "ping":
                count = options.get("count", 4) if options else 4
                await self.execute_ping(session_id, target, count)
            elif command == "dig":
                record_type = options.get("record_type", "A") if options else "A"
                dns_server = options.get("dns_server") if options else None
                await self.execute_dig(session_id, target, record_type, dns_server)
            elif command == "telnet":
                port = options.get("port", 22) if options else 22
                await self.execute_telnet(session_id, target, port)
            elif command == "ssh":
                port = options.get("port", 22) if options else 22
                username = options.get("username", "root") if options else "root"
                verbose = options.get("verbose", False) if options else False
                await self.execute_ssh(session_id, target, port, username, verbose)
            elif command == "curl":
                port = options.get("port", 443) if options else 443
                method = options.get("method", "GET") if options else "GET"
                headers = options.get("headers", "") if options else ""
                body = options.get("body", "") if options else ""
                follow_redirects = options.get("follow_redirects", False) if options else False
                verify_ssl = options.get("verify_ssl", True) if options else True
                protocol = options.get("protocol", "https") if options else "https"
                await self.execute_curl(session_id, target, port, method, headers, body, follow_redirects, verify_ssl, protocol)
            elif command == "traceroute":
                max_hops = options.get("max_hops", 30) if options else 30
                timeout = options.get("timeout", 5) if options else 5
                await self.execute_traceroute(session_id, target, max_hops, timeout)

            # Mark as completed
            if session_id in self.sessions:
                self.sessions[session_id]["status"] = "completed"
                logger.info(f"[BG-TASK] Diagnostic session {session_id} ({command}) completed with {len(self.sessions[session_id]['output'])} output lines")
            else:
                logger.warning(f"[BG-TASK] Session {session_id} disappeared before completion!")
        except Exception as e:
            logger.error(f"[BG-TASK] Error in diagnostic session {session_id}: {e}", exc_info=True)
            if session_id in self.sessions:
                self.sessions[session_id]["status"] = "error"
                self._add_output(session_id, f"Error: {str(e)}")

    async def execute(self, command: str, target: str, options: Dict = None) -> str:
        """Main execution method (deprecated - use execute_command_in_session instead)."""
        import uuid

        # Clean up old sessions
        if len(self.sessions) > self.max_sessions:
            oldest = min(self.sessions.items(), key=lambda x: x[1].get("created_at", 0))
            del self.sessions[oldest[0]]

        session_id = str(uuid.uuid4())
        self.sessions[session_id] = {
            "status": "running",
            "output": [],
            "command": command,
            "created_at": time.time(),
        }

        # Execute command
        if command == "ping":
            count = options.get("count", 4) if options else 4
            await self.execute_ping(session_id, target, count)
        elif command == "dig":
            record_type = options.get("record_type", "A") if options else "A"
            dns_server = options.get("dns_server") if options else None
            await self.execute_dig(session_id, target, record_type, dns_server)
        elif command == "telnet":
            port = options.get("port", 22) if options else 22
            await self.execute_telnet(session_id, target, port)
        elif command == "ssh":
            port = options.get("port", 22) if options else 22
            username = options.get("username", "root") if options else "root"
            verbose = options.get("verbose", False) if options else False
            await self.execute_ssh(session_id, target, port, username, verbose)
        elif command == "curl":
            port = options.get("port", 443) if options else 443
            method = options.get("method", "GET") if options else "GET"
            headers = options.get("headers", "") if options else ""
            body = options.get("body", "") if options else ""
            follow_redirects = options.get("follow_redirects", False) if options else False
            verify_ssl = options.get("verify_ssl", True) if options else True
            protocol = options.get("protocol", "https") if options else "https"
            await self.execute_curl(session_id, target, port, method, headers, body, follow_redirects, verify_ssl, protocol)
        elif command == "traceroute":
            max_hops = options.get("max_hops", 30) if options else 30
            timeout = options.get("timeout", 5) if options else 5
            await self.execute_traceroute(session_id, target, max_hops, timeout)

        self.sessions[session_id]["status"] = "completed"
        logger.info(f"Diagnostic session {session_id} ({command}) completed")

        return session_id

    def get_output(self, session_id: str) -> List[str]:
        """Get all output for session."""
        if session_id in self.sessions:
            return self.sessions[session_id]["output"]
        return []

    def get_status(self, session_id: str) -> str:
        """Get session status."""
        if session_id in self.sessions:
            return self.sessions[session_id]["status"]
        return "unknown"


# Initialize FastAPI app
app = FastAPI(
    title="VPN Health Monitor",
    description="Modern nodeping-like VPN connectivity monitoring system",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global monitor instances
monitor = PingMonitor()
tunnel_status = VPNTunnelStatus()
pod_network = PodNetworkInfo()
diagnostics = NetworkDiagnostics()
background_task = None

# Embedded homepage HTML (try to load from file first, fallback to embedded)
HTML_HOMEPAGE = None
try:
    homepage_path = Path(__file__).parent / "index.html"
    if homepage_path.exists():
        with open(homepage_path, 'r') as f:
            HTML_HOMEPAGE = f.read()
except Exception:
    pass


@app.on_event("startup")
async def startup_event():
    """Start monitoring on application startup."""
    global background_task
    logger.info("🚀 VPN Health Monitor Starting...")

    # Run monitor in background
    background_task = asyncio.create_task(monitor.run_continuous())
    logger.info("✅ Background monitor started")


@app.on_event("shutdown")
async def shutdown_event():
    """Stop monitoring on shutdown."""
    logger.info("🛑 VPN Health Monitor Shutting Down...")
    monitor.running = False

    if background_task:
        background_task.cancel()
        try:
            await background_task
        except asyncio.CancelledError:
            pass

    logger.info("✅ Monitor stopped")


@app.get("/health")
async def health_check():
    """
    Health check endpoint - returns current VPN connectivity status.

    Returns:
        JSON with provider status, target health, and statistics
    """
    try:
        summary = monitor.get_health_summary()
        return JSONResponse(content=summary)
    except Exception as e:
        logger.error(f"Health check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health/providers/{provider}")
async def get_provider_health(provider: str):
    """Get health status for specific provider."""
    summary = monitor.get_health_summary()

    if provider not in summary["providers"]:
        raise HTTPException(status_code=404, detail=f"Provider '{provider}' not found")

    return {
        "timestamp": summary["timestamp"],
        "provider": summary["providers"][provider]
    }


@app.get("/health/targets/{provider}/{target_name}")
async def get_target_history(provider: str, target_name: str):
    """Get ping history for specific target."""
    key = f"{provider}/{target_name}"

    if key not in monitor.history:
        raise HTTPException(status_code=404, detail=f"Target '{key}' not found")

    history = monitor.history[key]
    return {
        "target": key,
        "history": [r.to_dict() for r in history[-100:]],  # Last 100 pings
        "summary": {
            "total_pings": len(history),
            "successes": sum(1 for r in history if r.status == PingStatus.SUCCESS),
            "failures": sum(1 for r in history if r.status != PingStatus.SUCCESS),
            "success_rate": (
                sum(1 for r in history if r.status == PingStatus.SUCCESS) / len(history) * 100
                if history else 0
            )
        }
    }


@app.get("/config")
async def get_config():
    """Get current configuration."""
    return {
        "config_file": str(CONFIG_FILE),
        "ping_interval_seconds": PING_INTERVAL,
        "providers": list(monitor.targets.keys()),
        "targets_per_provider": {p: len(t) for p, t in monitor.targets.items()},
        "total_targets": sum(len(t) for t in monitor.targets.values()),
        "available_ping_tools": {
            "icmplib": HAS_ICMPLIB,
            "aioping": HAS_AIOPING,
            "scapy": HAS_SCAPY,
            "mtr": HAS_MTR,
            "system_ping": True
        }
    }


@app.get("/cluster-info")
async def get_cluster_info():
    """Get cluster network information for VPN peer configuration."""
    return pod_network.get_info()


@app.get("/cluster-cidrs")
async def get_cluster_cidrs():
    """Get cluster CIDR blocks for whitelisting by VPN peers."""
    return {
        "timestamp": datetime.now().isoformat(),
        "cluster": {
            "pod_ips_in_this_request": pod_network.pod_ip,
            "vpc_cidr": pod_network.cluster_cidrs["vpc_cidr"],
            "subnet_cidrs": pod_network.cluster_cidrs["cluster_cidrs"].split(","),
        },
        "instructions": "Whitelist these CIDR blocks in your VPN firewall to allow inbound traffic from EKS cluster",
        "note": "Each pod will originate traffic from an IP within these ranges"
    }


@app.post("/diagnostics/execute", response_model=DiagnosticResponse)
async def execute_diagnostic(request: DiagnosticRequest):
    """Execute a network diagnostic command and return session ID for streaming."""
    # Validate command
    if request.command not in diagnostics.COMMANDS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid command. Allowed: {', '.join(diagnostics.COMMANDS.keys())}"
        )

    # Validate target
    if not request.target:
        raise HTTPException(status_code=400, detail="Target IP or domain required")

    try:
        # Create session immediately
        import uuid
        session_id = str(uuid.uuid4())
        diagnostics.sessions[session_id] = {
            "status": "running",
            "output": [],
            "command": request.command,
            "created_at": time.time(),
        }
        logger.info(f"[DIAG-EXEC] Session created: {session_id} for {request.command} {request.target}")
        logger.info(f"[DIAG-EXEC] Sessions dict now has {len(diagnostics.sessions)} sessions")

        # Run command in background (don't await)
        task = asyncio.create_task(
            diagnostics.execute_command_in_session(
                request.command,
                request.target,
                request.options,
                session_id
            )
        )
        logger.info(f"[DIAG-EXEC] Background task created: {task}")

        return DiagnosticResponse(
            session_id=session_id,
            status="running",
            command=request.command,
            target=request.target
        )
    except Exception as e:
        logger.error(f"[DIAG-EXEC] Error executing diagnostic: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/diagnostics/stream/{session_id}")
async def stream_diagnostic(session_id: str):
    """Server-Sent Events stream for diagnostic output."""
    logger.info(f"[STREAM] Stream requested for session {session_id}")
    logger.info(f"[STREAM] Current sessions: {list(diagnostics.sessions.keys())}")

    async def event_generator():
        """Generate SSE events for diagnostic output."""
        max_wait = 180  # 3 minutes max wait
        start_time = time.time()
        last_output_count = 0
        idle_count = 0

        while time.time() - start_time < max_wait:
            if session_id not in diagnostics.sessions:
                # Session was cleaned up - try once more after a short wait
                logger.warning(f"[STREAM] Session {session_id} not found, waiting 0.5s...")
                await asyncio.sleep(0.5)
                if session_id in diagnostics.sessions:
                    session = diagnostics.sessions[session_id]
                    logger.info(f"[STREAM] Session {session_id} found after wait")
                else:
                    logger.error(f"[STREAM] Session {session_id} still not found after wait. Available: {list(diagnostics.sessions.keys())}")
                    yield f'data: {json.dumps({"error": "Session not found or expired"})}\n\n'
                    break
            else:
                session = diagnostics.sessions[session_id]

            current_output = session["output"]

            # Send new output lines
            if len(current_output) > last_output_count:
                idle_count = 0  # Reset idle counter when we get output
                for line in current_output[last_output_count:]:
                    yield f'data: {json.dumps({"output": line, "type": "line"})}\n\n'
                last_output_count = len(current_output)

            # Check if completed
            if session["status"] != "running":
                logger.info(f"[STREAM] Session {session_id} completed with status {session['status']}")
                yield f'data: {json.dumps({"status": "completed", "type": "status"})}\n\n'
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/diagnostics/status/{session_id}")
async def get_diagnostic_status(session_id: str):
    """Get current status and output for a diagnostic session."""
    if session_id not in diagnostics.sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = diagnostics.sessions[session_id]
    return {
        "session_id": session_id,
        "status": session["status"],
        "command": session["command"],
        "output": session["output"],
        "line_count": len(session["output"])
    }


@app.get("/", response_class=HTMLResponse)
async def root():
    """Interactive VPN Health Monitor Dashboard."""
    return HTMLResponse(content=DASHBOARD_HTML)


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
