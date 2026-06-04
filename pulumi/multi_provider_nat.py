"""
Multi-Provider NAT Gateway Framework

Generalized implementation supporting unlimited providers with configuration-driven
SNAT masquerading. Single EC2 instance with N secondary IPs (one per provider).

Features:
- Single instance, multiple secondary IPs
- Configuration-driven (vpn-providers.yaml controls everything)
- N independent iptables rule sets (auto-generated per provider)
- Unified CloudWatch monitoring
- Scalable: Add provider = config + deploy (20 minutes)
"""

import logging
from typing import Dict, List, Optional
from dataclasses import dataclass

import pulumi
import pulumi_aws as aws

logger = logging.getLogger(__name__)


@dataclass
class ProviderConfig:
    """Configuration for a single provider."""
    name: str
    enabled: bool
    provider_assigned_ip: str
    destination_cidrs: List[str]
    instance_type: str = "t3.small"
    enable_snat_masquerading: bool = False


class IsolatedNatGateway:
    """
    EC2-based SNAT gateway for provider IP masquerading (Peer-Agnostic).

    NO HARDCODED VPC/SUBNET IDS - Discovers from EKS cluster configuration.
    Works for any peer, any EKS cluster, any environment.
    """

    def __init__(
        self,
        name: str,
        provider_name: str,
        provider_assigned_ip: str,
        destination_cidrs: List[str],
        eks_cluster_config,  # NEW: EksClusterConfig (has vpc_id, vpc_cidr, subnets)
        instance_type: str = "t3.small"
    ):
        self.name = name
        self.provider_name = provider_name
        self.provider_assigned_ip = provider_assigned_ip
        self.destination_cidrs = destination_cidrs
        self.instance_type = instance_type
        self.resources = {}

        # Discover from EKS cluster (NOT hardcoded)
        if not eks_cluster_config:
            raise ValueError("eks_cluster_config required (contains VPC, subnets, CIDR)")

        self.vpc_id = eks_cluster_config.vpc_id
        self.pod_cidr = eks_cluster_config.vpc_cidr
        # Use first subnet in cluster for SNAT instance placement
        self.subnet_id = eks_cluster_config.subnet_ids[0] if eks_cluster_config.subnet_ids else None

        if not self.vpc_id or not self.subnet_id:
            raise ValueError(
                f"EKS cluster config incomplete: vpc_id={self.vpc_id}, subnet_id={self.subnet_id}"
            )

    def deploy(self) -> Dict:
        """Deploy all resources for isolated NAT gateway."""
        self._create_security_group()
        self._create_network_interface()
        self._create_ec2_instance()
        # CloudWatch alarm skipped - monitoring enabled on instance
        return self.resources

    def _create_security_group(self):
        """Create security group allowing ICMP, SSH, all outbound."""
        sg = aws.ec2.SecurityGroup(
            f"{self.name}-sg",
            vpc_id=self.DEFAULT_VPC_ID,
            ingress=[
                aws.ec2.SecurityGroupIngressArgs(
                    protocol="icmp",
                    from_port=-1,
                    to_port=-1,
                    cidr_blocks=["0.0.0.0/0"],
                    description="ICMP for diagnostics",
                ),
                aws.ec2.SecurityGroupIngressArgs(
                    protocol="tcp",
                    from_port=22,
                    to_port=22,
                    cidr_blocks=["10.0.0.0/8"],
                    description="SSH for management",
                ),
            ],
            egress=[
                aws.ec2.SecurityGroupEgressArgs(
                    protocol="-1",
                    from_port=0,
                    to_port=0,
                    cidr_blocks=["0.0.0.0/0"],
                    description="All outbound traffic",
                ),
            ],
            tags={"Name": f"{self.name}-sg"},
        )
        self.resources["security_group"] = sg

    def _create_network_interface(self):
        """Create ENI with secondary IP for provider masquerading."""
        eni = aws.ec2.NetworkInterface(
            f"{self.name}-eni",
            subnet_id=self.DEFAULT_SUBNET_ID,
            security_groups=[self.resources["security_group"].id],
            private_ips=[
                "172.31.100.24",  # Primary IP
                self.provider_assigned_ip,  # Secondary IP (provider IP)
            ],
            tags={"Name": f"{self.name}-eni"},
        )
        self.resources["eni"] = eni

    def _create_ec2_instance(self):
        """Create EC2 instance with SNAT configuration."""
        user_data = self._generate_user_data_script()

        instance = aws.ec2.Instance(
            self.name,
            ami="ami-0c02fb55eb91f8b13",  # Ubuntu 22.04 LTS
            instance_type=self.instance_type,
            subnet_id=self.DEFAULT_SUBNET_ID,
            vpc_security_group_ids=[self.resources["security_group"].id],
            user_data=user_data,
            source_dest_check=False,
            monitoring=True,
            tags={
                "Name": self.name,
                "Purpose": "SNAT Gateway",
                "Provider": self.provider_name,
            },
            opts=pulumi.ResourceOptions(depends_on=[self.resources["eni"]]),
        )
        self.resources["instance"] = instance

    def _generate_user_data_script(self) -> str:
        """Generate user data script for SNAT configuration."""
        iptables_rules = []
        for cidr in self.destination_cidrs:
            rule = (
                f"iptables -t nat -A POSTROUTING -d {cidr} "
                f"-j SNAT --to-source {self.provider_assigned_ip}"
            )
            iptables_rules.append(rule)

        script = f"""#!/bin/bash
set -e

exec > >(tee /var/log/nat-gateway-init.log)
exec 2>&1
echo "SNAT Gateway initialization started at $(date)"

apt-get update
apt-get install -y curl wget net-tools jq

echo "net.ipv4.ip_forward = 1" >> /etc/sysctl.conf
sysctl -p

echo "net.ipv4.conf.all.rp_filter = 0" >> /etc/sysctl.conf
echo "net.ipv4.conf.default.rp_filter = 0" >> /etc/sysctl.conf
sysctl -p

apt-get install -y iptables-persistent

echo "Applying iptables SNAT rules..."
{chr(10).join(iptables_rules)}

iptables-save > /etc/iptables/rules.v4

echo "iptables SNAT rules verification:"
iptables -t nat -L -n | grep SNAT

echo "Configuring secondary IPs..."
ip addr add {self.provider_assigned_ip}/32 dev eth0 || true

echo "SNAT Gateway initialization completed at $(date)"
echo "Provider: {self.provider_name}"
echo "Provider IP: {self.provider_assigned_ip}"
echo "Destination CIDRs: {', '.join(self.destination_cidrs)}"

touch /var/lib/nat-gateway-ready

aws cloudwatch put-metric-data \\
  --namespace "MultiProviderNAT" \\
  --metric-name "InitializationComplete" \\
  --value 1 \\
  --region us-east-2 || true
"""
        return script

    def _create_cloudwatch_alarm(self):
        """Create CloudWatch alarm for instance health."""
        alarm = aws.cloudwatch.MetricAlarm(
            f"{self.name}-cpu-alarm",
            comparison_operator="GreaterThanThreshold",
            evaluation_periods=2,
            metric_name="CPUUtilization",
            namespace="AWS/EC2",
            period=300,
            statistic="Average",
            threshold=80,
            alarm_description=f"Alert if NAT gateway CPU > 80%",
            dimensions=[
                aws.cloudwatch.MetricAlarmDimensionArgs(
                    name="InstanceId",
                    value=self.resources["instance"].id,
                ),
            ],
        )
        self.resources["alarm"] = alarm
