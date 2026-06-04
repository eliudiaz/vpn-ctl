#!/bin/bash

#===============================================================================
# VPN Form Filler - Easy Shell Wrapper
#===============================================================================
# Reusable script to fill VPN form with configuration data
#
# Usage:
#   ./fill-form.sh atg                      # Use ATG defaults + config
#   ./fill-form.sh config <json-file>       # Use custom JSON config
#   ./fill-form.sh custom --ip X --device Y # Use custom parameters
#   ./fill-form.sh help                     # Show help
#===============================================================================

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/venv-docx"
PYTHON="${VENV_DIR}/bin/python"

# Check if venv exists
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}Creating Python environment for DOCX processing...${NC}"
    python3 -m venv "$VENV_DIR" --upgrade-deps
    source "${VENV_DIR}/bin/activate"
    pip install python-docx -q
    deactivate
fi

# Activate venv
source "${VENV_DIR}/bin/activate"

# Print help
show_help() {
    cat << EOF

${BLUE}╔══════════════════════════════════════════════════════════════════════════════╗${NC}
${BLUE}║                       VPN Form Filler - Help                                  ║${NC}
${BLUE}╚══════════════════════════════════════════════════════════════════════════════╝${NC}

${GREEN}USAGE:${NC}
  ./fill-form.sh [COMMAND] [OPTIONS]

${GREEN}COMMANDS:${NC}

  ${BLUE}atg${NC}                    Fill form with ATG defaults and configuration
  ${BLUE}config <json-file>${NC}      Fill form with custom JSON configuration
  ${BLUE}custom [OPTIONS]${NC}        Fill form with custom parameters
  ${BLUE}help${NC}                   Show this help message

${GREEN}OPTIONS (for 'custom' command):${NC}

  --template FILE              Path to VPN form template
  --output FILE                Output file path
  --org-ip IP             Organization VPN IP address
  --org-device DEVICE     Organization VPN device type
  --org-cidr CIDR         Organization source CIDR

${GREEN}EXAMPLES:${NC}

  # Fill with ATG defaults
  $ ./fill-form.sh atg

  # Fill with ATG config and save as custom name
  $ ./fill-form.sh atg --output my-form.docx

  # Fill with custom JSON config
  $ ./fill-form.sh config my-vpn-config.json

  # Fill with custom parameters
  $ ./fill-form.sh custom \\
      --org-ip 3.151.94.15 \\
      --org-device "AWS Transit Gateway" \\
      --output form.docx

${GREEN}OUTPUT:${NC}
  Generated file will be created in current directory with timestamp
  Example: Form_VPN_Filled_20251225_225530.docx

${GREEN}NOTES:${NC}
  • MockPeerA section will be left BLANK for manual completion
  • Organization section will be filled with provided configuration
  • All signature fields will be left blank for manual signatures
  • A Python virtual environment will be created automatically

EOF
}

# Main function
main() {
    local command="${1:-}"
    shift || true

    case "$command" in
        atg)
            echo -e "${GREEN}Filling form with ATG configuration...${NC}\n"
            python "$SCRIPT_DIR/fill-vpn-form.py" --use-atg "$@"
            ;;

        config)
            local config_file="${1:-}"
            if [ -z "$config_file" ]; then
                echo -e "${RED}ERROR: Config file required${NC}"
                echo "Usage: ./fill-form.sh config <json-file>"
                exit 1
            fi
            echo -e "${GREEN}Filling form with configuration: $config_file${NC}\n"
            python "$SCRIPT_DIR/fill-vpn-form.py" --config "$config_file" "${@:2}"
            ;;

        custom)
            echo -e "${GREEN}Filling form with custom parameters...${NC}\n"
            python "$SCRIPT_DIR/fill-vpn-form.py" "$@"
            ;;

        help|--help|-h)
            show_help
            ;;

        "")
            echo -e "${RED}ERROR: Command required${NC}\n"
            show_help
            exit 1
            ;;

        *)
            echo -e "${RED}ERROR: Unknown command: $command${NC}\n"
            show_help
            exit 1
            ;;
    esac
}

# Run main
main "$@"
