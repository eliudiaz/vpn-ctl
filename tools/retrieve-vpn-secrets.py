#!/usr/bin/env python3
"""
VPN Secrets Retrieval Script - AFF-ATG

Script para recuperar y validar Pre-Shared Keys (PSK) y configuración VPN.
Genera reportes seguros para compartir con la red remota (Vimenca/Checkpoint).

Uso:
    python retrieve-vpn-secrets.py --action get-all
    python retrieve-vpn-secrets.py --action get-tunnel1
    python retrieve-vpn-secrets.py --action get-tunnel2
    python retrieve-vpn-secrets.py --action generate-config
    python retrieve-vpn-secrets.py --action validate
    python retrieve-vpn-secrets.py --action test-connectivity

Seguridad:
    - PSKs solo se muestran con confirmación interactiva
    - Archivos creados con permisos restrictivos (0o600)
    - Validación de integridad de archivos
    - Logs de auditoría incluidos
"""

import os
import sys
import json
import argparse
import logging
import subprocess
import hashlib
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import boto3
from botocore.exceptions import ClientError


# Configurar logging
def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configura el sistema de logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('vpn-secrets-audit.log')
        ]
    )
    return logging.getLogger(__name__)


logger = setup_logging()


class VPNSecretsManager:
    """Gestor de secrets VPN con validaciones de seguridad."""

    def __init__(self, region: str = "us-east-1", profile: str = None):
        """
        Inicializa el manager de secrets.

        Args:
            region: Región AWS
            profile: Perfil AWS para usar
        """
        self.region = region
        self.profile = profile
        self.secrets_dir = Path("secrets")
        self.vpn_config_file = self.secrets_dir / "vpn-config.json"
        self.tunnel1_psk_file = self.secrets_dir / "tunnel1-psk.txt"
        self.tunnel2_psk_file = self.secrets_dir / "tunnel2-psk.txt"

        # Validar que el directorio secrets existe
        if not self.secrets_dir.exists():
            logger.error(f"Directorio de secrets no encontrado: {self.secrets_dir}")
            raise FileNotFoundError(f"Directorio {self.secrets_dir} no existe")

        # Inicializar cliente boto3
        try:
            session = boto3.Session(profile_name=profile, region_name=region)
            self.ec2_client = session.client('ec2', region_name=region)
            logger.info(f"Conectado a AWS región: {region}")
        except Exception as e:
            logger.error(f"Error conectando a AWS: {e}")
            raise

    def get_psk(self, tunnel: int) -> Optional[str]:
        """
        Obtiene la Pre-Shared Key de un túnel.

        Args:
            tunnel: Número de túnel (1 o 2)

        Returns:
            PSK limpia (sin comentarios)
        """
        if tunnel not in [1, 2]:
            raise ValueError("Túnel debe ser 1 o 2")

        psk_file = self.tunnel1_psk_file if tunnel == 1 else self.tunnel2_psk_file

        if not psk_file.exists():
            logger.error(f"Archivo PSK no encontrado: {psk_file}")
            return None

        try:
            with open(psk_file, 'r') as f:
                lines = f.readlines()
                # La PSK está en la última línea no vacía
                psk = [l.strip() for l in lines if l.strip() and not l.startswith('#')][-1]
                logger.info(f"PSK Túnel {tunnel} cargada exitosamente")
                return psk
        except Exception as e:
            logger.error(f"Error leyendo PSK Túnel {tunnel}: {e}")
            return None

    def get_vpn_config(self) -> Optional[Dict]:
        """Obtiene la configuración VPN desde el archivo JSON."""
        if not self.vpn_config_file.exists():
            logger.error(f"Archivo de configuración no encontrado: {self.vpn_config_file}")
            return None

        try:
            with open(self.vpn_config_file, 'r') as f:
                config = json.load(f)
                logger.info("Configuración VPN cargada exitosamente")
                return config
        except Exception as e:
            logger.error(f"Error leyendo configuración VPN: {e}")
            return None

    def fetch_vpn_details_from_aws(self, vpn_connection_id: str) -> Optional[Dict]:
        """
        Obtiene detalles VPN desde AWS usando boto3.

        Args:
            vpn_connection_id: ID de la VPN Connection

        Returns:
            Detalles de la VPN
        """
        try:
            response = self.ec2_client.describe_vpn_connections(
                VpnConnectionIds=[vpn_connection_id]
            )

            if not response['VpnConnections']:
                logger.error(f"VPN Connection no encontrada: {vpn_connection_id}")
                return None

            vpn = response['VpnConnections'][0]
            logger.info(f"Detalles VPN obtenidos de AWS: {vpn_connection_id}")

            # Extraer información relevante
            details = {
                'vpn_id': vpn['VpnConnectionId'],
                'customer_gateway_id': vpn['CustomerGatewayId'],
                'transit_gateway_id': vpn.get('TransitGatewayId'),
                'state': vpn['State'],
                'type': vpn['Type'],
                'tunnel1': {
                    'address': vpn.get('VpnConnectionOptions', {}).get('TunnelOptions', [{}])[0].get('OutsideIpAddress'),
                    'status': vpn.get('VgwTelemetry', [{}])[0].get('Status') if len(vpn.get('VgwTelemetry', [])) > 0 else 'Unknown'
                },
                'tunnel2': {
                    'address': vpn.get('VpnConnectionOptions', {}).get('TunnelOptions', [{}])[1].get('OutsideIpAddress') if len(vpn.get('VpnConnectionOptions', {}).get('TunnelOptions', [])) > 1 else None,
                    'status': vpn.get('VgwTelemetry', [{}])[1].get('Status') if len(vpn.get('VgwTelemetry', [])) > 1 else 'Unknown'
                }
            }

            return details
        except ClientError as e:
            logger.error(f"Error obteniendo detalles de AWS: {e}")
            return None

    def validate_psk_files(self) -> Tuple[bool, List[str]]:
        """
        Valida integridad de archivos PSK.

        Returns:
            Tupla (válido, lista de mensajes)
        """
        messages = []
        valid = True

        for tunnel, psk_file in [(1, self.tunnel1_psk_file), (2, self.tunnel2_psk_file)]:
            if not psk_file.exists():
                messages.append(f"❌ PSK Túnel {tunnel} no existe: {psk_file}")
                valid = False
                continue

            # Verificar permisos (debe ser 0o600)
            stat_info = os.stat(psk_file)
            mode = stat_info.st_mode & 0o777

            if mode != 0o600:
                messages.append(f"⚠️  PSK Túnel {tunnel} tiene permisos inseguros: {oct(mode)}")
                # Intentar corregir
                try:
                    os.chmod(psk_file, 0o600)
                    messages.append(f"✓  Permisos corregidos para PSK Túnel {tunnel}")
                except Exception as e:
                    messages.append(f"❌ Error corrigiendo permisos: {e}")
                    valid = False
            else:
                messages.append(f"✓  PSK Túnel {tunnel} tiene permisos correctos (0o600)")

            # Verificar contenido
            try:
                psk = self.get_psk(tunnel)
                if psk and len(psk) == 32:
                    # Calcular hash
                    file_hash = hashlib.sha256(psk.encode()).hexdigest()[:8]
                    messages.append(f"✓  PSK Túnel {tunnel} válida (hash: {file_hash}...)")
                else:
                    messages.append(f"❌ PSK Túnel {tunnel} formato inválido")
                    valid = False
            except Exception as e:
                messages.append(f"❌ Error validando PSK Túnel {tunnel}: {e}")
                valid = False

        return valid, messages

    def generate_checkpoint_config(self, output_file: str = "checkpoint-vpn-config.txt") -> bool:
        """
        Genera archivo de configuración para Checkpoint Firewall.

        Args:
            output_file: Archivo de salida

        Returns:
            True si se generó exitosamente
        """
        config = self.get_vpn_config()
        if not config:
            logger.error("No se pudo obtener configuración VPN")
            return False

        tunnel1_psk = self.get_psk(1)
        tunnel2_psk = self.get_psk(2)

        if not (tunnel1_psk and tunnel2_psk):
            logger.error("No se pudieron obtener PSKs")
            return False

        checkpoint_config = f"""
================================================================================
CONFIGURACIÓN VPN CHECKPOINT - COMPANY TO VIMENCA
================================================================================

Generado: {datetime.now().isoformat()}
Customer: Organization

================================================================================
1. INFORMACIÓN DE CONEXIÓN
================================================================================

VPN Connection ID (AWS):      {config.get('vpn_connection_id')}
Customer Gateway ID:          {config.get('customer_gateway_id')}
Checkpoint Firewall Version:  R80.10
Organization Outside IP:          191.97.106.141

Destinos de Organization (CIDR):
  - 172.31.0.0/16        (EKS VPC Principal)
  - 172.33.6.0/28        (VPC Organization 1)
  - 172.33.16.0/28       (VPC Organization 2)

================================================================================
2. TÚNEL 1 (PRIMARIO)
================================================================================

Outside IP (AWS):             {config.get('tunnel1_address')}
Inside CIDR Block:            169.254.23.200/30
AWS Inside IP:                169.254.23.201
Checkpoint Inside IP:         169.254.23.202
BGP ASN (AWS):                64512
BGP ASN (Vimenca):            65000
Pre-Shared Key:               {tunnel1_psk}

================================================================================
3. TÚNEL 2 (BACKUP/SECUNDARIO)
================================================================================

Outside IP (AWS):             {config.get('tunnel2_address')}
Inside CIDR Block:            169.254.107.44/30
AWS Inside IP:                169.254.107.45
Checkpoint Inside IP:         169.254.107.46
BGP ASN (AWS):                64512
BGP ASN (Vimenca):            65000
Pre-Shared Key:               {tunnel2_psk}

================================================================================
4. PARÁMETROS IPSec (IKEv2)
================================================================================

Protocolo IKE:                IKEv2
Encriptación (FASE 1):        AES-256
Encriptación (FASE 2):        AES-256
Integridad (FASE 1):          SHA2-256
Integridad (FASE 2):          SHA2-256
Diffie-Hellman FASE 1:        Group 14 (2048-bit)
Diffie-Hellman FASE 2:        Group 14 (2048-bit)
Lifetime FASE 1:              28800 segundos (8 horas)
Lifetime FASE 2:              3600 segundos (60 minutos)
Dead Peer Detection (DPD):    Habilitado (30 seg interval)
Perfect Forward Secrecy:      Habilitado
NAT Traversal:                Habilitado
Replay Detection:             Habilitado

================================================================================
5. RUTAS REQUERIDAS EN CHECKPOINT
================================================================================

Destino                 Gateway
172.31.0.0/16          VPN Tunnel (EKS VPC)
172.33.6.0/28          VPN Tunnel (Organization VPC 1)
172.33.16.0/28         VPN Tunnel (Organization VPC 2)

================================================================================
6. REGLAS DE FIREWALL REQUERIDAS
================================================================================

Dirección  | Puerto | Protocolo | Origen/Destino  | Acción
-----------|--------|-----------|-----------------|-------
Ingress    | 80     | TCP       | 172.31.0.0/16   | ALLOW
Ingress    | 443    | TCP       | 172.31.0.0/16   | ALLOW
Ingress    | ICMP   | ICMP      | 172.31.0.0/16   | ALLOW
Egress     | 80     | TCP       | 172.31.0.0/16   | ALLOW
Egress     | 443    | TCP       | 172.31.0.0/16   | ALLOW
Egress     | ICMP   | ICMP      | 172.31.0.0/16   | ALLOW

================================================================================
7. PROCEDIMIENTO DE ACTIVACIÓN
================================================================================

1. Importar configuración en Checkpoint
2. Configurar túnel 1 (primario) con PSK proporcionada
3. Configurar túnel 2 (backup) con PSK proporcionada
4. Verificar que ambos túneles están UP
5. Agregar rutas estáticas hacia Organization
6. Aplicar reglas de firewall
7. Contactar a Organization para confirmar ambos lados UP

Contacto Vimenca:
  - Eric Frias (Principal): 809-487-2679
  - Fermir Quezada (Secundario): 809-487-2602

Contacto Organization:
  - Josué Ubico (Principal): 809.274.0000
  - Ricardo Peña (Secundario): 809.274.0000

================================================================================
INFORMACIÓN DE SEGURIDAD
================================================================================

- PRE-SHARED KEYS son CONFIDENCIALES
- NO distribuir por email sin encripción
- Intercambiar vía telefónica segura
- Verificar identidad antes de proporcionar claves
- Mantener backup seguro de este documento
- Destruir después de configuración correcta

Generado por: Pulumi AFF-ATG Script
Fecha: {datetime.now().isoformat()}
================================================================================
"""

        try:
            output_path = Path(output_file)
            with open(output_path, 'w') as f:
                f.write(checkpoint_config)
            os.chmod(output_path, 0o600)
            logger.info(f"Configuración Checkpoint generada: {output_file}")
            return True
        except Exception as e:
            logger.error(f"Error generando configuración Checkpoint: {e}")
            return False

    def test_vpn_connectivity(self) -> Tuple[bool, List[str]]:
        """
        Prueba conectividad VPN.

        Returns:
            Tupla (conectado, lista de mensajes)
        """
        messages = []
        config = self.get_vpn_config()

        if not config:
            return False, ["No se pudo obtener configuración VPN"]

        vpn_id = config.get('vpn_connection_id')
        tunnel1_ip = config.get('tunnel1_address')
        tunnel2_ip = config.get('tunnel2_address')

        try:
            # Obtener estado VPN desde AWS
            vpn_details = self.fetch_vpn_details_from_aws(vpn_id)

            if not vpn_details:
                return False, ["No se pudieron obtener detalles VPN de AWS"]

            connected = vpn_details['state'] == 'available'

            messages.append(f"Estado VPN: {vpn_details['state']}")
            messages.append(f"Túnel 1 ({tunnel1_ip}): {vpn_details['tunnel1']['status']}")
            messages.append(f"Túnel 2 ({tunnel2_ip}): {vpn_details['tunnel2']['status']}")

            return connected, messages

        except Exception as e:
            logger.error(f"Error probando conectividad: {e}")
            return False, [f"Error: {e}"]

    def show_psk_interactive(self, tunnel: int) -> bool:
        """
        Muestra PSK de forma interactiva con confirmación.

        Args:
            tunnel: Número de túnel

        Returns:
            True si se mostró
        """
        print(f"\n{'='*80}")
        print(f"ADVERTENCIA DE SEGURIDAD - PRE-SHARED KEY TÚNEL {tunnel}")
        print(f"{'='*80}")
        print("Esta es una clave CONFIDENCIAL y debe ser:")
        print("  ✓ Comunicada vía TELÉFONO SEGURO")
        print("  ✓ JAMÁS enviada por email sin encriptación")
        print("  ✓ Tratada como secreto de máxima importancia")
        print(f"{'='*80}\n")

        # Pedir confirmación
        confirm = input(f"¿Deseas ver la PSK del Túnel {tunnel}? (escribe 'si' para confirmar): ")

        if confirm.lower() != 'si':
            logger.info(f"Visualización de PSK Túnel {tunnel} cancelada por usuario")
            return False

        psk = self.get_psk(tunnel)
        if not psk:
            print(f"ERROR: No se pudo obtener PSK del Túnel {tunnel}")
            return False

        # Mostrar PSK con formato protegido
        print(f"\nPre-Shared Key - Túnel {tunnel}:")
        print(f"{'─'*50}")
        print(f"{psk}")
        print(f"{'─'*50}\n")

        # Log de auditoría
        logger.warning(f"PSK Túnel {tunnel} mostrada en consola (auditoría registrada)")

        # Opción de copiar al portapapeles
        try:
            import subprocess
            process = subprocess.Popen(
                ['pbcopy'],
                stdin=subprocess.PIPE,
                text=True
            )
            process.communicate(input=psk)
            print("✓ PSK copiada al portapapeles (macOS)")
        except Exception:
            print("(En Linux/Windows, copiar manualmente)")

        return True


def main():
    """Función principal."""
    parser = argparse.ArgumentParser(
        description="Gestor de Secrets VPN - AFF-ATG",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Obtener todas las PSKs
  python retrieve-vpn-secrets.py --action get-all

  # Obtener PSK Túnel 1
  python retrieve-vpn-secrets.py --action get-tunnel1

  # Generar configuración para Checkpoint
  python retrieve-vpn-secrets.py --action generate-config

  # Validar integridad de secrets
  python retrieve-vpn-secrets.py --action validate

  # Probar conectividad VPN
  python retrieve-vpn-secrets.py --action test-connectivity

SEGURIDAD:
  - Las PSKs se muestran solo con confirmación interactiva
  - Se registran todas las acciones en vpn-secrets-audit.log
  - Los archivos se crean con permisos restrictivos (0o600)
        """
    )

    parser.add_argument(
        '--action',
        choices=['get-all', 'get-tunnel1', 'get-tunnel2', 'generate-config', 'validate', 'test-connectivity'],
        default='validate',
        help='Acción a realizar'
    )

    parser.add_argument(
        '--region',
        default='us-east-1',
        help='Región AWS (default: us-east-1)'
    )

    parser.add_argument(
        '--profile',
        help='Perfil AWS a usar'
    )

    parser.add_argument(
        '--output',
        default='checkpoint-vpn-config.txt',
        help='Archivo de salida para configuración Checkpoint'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Modo verbose (debug)'
    )

    args = parser.parse_args()

    # Crear manager
    try:
        manager = VPNSecretsManager(region=args.region, profile=args.profile)
    except Exception as e:
        logger.error(f"No se pudo inicializar: {e}")
        sys.exit(1)

    # Ejecutar acción
    try:
        if args.action == 'validate':
            print("\n" + "="*80)
            print("VALIDACIÓN DE SECRETS VPN")
            print("="*80 + "\n")

            valid, messages = manager.validate_psk_files()
            for msg in messages:
                print(msg)

            config = manager.get_vpn_config()
            if config:
                print("\n✓ Configuración VPN cargada exitosamente")
                print(f"  VPN ID: {config.get('vpn_connection_id')}")
                print(f"  Customer: {config.get('customer')}")
                print(f"  Túnel 1: {config.get('tunnel1_address')}")
                print(f"  Túnel 2: {config.get('tunnel2_address')}")
            else:
                print("\n❌ Error cargando configuración VPN")
                valid = False

            print(f"\nEstado General: {'✓ VÁLIDO' if valid else '❌ INVÁLIDO'}\n")
            return 0 if valid else 1

        elif args.action == 'get-tunnel1':
            return 1 if not manager.show_psk_interactive(1) else 0

        elif args.action == 'get-tunnel2':
            return 1 if not manager.show_psk_interactive(2) else 0

        elif args.action == 'get-all':
            manager.show_psk_interactive(1)
            manager.show_psk_interactive(2)
            return 0

        elif args.action == 'generate-config':
            print("\nGenerando configuración Checkpoint...")
            success = manager.generate_checkpoint_config(args.output)
            if success:
                print(f"✓ Configuración generada: {args.output}")
                print("  ⚠️  CONFIDENCIAL - Proteger con permisos 0o600")
                return 0
            else:
                print("❌ Error generando configuración")
                return 1

        elif args.action == 'test-connectivity':
            print("\nProbando conectividad VPN...")
            connected, messages = manager.test_vpn_connectivity()
            for msg in messages:
                print(f"  {msg}")
            print(f"\nEstado: {'✓ CONECTADO' if connected else '❌ DESCONECTADO'}\n")
            return 0 if connected else 1

    except Exception as e:
        logger.error(f"Error ejecutando acción: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
