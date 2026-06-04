#!/bin/bash

################################################################################
# test-all-providers.sh
# Test connectivity to all VPN provider targets
# Usage: ./test-all-providers.sh [provider|all]
# Examples:
#   ./test-all-providers.sh vimenca
#   ./test-all-providers.sh org-legacy
#   ./test-all-providers.sh cibao
#   ./test-all-providers.sh all
################################################################################

set -e

PROVIDER="${1:-all}"
NAMESPACE="default"
TEST_TIMEOUT=5

# ANSI Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

################################################################################
# TEST FUNCTIONS
################################################################################

print_header() {
    echo -e "${BLUE}================================================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}================================================================================${NC}"
    echo ""
}

test_ping() {
    local target=$1
    local name=$2

    echo -n "  PING $name ($target)... "

    if kubectl run "test-ping-${RANDOM}" \
        --image=alpine \
        --restart=Never \
        --rm=true \
        -i \
        --quiet \
        -- ping -c 3 -W 2 "$target" > /tmp/ping-result.txt 2>&1; then

        local response_count=$(grep "packets received" /tmp/ping-result.txt | sed -n 's/.*\([0-9][0-9]*\) packets received.*/\1/p' || echo "0")
        if [ "$response_count" -gt 0 ]; then
            local latency=$(grep "min/avg/max" /tmp/ping-result.txt | sed -n 's/.*avg=\([^/]*\).*/\1/p' || echo "?")
            echo -e "${GREEN}✓ OK${NC} ($response_count/3 responses, avg latency: ${latency}ms)"
            return 0
        fi
    fi

    echo -e "${RED}✗ TIMEOUT${NC}"
    return 1
}

test_port() {
    local target=$1
    local name=$2
    local port=$3

    echo -n "  PORT $name ($target:$port)... "

    if kubectl run "test-port-${RANDOM}" \
        --image=busybox \
        --restart=Never \
        --rm=true \
        -i \
        --quiet \
        -- sh -c "timeout $TEST_TIMEOUT nc -zv $target $port 2>&1" > /tmp/port-result.txt 2>&1; then

        echo -e "${GREEN}✓ OK${NC} (port open)"
        return 0
    fi

    echo -e "${RED}✗ TIMEOUT${NC} (port closed or blocked)"
    return 1
}

test_http() {
    local target=$1
    local name=$2
    local url="http://$target/health"

    echo -n "  HTTP $name ($url)... "

    if kubectl run "test-http-${RANDOM}" \
        --image=curlimages/curl \
        --restart=Never \
        --rm=true \
        -i \
        --quiet \
        -- curl -s -o /dev/null -w "%{http_code}" --max-time $TEST_TIMEOUT "$url" 2>/dev/null | grep -q "2\|3\|4"; then

        echo -e "${GREEN}✓ OK${NC} (HTTP reachable)"
        return 0
    fi

    echo -e "${YELLOW}⚠ UNKNOWN${NC} (HTTP endpoint not responding)"
    return 1
}

################################################################################
# PROVIDER TEST ROUTINES
################################################################################

test_vimenca() {
    print_header "VIMENCA - Banking Services (SNAT Masquerading)"

    echo "Service Details:"
    echo "  • Primary Banking: 172.16.70.0/24 (8080)"
    echo "  • Securities: 172.16.65.21/32 (443)"
    echo "  • Integration Hub: 172.16.82.0/24 (8088)"
    echo "  • Source IP (seen by Vimenca): 203.0.113.10 (masqueraded)"
    echo "  • VPN Tunnel: vpn-05ea9c12f40b67844"
    echo ""

    local pass=0
    local fail=0

    echo "Testing Primary Banking (172.16.70.1)..."
    test_ping "172.16.70.1" "Primary" && ((pass++)) || ((fail++))
    test_port "172.16.70.1" "Primary" "8080" && ((pass++)) || ((fail++))
    echo ""

    echo "Testing Securities (172.16.65.21)..."
    test_ping "172.16.65.21" "Securities" && ((pass++)) || ((fail++))
    test_port "172.16.65.21" "Securities" "443" && ((pass++)) || ((fail++))
    echo ""

    echo "Testing Integration Hub (172.16.82.28)..."
    test_ping "172.16.82.28" "Integration Hub" && ((pass++)) || ((fail++))
    test_port "172.16.82.28" "Integration Hub" "8088" && ((pass++)) || ((fail++))
    echo ""

    print_summary "VIMENCA" $pass $fail
}

test_cibao() {
    print_header "CIBAO - Enterprise Network (Original Pod IPs)"

    echo "Service Details:"
    echo "  • Data Warehouse: 172.17.10.50:1433 (SQL Server)"
    echo "  • CRM Portal: 172.17.5.10:8080 (REST API)"
    echo "  • ERP API: 172.17.5.20:8443 (HTTPS)"
    echo "  • Message Broker: 172.17.20.10:5672 (RabbitMQ)"
    echo "  • Source IP (seen by CIBAO): 172.31.x.x (original pod IP)"
    echo "  • VPN Tunnel: vpn-0e751eec94d5d4743"
    echo "  • Firewall Status: ⏳ PENDING ACTIVATION"
    echo ""

    local pass=0
    local fail=0

    echo "Testing Data Warehouse (172.17.10.50)..."
    test_ping "172.17.10.50" "DW" && ((pass++)) || ((fail++))
    test_port "172.17.10.50" "DW" "1433" && ((pass++)) || ((fail++))
    echo ""

    echo "Testing CRM Portal (172.17.5.10)..."
    test_ping "172.17.5.10" "CRM" && ((pass++)) || ((fail++))
    test_port "172.17.5.10" "CRM" "8080" && ((pass++)) || ((fail++))
    echo ""

    echo "Testing ERP API (172.17.5.20)..."
    test_ping "172.17.5.20" "ERP" && ((pass++)) || ((fail++))
    test_port "172.17.5.20" "ERP" "8443" && ((pass++)) || ((fail++))
    echo ""

    echo "Testing Message Broker (172.17.20.10)..."
    test_ping "172.17.20.10" "Broker" && ((pass++)) || ((fail++))
    test_port "172.17.20.10" "Broker" "5672" && ((pass++)) || ((fail++))
    echo ""

    print_summary "CIBAO" $pass $fail
}

test_vpn_legacy() {
    print_header "ORGANIZATION-LEGACY - MSSQL Databases (Original Pod IPs)"

    echo "Service Details:"
    echo "  • APAP Producción: 192.168.100.8:1433 (SQL Server)"
    echo "  • Pruebas: 192.168.100.11:1433 (SQL Server)"
    echo "  • Producción Secondary: 192.168.100.12:1433 (SQL Server)"
    echo "  • Legacy Application Gateway: 172.133.5.4:443 (New - HTTPS)"
    echo "  • Source IP (seen by Legacy): 172.31.x.x (original pod IP)"
    echo "  • VPN Tunnel: vpn-028ce4c7f59b83bdd"
    echo "  • Firewall Status: ✅ ACCEPTING traffic"
    echo ""

    local pass=0
    local fail=0

    echo "Testing APAP Producción (192.168.100.8)..."
    test_ping "192.168.100.8" "APAP" && ((pass++)) || ((fail++))
    test_port "192.168.100.8" "APAP" "1433" && ((pass++)) || ((fail++))
    echo ""

    echo "Testing Pruebas (192.168.100.11)..."
    test_ping "192.168.100.11" "Pruebas" && ((pass++)) || ((fail++))
    test_port "192.168.100.11" "Pruebas" "1433" && ((pass++)) || ((fail++))
    echo ""

    echo "Testing Producción Secondary (192.168.100.12)..."
    test_ping "192.168.100.12" "Secondary" && ((pass++)) || ((fail++))
    test_port "192.168.100.12" "Secondary" "1433" && ((pass++)) || ((fail++))
    echo ""

    echo "Testing Legacy Application Gateway (172.133.5.4)..."
    test_ping "172.133.5.4" "AppGateway" && ((pass++)) || ((fail++))
    test_port "172.133.5.4" "AppGateway" "443" && ((pass++)) || ((fail++))
    echo ""

    print_summary "ORGANIZATION-LEGACY" $pass $fail
}

print_summary() {
    local provider=$1
    local pass=$2
    local fail=$3
    local total=$((pass + fail))
    local percent=$((pass * 100 / total))

    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    if [ $fail -eq 0 ]; then
        echo -e "${GREEN}✓ $provider: ALL TESTS PASSED ($pass/$total)${NC}"
    elif [ $pass -eq 0 ]; then
        echo -e "${RED}✗ $provider: ALL TESTS FAILED ($pass/$total)${NC}"
    else
        echo -e "${YELLOW}⚠ $provider: PARTIAL SUCCESS ($pass/$total, $percent%)${NC}"
    fi

    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
}

print_final_summary() {
    echo ""
    echo "═════════════════════════════════════════════════════════════════════════════"
    echo "OVERALL CONNECTIVITY STATUS"
    echo "═════════════════════════════════════════════════════════════════════════════"
    echo ""

    echo -e "${BLUE}For more detailed information:${NC}"
    echo "  • Vimenca:          providers-conn-docs/VIMENCA.md"
    echo "  • CIBAO:            providers-conn-docs/CIBAO.md"
    echo "  • Organization-Legacy:  providers-conn-docs/ORGANIZATION-LEGACY.md"
    echo ""

    echo -e "${BLUE}Quick Troubleshooting:${NC}"
    echo "  1. If PING fails   → VPN tunnel issue"
    echo "  2. If PORT fails   → Service not running or firewall blocking"
    echo "  3. If HTTP fails   → Service endpoint not responding (expected for DB ports)"
    echo ""

    echo -e "${BLUE}Check CloudWatch VPC Flow Logs:${NC}"
    echo "  aws logs filter-log-events --log-group-name '/aws/vpc/flowlogs/asg-plat-dev' \\"
    echo "    --filter-pattern '[..., dstip, ...]' --region us-east-2"
    echo ""
}

################################################################################
# MAIN
################################################################################

main() {
    case "$PROVIDER" in
        vimenca)
            test_vimenca
            print_final_summary
            ;;
        cibao)
            test_cibao
            print_final_summary
            ;;
        org-legacy|default)
            test_vpn_legacy
            print_final_summary
            ;;
        all)
            test_vimenca
            echo ""
            test_cibao
            echo ""
            test_vpn_legacy
            print_final_summary
            ;;
        *)
            echo "Usage: $0 [vimenca|cibao|org-legacy|all]"
            echo ""
            echo "Examples:"
            echo "  $0 vimenca          - Test Vimenca banking services"
            echo "  $0 cibao            - Test CIBAO enterprise network"
            echo "  $0 org-legacy  - Test Organization-Legacy MSSQL databases"
            echo "  $0 all              - Test all providers"
            exit 1
            ;;
    esac
}

main "$@"
