#!/usr/bin/env python3
"""
vpnctl Spec Runner - K8s-style declarative infrastructure management

Executes vpnctl specs (YAML manifests) with support for:
- Multiple IaC providers (Pulumi, Terraform, CloudFormation)
- Declarative stack deployments
- Audit logging
- Rollback capabilities
"""

import yaml
import json
import subprocess
import os
import sys
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class StackPhase(Enum):
    """Stack deployment phases."""
    Pending = "Pending"
    Deploying = "Deploying"
    Deployed = "Deployed"
    Failed = "Failed"
    Destroying = "Destroying"
    Destroyed = "Destroyed"


@dataclass
class StackSpec:
    """K8s-style stack specification."""
    apiVersion: str
    kind: str
    metadata: Dict[str, Any]
    spec: Dict[str, Any]
    status: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_yaml(yaml_file: str) -> "StackSpec":
        """Load spec from YAML file."""
        with open(yaml_file, 'r') as f:
            data = yaml.safe_load(f)

        return StackSpec(
            apiVersion=data.get('apiVersion'),
            kind=data.get('kind'),
            metadata=data.get('metadata', {}),
            spec=data.get('spec', {}),
            status=data.get('status', {})
        )

    def to_yaml(self) -> str:
        """Convert to YAML string."""
        return yaml.dump({
            'apiVersion': self.apiVersion,
            'kind': self.kind,
            'metadata': self.metadata,
            'spec': self.spec,
            'status': self.status
        }, default_flow_style=False)

    def save(self, output_file: str):
        """Save spec to file."""
        with open(output_file, 'w') as f:
            f.write(self.to_yaml())


class ValueResolver:
    """Resolve dynamic values without hardcoding."""

    @staticmethod
    def resolve_transit_gateway_id(aws_profile: str = "default", region: str = "us-east-2") -> Optional[str]:
        """Query AWS for Transit Gateway ID (vpn-hub)."""
        try:
            result = subprocess.run([
                "aws", "ec2", "describe-transit-gateways",
                "--profile", aws_profile,
                "--region", region,
                "--filters", "Name=tag:Name,Values=*vpn-hub*",
                "--query", "TransitGateways[0].TransitGatewayId",
                "--output", "text"
            ], capture_output=True, text=True)

            if result.returncode == 0:
                tgw_id = result.stdout.strip()
                if tgw_id and tgw_id != "None":
                    logger.info(f"✓ Resolved Transit Gateway ID: {tgw_id}")
                    return tgw_id

        except Exception as e:
            logger.warning(f"Failed to query Transit Gateway ID: {e}")

        return None

    @staticmethod
    def resolve_transit_gateway_route_table_id(tgw_id: str, aws_profile: str = "default", region: str = "us-east-2") -> Optional[str]:
        """Query AWS for Transit Gateway Route Table ID."""
        if not tgw_id:
            return None

        try:
            result = subprocess.run([
                "aws", "ec2", "describe-transit-gateway-route-tables",
                "--profile", aws_profile,
                "--region", region,
                "--filters", f"Name=transit-gateway-id,Values={tgw_id}",
                "--query", "TransitGatewayRouteTables[0].TransitGatewayRouteTableId",
                "--output", "text"
            ], capture_output=True, text=True)

            if result.returncode == 0:
                rt_id = result.stdout.strip()
                if rt_id and rt_id != "None":
                    logger.info(f"✓ Resolved Route Table ID: {rt_id}")
                    return rt_id

        except Exception as e:
            logger.warning(f"Failed to query Route Table ID: {e}")

        return None

    @staticmethod
    def resolve_pulumi_output(stack_name: str, output_name: str, stack_dir: str = None) -> Optional[str]:
        """Query Pulumi stack for output value."""
        try:
            cmd = ["pulumi", "stack", "output", output_name, "--json"]
            result = subprocess.run(
                cmd,
                cwd=stack_dir,
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                value = result.stdout.strip().strip('"')
                if value:
                    logger.info(f"✓ Resolved Pulumi output {output_name}: {value}")
                    return value

        except Exception as e:
            logger.warning(f"Failed to query Pulumi output: {e}")

        return None

    @staticmethod
    def resolve_value(value: Any, aws_profile: str = "default", region: str = "us-east-2") -> Any:
        """Resolve dynamic value expressions."""
        if not isinstance(value, str):
            return value

        # Pattern: $(aws:transit_gateway_id)
        if match := re.match(r'\$\(aws:([^)]+)\)', value):
            resolver_name = match.group(1)
            if resolver_name == "transit_gateway_id":
                return ValueResolver.resolve_transit_gateway_id(aws_profile, region)

        # Pattern: $(aws:transit_gateway_route_table_id:tgw-xxxx)
        if match := re.match(r'\$\(aws:transit_gateway_route_table_id:([^)]+)\)', value):
            tgw_id = match.group(1)
            return ValueResolver.resolve_transit_gateway_route_table_id(tgw_id, aws_profile, region)

        # Pattern: $(pulumi:stack-name:output-name)
        if match := re.match(r'\$\(pulumi:([^:]+):([^)]+)\)', value):
            stack_name = match.group(1)
            output_name = match.group(2)
            return ValueResolver.resolve_pulumi_output(stack_name, output_name)

        return value

    @staticmethod
    def resolve_spec_values(spec: Dict[str, Any], aws_profile: str = "default", region: str = "us-east-2") -> Dict[str, Any]:
        """Recursively resolve all dynamic values in spec config."""
        if not isinstance(spec, dict):
            return spec

        config = spec.get("config", {})
        if config:
            # First pass: resolve transit_gateway_id
            tgw_id = None
            for key, value in list(config.items()):
                if key == "transit_gateway_id":
                    resolved = ValueResolver.resolve_value(value, aws_profile, region)
                    if resolved:
                        config[key] = resolved
                        tgw_id = resolved

            # Second pass: resolve other values (including route table which depends on TGW ID)
            for key, value in list(config.items()):
                if key != "transit_gateway_id" and isinstance(value, str) and value.startswith("$("):
                    if key == "transit_gateway_route_table_id" and tgw_id:
                        # Use discovered TGW ID for route table resolution
                        resolved = ValueResolver.resolve_transit_gateway_route_table_id(tgw_id, aws_profile, region)
                        if resolved:
                            config[key] = resolved
                    else:
                        resolved = ValueResolver.resolve_value(value, aws_profile, region)
                        if resolved:
                            config[key] = resolved

        return spec


class ProviderAdapter:
    """Abstract adapter for IaC providers."""

    def __init__(self, provider: str, version: str, config: Dict[str, Any]):
        """Initialize adapter for provider."""
        self.provider = provider
        self.version = version
        self.config = config

    def deploy(self, spec: StackSpec) -> bool:
        """Deploy infrastructure from spec."""
        raise NotImplementedError

    def destroy(self, spec: StackSpec) -> bool:
        """Destroy infrastructure from spec."""
        raise NotImplementedError

    def preview(self, spec: StackSpec) -> Dict[str, Any]:
        """Preview changes without deploying."""
        raise NotImplementedError


class PulumiAdapter(ProviderAdapter):
    """Adapter for Pulumi provider."""

    def __init__(self, version: str, config: Dict[str, Any]):
        super().__init__("pulumi", version, config)

    def deploy(self, spec: StackSpec) -> bool:
        """Deploy using Pulumi."""
        stack_name = spec.metadata.get('name')
        stack_dir = spec.spec.get('stack_directory', f'pulumi/stacks/{stack_name}')

        # Set status to Deploying
        spec.status['phase'] = StackPhase.Deploying.value
        spec.status['startTime'] = datetime.utcnow().isoformat()

        try:
            # Set Pulumi config values
            for key, value in spec.spec.get('config', {}).items():
                subprocess.run(
                    ['pulumi', 'config', 'set', f'aff-atg:{key}', str(value)],
                    cwd=stack_dir,
                    check=True,
                    capture_output=True
                )

            # Select stack
            subprocess.run(
                ['pulumi', 'stack', 'select', stack_name],
                cwd=stack_dir,
                check=True,
                capture_output=True
            )

            # Deploy
            result = subprocess.run(
                ['pulumi', 'up', '--yes', '--skip-preview'],
                cwd=stack_dir,
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                spec.status['phase'] = StackPhase.Failed.value
                spec.status['message'] = f"Pulumi deployment failed: {result.stderr}"
                return False

            spec.status['phase'] = StackPhase.Deployed.value
            spec.status['completionTime'] = datetime.utcnow().isoformat()
            return True

        except Exception as e:
            spec.status['phase'] = StackPhase.Failed.value
            spec.status['message'] = str(e)
            return False

    def destroy(self, spec: StackSpec) -> bool:
        """Destroy using Pulumi."""
        stack_name = spec.metadata.get('name')
        stack_dir = spec.spec.get('stack_directory', f'pulumi/stacks/{stack_name}')

        spec.status['phase'] = StackPhase.Destroying.value

        try:
            subprocess.run(
                ['pulumi', 'stack', 'select', stack_name],
                cwd=stack_dir,
                check=True,
                capture_output=True
            )

            result = subprocess.run(
                ['pulumi', 'destroy', '--yes', '--skip-preview'],
                cwd=stack_dir,
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                spec.status['phase'] = StackPhase.Failed.value
                return False

            spec.status['phase'] = StackPhase.Destroyed.value
            return True

        except Exception as e:
            spec.status['phase'] = StackPhase.Failed.value
            return False

    def preview(self, spec: StackSpec) -> Dict[str, Any]:
        """Preview changes."""
        stack_name = spec.metadata.get('name')
        stack_dir = spec.spec.get('stack_directory', f'pulumi/stacks/{stack_name}')

        try:
            result = subprocess.run(
                ['pulumi', 'preview', '--json'],
                cwd=stack_dir,
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                return json.loads(result.stdout)
            return {}

        except Exception:
            return {}


class SpecRunner:
    """Execute vpnctl specs for infrastructure deployment."""

    def __init__(self, base_dir: str = "."):
        self.base_dir = Path(base_dir)
        self.audit_log = self.base_dir / ".vpnctl" / "audit.log"
        self.audit_log.parent.mkdir(parents=True, exist_ok=True)

    def apply(self, spec_file: str, dry_run: bool = False) -> bool:
        """Apply a spec (deploy infrastructure)."""
        spec = StackSpec.from_yaml(spec_file)
        self._log_audit(f"apply {spec.metadata.get('name')}", dry_run=dry_run)

        # CRITICAL: Resolve dynamic values (no hardcoding!)
        print(f"🔍 Resolving dynamic configuration values...")
        aws_profile = spec.spec.get('config', {}).get('aws_profile', 'default')
        aws_region = spec.spec.get('config', {}).get('aws_region', 'us-east-2')
        spec.spec = ValueResolver.resolve_spec_values(spec.spec, aws_profile, aws_region)

        provider_name = spec.spec.get('provider', 'pulumi')
        version = spec.spec.get('version', '3.x')
        config = spec.spec.get('config', {})

        # Get appropriate adapter
        adapter = self._get_adapter(provider_name, version, config)

        if dry_run:
            print(f"🔍 Preview: {spec.metadata.get('name')} ({provider_name})")
            preview = adapter.preview(spec)
            print(json.dumps(preview, indent=2))
            return True

        print(f"🚀 Deploying: {spec.metadata.get('name')} ({provider_name})")
        success = adapter.deploy(spec)

        # Save updated spec with resolved values and status
        spec.save(spec_file)

        if success:
            print(f"✅ Deployment complete")
        else:
            print(f"❌ Deployment failed: {spec.status.get('message')}")

        return success

    def destroy(self, spec_file: str, dry_run: bool = False) -> bool:
        """Destroy infrastructure from spec."""
        spec = StackSpec.from_yaml(spec_file)
        self._log_audit(f"destroy {spec.metadata.get('name')}", dry_run=dry_run)

        if dry_run:
            print(f"🔍 Would destroy: {spec.metadata.get('name')}")
            return True

        provider_name = spec.spec.get('provider', 'pulumi')
        version = spec.spec.get('version', '3.x')
        config = spec.spec.get('config', {})

        adapter = self._get_adapter(provider_name, version, config)

        print(f"🗑️  Destroying: {spec.metadata.get('name')} ({provider_name})")
        success = adapter.destroy(spec)

        spec.save(spec_file)

        if success:
            print(f"✅ Destruction complete")
        else:
            print(f"❌ Destruction failed")

        return success

    def status(self, spec_file: str) -> Dict[str, Any]:
        """Get deployment status."""
        spec = StackSpec.from_yaml(spec_file)
        return {
            'name': spec.metadata.get('name'),
            'kind': spec.kind,
            'provider': spec.spec.get('provider'),
            'phase': spec.status.get('phase', 'Unknown'),
            'lastUpdate': spec.status.get('completionTime'),
            'message': spec.status.get('message', '')
        }

    def _get_adapter(self, provider: str, version: str, config: Dict[str, Any]) -> ProviderAdapter:
        """Get adapter for provider."""
        if provider == 'pulumi':
            return PulumiAdapter(version, config)
        elif provider == 'terraform':
            raise NotImplementedError("Terraform adapter coming soon")
        elif provider == 'cloudformation':
            raise NotImplementedError("CloudFormation adapter coming soon")
        else:
            raise ValueError(f"Unknown provider: {provider}")

    def _log_audit(self, action: str, dry_run: bool = False):
        """Log action to audit log."""
        timestamp = datetime.utcnow().isoformat()
        user = os.environ.get('USER', 'unknown')
        dry_run_str = "[DRY-RUN] " if dry_run else ""
        log_entry = f"{timestamp} | {user} | {dry_run_str}{action}\n"

        with open(self.audit_log, 'a') as f:
            f.write(log_entry)

        logger.info(f"Audit: {action}")
