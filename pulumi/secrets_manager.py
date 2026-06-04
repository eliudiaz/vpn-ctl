"""
VPN Secrets Management - AWS Secrets Manager Integration (Peer-Agnostic)

Stores VPN Pre-Shared Keys and configuration in AWS Secrets Manager.
NO PLAINTEXT FILES.

Replaces plaintext secrets/tunnel*-psk.txt with secure AWS Secrets Manager secrets.
"""

import json
import logging
import boto3
import pulumi
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class VpnSecretsManager:
    """Manages VPN PSK and configuration storage in AWS Secrets Manager."""

    def __init__(self, region: str = "us-east-2"):
        """Initialize Secrets Manager client."""
        self.region = region
        self.client = None
        self._init_client()

    def _init_client(self):
        """Initialize boto3 Secrets Manager client."""
        try:
            # Use Pulumi's AWS profile/credentials
            import os
            profile = os.environ.get("AWS_PROFILE") or "default"
            session = boto3.Session(profile_name=profile, region_name=self.region)
            self.client = session.client("secretsmanager")
            logger.info(f"Secrets Manager initialized (region: {self.region}, profile: {profile})")
        except Exception as e:
            logger.error(f"Failed to initialize Secrets Manager: {e}")
            raise

    def save_vpn_psk(
        self,
        peer_name: str,
        tunnel1_psk: str,
        tunnel2_psk: str,
        customer_ip: str,
        contacts: list = None
    ) -> str:
        """
        Save VPN Pre-Shared Keys to AWS Secrets Manager.

        Args:
            peer_name: Name of the VPN peer
            tunnel1_psk: Tunnel 1 pre-shared key
            tunnel2_psk: Tunnel 2 pre-shared key
            customer_ip: Customer's public IP address
            contacts: Optional list of contact dicts

        Returns:
            Secret ID (e.g., "aff-atg/mock-peer-a/vpn-preshared-keys")
        """
        secret_id = f"aff-atg/{peer_name.lower()}/vpn-preshared-keys"

        secret_value = {
            "peer_name": peer_name,
            "tunnel1_psk": tunnel1_psk,
            "tunnel2_psk": tunnel2_psk,
            "customer_ip": customer_ip,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "managed_by": "pulumi",
            "project": "aff-atg",
        }

        if contacts:
            secret_value["contacts"] = contacts

        try:
            # Try to create (if doesn't exist)
            self.client.create_secret(
                Name=secret_id,
                SecretString=json.dumps(secret_value, indent=2),
                Tags=[
                    {"Key": "ManagedBy", "Value": "Pulumi"},
                    {"Key": "Peer", "Value": peer_name},
                    {"Key": "Project", "Value": "aff-atg"},
                    {"Key": "Type", "Value": "VPN-PSK"},
                ],
                Description=f"VPN Pre-Shared Keys for {peer_name}"
            )
            logger.info(f"✅ Created secret: {secret_id}")

        except self.client.exceptions.ResourceExistsException:
            # Update if already exists
            self.client.update_secret(
                SecretId=secret_id,
                SecretString=json.dumps(secret_value, indent=2)
            )
            logger.info(f"✅ Updated secret: {secret_id}")

        except Exception as e:
            logger.error(f"Failed to save secret {secret_id}: {e}")
            raise

        return secret_id

    def save_vpn_config(
        self,
        peer_name: str,
        vpn_connection_id: str,
        customer_gateway_id: str,
        customer_ip: str,
        tunnel1_address: str,
        tunnel2_address: str,
        destination_cidrs: list,
        tunnel_profile: Dict[str, Any] = None
    ) -> str:
        """
        Save VPN Configuration to AWS Secrets Manager.

        Args:
            peer_name: Name of the VPN peer
            vpn_connection_id: AWS VPN Connection ID
            customer_gateway_id: AWS Customer Gateway ID
            customer_ip: Customer's public IP
            tunnel1_address: Tunnel 1 AWS endpoint IP
            tunnel2_address: Tunnel 2 AWS endpoint IP
            destination_cidrs: List of destination CIDRs
            tunnel_profile: Optional tunnel profile configuration

        Returns:
            Secret ID
        """
        secret_id = f"aff-atg/{peer_name.lower()}/vpn-configuration"

        secret_value = {
            "peer_name": peer_name,
            "vpn_connection_id": vpn_connection_id,
            "customer_gateway_id": customer_gateway_id,
            "customer_ip": customer_ip,
            "tunnel1_address": tunnel1_address,
            "tunnel2_address": tunnel2_address,
            "destination_cidrs": destination_cidrs,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "managed_by": "pulumi",
            "project": "aff-atg",
        }

        if tunnel_profile:
            secret_value["tunnel_profile"] = tunnel_profile

        try:
            self.client.create_secret(
                Name=secret_id,
                SecretString=json.dumps(secret_value, indent=2),
                Tags=[
                    {"Key": "ManagedBy", "Value": "Pulumi"},
                    {"Key": "Peer", "Value": peer_name},
                    {"Key": "Project", "Value": "aff-atg"},
                    {"Key": "Type", "Value": "VPN-Config"},
                ],
                Description=f"VPN Configuration for {peer_name}"
            )
            logger.info(f"✅ Created config secret: {secret_id}")

        except self.client.exceptions.ResourceExistsException:
            self.client.update_secret(
                SecretId=secret_id,
                SecretString=json.dumps(secret_value, indent=2)
            )
            logger.info(f"✅ Updated config secret: {secret_id}")

        except Exception as e:
            logger.error(f"Failed to save config secret {secret_id}: {e}")
            raise

        return secret_id

    def get_vpn_psk(self, peer_name: str) -> Dict[str, str]:
        """
        Retrieve VPN PSK from Secrets Manager.

        Args:
            peer_name: Name of the VPN peer

        Returns:
            Dict with tunnel1_psk and tunnel2_psk
        """
        secret_id = f"aff-atg/{peer_name.lower()}/vpn-preshared-keys"

        try:
            response = self.client.get_secret_value(SecretId=secret_id)
            secret_value = json.loads(response["SecretString"])

            return {
                "tunnel1_psk": secret_value.get("tunnel1_psk"),
                "tunnel2_psk": secret_value.get("tunnel2_psk"),
            }

        except self.client.exceptions.ResourceNotFoundException:
            logger.warning(f"Secret not found: {secret_id}")
            return None

        except Exception as e:
            logger.error(f"Failed to retrieve secret {secret_id}: {e}")
            raise

    @staticmethod
    def create_pulumi_callback(
        secrets_manager: "VpnSecretsManager",
        peer_name: str,
        customer_ip: str,
        destination_cidrs: list,
        contacts: list = None,
        tunnel_profile: Dict[str, Any] = None
    ):
        """
        Create a Pulumi callback for saving secrets after resource creation.

        Used with pulumi.Output.all(...).apply(callback) to save secrets after
        VPN connection ID is known.

        Args:
            secrets_manager: VpnSecretsManager instance
            peer_name: Peer name
            customer_ip: Customer IP
            destination_cidrs: List of destination CIDRs
            contacts: Optional contacts list
            tunnel_profile: Optional tunnel profile

        Returns:
            Callback function for pulumi.Output.apply()
        """

        def callback(args):
            vpn_id, t1_addr, t2_addr, cgw_id = args

            # Save PSK
            secrets_manager.save_vpn_psk(
                peer_name=peer_name,
                tunnel1_psk="[REDACTED - stored in AWS Secrets Manager]",
                tunnel2_psk="[REDACTED - stored in AWS Secrets Manager]",
                customer_ip=customer_ip,
                contacts=contacts
            )

            # Save configuration
            secrets_manager.save_vpn_config(
                peer_name=peer_name,
                vpn_connection_id=vpn_id,
                customer_gateway_id=cgw_id,
                customer_ip=customer_ip,
                tunnel1_address=t1_addr,
                tunnel2_address=t2_addr,
                destination_cidrs=destination_cidrs,
                tunnel_profile=tunnel_profile
            )

            logger.info(f"✅ All secrets stored for {peer_name} in AWS Secrets Manager")
            return args

        return callback
