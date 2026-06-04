#!/bin/bash
#
# Script de prueba de conectividad VPN
#
# Este script verifica la conectividad entre AWS y Vimenca
# después de configurar el Transit Gateway y la VPN.
#
# Uso: ./test-vpn-connectivity.sh [--from-pod]
#

set -e

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

# Configuración
VIMENCA_CIDR="172.16.70.0/24"
VIMENCA_TEST_IP="172.16.70.1"
ORGANIZATION_CIDRS=("172.33.6.0/28" "172.33.16.0/28")
REGION="${AWS_REGION:-us-east-1}"
AWS_PROFILE="${AWS_PROFILE:-default}"

print_header() {
    echo -e "\n${BLUE}${BOLD}════════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}${BOLD}  $1${NC}"
    echo -e "${BLUE}${BOLD}════════════════════════════════════════════════════════════════════════════════${NC}"
}

print_check() {
    local name=$1
    local status=$2
    local details=$3

    if [ "$status" = "PASS" ]; then
        echo -e "  ${GREEN}✅ PASS${NC} $name"
    elif [ "$status" = "FAIL" ]; then
        echo -e "  ${RED}❌ FAIL${NC} $name"
    else
        echo -e "  ${YELLOW}⏳ $status${NC} $name"
    fi

    if [ -n "$details" ]; then
        echo -e "       ${YELLOW}$details${NC}"
    fi
}

print_header "TEST DE CONECTIVIDAD VPN - Organization <-> Vimenca"
echo -e "\nFecha: $(date)"
echo -e "Región: $REGION"
echo -e "Profile: $AWS_PROFILE"

# ============================================================================
# 1. Verificar VPN Connection Status
# ============================================================================
print_header "1. ESTADO DE VPN CONNECTION"

echo -e "\nObteniendo información de VPN..."
VPN_INFO=$(aws ec2 describe-vpn-connections \
    --filters "Name=state,Values=available,pending" \
    --query 'VpnConnections[0]' \
    --region $REGION \
    --profile $AWS_PROFILE \
    --output json 2>/dev/null || echo "{}")

if [ "$VPN_INFO" != "{}" ] && [ "$VPN_INFO" != "null" ]; then
    VPN_ID=$(echo $VPN_INFO | jq -r '.VpnConnectionId')
    VPN_STATE=$(echo $VPN_INFO | jq -r '.State')
    TUNNEL1_STATUS=$(echo $VPN_INFO | jq -r '.VgwTelemetry[0].Status')
    TUNNEL2_STATUS=$(echo $VPN_INFO | jq -r '.VgwTelemetry[1].Status')
    TUNNEL1_IP=$(echo $VPN_INFO | jq -r '.VgwTelemetry[0].OutsideIpAddress')
    TUNNEL2_IP=$(echo $VPN_INFO | jq -r '.VgwTelemetry[1].OutsideIpAddress')

    echo -e "\nVPN Connection ID: ${BOLD}$VPN_ID${NC}"
    echo -e "Estado: ${BOLD}$VPN_STATE${NC}"
    echo ""

    if [ "$VPN_STATE" = "available" ]; then
        print_check "VPN Connection disponible" "PASS" "ID: $VPN_ID"
    else
        print_check "VPN Connection disponible" "FAIL" "Estado: $VPN_STATE"
    fi

    echo -e "\nTúneles:"
    echo -e "  Túnel 1: $TUNNEL1_IP"
    if [ "$TUNNEL1_STATUS" = "UP" ]; then
        print_check "  Estado Túnel 1" "PASS" "UP"
    else
        print_check "  Estado Túnel 1" "FAIL" "$TUNNEL1_STATUS (esperando configuración en Vimenca)"
    fi

    echo -e "  Túnel 2: $TUNNEL2_IP"
    if [ "$TUNNEL2_STATUS" = "UP" ]; then
        print_check "  Estado Túnel 2" "PASS" "UP"
    else
        print_check "  Estado Túnel 2" "FAIL" "$TUNNEL2_STATUS (esperando configuración en Vimenca)"
    fi
else
    print_check "VPN Connection" "FAIL" "No se encontró VPN Connection"
fi

# ============================================================================
# 2. Verificar Customer Gateway
# ============================================================================
print_header "2. CUSTOMER GATEWAY (Vimenca)"

CGW_INFO=$(aws ec2 describe-customer-gateways \
    --filters "Name=state,Values=available" \
    --query 'CustomerGateways[0]' \
    --region $REGION \
    --profile $AWS_PROFILE \
    --output json 2>/dev/null || echo "{}")

if [ "$CGW_INFO" != "{}" ] && [ "$CGW_INFO" != "null" ]; then
    CGW_ID=$(echo $CGW_INFO | jq -r '.CustomerGatewayId')
    CGW_IP=$(echo $CGW_INFO | jq -r '.IpAddress')
    CGW_STATE=$(echo $CGW_INFO | jq -r '.State')

    if [ "$CGW_STATE" = "available" ]; then
        print_check "Customer Gateway disponible" "PASS" "ID: $CGW_ID, IP: $CGW_IP"
    else
        print_check "Customer Gateway disponible" "FAIL" "Estado: $CGW_STATE"
    fi
else
    print_check "Customer Gateway" "FAIL" "No encontrado"
fi

# ============================================================================
# 3. Verificar Transit Gateway Attachment
# ============================================================================
print_header "3. TRANSIT GATEWAY ATTACHMENT"

TGW_ATTACH=$(aws ec2 describe-transit-gateway-attachments \
    --filters "Name=resource-type,Values=vpc" \
    --query 'TransitGatewayAttachments[0]' \
    --region $REGION \
    --profile $AWS_PROFILE \
    --output json 2>/dev/null || echo "{}")

if [ "$TGW_ATTACH" != "{}" ] && [ "$TGW_ATTACH" != "null" ]; then
    ATTACH_ID=$(echo $TGW_ATTACH | jq -r '.TransitGatewayAttachmentId')
    ATTACH_STATE=$(echo $TGW_ATTACH | jq -r '.State')
    TGW_ID=$(echo $TGW_ATTACH | jq -r '.TransitGatewayId')

    if [ "$ATTACH_STATE" = "available" ]; then
        print_check "TGW Attachment disponible" "PASS" "ID: $ATTACH_ID, TGW: $TGW_ID"
    else
        print_check "TGW Attachment disponible" "FAIL" "Estado: $ATTACH_STATE"
    fi
else
    print_check "TGW Attachment" "FAIL" "No encontrado"
fi

# ============================================================================
# 4. Verificar VPC Endpoints
# ============================================================================
print_header "4. VPC ENDPOINTS"

ENDPOINTS=$(aws ec2 describe-vpc-endpoints \
    --filters "Name=vpc-endpoint-state,Values=available" \
    --query 'VpcEndpoints[].ServiceName' \
    --region $REGION \
    --profile $AWS_PROFILE \
    --output json 2>/dev/null || echo "[]")

EXPECTED_ENDPOINTS=("ecr.dkr" "ecr.api" "ec2" "sts" "logs" "elasticloadbalancing" "s3")

for endpoint in "${EXPECTED_ENDPOINTS[@]}"; do
    if echo "$ENDPOINTS" | grep -q "$endpoint"; then
        print_check "Endpoint $endpoint" "PASS" "disponible"
    else
        print_check "Endpoint $endpoint" "FAIL" "no encontrado"
    fi
done

# ============================================================================
# 5. Verificar Route Tables
# ============================================================================
print_header "5. RUTAS A VIMENCA"

ROUTES=$(aws ec2 describe-route-tables \
    --query 'RouteTables[].Routes[?TransitGatewayId!=`null`]' \
    --region $REGION \
    --profile $AWS_PROFILE \
    --output json 2>/dev/null || echo "[]")

if echo "$ROUTES" | grep -q "$VIMENCA_CIDR"; then
    print_check "Ruta a Vimenca ($VIMENCA_CIDR)" "PASS" "via Transit Gateway"
else
    print_check "Ruta a Vimenca ($VIMENCA_CIDR)" "FAIL" "no encontrada"
fi

# ============================================================================
# 6. Verificar archivos de Pre-Shared Keys
# ============================================================================
print_header "6. PRE-SHARED KEYS"

if [ -f "secrets/tunnel1-psk.txt" ]; then
    print_check "PSK Túnel 1" "PASS" "secrets/tunnel1-psk.txt existe"
else
    print_check "PSK Túnel 1" "FAIL" "archivo no encontrado"
fi

if [ -f "secrets/tunnel2-psk.txt" ]; then
    print_check "PSK Túnel 2" "PASS" "secrets/tunnel2-psk.txt existe"
else
    print_check "PSK Túnel 2" "FAIL" "archivo no encontrado"
fi

if [ -f "secrets/vpn-config.json" ]; then
    print_check "Configuración VPN" "PASS" "secrets/vpn-config.json existe"
else
    print_check "Configuración VPN" "FAIL" "archivo no encontrado"
fi

# ============================================================================
# 7. Test de conectividad (si se ejecuta desde un pod)
# ============================================================================
if [ "$1" = "--from-pod" ]; then
    print_header "7. TEST DE CONECTIVIDAD (desde pod)"

    echo -e "\n${YELLOW}Ejecutando ping a Vimenca ($VIMENCA_TEST_IP)...${NC}"
    if ping -c 3 -W 5 $VIMENCA_TEST_IP > /dev/null 2>&1; then
        print_check "Ping a Vimenca" "PASS" "$VIMENCA_TEST_IP responde"
    else
        print_check "Ping a Vimenca" "FAIL" "$VIMENCA_TEST_IP no responde (túnel puede no estar UP)"
    fi

    echo -e "\n${YELLOW}Verificando acceso a ECR...${NC}"
    if aws ecr get-login-password --region $REGION > /dev/null 2>&1; then
        print_check "Acceso a ECR" "PASS" "autenticación exitosa"
    else
        print_check "Acceso a ECR" "FAIL" "error de autenticación"
    fi

    echo -e "\n${YELLOW}Verificando acceso a S3...${NC}"
    if aws s3 ls --region $REGION > /dev/null 2>&1; then
        print_check "Acceso a S3" "PASS" "listado exitoso"
    else
        print_check "Acceso a S3" "FAIL" "error de acceso"
    fi
fi

# ============================================================================
# RESUMEN
# ============================================================================
print_header "RESUMEN"

echo -e "
${BOLD}Estado de la infraestructura:${NC}
  - VPN Connection: ${VPN_STATE:-No disponible}
  - Túnel 1: ${TUNNEL1_STATUS:-DOWN}
  - Túnel 2: ${TUNNEL2_STATUS:-DOWN}
  - TGW Attachment: ${ATTACH_STATE:-No disponible}

${BOLD}Archivos generados:${NC}
  - secrets/tunnel1-psk.txt
  - secrets/tunnel2-psk.txt
  - secrets/vpn-config.json
  - vpn-spec.md

${BOLD}Próximos pasos:${NC}"

if [ "$TUNNEL1_STATUS" != "UP" ] || [ "$TUNNEL2_STATUS" != "UP" ]; then
    echo -e "
  ${YELLOW}1. Intercambiar Pre-Shared Keys con Vimenca:${NC}
     Contacto: Eric Frias - 809-487-2679
     Archivos: secrets/tunnel1-psk.txt, secrets/tunnel2-psk.txt

  ${YELLOW}2. Enviar información de configuración a Vimenca:${NC}
     - IPs de túneles AWS: $TUNNEL1_IP, $TUNNEL2_IP
     - Redes Organization: $VIMENCA_CIDR
     - Configuración IPSec: IKEv2, AES256, SHA256, DH Group 14

  ${YELLOW}3. Esperar confirmación de Vimenca y verificar túneles UP${NC}

  ${YELLOW}4. Probar conectividad desde pod EKS:${NC}
     kubectl run vpn-test --rm -it --image=amazonlinux:2 -- bash
     ping 172.16.70.1
"
else
    echo -e "
  ${GREEN}Los túneles VPN están UP!${NC}

  ${YELLOW}1. Probar conectividad desde pod EKS:${NC}
     kubectl run vpn-test --rm -it --image=amazonlinux:2 -- bash
     ping 172.16.70.1
     curl http://172.16.70.X

  ${YELLOW}2. Verificar que los servicios de Vimenca son accesibles${NC}
"
fi

echo -e "${BLUE}════════════════════════════════════════════════════════════════════════════════${NC}"
