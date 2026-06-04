#!/bin/bash
#
# Script para desplegar infraestructura con Pulumi - Conectividad EKS-TGW
#
# Este script ejecuta 'pulumi up' para conectar la VPC de EKS al Transit Gateway
# sin NAT Gateway, usando VPC Endpoints para acceso a servicios AWS.
#
# Uso: ./pulumi-up.sh [stack-name] [--yes]
#
# Ejemplo:
#   ./pulumi-up.sh dev         # Pide confirmación
#   ./pulumi-up.sh prod --yes  # Sin confirmación (para CI/CD)
#

set -e

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

echo -e "${BLUE}════════════════════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  PULUMI UP - Conectividad EKS a Transit Gateway (sin NAT)${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════════════════════${NC}"

# Verificar que Pulumi está instalado
if ! command -v pulumi &> /dev/null; then
    echo -e "${RED}Error: Pulumi no está instalado${NC}"
    echo "Instalar con: curl -fsSL https://get.pulumi.com | sh"
    exit 1
fi

# Verificar que estamos en el directorio correcto
if [ ! -f "pulumi/Pulumi.yaml" ]; then
    echo -e "${RED}Error: No se encontró pulumi/Pulumi.yaml${NC}"
    echo "Ejecutar este script desde el directorio raíz del proyecto"
    exit 1
fi

# Change to pulumi directory
cd pulumi

# Parsear argumentos
STACK_NAME="dev"
AUTO_APPROVE=""

for arg in "$@"; do
    case $arg in
        --yes|-y)
            AUTO_APPROVE="--yes"
            ;;
        *)
            STACK_NAME=$arg
            ;;
    esac
done

echo -e "\n${YELLOW}Stack: ${STACK_NAME}${NC}"
if [ -n "$AUTO_APPROVE" ]; then
    echo -e "${YELLOW}Modo: Auto-approve habilitado${NC}"
fi

# Crear virtualenv si no existe
if [ ! -d "venv" ]; then
    echo -e "\n${YELLOW}Creando entorno virtual...${NC}"
    python3 -m venv venv
fi

# Activar virtualenv e instalar dependencias
echo -e "\n${YELLOW}Instalando dependencias...${NC}"
source ../venv/bin/activate 2>/dev/null || python3 -m venv ../venv && source ../venv/bin/activate
pip install -q -r ../requirements.txt

# Configurar PULUMI_PYTHON_COMMAND para usar el Python del venv
export PULUMI_PYTHON_COMMAND=$(cd .. && pwd)/venv/bin/python3

# Seleccionar o crear stack
echo -e "\n${YELLOW}Seleccionando stack ${STACK_NAME}...${NC}"
pulumi stack select ${STACK_NAME} 2>/dev/null || pulumi stack init ${STACK_NAME}

# Verificar configuración requerida
echo -e "\n${YELLOW}Verificando configuración...${NC}"

check_config() {
    local key=$1
    local value=$(pulumi config get ${key} 2>/dev/null || echo "")
    if [ -z "$value" ]; then
        echo -e "${RED}  ✗ ${key} no configurado${NC}"
        return 1
    else
        echo -e "${GREEN}  ✓ ${key}: ${value}${NC}"
        return 0
    fi
}

CONFIG_OK=true

check_config "aws:region" || CONFIG_OK=false
check_config "eks_cluster_name" || CONFIG_OK=false
check_config "transit_gateway_id" || CONFIG_OK=false

if [ "$CONFIG_OK" = false ]; then
    echo -e "\n${RED}════════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${RED}Error: Configuración incompleta${NC}"
    echo -e "${RED}════════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "\nConfigurar valores requeridos:"
    echo -e "  pulumi config set aws:region us-east-1"
    echo -e "  pulumi config set eks_cluster_name <nombre-cluster>"
    echo -e "  pulumi config set transit_gateway_id tgw-xxxxx"
    echo -e "\nOpcionales:"
    echo -e "  pulumi config set vimenca_cidr 172.16.70.0/24"
    echo -e "  pulumi config set vpn_cidrs 172.33.6.0/28,172.33.16.0/28"
    exit 1
fi

# Advertencia antes del deploy
if [ -z "$AUTO_APPROVE" ]; then
    echo -e "\n${YELLOW}════════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${YELLOW}  ADVERTENCIA${NC}"
    echo -e "${YELLOW}════════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "
Este script creará los siguientes recursos en AWS:

  ${BOLD}Transit Gateway:${NC}
    - 1 VPC Attachment al Transit Gateway existente

  ${BOLD}VPC Endpoints Interface (\$7.20/mes c/u):${NC}
    - ecr.dkr (Docker Registry)
    - ecr.api (ECR API)
    - ec2 (EC2 API)
    - sts (STS para IAM roles)
    - logs (CloudWatch Logs)
    - elasticloadbalancing (ELB)
    - autoscaling (Cluster Autoscaler)

  ${BOLD}VPC Endpoints Gateway (GRATIS):${NC}
    - s3
    - dynamodb

  ${BOLD}Security Groups:${NC}
    - Security Group para VPC Endpoints
    - Security Group para egress de nodos

  ${BOLD}Rutas:${NC}
    - 172.16.70.0/24 -> Transit Gateway (Vimenca)
    - 172.33.0.0/16 -> Transit Gateway (Organization)

  ${GREEN}Costo mensual estimado: \$86-126/mes${NC}
  ${GREEN}Ahorro vs NAT Gateway: \$64-174/mes${NC}
"
fi

# Ejecutar deploy
echo -e "${BLUE}════════════════════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  EJECUTANDO DEPLOY${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════════════════════${NC}"

START_TIME=$(date +%s)

if pulumi up --diff ${AUTO_APPROVE}; then
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))

    echo -e "\n${GREEN}════════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  DEPLOY COMPLETADO EXITOSAMENTE${NC}"
    echo -e "${GREEN}════════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "\nTiempo de ejecución: ${DURATION} segundos"

    # Mostrar estado de túneles VPN
    echo -e "\n${BLUE}════════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  ESTADO DE TÚNELES VPN${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════════════════════════════${NC}"

    python3 << 'PYTHON_EOF'
import subprocess
import json
import os

try:
    env = os.environ.copy()
    result = subprocess.run(
        ['pulumi', 'stack', 'output', 'vpn_tunnel_status', '--json'],
        cwd='pulumi',
        capture_output=True,
        text=True,
        timeout=10,
        env=env
    )

    if result.returncode == 0 and result.stdout.strip():
        data = json.loads(result.stdout)
        for peer, info in data.items():
            print(f"\n{peer}:")
            t1_status = info.get('tunnel1', {}).get('status', 'UNKNOWN')
            t2_status = info.get('tunnel2', {}).get('status', 'UNKNOWN')
            t1_ip = info.get('tunnel1', {}).get('ip', 'N/A')
            t2_ip = info.get('tunnel2', {}).get('ip', 'N/A')

            t1_icon = "✓" if t1_status == "UP" else "✗"
            t2_icon = "✓" if t2_status == "UP" else "✗"

            print(f"  Tunnel1: {t1_icon} {t1_status:4} ({t1_ip})")
            print(f"  Tunnel2: {t2_icon} {t2_status:4} ({t2_ip})")
except Exception as e:
    import traceback
    traceback.print_exc()
PYTHON_EOF

    # Mostrar outputs importantes
    echo -e "\n${YELLOW}Outputs del deploy:${NC}"
    pulumi stack output tgw_attachment_id 2>/dev/null && echo ""
    pulumi stack output endpoint_sg_id 2>/dev/null && echo ""

    # Ejecutar validación automática
    echo -e "\n${YELLOW}════════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${YELLOW}  EJECUTANDO VALIDACIÓN AUTOMÁTICA${NC}"
    echo -e "${YELLOW}════════════════════════════════════════════════════════════════════════════════${NC}"

    REGION=$(pulumi config get aws:region)
    python ../tools/validate.py --region ${REGION}

    # Instrucciones post-deploy
    echo -e "\n${BLUE}════════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  PRÓXIMOS PASOS${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "
1. ${BOLD}Verificar conectividad desde un pod:${NC}
   kubectl run test-connectivity --rm -it --image=amazonlinux:2 -- bash

2. ${BOLD}Dentro del pod, probar:${NC}
   # Test ECR
   aws ecr get-login-password --region ${REGION}

   # Test S3
   aws s3 ls

   # Test Vimenca
   ping -c 3 172.16.70.1

   # Test Organization
   curl -v http://172.33.6.5

3. ${BOLD}Ver outputs completos:${NC}
   pulumi stack output

4. ${BOLD}Ver validación detallada:${NC}
   python ../tools/validate.py --region ${REGION}
"
else
    echo -e "\n${RED}════════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${RED}  ERROR EN EL DEPLOY${NC}"
    echo -e "${RED}════════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "\nRevise los errores arriba y corrija la configuración."
    echo -e "Para ver el estado actual: pulumi stack"
    exit 1
fi
