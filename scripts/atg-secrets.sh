#!/bin/bash

#===============================================================================
# ATG VPN Secrets Management Script
#===============================================================================
# Script para gestionar secrets VPN de forma segura
#
# Uso:
#   ./atg-secrets.sh validate              # Validar secrets
#   ./atg-secrets.sh get-psk-1             # Obtener PSK Túnel 1
#   ./atg-secrets.sh get-psk-2             # Obtener PSK Túnel 2
#   ./atg-secrets.sh get-all-psks           # Obtener ambas PSKs
#   ./atg-secrets.sh generate-checkpoint    # Generar config Checkpoint
#   ./atg-secrets.sh test-vpn               # Probar conectividad VPN
#   ./atg-secrets.sh help                  # Mostrar esta ayuda
#===============================================================================

set -euo pipefail

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Directorios
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SECRETS_DIR="${SCRIPT_DIR}/secrets"
PYTHON_SCRIPT="${SCRIPT_DIR}/retrieve-vpn-secrets.py"

# Verificar que Python script existe
if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo -e "${RED}ERROR: Script Python no encontrado: ${PYTHON_SCRIPT}${NC}"
    exit 1
fi

# Verificar que secrets directory existe
if [ ! -d "$SECRETS_DIR" ]; then
    echo -e "${RED}ERROR: Directorio de secrets no encontrado: ${SECRETS_DIR}${NC}"
    exit 1
fi

# Verificar Python 3
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}ERROR: Python 3 no está instalado${NC}"
    exit 1
fi

# Función para imprimir encabezado
print_header() {
    echo ""
    echo -e "${BLUE}===============================================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}===============================================================================${NC}"
    echo ""
}

# Función para imprimir success
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

# Función para imprimir error
print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# Función para imprimir warning
print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# Función para imprimir info
print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# Función de ayuda
show_help() {
    cat << EOF

${BLUE}╔══════════════════════════════════════════════════════════════════════════════╗${NC}
${BLUE}║                    ATG VPN Secrets Management - Ayuda                         ║${NC}
${BLUE}╚══════════════════════════════════════════════════════════════════════════════╝${NC}

${GREEN}OPCIONES:${NC}

  ${BLUE}validate${NC}               Validar integridad de todos los secrets
  ${BLUE}get-psk-1${NC}              Mostrar PSK del Túnel 1 (Primario)
  ${BLUE}get-psk-2${NC}              Mostrar PSK del Túnel 2 (Backup)
  ${BLUE}get-all-psks${NC}           Mostrar ambas PSKs (con confirmación)
  ${BLUE}generate-checkpoint${NC}    Generar configuración para Checkpoint Firewall
  ${BLUE}test-vpn${NC}               Probar conectividad VPN desde AWS
  ${BLUE}help${NC}                   Mostrar esta ayuda

${GREEN}EJEMPLOS:${NC}

  # Validar todos los secrets
  $ ./atg-secrets.sh validate

  # Obtener PSK Túnel 1 para dictar por teléfono
  $ ./atg-secrets.sh get-psk-1

  # Generar archivo de configuración Checkpoint
  $ ./atg-secrets.sh generate-checkpoint

  # Probar que VPN está conectada
  $ ./atg-secrets.sh test-vpn

${GREEN}SEGURIDAD:${NC}

  ✓ Las PSKs se muestran solo con confirmación interactiva
  ✓ Se registran todas las acciones en vpn-secrets-audit.log
  ✓ Los archivos se crean con permisos restrictivos (0o600)
  ✓ Las PSKs deben intercambiarse por TELÉFONO, nunca por email

${GREEN}CONTACTOS VIMENCA:${NC}

  • Eric Frias (Principal): 809-487-2679
  • Fermir Quezada (Secundario): 809-487-2602

${GREEN}CONTACTOS ORGANIZATION:${NC}

  • Josué Ubico (Principal): 809.274.0000
  • Ricardo Peña (Secundario): 809.274.0000

EOF
}

# Función main
main() {
    local action="${1:-help}"
    local region="${2:-us-east-1}"
    local profile="${3:-}"

    case "$action" in
        validate)
            print_header "VALIDANDO SECRETS VPN"
            python3 "$PYTHON_SCRIPT" --action validate --region "$region" ${profile:+--profile "$profile"}
            ;;

        get-psk-1)
            print_header "OBTENIENDO PSK - TÚNEL 1 (PRIMARIO)"
            python3 "$PYTHON_SCRIPT" --action get-tunnel1 --region "$region" ${profile:+--profile "$profile"}
            ;;

        get-psk-2)
            print_header "OBTENIENDO PSK - TÚNEL 2 (BACKUP)"
            python3 "$PYTHON_SCRIPT" --action get-tunnel2 --region "$region" ${profile:+--profile "$profile"}
            ;;

        get-all-psks)
            print_header "OBTENIENDO TODAS LAS PSKs"
            python3 "$PYTHON_SCRIPT" --action get-all --region "$region" ${profile:+--profile "$profile"}
            ;;

        generate-checkpoint)
            print_header "GENERANDO CONFIGURACIÓN CHECKPOINT"
            local output_file="${SCRIPT_DIR}/checkpoint-vpn-config.txt"
            python3 "$PYTHON_SCRIPT" --action generate-config \
                --region "$region" \
                --output "$output_file" \
                ${profile:+--profile "$profile"}
            if [ $? -eq 0 ]; then
                print_success "Configuración generada: $output_file"
                print_warning "CONFIDENCIAL - Proteger este archivo"
                print_info "Permisos del archivo: $(stat -f '%OLp' "$output_file" 2>/dev/null || stat -c '%a' "$output_file" 2>/dev/null)"
            fi
            ;;

        test-vpn)
            print_header "PROBANDO CONECTIVIDAD VPN"
            python3 "$PYTHON_SCRIPT" --action test-connectivity --region "$region" ${profile:+--profile "$profile"}
            ;;

        help|--help|-h)
            show_help
            ;;

        *)
            print_error "Opción desconocida: $action"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# Ejecutar main
main "$@"
