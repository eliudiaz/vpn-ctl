#!/usr/bin/env python3
"""
Script de validación post-deploy para la conectividad EKS-Transit Gateway.

Verifica que todos los recursos fueron creados correctamente y están disponibles.
"""

import boto3
import json
import subprocess
import sys
from typing import Dict, List, Tuple
import argparse


class Colors:
    """Colores ANSI para output en terminal."""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'


def print_header(text: str) -> None:
    """Imprime un encabezado formateado."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 80}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 80}{Colors.END}")


def print_check(name: str, passed: bool, details: str = "") -> None:
    """Imprime el resultado de una verificación."""
    status = f"{Colors.GREEN}✅ PASS{Colors.END}" if passed else f"{Colors.RED}❌ FAIL{Colors.END}"
    print(f"  {status} {name}")
    if details:
        print(f"       {Colors.YELLOW}{details}{Colors.END}")


def get_pulumi_output(key: str) -> str:
    """Obtiene un output de Pulumi."""
    try:
        result = subprocess.run(
            ["pulumi", "stack", "output", key, "--json"],
            capture_output=True,
            text=True,
            check=True
        )
        return json.loads(result.stdout)
    except subprocess.CalledProcessError:
        return None
    except json.JSONDecodeError:
        return result.stdout.strip().strip('"')


def validate_tgw_attachment(ec2_client, vpc_id: str, tgw_id: str) -> Tuple[bool, str]:
    """
    Valida que el Transit Gateway Attachment existe y está disponible.

    Args:
        ec2_client: Cliente boto3 de EC2
        vpc_id: ID de la VPC
        tgw_id: ID del Transit Gateway

    Returns:
        Tupla (passed, details)
    """
    try:
        response = ec2_client.describe_transit_gateway_vpc_attachments(
            Filters=[
                {'Name': 'vpc-id', 'Values': [vpc_id]},
                {'Name': 'transit-gateway-id', 'Values': [tgw_id]},
            ]
        )

        attachments = response.get('TransitGatewayVpcAttachments', [])
        if not attachments:
            return False, "No se encontró attachment"

        attachment = attachments[0]
        state = attachment['State']
        attachment_id = attachment['TransitGatewayAttachmentId']

        if state == 'available':
            return True, f"ID: {attachment_id}, Estado: {state}"
        elif state == 'pending':
            return False, f"ID: {attachment_id}, Estado: {state} (aún creándose)"
        else:
            return False, f"ID: {attachment_id}, Estado: {state}"

    except Exception as e:
        return False, f"Error: {str(e)}"


def validate_vpc_endpoints(ec2_client, vpc_id: str, expected_services: List[str]) -> Dict[str, Tuple[bool, str]]:
    """
    Valida que los VPC Endpoints existen y están disponibles.

    Args:
        ec2_client: Cliente boto3 de EC2
        vpc_id: ID de la VPC
        expected_services: Lista de servicios esperados

    Returns:
        Diccionario con resultados por servicio
    """
    results = {}

    try:
        response = ec2_client.describe_vpc_endpoints(
            Filters=[
                {'Name': 'vpc-id', 'Values': [vpc_id]},
            ]
        )

        endpoints = {e['ServiceName'].split('.')[-1]: e for e in response.get('VpcEndpoints', [])}

        for service in expected_services:
            # Normalizar nombre del servicio
            service_key = service.replace('.', '-') if '.' in service else service

            # Buscar endpoint
            found = None
            for key, endpoint in endpoints.items():
                if service in endpoint['ServiceName']:
                    found = endpoint
                    break

            if found:
                state = found['State']
                endpoint_id = found['VpcEndpointId']
                private_dns = found.get('PrivateDnsEnabled', False)

                if state == 'available':
                    if private_dns or found['VpcEndpointType'] == 'Gateway':
                        results[service] = (True, f"ID: {endpoint_id}, DNS Privado: {'Sí' if private_dns else 'N/A (Gateway)'}")
                    else:
                        results[service] = (False, f"ID: {endpoint_id}, DNS Privado: DESHABILITADO (crítico)")
                else:
                    results[service] = (False, f"ID: {endpoint_id}, Estado: {state}")
            else:
                results[service] = (False, "No encontrado")

    except Exception as e:
        for service in expected_services:
            results[service] = (False, f"Error: {str(e)}")

    return results


def validate_routes(ec2_client, route_table_ids: List[str], expected_cidrs: List[str], tgw_id: str) -> Dict[str, Tuple[bool, str]]:
    """
    Valida que las rutas hacia el Transit Gateway existen.

    Args:
        ec2_client: Cliente boto3 de EC2
        route_table_ids: Lista de IDs de route tables
        expected_cidrs: CIDRs esperados
        tgw_id: ID del Transit Gateway

    Returns:
        Diccionario con resultados por CIDR
    """
    results = {cidr: (False, "No encontrada") for cidr in expected_cidrs}

    try:
        response = ec2_client.describe_route_tables(RouteTableIds=route_table_ids)

        for rt in response.get('RouteTables', []):
            rt_id = rt['RouteTableId']
            for route in rt.get('Routes', []):
                dest = route.get('DestinationCidrBlock', '')
                gateway = route.get('TransitGatewayId', '')

                for cidr in expected_cidrs:
                    if dest == cidr:
                        if gateway == tgw_id:
                            results[cidr] = (True, f"RT: {rt_id} -> TGW: {gateway}")
                        else:
                            results[cidr] = (False, f"RT: {rt_id} -> Gateway incorrecto: {gateway}")

    except Exception as e:
        for cidr in expected_cidrs:
            results[cidr] = (False, f"Error: {str(e)}")

    return results


def validate_security_groups(ec2_client, vpc_id: str, sg_name_pattern: str) -> Tuple[bool, str]:
    """
    Valida que los Security Groups existen.

    Args:
        ec2_client: Cliente boto3 de EC2
        vpc_id: ID de la VPC
        sg_name_pattern: Patrón de nombre a buscar

    Returns:
        Tupla (passed, details)
    """
    try:
        response = ec2_client.describe_security_groups(
            Filters=[
                {'Name': 'vpc-id', 'Values': [vpc_id]},
                {'Name': 'group-name', 'Values': [f'*{sg_name_pattern}*']},
            ]
        )

        sgs = response.get('SecurityGroups', [])
        if sgs:
            sg_ids = [sg['GroupId'] for sg in sgs]
            return True, f"Encontrados: {', '.join(sg_ids)}"
        else:
            return False, "No encontrado"

    except Exception as e:
        return False, f"Error: {str(e)}"


def validate_dns_settings(ec2_client, vpc_id: str) -> Tuple[bool, str]:
    """
    Valida que la VPC tiene DNS habilitado.

    Args:
        ec2_client: Cliente boto3 de EC2
        vpc_id: ID de la VPC

    Returns:
        Tupla (passed, details)
    """
    try:
        dns_support = ec2_client.describe_vpc_attribute(
            VpcId=vpc_id,
            Attribute='enableDnsSupport'
        )['EnableDnsSupport']['Value']

        dns_hostnames = ec2_client.describe_vpc_attribute(
            VpcId=vpc_id,
            Attribute='enableDnsHostnames'
        )['EnableDnsHostnames']['Value']

        if dns_support and dns_hostnames:
            return True, "DNS Support: Sí, DNS Hostnames: Sí"
        else:
            return False, f"DNS Support: {'Sí' if dns_support else 'No'}, DNS Hostnames: {'Sí' if dns_hostnames else 'No'}"

    except Exception as e:
        return False, f"Error: {str(e)}"


def main():
    """Función principal de validación."""
    parser = argparse.ArgumentParser(description='Validar conectividad EKS-TGW')
    parser.add_argument('--region', default='us-east-1', help='Región de AWS')
    parser.add_argument('--vpc-id', help='ID de la VPC (opcional, se obtiene de Pulumi)')
    parser.add_argument('--tgw-id', help='ID del Transit Gateway (opcional, se obtiene de Pulumi)')
    args = parser.parse_args()

    print_header("VALIDACIÓN DE CONECTIVIDAD EKS-TRANSIT GATEWAY")
    print(f"\nRegión: {args.region}")

    # Inicializar cliente EC2
    ec2_client = boto3.client('ec2', region_name=args.region)

    # Obtener configuración de Pulumi
    print("\n📋 Obteniendo configuración de Pulumi...")

    config = get_pulumi_output("eksConnectivityConfig")
    if config:
        vpc_id = args.vpc_id or config.get('cluster', {}).get('vpc_id')
        tgw_id = args.tgw_id or config.get('transitGateway', {}).get('id')
        cluster_name = config.get('cluster', {}).get('name', 'eks')
    else:
        print(f"{Colors.YELLOW}⚠️  No se pudo obtener configuración de Pulumi, usando argumentos{Colors.END}")
        vpc_id = args.vpc_id
        tgw_id = args.tgw_id
        cluster_name = 'eks'

    if not vpc_id or not tgw_id:
        print(f"{Colors.RED}❌ Error: Se requiere vpc-id y tgw-id{Colors.END}")
        sys.exit(1)

    print(f"VPC ID: {vpc_id}")
    print(f"Transit Gateway ID: {tgw_id}")

    all_passed = True

    # 1. Validar DNS de VPC
    print_header("1. CONFIGURACIÓN DNS DE VPC")
    passed, details = validate_dns_settings(ec2_client, vpc_id)
    print_check("DNS habilitado en VPC", passed, details)
    all_passed = all_passed and passed

    # 2. Validar Transit Gateway Attachment
    print_header("2. TRANSIT GATEWAY ATTACHMENT")
    passed, details = validate_tgw_attachment(ec2_client, vpc_id, tgw_id)
    print_check("TGW Attachment disponible", passed, details)
    all_passed = all_passed and passed

    # 3. Validar VPC Endpoints Interface
    print_header("3. VPC ENDPOINTS (INTERFACE)")
    interface_services = ["ecr.dkr", "ecr.api", "ec2", "sts", "logs", "elasticloadbalancing", "autoscaling"]
    results = validate_vpc_endpoints(ec2_client, vpc_id, interface_services)
    for service, (passed, details) in results.items():
        print_check(f"Endpoint {service}", passed, details)
        all_passed = all_passed and passed

    # 4. Validar VPC Endpoints Gateway
    print_header("4. VPC ENDPOINTS (GATEWAY - GRATIS)")
    gateway_services = ["s3", "dynamodb"]
    results = validate_vpc_endpoints(ec2_client, vpc_id, gateway_services)
    for service, (passed, details) in results.items():
        print_check(f"Endpoint {service}", passed, details)
        all_passed = all_passed and passed

    # 5. Validar rutas
    print_header("5. RUTAS A TRANSIT GATEWAY")

    # Obtener route tables de la VPC
    try:
        rt_response = ec2_client.describe_route_tables(
            Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
        )
        route_table_ids = [rt['RouteTableId'] for rt in rt_response.get('RouteTables', [])]
    except Exception as e:
        route_table_ids = []
        print(f"{Colors.RED}Error obteniendo route tables: {e}{Colors.END}")

    expected_cidrs = ["172.16.70.0/24", "172.33.0.0/16"]
    if route_table_ids:
        results = validate_routes(ec2_client, route_table_ids, expected_cidrs, tgw_id)
        for cidr, (passed, details) in results.items():
            print_check(f"Ruta a {cidr}", passed, details)
            all_passed = all_passed and passed
    else:
        print(f"{Colors.RED}❌ No se encontraron route tables{Colors.END}")
        all_passed = False

    # 6. Resumen
    print_header("RESUMEN")
    if all_passed:
        print(f"\n{Colors.GREEN}{Colors.BOLD}✅ TODAS LAS VALIDACIONES PASARON{Colors.END}")
        print("\nLa conectividad EKS-Transit Gateway está configurada correctamente.")
        print("\nPróximos pasos:")
        print("  1. Probar conectividad desde un pod:")
        print("     kubectl run test --rm -it --image=amazonlinux:2 -- bash")
        print("  2. Verificar pull de imágenes ECR")
        print("  3. Verificar conectividad a Vimenca (ping 172.16.70.1)")
    else:
        print(f"\n{Colors.RED}{Colors.BOLD}❌ ALGUNAS VALIDACIONES FALLARON{Colors.END}")
        print("\nPor favor revise los errores arriba y corrija la configuración.")
        sys.exit(1)

    # 7. Mostrar costos estimados
    print_header("COSTOS ESTIMADOS")
    cost_breakdown = get_pulumi_output("costBreakdown")
    if cost_breakdown:
        monthly = cost_breakdown.get('monthly', {})
        comparison = cost_breakdown.get('comparison', {})

        print(f"\n{Colors.BOLD}Costos Mensuales:{Colors.END}")
        print(f"  TGW Attachment:           {monthly.get('tgw_attachment', 'N/A')}")
        print(f"  VPC Endpoints Interface:  {monthly.get('vpc_endpoints_interface', 'N/A')}")
        print(f"  VPC Endpoints Gateway:    {monthly.get('vpc_endpoints_gateway', 'N/A')}")
        print(f"  Data Processing:          {monthly.get('data_processing_tgw', 'N/A')}")
        print(f"  {Colors.BOLD}Total Estimado:           {monthly.get('estimated_total', 'N/A')}{Colors.END}")

        print(f"\n{Colors.BOLD}Comparación vs NAT Gateway:{Colors.END}")
        print(f"  Solución NAT Gateway:     {comparison.get('nat_gateway_solution', 'N/A')}")
        print(f"  Esta solución:            {comparison.get('this_solution', 'N/A')}")
        print(f"  {Colors.GREEN}Ahorro mensual:           {comparison.get('monthly_savings', 'N/A')}{Colors.END}")


if __name__ == "__main__":
    main()
