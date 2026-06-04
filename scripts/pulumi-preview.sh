#!/bin/bash
#
# Script para previsualizar cambios de Pulumi - Conectividad EKS-TGW
#
# Este script ejecuta 'pulumi preview' con la configuración necesaria
# para conectar la VPC de EKS al Transit Gateway sin NAT Gateway.
#
# Uso: ./pulumi-preview.sh [stack-name]
#
# Ejemplo:
#   ./pulumi-preview.sh dev
#   ./pulumi-preview.sh prod
#

set -e

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}════════════════════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  PULUMI PREVIEW - Conectividad EKS a Transit Gateway (sin NAT)${NC}"
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

# Stack name (opcional)
STACK_NAME=${1:-"dev"}

echo -e "\n${YELLOW}Stack: ${STACK_NAME}${NC}"

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

# Valores opcionales (tienen defaults)
echo -e "\n${YELLOW}Configuración opcional (con defaults):${NC}"
pulumi config get mock-peer-a_cidr 2>/dev/null && echo -e "${GREEN}  ✓ mock-peer-a_cidr configurado${NC}" || echo -e "${YELLOW}  - mock-peer-a_cidr: usando default (172.16.70.0/24)${NC}"
pulumi config get vpn_cidrs 2>/dev/null && echo -e "${GREEN}  ✓ vpn_cidrs configurado${NC}" || echo -e "${YELLOW}  - vpn_cidrs: usando default (172.33.6.0/28,172.33.16.0/28)${NC}"

if [ "$CONFIG_OK" = false ]; then
    echo -e "\n${RED}════════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${RED}Error: Configuración incompleta${NC}"
    echo -e "${RED}════════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "\nConfigurar valores requeridos:"
    echo -e "  pulumi config set aws:region us-east-1"
    echo -e "  pulumi config set eks_cluster_name <nombre-cluster>"
    echo -e "  pulumi config set transit_gateway_id tgw-xxxxx"
    echo -e "\nOpcionales:"
    echo -e "  pulumi config set mock-peer-a_cidr 172.16.70.0/24"
    echo -e "  pulumi config set vpn_cidrs 172.33.6.0/28,172.33.16.0/28"
    exit 1
fi

# Mostrar estimación de costos
echo -e "\n${BLUE}════════════════════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  ESTIMACIÓN DE COSTOS${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════════════════════${NC}"
echo -e "
  ${GREEN}Esta solución (sin NAT Gateway):${NC}
    - TGW Attachment:           \$36/mes
    - VPC Endpoints Interface:  \$50.40/mes (7 endpoints x \$7.20)
    - VPC Endpoints Gateway:    \$0/mes (GRATIS)
    - Data Processing:          \$0.02/GB
    - ${GREEN}Total estimado:           \$86-126/mes${NC}

  ${RED}Solución con NAT Gateway:${NC}
    - NAT Gateway:              \$96/mes (3 AZs x \$32)
    - Data Processing:          \$0.045/GB
    - ${RED}Total estimado:           \$150-300/mes${NC}

  ${GREEN}AHORRO MENSUAL: \$64-174/mes (40-60%)${NC}
"

# Ejecutar preview
echo -e "${BLUE}════════════════════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  EJECUTANDO PREVIEW${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════════════════════${NC}"

pulumi preview --diff

echo -e "\n${GREEN}════════════════════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  PREVIEW COMPLETADO${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════════════════════════${NC}"
echo -e "\nPara aplicar los cambios, ejecutar:"
echo -e "  ${YELLOW}./pulumi-up.sh ${STACK_NAME}${NC}"
echo ""
