"""
Infraestructura de Transit Gateway para conectar múltiples clusters EKS.

Arquitectura escalable usando POO:
- TransitGatewayHub: Hub central de conectividad
- EksClusterConnector: Conecta un cluster EKS al TGW
- VpnConnector: Crea VPN Site-to-Site a terceros

Uso:
    # En clusters.py o directamente aquí
    hub = TransitGatewayHub("affinity-hub", region="us-east-2")

    cluster1 = EksClusterConnector(
        name="asg-plat-dev",
        hub=hub,
        region="us-east-2"
    )

    cluster2 = EksClusterConnector(
        name="asg-plat-prod",
        hub=hub,
        region="us-east-2"
    )
"""

import pulumi
import pulumi_aws as aws
import boto3
import json
import os
import secrets
import string
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
import logging
from pathlib import Path

# Import new orchestrator abstractions
from stack_orchestrator import create_orchestrator, StackOrchestrator
from secrets_manager import VpnSecretsManager
from multi_provider_nat import IsolatedNatGateway
from vpn_registry import VpnRegistry
from vpn_attachment import VpnAttachmentManager, VpnAttachmentExecutor

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configurar boto3 con el profile de AWS desde Pulumi
def get_boto3_session(region: str = None) -> boto3.Session:
    """Obtiene una sesión boto3 con el perfil correcto."""
    aws_config = pulumi.Config("aws")
    profile = aws_config.get("profile") or os.environ.get("AWS_PROFILE")
    region = region or aws_config.get("region") or "us-east-2"
    return boto3.Session(profile_name=profile, region_name=region)


def get_vpn_tunnel_status(vpn_connection_id: str, region: str = "us-east-2") -> Dict[str, Any]:
    """
    Obtiene el estado UP/DOWN de los túneles VPN desde AWS.

    Returns:
        Dict con estructura: {
            "vpn_id": "...",
            "tunnel1": {"ip": "...", "status": "UP|DOWN"},
            "tunnel2": {"ip": "...", "status": "UP|DOWN"},
        }
    """
    try:
        session = get_boto3_session(region)
        ec2 = session.client('ec2')

        response = ec2.describe_vpn_connections(VpnConnectionIds=[vpn_connection_id])
        if not response['VpnConnections']:
            return None

        vpn = response['VpnConnections'][0]
        telemetries = vpn.get('VgwTelemetry', [])

        tunnel_status = {
            "vpn_id": vpn_connection_id,
            "tunnel1": {
                "ip": telemetries[0]['OutsideIpAddress'] if telemetries else "N/A",
                "status": telemetries[0]['Status'].upper() if telemetries else "UNKNOWN"
            },
            "tunnel2": {
                "ip": telemetries[1]['OutsideIpAddress'] if len(telemetries) > 1 else "N/A",
                "status": telemetries[1]['Status'].upper() if len(telemetries) > 1 else "UNKNOWN"
            }
        }
        return tunnel_status
    except Exception as e:
        logger.warning(f"Could not query tunnel status for {vpn_connection_id}: {str(e)}")
        return None


# =============================================================================
# DATA CLASSES - Configuración
# =============================================================================

@dataclass
class VpnPeerConfig:
    """Configuración de un peer VPN (ej: Vimenca)."""
    name: str
    public_ip: str
    bgp_asn: int
    destination_cidrs: List[str]
    device_type: str = "Checkpoint"
    device_version: str = "R80.10"
    contacts: List[Dict[str, str]] = field(default_factory=list)
    tunnel_inside_cidrs: List[str] = field(default_factory=list)  # Custom tunnel inside CIDRs
    provider_assigned_ip: str = ""  # Static IP/CIDR whitelisted by provider (e.g. "203.0.113.10")
    imported_cidrs: List[str] = field(default_factory=list)  # Pre-existing TGW routes managed as imported+protected


@dataclass
class TunnelProfile:
    """Named IPsec/IKE tunnel configuration profile."""
    name: str
    description: str
    ike_versions: List[str]
    phase1_encryption: List[str]
    phase1_integrity: List[str]
    phase1_dh_groups: List[int]
    phase1_lifetime: int
    phase2_encryption: List[str]
    phase2_integrity: List[str]
    phase2_dh_groups: List[int]
    phase2_lifetime: int
    dpd_timeout: int
    dpd_action: str
    static_routes_only: bool = True

    @classmethod
    def from_yaml(cls, name: str, data: dict) -> 'TunnelProfile':
        """Create profile from YAML data."""
        return cls(
            name=name,
            description=data.get('description', ''),
            ike_versions=data.get('ike_versions', ['ikev2']),
            phase1_encryption=data['phase1']['encryption'],
            phase1_integrity=data['phase1']['integrity'],
            phase1_dh_groups=data['phase1']['dh_groups'],
            phase1_lifetime=data['phase1']['lifetime'],
            phase2_encryption=data['phase2']['encryption'],
            phase2_integrity=data['phase2']['integrity'],
            phase2_dh_groups=data['phase2']['dh_groups'],
            phase2_lifetime=data['phase2']['lifetime'],
            dpd_timeout=data['dpd']['timeout'],
            dpd_action=data['dpd']['action'],
            static_routes_only=data.get('static_routes_only', True)
        )


@dataclass
class EksClusterConfig:
    """Configuración de un cluster EKS."""
    name: str
    region: str
    vpc_id: Optional[str] = None
    vpc_cidr: Optional[str] = None
    subnet_ids: Optional[List[str]] = None
    route_table_ids: Optional[List[str]] = None
    security_group_ids: Optional[List[str]] = None

    def __post_init__(self):
        """Obtiene información del cluster si no se proporciona."""
        if not self.vpc_id:
            self._fetch_cluster_info()

    def _fetch_cluster_info(self):
        """Obtiene información del cluster EKS usando boto3."""
        logger.info(f"Obteniendo información del cluster EKS: {self.name}")

        session = get_boto3_session(self.region)
        eks_client = session.client('eks')
        ec2_client = session.client('ec2')

        try:
            cluster_info = eks_client.describe_cluster(name=self.name)['cluster']
            self.vpc_id = cluster_info['resourcesVpcConfig']['vpcId']
            self.subnet_ids = cluster_info['resourcesVpcConfig']['subnetIds']
            self.security_group_ids = [cluster_info['resourcesVpcConfig']['clusterSecurityGroupId']]

            if cluster_info['resourcesVpcConfig'].get('securityGroupIds'):
                self.security_group_ids.extend(cluster_info['resourcesVpcConfig']['securityGroupIds'])

            # Obtener CIDR de la VPC
            vpc_info = ec2_client.describe_vpcs(VpcIds=[self.vpc_id])['Vpcs'][0]
            self.vpc_cidr = vpc_info['CidrBlock']

            # Obtener route tables
            self.route_table_ids = self._get_route_tables(ec2_client)

            logger.info(f"Cluster {self.name}: VPC={self.vpc_id}, CIDR={self.vpc_cidr}")

        except Exception as e:
            raise RuntimeError(f"Error obteniendo info del cluster {self.name}: {e}")

    def _get_route_tables(self, ec2_client) -> List[str]:
        """Obtiene route tables asociadas a las subnets."""
        route_table_ids = set()

        for subnet_id in self.subnet_ids:
            response = ec2_client.describe_route_tables(
                Filters=[{'Name': 'association.subnet-id', 'Values': [subnet_id]}]
            )
            for rt in response.get('RouteTables', []):
                route_table_ids.add(rt['RouteTableId'])

        # Si no hay asociaciones explícitas, usar la main route table
        if not route_table_ids:
            response = ec2_client.describe_route_tables(
                Filters=[
                    {'Name': 'vpc-id', 'Values': [self.vpc_id]},
                    {'Name': 'association.main', 'Values': ['true']}
                ]
            )
            for rt in response.get('RouteTables', []):
                route_table_ids.add(rt['RouteTableId'])

        return list(route_table_ids)


# =============================================================================
# VPN CONFIG MANAGER - YAML-driven configuration
# =============================================================================

class VpnConfigManager:
    """Manages VPN peer and tunnel profile configurations from YAML."""

    def __init__(self, config_file: str = "vpn-peers.yaml"):
        self.config_file = config_file
        self.tunnel_profiles: Dict[str, TunnelProfile] = {}
        self.peers: List[Dict] = []

        if os.path.exists(config_file):
            self.load_config()
        else:
            logger.warning(f"VPN config file not found: {config_file}")
            self._create_default_profile()

    def _create_default_profile(self):
        """Create default Checkpoint R80.10 profile (Vimenca standard)."""
        self.tunnel_profiles['checkpoint_r80'] = TunnelProfile(
            name='checkpoint_r80',
            description='Checkpoint R80.10 compatible (Vimenca standard)',
            ike_versions=['ikev2'],
            phase1_encryption=['AES256'],
            phase1_integrity=['SHA2-256'],
            phase1_dh_groups=[14],
            phase1_lifetime=28800,
            phase2_encryption=['AES256'],
            phase2_integrity=['SHA2-256'],
            phase2_dh_groups=[],  # PFS disabled
            phase2_lifetime=3600,
            dpd_timeout=30,
            dpd_action='restart',
            static_routes_only=True
        )

    def load_config(self):
        """Load and parse YAML configuration."""
        import yaml

        with open(self.config_file, 'r') as f:
            data = yaml.safe_load(f)

        # Load tunnel profiles
        for profile_name, profile_data in data.get('tunnel_profiles', {}).items():
            self.tunnel_profiles[profile_name] = TunnelProfile.from_yaml(
                profile_name, profile_data
            )

        # If no profiles defined, create default
        if not self.tunnel_profiles:
            self._create_default_profile()

        # Load enabled peers only
        self.peers = [p for p in data.get('peers', []) if p.get('enabled', True)]

        logger.info(f"Loaded {len(self.tunnel_profiles)} tunnel profiles")
        logger.info(f"Loaded {len(self.peers)} enabled VPN peers")

    def get_profile(self, profile_name: str) -> TunnelProfile:
        """Get tunnel profile by name."""
        if profile_name not in self.tunnel_profiles:
            raise ValueError(
                f"Unknown tunnel profile: {profile_name}. "
                f"Available: {', '.join(self.tunnel_profiles.keys())}"
            )
        return self.tunnel_profiles[profile_name]

    def get_peer_configs(self) -> List[Tuple[VpnPeerConfig, TunnelProfile, Optional[str], Optional[str]]]:
        """Get list of (VpnPeerConfig, TunnelProfile, psk1, psk2) tuples."""
        configs = []

        for peer_data in self.peers:
            # Normalize provider_assigned_ip: bare IP → /32, existing CIDR → keep as-is
            provider_assigned_ip_raw = peer_data.get('provider_assigned_ip', '')
            if provider_assigned_ip_raw and '/' not in provider_assigned_ip_raw:
                provider_assigned_ip = f"{provider_assigned_ip_raw}/32"
            else:
                provider_assigned_ip = provider_assigned_ip_raw

            peer_config = VpnPeerConfig(
                name=peer_data['name'],
                public_ip=peer_data['public_ip'],
                bgp_asn=peer_data.get('bgp_asn'),  # Optional - not needed for static routes
                destination_cidrs=peer_data['destination_cidrs'],
                device_type=peer_data.get('device_type', 'Unknown'),
                device_version=peer_data.get('device_version', 'Unknown'),
                contacts=peer_data.get('contacts', []),
                tunnel_inside_cidrs=peer_data.get('tunnel_inside_cidrs', []),
                provider_assigned_ip=provider_assigned_ip,
                imported_cidrs=peer_data.get('imported_cidrs', [])
            )

            # Get tunnel profile
            profile_name = peer_data.get('tunnel_profile', 'checkpoint_r80')
            tunnel_profile = self.get_profile(profile_name)

            # Get PSKs if provided
            psk_data = peer_data.get('psk', {})
            tunnel1_psk = psk_data.get('tunnel1') if psk_data else None
            tunnel2_psk = psk_data.get('tunnel2') if psk_data else None

            configs.append((peer_config, tunnel_profile, tunnel1_psk, tunnel2_psk))

        return configs


# =============================================================================
# CLASE BASE - Infraestructura
# =============================================================================

class InfrastructureComponent(ABC):
    """Clase base para componentes de infraestructura."""

    def __init__(self, name: str, tags: Dict[str, str] = None):
        self.name = name
        self.base_tags = {
            "ManagedBy": "Pulumi",
            "Project": "aff-atg",
            "CreatedAt": datetime.now().strftime("%Y-%m-%d"),
            **(tags or {})
        }
        self.resources: Dict[str, Any] = {}

    def _get_tags(self, extra_tags: Dict[str, str] = None) -> Dict[str, str]:
        """Genera tags para un recurso."""
        return {**self.base_tags, **(extra_tags or {})}

    @abstractmethod
    def create(self) -> Dict[str, Any]:
        """Crea los recursos de infraestructura."""
        pass

    def get_outputs(self) -> Dict[str, Any]:
        """Retorna outputs para exportar."""
        return self.resources


# =============================================================================
# TRANSIT GATEWAY HUB
# =============================================================================

class TransitGatewayHub(InfrastructureComponent):
    """
    Hub central de Transit Gateway.

    Crea y gestiona el Transit Gateway que conecta todas las VPCs y VPNs.
    """

    def __init__(
        self,
        name: str,
        region: str,
        amazon_side_asn: int = 64512,
        auto_accept_attachments: bool = True,
        description: str = None,
        tags: Dict[str, str] = None
    ):
        super().__init__(name, tags)
        self.region = region
        self.amazon_side_asn = amazon_side_asn
        self.auto_accept_attachments = auto_accept_attachments
        self.description = description or f"Transit Gateway Hub - {name}"

        # Recursos creados
        self.transit_gateway: aws.ec2transitgateway.TransitGateway = None
        self.route_table: aws.ec2transitgateway.RouteTable = None

        # Crear recursos
        self.create()

    def create(self) -> Dict[str, Any]:
        """Crea el Transit Gateway y route table."""
        logger.info(f"Creando Transit Gateway Hub: {self.name}")

        # Transit Gateway
        self.transit_gateway = aws.ec2transitgateway.TransitGateway(
            f"{self.name}-tgw",
            amazon_side_asn=self.amazon_side_asn,
            auto_accept_shared_attachments="enable" if self.auto_accept_attachments else "disable",
            default_route_table_association="enable",
            default_route_table_propagation="enable",
            dns_support="enable",
            vpn_ecmp_support="enable",
            description=self.description,
            tags=self._get_tags({
                "Name": f"{self.name}-tgw",
                "Component": "TransitGatewayHub",
            }),
        )

        self.resources['transit_gateway'] = self.transit_gateway
        self.resources['transit_gateway_id'] = self.transit_gateway.id

        logger.info(f"Transit Gateway Hub creado: {self.name}")
        return self.resources

    @property
    def id(self) -> pulumi.Output[str]:
        """Retorna el ID del Transit Gateway."""
        return self.transit_gateway.id

    def add_route(
        self,
        destination_cidr: str,
        attachment_id: pulumi.Output[str],
        route_name: str
    ) -> aws.ec2transitgateway.Route:
        """Agrega una ruta al Transit Gateway."""
        return aws.ec2transitgateway.Route(
            f"{self.name}-route-{route_name}",
            transit_gateway_route_table_id=self.transit_gateway.association_default_route_table_id,
            destination_cidr_block=destination_cidr,
            transit_gateway_attachment_id=attachment_id,
        )


# =============================================================================
# EKS CLUSTER CONNECTOR
# =============================================================================

class EksClusterConnector(InfrastructureComponent):
    """
    Conecta un cluster EKS al Transit Gateway Hub.

    Crea:
    - Transit Gateway Attachment
    - Rutas hacia destinos (Vimenca, otras VPCs)
    - Security Groups adicionales
    """

    def __init__(
        self,
        name: str,
        hub: TransitGatewayHub,
        region: str,
        destination_cidrs: List[str] = None,
        tags: Dict[str, str] = None
    ):
        super().__init__(name, tags)
        self.hub = hub
        self.region = region
        self.destination_cidrs = destination_cidrs or []

        # Obtener configuración del cluster
        self.cluster_config = EksClusterConfig(name=name, region=region)

        # Recursos
        self.tgw_attachment: aws.ec2.TransitGatewayVpcAttachment = None
        self.routes: List[aws.ec2.Route] = []
        self.egress_sg: aws.ec2.SecurityGroup = None

        # Crear recursos
        self.create()

    def create(self) -> Dict[str, Any]:
        """Crea todos los recursos para conectar el cluster."""
        logger.info(f"Conectando cluster EKS al TGW Hub: {self.name}")

        # 1. Transit Gateway Attachment
        self._create_tgw_attachment()

        # 3. Rutas hacia destinos via TGW
        self._create_routes()

        # 4. Security Group de egress
        self._create_egress_security_group()

        self.resources['cluster_config'] = {
            'name': self.name,
            'vpc_id': self.cluster_config.vpc_id,
            'vpc_cidr': self.cluster_config.vpc_cidr,
            'subnet_ids': self.cluster_config.subnet_ids,
        }

        logger.info(f"Cluster {self.name} conectado al TGW Hub")
        return self.resources

    def _create_tgw_attachment(self):
        """Crea el attachment al Transit Gateway."""
        self.tgw_attachment = aws.ec2transitgateway.VpcAttachment(
            f"{self.name}-tgw-attachment",
            transit_gateway_id=self.hub.id,
            vpc_id=self.cluster_config.vpc_id,
            subnet_ids=self.cluster_config.subnet_ids,
            dns_support="enable",
            tags=self._get_tags({
                "Name": f"{self.name}-tgw-attachment",
                "Cluster": self.name,
                "Component": "EksClusterConnector",
            }),
        )
        self.resources['tgw_attachment'] = self.tgw_attachment
        self.resources['tgw_attachment_id'] = self.tgw_attachment.id

    def _create_routes(self):
        """Crea rutas hacia los destinos via TGW."""
        for cidr in self.destination_cidrs:
            cidr_name = cidr.replace("/", "-").replace(".", "-")

            for rt_id in self.cluster_config.route_table_ids:
                route = aws.ec2.Route(
                    f"{self.name}-route-{rt_id[-8:]}-{cidr_name}",
                    route_table_id=rt_id,
                    destination_cidr_block=cidr,
                    transit_gateway_id=self.hub.id,
                )
                self.routes.append(route)

        self.resources['routes_count'] = len(self.routes)

    def _create_egress_security_group(self):
        """Crea Security Group para egress hacia redes privadas."""
        egress_rules = [
            aws.ec2.SecurityGroupEgressArgs(
                description=f"Trafico a {cidr}",
                from_port=0,
                to_port=0,
                protocol="-1",
                cidr_blocks=[cidr],
            )
            for cidr in self.destination_cidrs
        ]

        # Agregar egress a la propia VPC
        egress_rules.append(
            aws.ec2.SecurityGroupEgressArgs(
                description="Trafico dentro de VPC",
                from_port=0,
                to_port=0,
                protocol="-1",
                cidr_blocks=[self.cluster_config.vpc_cidr],
            )
        )

        self.egress_sg = aws.ec2.SecurityGroup(
            f"{self.name}-node-egress-sg",
            vpc_id=self.cluster_config.vpc_id,
            description="Reglas de egress para nodos EKS hacia redes privadas",
            egress=egress_rules,
            tags=self._get_tags({
                "Name": f"{self.name}-node-egress-sg",
                "Component": "EksClusterConnector",
            }),
        )
        self.resources['egress_sg'] = self.egress_sg

    def add_destination(self, cidr: str):
        """Agrega un nuevo destino (crea rutas adicionales)."""
        self.destination_cidrs.append(cidr)
        cidr_name = cidr.replace("/", "-").replace(".", "-")

        for rt_id in self.cluster_config.route_table_ids:
            route = aws.ec2.Route(
                f"{self.name}-route-{rt_id[-8:]}-{cidr_name}",
                route_table_id=rt_id,
                destination_cidr_block=cidr,
                transit_gateway_id=self.hub.id,
            )
            self.routes.append(route)

    def add_destination_via_eni(self, cidr: str, eni_id: pulumi.Output[str]):
        """Agrega un nuevo destino que va a través de una ENI (por ej, SNAT instance)."""
        self.destination_cidrs.append(cidr)
        cidr_name = cidr.replace("/", "-").replace(".", "-")

        for rt_id in self.cluster_config.route_table_ids:
            route = aws.ec2.Route(
                f"{self.name}-route-{rt_id[-8:]}-{cidr_name}-via-eni",
                route_table_id=rt_id,
                destination_cidr_block=cidr,
                network_interface_id=eni_id,
            )
            self.routes.append(route)


# =============================================================================
# NAT INSTANCE FOR VPN SNAT
# =============================================================================

class VpnSnatInstance(InfrastructureComponent):
    """
    EC2 NAT instance that performs SNAT on packets destined for VPN peers.

    Configures:
    - EC2 instance with iptables POSTROUTING SNAT rules
    - Secondary IP (provider_assigned_ip) for source IP rewriting
    - Source/Dest check disabled to allow forwarding
    - User data script to configure iptables and IP forwarding

    Traffic flow:
      Pod (172.31.x.x) → NAT Instance → SNAT to provider_assigned_ip → TGW → VPN → Peer
    """

    def __init__(
        self,
        name: str,
        vpc_id: str,
        subnet_id: str,
        provider_assigned_ip: str,
        pod_cidr: str,
        peer_destination_cidrs: List[str],
        instance_type: str = "t3.small",
        tags: Dict[str, str] = None
    ):
        super().__init__(name, tags)
        self.vpc_id = vpc_id
        self.subnet_id = subnet_id
        self.provider_assigned_ip = provider_assigned_ip
        self.pod_cidr = pod_cidr
        self.peer_destination_cidrs = peer_destination_cidrs
        self.instance_type = instance_type

        # Create resources
        self.create()

    def create(self) -> Dict[str, Any]:
        """Creates the SNAT instance and configuration."""
        # Create security group for NAT
        self.sg = self._create_security_group()

        # Create network interface
        self.eni = self._create_network_interface()

        # Launch EC2 instance (with source_dest_check=False for NAT)
        self.instance = self._create_instance()

        logger.info(f"✅ VPN SNAT Instance created: {self.name}")
        logger.info(f"   Instance ID: {self.instance.id}")
        logger.info(f"   Provider IP: {self.provider_assigned_ip}")
        logger.info(f"   SNAT will rewrite source 172.31.x.x → {self.provider_assigned_ip}")

        # Store resources for export
        self.resources = {
            "instance_id": self.instance.id,
            "instance_type": self.instance_type,
            "primary_ip": self.instance.private_ip,
            "provider_ip": self.provider_assigned_ip,
            "security_group_id": self.sg.id,
            "pod_cidr": self.pod_cidr,
            "destination_cidrs": self.peer_destination_cidrs,
        }

        return self.resources

    def _create_security_group(self) -> aws.ec2.SecurityGroup:
        """Security group allowing ingress from pod CIDR and all egress."""
        return aws.ec2.SecurityGroup(
            f"{self.name}-sg",
            vpc_id=self.vpc_id,
            description=f"Security group for VPN SNAT instance {self.name}",
            ingress=[
                # Allow all traffic from pod CIDR
                aws.ec2.SecurityGroupIngressArgs(
                    protocol="-1",
                    from_port=0,
                    to_port=0,
                    cidr_blocks=[self.pod_cidr],
                    description="All traffic from EKS pod CIDR"
                ),
            ],
            egress=[
                # Allow all outbound traffic (required for SNAT)
                aws.ec2.SecurityGroupEgressArgs(
                    protocol="-1",
                    from_port=0,
                    to_port=0,
                    cidr_blocks=["0.0.0.0/0"],
                    description="All outbound traffic"
                ),
            ],
            tags=self._get_tags({
                "Name": f"{self.name}-sg",
                "Component": "VpnSnatInstance",
            }),
        )

    def _create_network_interface(self) -> aws.ec2.NetworkInterface:
        """Create ENI with secondary IP for SNAT."""
        return aws.ec2.NetworkInterface(
            f"{self.name}-eni",
            subnet_id=self.subnet_id,
            security_groups=[self.sg.id],
            description=f"ENI for SNAT instance {self.name}",
            tags=self._get_tags({
                "Name": f"{self.name}-eni",
                "Component": "VpnSnatInstance",
            }),
        )

    def _create_instance(self) -> aws.ec2.Instance:
        """Create EC2 NAT instance with iptables SNAT rules."""

        # User data script to configure SNAT
        user_data = self._generate_user_data()

        # Get latest Amazon Linux 2 AMI
        ami = aws.ec2.get_ami(
            most_recent=True,
            owners=["amazon"],
            filters=[
                {"name": "name", "values": ["amzn2-ami-hvm-*-x86_64-gp2"]},
                {"name": "state", "values": ["available"]},
            ],
        )

        instance = aws.ec2.Instance(
            f"{self.name}-instance",
            ami=ami.id,
            instance_type=self.instance_type,
            subnet_id=self.subnet_id,
            vpc_security_group_ids=[self.sg.id],
            user_data=user_data,
            associate_public_ip_address=False,
            source_dest_check=False,  # Required for NAT forwarding
            tags=self._get_tags({
                "Name": f"{self.name}-instance",
                "Component": "VpnSnatInstance",
                "Role": "VPN-SNAT",
            }),
        )

        return instance

    def _generate_user_data(self) -> str:
        """Generate user data script for iptables SNAT configuration."""

        # Build iptables SNAT rules for each destination CIDR
        snat_rules = []
        for cidr in self.peer_destination_cidrs:
            snat_rules.append(
                f"iptables -t nat -A POSTROUTING -d {cidr} "
                f"-j SNAT --to-source {self.provider_assigned_ip}"
            )

        snat_rules_str = "\n".join(snat_rules)

        user_data = f"""#!/bin/bash
set -x

# Log output
exec > >(tee /var/log/vpn-snat-setup.log)
exec 2>&1

echo "=== VPN SNAT Instance Setup Started ==="
echo "Time: $(date)"
echo "Provider IP: {self.provider_assigned_ip}"
echo "Pod CIDR: {self.pod_cidr}"
echo "Destination CIDRs: {', '.join(self.peer_destination_cidrs)}"

# Update system
yum update -y

# Enable IP forwarding
echo "=== Enabling IP Forwarding ==="
sysctl -w net.ipv4.ip_forward=1
echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
sysctl -p

# Install required packages
yum install -y net-tools iptables-services

# Get primary IP from metadata
PRIMARY_IP=$(ec2-metadata --local-ipv4 | cut -d " " -f 2)
echo "Primary IP: $PRIMARY_IP"

# Configure secondary IP (provider_assigned_ip) on loopback for SNAT source
echo "=== Configuring Secondary IP on Loopback ==="
ip addr add {self.provider_assigned_ip}/32 dev lo
ip addr show lo

# Make it persistent
cat > /etc/network/interfaces.d/99-snat-ip.conf <<'IFCONFIG'
auto lo:1
iface lo:1 inet static
  address {self.provider_assigned_ip}
  netmask 255.255.255.255
IFCONFIG

# Ensure iptables persistence service is enabled
systemctl enable iptables

# Flush existing rules
echo "=== Configuring iptables SNAT Rules ==="
iptables -t nat -F POSTROUTING
iptables -t nat -F PREROUTING

# Add SNAT rules for VPN peer CIDRs
# When packets are destined for peer CIDRs, rewrite source IP to provider_assigned_ip
{snat_rules_str}

# Also allow ESTABLISHED and RELATED packets
iptables -t nat -I POSTROUTING -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# Forward packets
iptables -A FORWARD -i eth0 -o eth0 -j ACCEPT

# Save iptables rules
iptables-save > /etc/sysconfig/iptables
systemctl restart iptables

echo "=== iptables Rules Applied ==="
iptables -t nat -L -n -v --line-numbers

echo "=== VPN SNAT Setup Complete ==="
echo "Packets to {', '.join(self.peer_destination_cidrs)} will be SNAT'd to {self.provider_assigned_ip}"
"""
        return user_data

    def _disable_source_dest_check(self) -> None:
        """Disable source/dest check to allow NAT functionality."""
        # Source/dest check is already disabled at instance creation time
        # since we didn't set source_dest_check=True in _create_instance
        # AWS defaults to enabled, so we explicitly set it to False there
        pass

    def get_instance_id(self) -> pulumi.Output[str]:
        """Return the instance ID."""
        return self.instance.id

    def get_primary_ip(self) -> pulumi.Output[str]:
        """Return the primary IP address."""
        return self.instance.private_ip

    def get_eni_id(self) -> pulumi.Output[str]:
        """Return the primary ENI ID for routing."""
        return self.eni.id


# =============================================================================
# VPN CONNECTOR
# =============================================================================

class VpnConnector(InfrastructureComponent):
    """
    Crea VPN Site-to-Site a un peer externo (ej: Vimenca).

    Incluye:
    - Customer Gateway
    - VPN Connection con 2 túneles
    - Generación de Pre-Shared Keys
    - Rutas estáticas
    """

    def __init__(
        self,
        name: str,
        hub: TransitGatewayHub,
        peer_config: VpnPeerConfig,
        tunnel_profile: TunnelProfile = None,
        aws_bgp_asn: int = 64512,
        tags: Dict[str, str] = None,
        tunnel1_preshared_key: str = None,
        tunnel2_preshared_key: str = None,
        tunnel_inside_cidrs: List[str] = None,
        vpn_attachment_data: Dict[str, Any] = None
    ):
        super().__init__(name, tags)
        self.hub = hub
        self.peer_config = peer_config
        self.tunnel_profile = tunnel_profile or TunnelProfile(
            name='default',
            description='Default Vimenca standard',
            ike_versions=['ikev2'],
            phase1_encryption=['AES256'],
            phase1_integrity=['SHA2-256'],
            phase1_dh_groups=[14],
            phase1_lifetime=28800,
            phase2_encryption=['AES256'],
            phase2_integrity=['SHA2-256'],
            phase2_dh_groups=[],
            phase2_lifetime=3600,
            dpd_timeout=30,
            dpd_action='restart'
        )
        self.aws_bgp_asn = aws_bgp_asn

        # Pre-shared keys - use provided keys or generate new ones
        self.tunnel1_psk = tunnel1_preshared_key or self._generate_psk()
        self.tunnel2_psk = tunnel2_preshared_key or self._generate_psk()

        # Tunnel inside CIDRs - use custom or peer_config or None (AWS auto-assigns)
        self.tunnel_inside_cidrs = tunnel_inside_cidrs or peer_config.tunnel_inside_cidrs or []

        # VPN Pool attachment data (for reusing existing VPNs)
        self.vpn_attachment_data = vpn_attachment_data or {}
        self.vpn_registry = VpnRegistry()
        self.vpn_attachment_executor = VpnAttachmentExecutor(self.vpn_registry)

        # Recursos
        self.customer_gateway: aws.ec2.CustomerGateway = None
        self.vpn_connection: aws.ec2.VpnConnection = None
        self.vpn_tgw_attachment: aws.ec2.TransitGatewayAttachment = None
        self.static_routes: List[aws.ec2transitgateway.Route] = []

        # Crear recursos
        self.create()

    @staticmethod
    def _generate_psk(length: int = 32) -> str:
        """Genera una Pre-Shared Key segura."""
        alphabet = string.ascii_letters + string.digits + "._"
        first_char = secrets.choice(string.ascii_letters)
        rest = ''.join(secrets.choice(alphabet) for _ in range(length - 1))
        return first_char + rest

    def create(self) -> Dict[str, Any]:
        """Crea Customer Gateway y VPN Connection."""
        logger.info(f"Creando VPN Connection a: {self.peer_config.name}")

        # 1. Customer Gateway
        self._create_customer_gateway()

        # 2. VPN Connection
        self._create_vpn_connection()

        # 3. VPN-to-TGW Attachment (skipped - created automatically with transit_gateway_id)
        # self._create_vpn_tgw_attachment()

        # 4. Rutas estáticas en TGW
        self._create_tgw_static_routes()

        # 4b. VPN connection static routes (for static routing mode)
        self._create_vpn_connection_static_routes()

        # 5. Guardar secrets
        self._save_secrets()

        logger.info(f"VPN a {self.peer_config.name} creada")
        return self.resources

    def _create_customer_gateway(self):
        """Crea el Customer Gateway."""
        # Use provided BGP ASN or default to 65000 for static-route-only peers (not used for routing)
        bgp_asn = self.peer_config.bgp_asn or 65000
        self.customer_gateway = aws.ec2.CustomerGateway(
            f"{self.name}-cgw",
            bgp_asn=str(bgp_asn),
            ip_address=self.peer_config.public_ip,
            type="ipsec.1",
            tags=self._get_tags({
                "Name": f"{self.name}-cgw",
                "Customer": self.peer_config.name,
                "Device": f"{self.peer_config.device_type} {self.peer_config.device_version}",
            }),
        )
        self.resources['customer_gateway'] = self.customer_gateway
        self.resources['customer_gateway_id'] = self.customer_gateway.id

    def _create_vpn_connection(self):
        """
        Creates or attaches VPN Connection.

        Decision logic:
        - If vpn_attachment_data specifies 'attach': Import existing VPN
        - If vpn_attachment_data specifies 'create': Create new VPN
        - Otherwise: Create new VPN (default behavior)
        """
        action = self.vpn_attachment_data.get('action', 'create')

        if action == 'attach':
            self._attach_existing_vpn()
        else:
            self._create_new_vpn()

    def _attach_existing_vpn(self):
        """Import and attach existing VPN from pool."""
        vpn_id = self.vpn_attachment_data.get('vpn_id')
        cgw_id = self.vpn_attachment_data.get('customer_gateway_id')

        logger.info(f"Attaching existing VPN: {vpn_id}")
        logger.info(f"  Tunnel IPs: {self.vpn_attachment_data.get('tunnel1_ip')}, {self.vpn_attachment_data.get('tunnel2_ip')}")

        # Import existing VPN connection into Pulumi state
        self.vpn_connection = aws.ec2.VpnConnection.get(
            f"{self.name}-vpn",
            id=vpn_id
        )

        # Also import existing customer gateway
        self.customer_gateway = aws.ec2.CustomerGateway.get(
            f"{self.name}-cgw",
            id=cgw_id
        )

        # Store tunnel IPs from existing VPN
        tunnel1_ip = self.vpn_attachment_data.get('tunnel1_ip')
        tunnel2_ip = self.vpn_attachment_data.get('tunnel2_ip')

        self.resources['vpn_connection'] = self.vpn_connection
        self.resources['vpn_connection_id'] = vpn_id
        self.resources['tunnel1_address'] = tunnel1_ip
        self.resources['tunnel2_address'] = tunnel2_ip
        self.resources['attached_existing_vpn'] = True
        self.resources['attachment_reason'] = self.vpn_attachment_data.get('reason', '')

        logger.info(f"✓ VPN attached (tunnel IPs preserved)")

    def _create_new_vpn(self):
        """Create new VPN connection."""
        tp = self.tunnel_profile  # Shorthand

        # Build VPN connection options
        vpn_options = {
            "customer_gateway_id": self.customer_gateway.id,
            "transit_gateway_id": self.hub.id,
            "type": "ipsec.1",
            "static_routes_only": tp.static_routes_only,
            "tunnel1_preshared_key": self.tunnel1_psk,
            "tunnel2_preshared_key": self.tunnel2_psk,

            # IKE Versions
            "tunnel1_ike_versions": tp.ike_versions,
            "tunnel2_ike_versions": tp.ike_versions,

            # Phase 1
            "tunnel1_phase1_encryption_algorithms": tp.phase1_encryption,
            "tunnel2_phase1_encryption_algorithms": tp.phase1_encryption,
            "tunnel1_phase1_integrity_algorithms": tp.phase1_integrity,
            "tunnel2_phase1_integrity_algorithms": tp.phase1_integrity,
            "tunnel1_phase1_dh_group_numbers": tp.phase1_dh_groups,
            "tunnel2_phase1_dh_group_numbers": tp.phase1_dh_groups,
            "tunnel1_phase1_lifetime_seconds": tp.phase1_lifetime,
            "tunnel2_phase1_lifetime_seconds": tp.phase1_lifetime,

            # Phase 2
            "tunnel1_phase2_encryption_algorithms": tp.phase2_encryption,
            "tunnel2_phase2_encryption_algorithms": tp.phase2_encryption,
            "tunnel1_phase2_integrity_algorithms": tp.phase2_integrity,
            "tunnel2_phase2_integrity_algorithms": tp.phase2_integrity,
            "tunnel1_phase2_dh_group_numbers": tp.phase2_dh_groups,
            "tunnel2_phase2_dh_group_numbers": tp.phase2_dh_groups,
            "tunnel1_phase2_lifetime_seconds": tp.phase2_lifetime,
            "tunnel2_phase2_lifetime_seconds": tp.phase2_lifetime,

            # DPD
            "tunnel1_dpd_timeout_seconds": tp.dpd_timeout,
            "tunnel2_dpd_timeout_seconds": tp.dpd_timeout,
            "tunnel1_dpd_timeout_action": tp.dpd_action,
            "tunnel2_dpd_timeout_action": tp.dpd_action,

            "tags": self._get_tags({
                "Name": f"{self.name}-vpn",
                "Customer": self.peer_config.name,
                "Component": "VpnConnector",
                "TunnelProfile": tp.name,
            }),
        }

        # Add custom tunnel inside CIDRs if provided
        if len(self.tunnel_inside_cidrs) >= 1:
            vpn_options["tunnel1_inside_cidr"] = self.tunnel_inside_cidrs[0]
        if len(self.tunnel_inside_cidrs) >= 2:
            vpn_options["tunnel2_inside_cidr"] = self.tunnel_inside_cidrs[1]

        # Create VPN with direct transit_gateway_id for automatic attachment
        self.vpn_connection = aws.ec2.VpnConnection(
            f"{self.name}-vpn",
            **vpn_options
        )

        self.resources['vpn_connection'] = self.vpn_connection
        self.resources['vpn_connection_id'] = self.vpn_connection.id
        self.resources['tunnel1_address'] = self.vpn_connection.tunnel1_address
        self.resources['tunnel2_address'] = self.vpn_connection.tunnel2_address
        self.resources['created_new_vpn'] = True

        # Register newly created VPN in pool
        self._register_vpn_in_pool()

    def _register_vpn_in_pool(self):
        """
        Register newly created VPN in the pool.

        Called after VPN is created to track it for future reuse.
        Uses Pulumi outputs to get tunnel IPs after VPN is fully created.
        """
        def register_vpn_async(vpn_id, tunnel1_ip, tunnel2_ip):
            """Called after VPN is created with actual tunnel IPs."""
            try:
                self.vpn_attachment_executor.register_new_vpn(
                    vpn_id=vpn_id,
                    customer_gateway_id=self.customer_gateway.id,
                    peer_name=self.peer_config.name,
                    tunnel_profile=self.tunnel_profile.name,
                    tunnel1_ip=tunnel1_ip,
                    tunnel2_ip=tunnel2_ip
                )
                logger.info(f"✓ VPN registered in pool: {vpn_id}")
            except Exception as e:
                logger.error(f"Failed to register VPN in pool: {e}")

        # Use Pulumi's apply to wait for VPN creation and get tunnel IPs
        pulumi.Output.all(
            self.vpn_connection.id,
            self.vpn_connection.tunnel1_address,
            self.vpn_connection.tunnel2_address
        ).apply(lambda args: register_vpn_async(args[0], args[1], args[2]))

    def _create_vpn_tgw_attachment(self):
        """Crea la conexión entre el VPN y el Transit Gateway."""
        self.vpn_tgw_attachment = aws.ec2.TransitGatewayAttachment(
            f"{self.name}-tgw-attachment",
            transit_gateway_id=self.hub.id,
            vpn_connection_id=self.vpn_connection.id,
        )
        self.resources['vpn_tgw_attachment'] = self.vpn_tgw_attachment
        self.resources['vpn_tgw_attachment_id'] = self.vpn_tgw_attachment.id

    def _create_static_routes(self):
        """Crea rutas en Transit Gateway para la VPN."""
        # Create TGW routes pointing to the explicit VPN attachment
        attachment_id = self.vpn_tgw_attachment.id

        for cidr in self.peer_config.destination_cidrs:
            cidr_name = cidr.replace("/", "-").replace(".", "-")
            # Create TGW route pointing to the VPN attachment
            route = aws.ec2transitgateway.Route(
                f"{self.name}-tgw-route-{cidr_name}",
                transit_gateway_route_table_id=self.hub.transit_gateway.association_default_route_table_id,
                destination_cidr_block=cidr,
                transit_gateway_attachment_id=attachment_id,
                opts=pulumi.ResourceOptions(depends_on=[self.vpn_tgw_attachment]),
            )
            self.static_routes.append(route)

        self.resources['static_routes_count'] = len(self.static_routes)

    def _create_tgw_static_routes(self):
        """Creates TGW static routes, skipping imported+protected CIDRs, handling new destination_cidrs and provider_assigned_ip."""
        # New CIDRs = destination_cidrs that are NOT already imported+protected
        new_cidrs = [c for c in self.peer_config.destination_cidrs
                     if c not in self.peer_config.imported_cidrs]

        # Also handle provider_assigned_ip
        if self.peer_config.provider_assigned_ip:
            new_cidrs.append(self.peer_config.provider_assigned_ip)

        for cidr in new_cidrs:
            safe_name = cidr.replace('/', '-').replace('.', '-')
            route = aws.ec2transitgateway.Route(
                f"{self.name}-tgw-route-{safe_name}",
                transit_gateway_route_table_id=self.hub.transit_gateway.association_default_route_table_id,
                destination_cidr_block=cidr,
                transit_gateway_attachment_id=self.vpn_connection.transit_gateway_attachment_id,
                opts=pulumi.ResourceOptions(depends_on=[self.vpn_connection]),
            )
            self.static_routes.append(route)

        self.resources['static_routes_count'] = len(self.static_routes)

    def _create_vpn_connection_static_routes(self):
        """VPN connection static routes NOT used for static_routes_only=true.
        Static routes must be added via Transit Gateway API, not VPN Connection routes.
        TGW routes created in _create_tgw_static_routes() are the proper mechanism."""
        if self.tunnel_profile.static_routes_only:
            logger.info(f"  Skipping VPN connection routes (static routes use Transit Gateway routes instead)")
            return

    def _save_secrets(self):
        """Guarda las Pre-Shared Keys en archivos."""
        secrets_dir = "secrets"
        os.makedirs(secrets_dir, exist_ok=True)

        # Guardar PSKs
        for i, psk in enumerate([self.tunnel1_psk, self.tunnel2_psk], 1):
            filepath = os.path.join(secrets_dir, f"tunnel{i}-psk.txt")
            with open(filepath, "w") as f:
                f.write(f"# Pre-Shared Key - Túnel {i}\n")
                f.write(f"# Generado: {datetime.now().isoformat()}\n")
                f.write(f"# Customer: {self.peer_config.name}\n")
                f.write(f"# CONFIDENCIAL - Intercambiar vía telefónica\n")
                if self.peer_config.contacts:
                    contact = self.peer_config.contacts[0]
                    f.write(f"# Contacto: {contact.get('name', 'N/A')} - {contact.get('phone', 'N/A')}\n")
                f.write(f"#\n")
                f.write(f"{psk}\n")
            os.chmod(filepath, 0o600)

        # Guardar config JSON
        config_path = os.path.join(secrets_dir, "vpn-config.json")

        def save_config(args):
            vpn_id, t1_addr, t2_addr, cgw_id = args
            config = {
                "vpn_connection_id": vpn_id,
                "customer_gateway_id": cgw_id,
                "customer": self.peer_config.name,
                "customer_ip": self.peer_config.public_ip,
                "tunnel1_address": t1_addr,
                "tunnel2_address": t2_addr,
                "destination_cidrs": self.peer_config.destination_cidrs,
                "generated_at": datetime.now().isoformat(),
                "ipsec_config": {
                    "ike_version": "IKEv2",
                    "encryption": "AES256",
                    "integrity": "SHA2-256",
                    "dh_group": 14,
                    "phase1_lifetime": 28800,
                    "phase2_lifetime": 3600,
                }
            }
            with open(config_path, "w") as f:
                json.dump(config, f, indent=2)
            os.chmod(config_path, 0o600)

        pulumi.Output.all(
            self.vpn_connection.id,
            self.vpn_connection.tunnel1_address,
            self.vpn_connection.tunnel2_address,
            self.customer_gateway.id,
        ).apply(save_config)

        logger.info(f"Secrets guardados en: {secrets_dir}/")


# =============================================================================
# CONFIGURACIÓN Y DESPLIEGUE
# =============================================================================

# Obtener configuración de Pulumi
config = pulumi.Config()
aws_config = pulumi.Config("aws")

region = aws_config.get("region") or "us-east-2"
project_name = config.get("project_name") or "affinity"

# CIDRs adicionales de Affinity
affinity_cidrs_str = config.get("affinity_cidrs") or "172.33.6.0/28,172.33.16.0/28"
affinity_cidrs = [cidr.strip() for cidr in affinity_cidrs_str.split(",")]
affinity_aggregate = config.get("affinity_aggregate_cidr") or "172.33.0.0/16"

# Lista de destinos para los clusters
# Will be set after loading VPN peer configurations
all_destination_cidrs = [affinity_aggregate]

logger.info("=" * 80)
logger.info("INICIANDO DESPLIEGUE: Infraestructura Transit Gateway")
logger.info("=" * 80)
logger.info(f"Proyecto: {project_name}")
logger.info(f"Región: {region}")
logger.info(f"Destinos: {all_destination_cidrs}")
logger.info("=" * 80)

# =============================================================================
# ORCHESTRATION: Stack-agnostic infrastructure deployment
# =============================================================================
# Uses StackOrchestrator pattern to eliminate branching logic for core vs peer stacks
# REFACTORING: Replaces 150+ lines of if/else branching with factory pattern

# Get current stack name
current_stack = pulumi.get_stack()
logger.info(f"Current Pulumi stack: {current_stack}")

# Determine stack type (used by remaining code sections)
is_peer_specific_stack = current_stack.startswith("peer-")
if is_peer_specific_stack:
    logger.info(f"🔹 Peer-specific stack mode: deploying ONLY peer resources")
else:
    logger.info(f"🔹 Shared infrastructure mode: deploying core + all peers")

# Load VPN configuration from YAML
# FUTURE: Migrate to unified vpn-infrastructure.yaml with ConfigManager
# For now, use VpnConfigManager which supports legacy vpn-peers.yaml
# CRITICAL: Resolve config path correctly whether called from pulumi/ or pulumi/stacks/peer-*/
# Walk up directory tree to find config/vpn-peers.yaml
def find_vpn_config():
    """Find vpn-peers.yaml by walking up from __file__ location."""
    current = Path(__file__).parent
    while current.name != '/' and str(current) != current.drive:
        config_file = current.parent / "config" / "vpn-peers.yaml"
        if config_file.exists():
            return str(config_file)
        current = current.parent
    # Fallback to relative path from pulumi root
    return str(Path(__file__).parent.parent / "config" / "vpn-peers.yaml")

vpn_config_path = find_vpn_config()
logger.info(f"Using VPN config: {vpn_config_path}")
vpn_config_manager = VpnConfigManager(vpn_config_path)

# Initialize Secrets Manager for secure PSK storage
secrets_manager = VpnSecretsManager(region=region)

# Factory pattern: Create appropriate orchestrator based on stack name
orchestrator: StackOrchestrator = create_orchestrator(
    stack_name=current_stack,
    config_manager=vpn_config_manager,
    vpc_connector_class=EksClusterConnector
)

logger.info(f"🔹 Stack type: {orchestrator.__class__.__name__}")

# REFACTORING: Single orchestrator interface handles both core and peer stacks
# No more scattered if/else branching - clean abstraction for all stack types

hub = orchestrator.create_tgw_hub()
logger.info(f"✓ Transit Gateway: {hub.id}")

# Get EKS connectors (empty dict for peer stacks)
connected_clusters: Dict[str, EksClusterConnector] = orchestrator.create_eks_connectors()
logger.info(f"✓ EKS clusters: {len(connected_clusters)}")

# Get VPN connector configurations (filtered per stack type)
vpn_connectors_config: Dict[str, Any] = orchestrator.create_vpn_connectors()
logger.info(f"✓ VPN configs: {len(vpn_connectors_config)}")

# Get SNAT instance configurations (only for peers with provider_assigned_ip)
snat_instances_config: Dict[str, Any] = orchestrator.create_snat_instances(hub, connected_clusters)
logger.info(f"✓ SNAT configs: {len(snat_instances_config)}")


# =============================================================================
# 3. LOAD VPN PEER CONFIGURATIONS FROM YAML
# =============================================================================

logger.info("=" * 80)
logger.info("LOADING VPN PEER CONFIGURATIONS")
logger.info("=" * 80)

# REFACTORING: Extract VPN peer configs from orchestrator result
# The orchestrator has already filtered peers based on stack type (core vs peer-specific)
all_peer_configs = vpn_config_manager.get_peer_configs()
logger.info(f"Total VPN peers available: {len(all_peer_configs)}")

# =============================================================================
# 3. CREATE VPN CONNECTORS
# =============================================================================

vpn_connectors: Dict[str, VpnConnector] = {}

# Instantiate actual VPN connectors from orchestrator configs
for peer_name, vpn_config in vpn_connectors_config.items():
    peer_config = vpn_config["peer_config"]
    tunnel_profile = vpn_config["tunnel_profile"]
    tunnel1_psk = vpn_config["tunnel1_psk"]
    tunnel2_psk = vpn_config["tunnel2_psk"]
    vpn_attachment_data = vpn_config.get("vpn_attachment_data", {})

    logger.info(f"Creating VPN for {peer_name} using profile: {tunnel_profile.name}")

    connector = VpnConnector(
        name=f"{project_name}-{peer_name.lower().replace(' ', '-')}",
        hub=hub,
        peer_config=peer_config,
        tunnel_profile=tunnel_profile,
        tags={
            "Customer": peer_name,
            "TunnelProfile": tunnel_profile.name,
        },
        tunnel1_preshared_key=tunnel1_psk,
        tunnel2_preshared_key=tunnel2_psk,
        vpn_attachment_data=vpn_attachment_data
    )

    # NOTE: Secrets manager callback removed due to serialization constraints
    # VPN connections are successfully created in AWS
    # Secrets can be managed separately via CLI or secrets management system

    vpn_connectors[peer_name] = connector
    logger.info(f"  ✓ VPN connector created: {peer_name}")

logger.info("=" * 80)

# =============================================================================
# 4. CREATE SNAT INSTANCES FOR VPN PEERS (Source IP Translation)
# =============================================================================
# REFACTORING: Uses IsolatedNatGateway with eks_cluster_config for dynamic VPC discovery
# Replaces old VpnSnatInstance with modern architecture

logger.info("Creating SNAT instances for VPN peers requiring source IP translation...")

snat_instances: Dict[str, Any] = {}
snat_peer_mapping: Dict[str, str] = {}  # Maps peer name to SNAT ENI ID
snat_route_tables: Dict[str, str] = {}  # Maps peer name to SNAT subnet route table ID

# REFACTORING: Instantiate SNAT instances from orchestrator configs
# Orchestrator has already filtered to only peers with provider_assigned_ip
if snat_instances_config and not is_peer_specific_stack:
    logger.info(f"Deploying {len(snat_instances_config)} SNAT instance(s)...")

    for peer_name, snat_config in snat_instances_config.items():
        peer_config = snat_config["peer_config"]
        hub_ref = snat_config["hub"]
        cluster_connectors = snat_config["cluster_connectors"]

        # REFACTORING: Use IsolatedNatGateway with dynamic eks_cluster_config
        # IsolatedNatGateway will discover VPC/Subnet/CIDR from EKS cluster at runtime
        logger.info(f"  Creating SNAT instance for {peer_name}:")
        logger.info(f"    Provider IP: {peer_config.provider_assigned_ip}")
        logger.info(f"    Destination CIDRs: {', '.join(peer_config.destination_cidrs)}")

        # Get first EKS cluster config (assumes single cluster per region)
        first_cluster = next(iter(cluster_connectors.values()))

        # REFACTORING: New signature - IsolatedNatGateway now takes eks_cluster_config
        nat_gateway = IsolatedNatGateway(
            name=f"{project_name}-{peer_name.lower().replace(' ', '-')}-snat",
            provider_name=peer_name,
            provider_assigned_ip=peer_config.provider_assigned_ip,
            destination_cidrs=peer_config.destination_cidrs,
            eks_cluster_config=first_cluster.cluster_config,
            instance_type="t3.small"
        )

        # Deploy the NAT gateway (creates instance and security group)
        nat_resources = nat_gateway.deploy()
        snat_instances[peer_name] = nat_resources

        if nat_resources.get("instance"):
            logger.info(f"  ✓ SNAT instance created for {peer_name}")
else:
    if is_peer_specific_stack:
        logger.info("Skipping SNAT deployment (peer-specific stack - shared infrastructure managed by core stack)")
    else:
        logger.info("No SNAT instances configured (no peers with provider_assigned_ip)")

logger.info("=" * 80)

# =============================================================================
# 4b. PROPAGATE VPN PEER ROUTES TO ALL EKS CLUSTER VPC ROUTE TABLES
# =============================================================================
# Routes traffic through SNAT instances (if available) or directly to TGW
# Uses EksClusterConnector.add_destination_via_eni() for SNAT or add_destination() for TGW
# Only propagate routes in dev/core stacks with cluster connectors

if not is_peer_specific_stack:
    logger.info("Propagating VPN peer routes to EKS cluster VPC route tables...")
else:
    logger.info("Skipping route propagation (peer-specific stack - routes managed by core stack)")

if not is_peer_specific_stack:
    for peer_config, _, _, _ in all_peer_configs:
        all_peer_cidrs = list(peer_config.destination_cidrs)
        if peer_config.provider_assigned_ip:
            all_peer_cidrs.append(peer_config.provider_assigned_ip)

        for cidr in all_peer_cidrs:
            for cluster_name, cluster_connector in connected_clusters.items():
                if cidr not in cluster_connector.destination_cidrs:
                    # If this peer has a SNAT instance, route through it
                    if peer_config.name in snat_peer_mapping:
                        snat_eni_id = snat_peer_mapping[peer_config.name]
                        logger.info(f"  {cluster_name}: adding route {cidr} → SNAT ENI")
                        cluster_connector.add_destination_via_eni(cidr, snat_eni_id)
                    else:
                        # Otherwise route directly to TGW
                        logger.info(f"  {cluster_name}: adding route {cidr} → TGW")
                        cluster_connector.add_destination(cidr)

    logger.info(f"Route propagation complete: {len(connected_clusters)} cluster(s)")

logger.info("=" * 80)

# =============================================================================
# 4a. IMPORT EXISTING TGW ROUTES (Pre-existing Vimenca routes from AWS)
# =============================================================================
# Only import these routes in dev/core stacks, not in peer-specific stacks

# Vimenca routes are now managed by PeerStack (included in vpn_peers)
# Routes will be created/updated as part of the VpnConnector deployment above


# =============================================================================
# 5. QUERY VPN TUNNEL STATUS (runs after stack deployment)
# =============================================================================

def query_tunnel_status_callback(vpn_id: str, peer_name: str, region: str):
    """Callback to query tunnel status after VPN ID is known."""
    def callback(vpn_connection_id: str):
        try:
            tunnel_status = get_vpn_tunnel_status(vpn_connection_id, region)
            if tunnel_status:
                logger.info(f"  {peer_name}: Tunnel1={tunnel_status['tunnel1']['status']}, Tunnel2={tunnel_status['tunnel2']['status']}")
            else:
                logger.warning(f"  {peer_name}: No se pudo obtener estado")
        except Exception as e:
            logger.warning(f"  {peer_name}: Error al obtener estado - {str(e)}")
    return callback

logger.info("Configurando queries de estado de túneles VPN...")
region = pulumi.Config("aws").get("region") or "us-east-2"

# Create dictionary to collect tunnel status outputs
vpn_tunnel_status_outputs: Dict[str, pulumi.Output] = {}

for peer_name, vpn_connector in vpn_connectors.items():
    vpn_id = vpn_connector.vpn_connection.id
    vpn_tunnel_status_outputs[peer_name] = vpn_id.apply(
        lambda vid: get_vpn_tunnel_status(vid, region)
    )


# =============================================================================
# EXPORTS
# =============================================================================

# Transit Gateway Hub
pulumi.export("transit_gateway_id", hub.id)
pulumi.export("transit_gateway_hub", hub.get_outputs())

# Clusters conectados
for name, connector in connected_clusters.items():
    pulumi.export(f"cluster_{name.replace('-', '_')}", connector.get_outputs())

# VPN Peers (dynamic exports)
for peer_name, vpn_connector in vpn_connectors.items():
    safe_name = peer_name.lower().replace('-', '_').replace(' ', '_')
    pulumi.export(f"vpn_{safe_name}", vpn_connector.get_outputs())
    pulumi.export(f"vpn_{safe_name}_tunnel1", vpn_connector.vpn_connection.tunnel1_address)
    pulumi.export(f"vpn_{safe_name}_tunnel2", vpn_connector.vpn_connection.tunnel2_address)

# SNAT Instances (dynamic exports)
for peer_name, snat_instance in snat_instances.items():
    safe_name = peer_name.lower().replace('-', '_').replace(' ', '_')
    pulumi.export(f"snat_{safe_name}_instance_id", snat_instance.get_instance_id())
    pulumi.export(f"snat_{safe_name}_primary_ip", snat_instance.get_primary_ip())
    pulumi.export(f"snat_{safe_name}_provider_ip", snat_instance.provider_assigned_ip)

# VPN Tunnel Status
if vpn_tunnel_status_outputs:
    tunnel_status_combined = pulumi.Output.all(*vpn_tunnel_status_outputs.values()).apply(
        lambda statuses: dict(zip(vpn_tunnel_status_outputs.keys(), statuses))
    )
    pulumi.export("vpn_tunnel_status", tunnel_status_combined)

# DEPRECATION: Remove old CIBA outputs (renamed to CIBAO)
# These exports are null to signal Pulumi to remove them from the stack
pulumi.export("vpn_ciba", None)
pulumi.export("vpn_ciba_tunnel1", None)
pulumi.export("vpn_ciba_tunnel2", None)

# Resumen de costos
tgw_attachment_cost = len(connected_clusters) * 36.0
vpn_cost = 36.0  # VPN connection cost

pulumi.export("cost_summary", {
    "monthly": {
        "tgw_attachments": f"${tgw_attachment_cost:.2f} ({len(connected_clusters)} clusters x $36)",
        "vpn_connection": f"${vpn_cost:.2f}",
        "total_tgw_vpn": f"${tgw_attachment_cost + vpn_cost:.2f}",
        "note": "VPC Endpoints managed separately (not included in cost)",
    },
    "clusters_connected": list(connected_clusters.keys()),
})

# Información para formulario VPN - Build from first peer if available
if vpn_peers:
    first_peer_config, _, _, _ = vpn_peers[0]
    first_vpn_connector = vpn_connectors.get(first_peer_config.name)

    vpn_form_data = {
        "affinity": {
            "company": "Affinity",
            "device": "AWS Transit Gateway",
            "version": "AWS Site-to-Site VPN",
            "source_cidrs": [c.cluster_config.vpc_cidr for c in connected_clusters.values()],
        },
        first_peer_config.name: {
            "company": first_peer_config.name,
            "device": first_peer_config.device_type,
            "version": first_peer_config.device_version,
            "ip": first_peer_config.public_ip,
            "destination_cidrs": first_peer_config.destination_cidrs,
        },
        "psk_files": ["secrets/tunnel1-psk.txt", "secrets/tunnel2-psk.txt"],
    }

    if first_vpn_connector:
        vpn_form_data["affinity"]["tunnel1_ip"] = first_vpn_connector.vpn_connection.tunnel1_address
        vpn_form_data["affinity"]["tunnel2_ip"] = first_vpn_connector.vpn_connection.tunnel2_address

    pulumi.export("vpn_form_data", vpn_form_data)

# Summary logging
logger.info("\n" + "=" * 80)
logger.info("CONFIGURACIÓN COMPLETADA")
logger.info("=" * 80)
logger.info(f"Transit Gateway Hub: {project_name}-hub")
logger.info(f"Clusters conectados: {len(connected_clusters)}")
for name in connected_clusters.keys():
    logger.info(f"  - {name}")
logger.info(f"VPN Peers configurados: {len(vpn_connectors)}")
for peer_name in vpn_connectors.keys():
    logger.info(f"  - {peer_name}")
logger.info("=" * 80)

# Diagnostic summary - Immediate peer info + delayed tunnel status
logger.info("")
logger.info("")

# Box drawing characters
box_top_left = "┌"
box_top_right = "┐"
box_bottom_left = "└"
box_bottom_right = "┘"
box_horizontal = "─"
box_vertical = "│"
box_t_right = "├"
box_t_left = "┤"

# Main header
logger.info(f"  {box_top_left}{box_horizontal * 71}{box_top_right}")
logger.info(f"  {box_vertical}  🔍 DIAGNÓSTICO DE TÚNELES VPN - ESTADO DE PARES  {' ' * 15}{box_vertical}")
logger.info(f"  {box_bottom_left}{box_horizontal * 71}{box_bottom_right}")
logger.info("")

# Show all configured peers
peer_count = len(vpn_connectors)
for idx, (peer_name, vpn_connector) in enumerate(vpn_connectors.items(), 1):
    # Peer header box
    logger.info(f"┌───────────────────────────────────────────────────────────────────────────┐")
    logger.info(f"│ [{idx}/{peer_count}] {peer_name:<69} │")
    logger.info(f"├───────────────────────────────────────────────────────────────────────────┤")
    logger.info(f"│ 🔧 BGP ASN ................ {str(vpn_connector.peer_config.bgp_asn):<47} │")
    logger.info(f"│ 📍 Device ................. {(vpn_connector.peer_config.device_type + ' ' + vpn_connector.peer_config.device_version):<47} │")
    logger.info(f"│ ⚙️  Profile ................. {vpn_connector.tunnel_profile.name:<47} │")

    cidr_str = ', '.join(vpn_connector.peer_config.destination_cidrs)
    if len(cidr_str) > 47:
        cidr_str = cidr_str[:44] + "..."
    logger.info(f"│ 🌐 Destination CIDRs ...... {cidr_str:<47} │")
    logger.info(f"│ ⏳ Tunnel Status ........... (available after deployment)                 │")
    logger.info(f"└───────────────────────────────────────────────────────────────────────────┘")

    if idx < peer_count:
        logger.info("")

logger.info("")

# Summary footer
logger.info(f"  {box_top_left}{box_horizontal * 71}{box_top_right}")
logger.info(f"  {box_vertical}  📊 RESUMEN  {' ' * 57}{box_vertical}")
logger.info(f"  {box_t_right}{box_horizontal * 71}{box_t_left}")
logger.info(f"  {box_vertical} Total de Pares ........... {len(vpn_connectors):<56} {box_vertical}")
logger.info(f"  {box_bottom_left}{box_horizontal * 71}{box_bottom_right}")
logger.info("")

# Export formatted diagnostic output and log it after deployment
if vpn_tunnel_status_outputs:
    def format_tunnel_diagnostics(tunnel_statuses: Dict[str, Any]) -> Dict[str, Any]:
        """Format tunnel status for display."""
        formatted = {}
        for peer_name, status_info in tunnel_statuses.items():
            if status_info:
                t1_status = status_info.get('tunnel1', {}).get('status', 'UNKNOWN')
                t2_status = status_info.get('tunnel2', {}).get('status', 'UNKNOWN')
                t1_ip = status_info.get('tunnel1', {}).get('ip', 'N/A')
                t2_ip = status_info.get('tunnel2', {}).get('ip', 'N/A')

                formatted[peer_name] = {
                    'tunnel1': f"{'✅' if t1_status == 'UP' else '❌'} {t1_status} ({t1_ip})",
                    'tunnel2': f"{'✅' if t2_status == 'UP' else '❌'} {t2_status} ({t2_ip})",
                }
        return formatted

    def log_tunnel_status(formatted_statuses: Dict[str, Any]) -> Dict[str, Any]:
        """Log tunnel status after deployment."""
        logger.info("")
        logger.info("=" * 80)
        logger.info("🔍 VPN TUNNEL STATUS (Post-Deployment)")
        logger.info("=" * 80)
        for peer_name, status_info in formatted_statuses.items():
            t1_status = status_info.get('tunnel1', 'UNKNOWN')
            t2_status = status_info.get('tunnel2', 'UNKNOWN')
            logger.info(f"{peer_name}:")
            logger.info(f"  Tunnel 1: {t1_status}")
            logger.info(f"  Tunnel 2: {t2_status}")
        logger.info("=" * 80)
        return formatted_statuses

    tunnel_status_formatted = pulumi.Output.all(*vpn_tunnel_status_outputs.values()).apply(
        lambda statuses: format_tunnel_diagnostics(dict(zip(vpn_tunnel_status_outputs.keys(), statuses)))
    )

    # Log tunnel status after export
    tunnel_status_formatted.apply(log_tunnel_status)

    pulumi.export("vpn_tunnel_status_formatted", tunnel_status_formatted)
logger.info("PRE-SHARED KEYS guardadas en: secrets/")
logger.info("  - secrets/tunnel1-psk.txt")
logger.info("  - secrets/tunnel2-psk.txt")
if vpn_peers:
    first_peer_config, _, _, _ = vpn_peers[0]
    if first_peer_config.contacts:
        logger.info(f"\nINTERCAMBIAR VÍA TELEFÓNICA con {first_peer_config.name}:")
        logger.info(f"  Contacto: {first_peer_config.contacts[0]['name']} - {first_peer_config.contacts[0]['phone']}")
logger.info("=" * 80)


# =============================================================================
# PHASE 1: MULTI-PROVIDER NAT GATEWAY (SNAT MASQUERADING)
# =============================================================================
# Only deploy in dev/core stacks - SNAT is shared infrastructure
# Peer-specific stacks use shared SNAT resources managed by dev stack

logger.info("")
logger.info("=" * 80)
logger.info("PHASE 1: MULTI-PROVIDER NAT GATEWAY")
logger.info("=" * 80)

if not is_peer_specific_stack:
    try:
        import yaml
        from multi_provider_nat import IsolatedNatGateway, ProviderConfig

        # Load provider configurations
        try:
            vpn_providers_path = str(Path(__file__).parent.parent / "config" / "vpn-providers.yaml")
            with open(vpn_providers_path, "r") as f:
                nat_config = yaml.safe_load(f)
        except Exception as e:
            logger.warning(f"Could not load vpn-providers.yaml: {e}. Skipping Phase 1.")
            nat_config = None

        if nat_config:
            providers_config = nat_config.get("providers", {})
            enabled_providers = {
                name: cfg for name, cfg in providers_config.items()
                if cfg.get("enabled") and cfg.get("enable_snat_masquerading")
            }

            if enabled_providers:
                logger.info(f"Deploying Phase 1: {len(enabled_providers)} provider(s) enabled")

                # Deploy NAT gateway for each enabled provider
                nat_resources = {}
                for provider_name, provider_cfg in enabled_providers.items():
                    logger.info(f"  Deploying NAT for {provider_name}: {provider_cfg.get('provider_assigned_ip')}")

                    nat = IsolatedNatGateway(
                        name=f"multi-provider-nat-{provider_name.lower()}",
                        provider_name=provider_name,
                        provider_assigned_ip=provider_cfg.get("provider_assigned_ip"),
                        destination_cidrs=provider_cfg.get("destination_cidrs", []),
                        instance_type=provider_cfg.get("instance_type", "t3.small")
                    )

                    nat_res = nat.deploy()
                    nat_resources[provider_name] = nat_res

                    # Export outputs
                    pulumi.export(
                        f"nat_{provider_name.lower()}_instance_id",
                        nat_res["instance"].id
                    )
                    pulumi.export(
                        f"nat_{provider_name.lower()}_secondary_ip",
                        provider_cfg.get("provider_assigned_ip")
                    )

                logger.info(f"Phase 1 deployment complete: {len(nat_resources)} provider(s)")
            else:
                logger.info("Phase 1: No providers configured for SNAT masquerading")
        else:
            logger.info("Phase 1: vpn-providers.yaml not found, skipping")

    except ImportError as e:
        logger.warning(f"Could not import NAT framework: {e}. Skipping Phase 1.")
    except Exception as e:
        logger.error(f"Phase 1 deployment error: {e}")
        raise
else:
    logger.info("Phase 1: Skipping SNAT deployment (peer-specific stack - shared infrastructure)")

logger.info("=" * 80)
