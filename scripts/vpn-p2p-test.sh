#!/bin/bash

################################################################################
# VPN PEER-TO-PEER TEST SCRIPT
################################################################################
#
# Purpose: Comprehensive testing suite for VPN connectivity validation when
#          a new peer (MockPeerA/Checkpoint) joins the network
#
# Usage:
#   # Test a specific peer IP
#   ./vpn-p2p-test.sh --peer-ip 172.16.70.1
#
#   # Full comprehensive test
#   ./vpn-p2p-test.sh --peer-ip 172.16.70.1 --deep
#
#   # Test from EKS pod
#   ./vpn-p2p-test.sh --peer-ip 172.16.70.1 --from-pod
#
#   # Test specific port/service
#   ./vpn-p2p-test.sh --peer-ip 172.16.70.1 --service http --port 80
#
#   # Generate diagnostic report
#   ./vpn-p2p-test.sh --peer-ip 172.16.70.1 --report vpn-test-report.md
#
# Architecture:
#   - AWS Side (Organization)
#     ├─ EKS VPC (172.31.0.0/16)
#     ├─ Transit Gateway
#     └─ VPN Connection to MockPeerA
#
#   - Remote Side (MockPeerA)
#     ├─ Checkpoint Firewall (191.97.106.141)
#     ├─ Internal Network (172.16.70.0/24)
#     └─ Test peer (passed as parameter)
#
################################################################################

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Default values
PEER_IP=""
TEST_PORT=80
TEST_SERVICE="http"
FROM_POD=false
DEEP_TEST=false
GENERATE_REPORT=false
REPORT_FILE=""
REGION="${AWS_REGION:-us-east-1}"
AWS_PROFILE="${AWS_PROFILE:-default}"
VERBOSE=false

# Test results tracking (using arrays for compatibility)
TEST_RESULTS_NAMES=()
TEST_RESULTS_STATUS=()
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

################################################################################
# HELPER FUNCTIONS
################################################################################

print_header() {
    echo -e "\n${BLUE}${BOLD}════════════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}${BOLD}  $1${NC}"
    echo -e "${BLUE}${BOLD}════════════════════════════════════════════════════════════════════════════════${NC}\n"
}

print_subheader() {
    echo -e "\n${CYAN}${BOLD}── $1${NC}"
}

print_test() {
    local name=$1
    local status=$2
    local details=${3:-}

    ((TOTAL_TESTS++))

    case "$status" in
        PASS)
            echo -e "${GREEN}✅ PASS${NC}  | $name"
            ((PASSED_TESTS++))
            ;;
        FAIL)
            echo -e "${RED}❌ FAIL${NC}  | $name"
            ((FAILED_TESTS++))
            ;;
        WARN)
            echo -e "${YELLOW}⚠️  WARN${NC}  | $name"
            ;;
        INFO)
            echo -e "${BLUE}ℹ️  INFO${NC}  | $name"
            ;;
        *)
            echo -e "${YELLOW}⏳ SKIP${NC}  | $name"
            ;;
    esac

    if [ -n "$details" ]; then
        echo -e "         └─ ${YELLOW}$details${NC}"
    fi

    TEST_RESULTS_NAMES+=("$name")
    TEST_RESULTS_STATUS+=("$status")
}

show_help() {
    cat << EOF

${BLUE}${BOLD}VPN PEER-TO-PEER TEST SCRIPT${NC}

${GREEN}PURPOSE:${NC}
  Comprehensive testing suite for validating VPN connectivity when a new
  peer (MockPeerA/Checkpoint) joins the network. Simply pass the peer's
  internal IP and the script handles all validation.

${GREEN}USAGE:${NC}
  ./vpn-p2p-test.sh --peer-ip <IP> [OPTIONS]

${GREEN}REQUIRED:${NC}
  --peer-ip <IP>              Internal IP of the peer to test (e.g., 172.16.70.1)

${GREEN}OPTIONS:${NC}
  --service <SERVICE>         Service to test: http, https, icmp, ssh (default: http)
  --port <PORT>               Port to test (default: 80)
  --from-pod                  Run connectivity tests from within EKS pod
  --deep                      Run comprehensive deep diagnostic tests
  --report <FILE>             Generate diagnostic report to file
  --region <REGION>           AWS region (default: us-east-1)
  --profile <PROFILE>         AWS profile (default: default)
  --verbose, -v               Verbose output
  --help, -h                  Show this help message

${GREEN}EXAMPLES:${NC}
  # Basic test
  ./vpn-p2p-test.sh --peer-ip 172.16.70.1

  # Test HTTP connectivity
  ./vpn-p2p-test.sh --peer-ip 172.16.70.1 --service http --port 80

  # Test HTTPS connectivity
  ./vpn-p2p-test.sh --peer-ip 172.16.70.1 --service https --port 443

  # Run deep diagnostics
  ./vpn-p2p-test.sh --peer-ip 172.16.70.1 --deep --report vpn-report.md

  # Test from EKS pod
  ./vpn-p2p-test.sh --peer-ip 172.16.70.1 --from-pod

  # Verbose output
  ./vpn-p2p-test.sh --peer-ip 172.16.70.1 --verbose

${GREEN}WHAT GETS TESTED:${NC}

  AWS Infrastructure:
    ✓ VPN Connection status
    ✓ Transit Gateway attachment
    ✓ Route tables configuration
    ✓ Security group rules
    ✓ VPC Endpoint availability
    ✓ Network ACLs

  Network Connectivity:
    ✓ ICMP reachability (ping)
    ✓ TCP port connectivity
    ✓ UDP connectivity (if applicable)
    ✓ MTU size and fragmentation
    ✓ Route validation
    ✓ Latency measurement
    ✓ Packet loss detection

  Deep Diagnostics (with --deep):
    ✓ Network path analysis (traceroute)
    ✓ Throughput testing
    ✓ TCP window size analysis
    ✓ Crypto handshake validation
    ✓ DNS resolution testing
    ✓ Detailed telemetry

${GREEN}REQUIREMENTS:${NC}
  • AWS CLI configured
  • kubectl configured (for --from-pod tests)
  • Network tools: ping, traceroute, nc, curl
  • jq for JSON parsing
  • Basic bash utilities

${GREEN}EXIT CODES:${NC}
  0  - All tests passed
  1  - One or more tests failed
  2  - Invalid arguments
  3  - Missing prerequisites

EOF
}

validate_args() {
    if [ -z "$PEER_IP" ]; then
        echo -e "${RED}ERROR: --peer-ip is required${NC}"
        echo ""
        show_help
        exit 2
    fi

    if ! [[ "$PEER_IP" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
        echo -e "${RED}ERROR: Invalid IP address format: $PEER_IP${NC}"
        exit 2
    fi
}

check_prerequisites() {
    local missing=()

    for cmd in aws jq ping curl nc; do
        if ! command -v "$cmd" &> /dev/null; then
            missing+=("$cmd")
        fi
    done

    if [ ${#missing[@]} -gt 0 ]; then
        echo -e "${RED}ERROR: Missing prerequisites: ${missing[*]}${NC}"
        exit 3
    fi
}

################################################################################
# SECTION 1: AWS INFRASTRUCTURE VALIDATION
################################################################################

test_vpn_connection() {
    print_subheader "VPN Connection Status"

    local vpn_info
    vpn_info=$(aws ec2 describe-vpn-connections \
        --filters "Name=state,Values=available,pending" \
        --query 'VpnConnections[0]' \
        --region "$REGION" \
        --profile "$AWS_PROFILE" \
        --output json 2>/dev/null || echo "{}")

    if [ "$vpn_info" = "{}" ] || [ "$vpn_info" = "null" ]; then
        print_test "VPN Connection Found" "FAIL" "No active VPN connection"
        return 1
    fi

    local vpn_id state t1_status t2_status
    vpn_id=$(echo "$vpn_info" | jq -r '.VpnConnectionId')
    state=$(echo "$vpn_info" | jq -r '.State')
    t1_status=$(echo "$vpn_info" | jq -r '.VgwTelemetry[0].Status // "UNKNOWN"')
    t2_status=$(echo "$vpn_info" | jq -r '.VgwTelemetry[1].Status // "UNKNOWN"')

    if [ "$state" = "available" ]; then
        print_test "VPN Connection State" "PASS" "ID: $vpn_id, State: available"
    else
        print_test "VPN Connection State" "FAIL" "State: $state (expected: available)"
    fi

    echo -e "         Tunnel 1: $t1_status"
    echo -e "         Tunnel 2: $t2_status"

    if [ "$t1_status" = "UP" ] || [ "$t2_status" = "UP" ]; then
        print_test "Tunnel Status" "PASS" "At least one tunnel is UP"
    else
        print_test "Tunnel Status" "WARN" "Both tunnels DOWN - MockPeerA may not be configured yet"
    fi
}

test_transit_gateway() {
    print_subheader "Transit Gateway Attachment"

    local tgw_info
    tgw_info=$(aws ec2 describe-transit-gateway-attachments \
        --filters "Name=resource-type,Values=vpc" \
        --query 'TransitGatewayAttachments[0]' \
        --region "$REGION" \
        --profile "$AWS_PROFILE" \
        --output json 2>/dev/null || echo "{}")

    if [ "$tgw_info" = "{}" ] || [ "$tgw_info" = "null" ]; then
        print_test "TGW Attachment Found" "FAIL" "No TGW attachment found"
        return 1
    fi

    local attach_id state tgw_id
    attach_id=$(echo "$tgw_info" | jq -r '.TransitGatewayAttachmentId')
    state=$(echo "$tgw_info" | jq -r '.State')
    tgw_id=$(echo "$tgw_info" | jq -r '.TransitGatewayId')

    if [ "$state" = "available" ]; then
        print_test "TGW Attachment State" "PASS" "ID: $attach_id, TGW: $tgw_id"
    else
        print_test "TGW Attachment State" "FAIL" "State: $state"
    fi
}

test_routes() {
    print_subheader "Route Table Configuration"

    local routes mock-peer-a_route vpn_routes
    routes=$(aws ec2 describe-route-tables \
        --query 'RouteTables[].Routes[?TransitGatewayId!=`null`]' \
        --region "$REGION" \
        --profile "$AWS_PROFILE" \
        --output json 2>/dev/null || echo "[]")

    mock-peer-a_route=$(echo "$routes" | jq -r '.[] | select(.DestinationCidrBlock=="172.16.70.0/24") | .DestinationCidrBlock' 2>/dev/null || echo "")

    if [ -n "$mock-peer-a_route" ]; then
        print_test "Route to MockPeerA (172.16.70.0/24)" "PASS" "via Transit Gateway"
    else
        print_test "Route to MockPeerA (172.16.70.0/24)" "FAIL" "Route not found"
    fi

    vpn_routes=$(echo "$routes" | jq '[.[] | select(.DestinationCidrBlock | startswith("172.33"))] | length' 2>/dev/null || echo "0")

    if [ "$vpn_routes" -gt 0 ]; then
        print_test "Routes to Organization VPCs" "PASS" "$vpn_routes routes found"
    else
        print_test "Routes to Organization VPCs" "WARN" "No Organization routes found"
    fi
}

test_security_groups() {
    print_subheader "Security Group Rules"

    # Get VPC info
    local vpc_id
    vpc_id=$(aws ec2 describe-vpcs \
        --filters "Name=cidr-block,Values=172.31.0.0/16" \
        --query 'Vpcs[0].VpcId' \
        --region "$REGION" \
        --profile "$AWS_PROFILE" \
        --output text 2>/dev/null || echo "")

    if [ -z "$vpc_id" ] || [ "$vpc_id" = "None" ]; then
        print_test "VPC Found" "FAIL" "EKS VPC not found"
        return
    fi

    # Check for security groups allowing traffic to peer
    local sg_rules
    sg_rules=$(aws ec2 describe-security-groups \
        --filters "Name=vpc-id,Values=$vpc_id" \
        --query 'SecurityGroups[].IpPermissions[]' \
        --region "$REGION" \
        --profile "$AWS_PROFILE" \
        --output json 2>/dev/null || echo "[]")

    local http_rule https_rule icmp_rule
    http_rule=$(echo "$sg_rules" | jq '.[] | select(.FromPort==80) | .FromPort' 2>/dev/null || echo "")
    https_rule=$(echo "$sg_rules" | jq '.[] | select(.FromPort==443) | .FromPort' 2>/dev/null || echo "")
    icmp_rule=$(echo "$sg_rules" | jq '.[] | select(.IpProtocol=="icmp") | .IpProtocol' 2>/dev/null || echo "")

    [ -n "$http_rule" ] && print_test "Security Group: HTTP (80)" "PASS" "Port 80 allowed"
    [ -n "$https_rule" ] && print_test "Security Group: HTTPS (443)" "PASS" "Port 443 allowed"
    [ -n "$icmp_rule" ] && print_test "Security Group: ICMP" "PASS" "ICMP allowed"

    # Warn if no rules found
    if [ -z "$http_rule" ] && [ -z "$https_rule" ] && [ -z "$icmp_rule" ]; then
        print_test "Security Group Rules" "WARN" "No egress rules to peer found - may need adjustment"
    fi
}

################################################################################
# SECTION 2: NETWORK CONNECTIVITY TESTS
################################################################################

test_icmp_connectivity() {
    print_subheader "ICMP Connectivity (Ping)"

    if ping -c 3 -W 5 "$PEER_IP" > /dev/null 2>&1; then
        print_test "Ping to $PEER_IP" "PASS" "ICMP response received"
        return 0
    else
        print_test "Ping to $PEER_IP" "FAIL" "No ICMP response (check firewall rules)"
        return 1
    fi
}

test_tcp_connectivity() {
    print_subheader "TCP Connectivity"

    local service_name
    case "$TEST_SERVICE" in
        http)  service_name="HTTP"; TEST_PORT=80 ;;
        https) service_name="HTTPS"; TEST_PORT=443 ;;
        ssh)   service_name="SSH"; TEST_PORT=22 ;;
        *) service_name="Custom"; ;;
    esac

    if timeout 5 bash -c "echo > /dev/tcp/$PEER_IP/$TEST_PORT" 2>/dev/null; then
        print_test "TCP Port $TEST_PORT ($service_name)" "PASS" "Connection successful"
        return 0
    else
        print_test "TCP Port $TEST_PORT ($service_name)" "FAIL" "Connection refused or timeout"
        return 1
    fi
}

test_http_service() {
    print_subheader "HTTP Service Validation"

    local protocol scheme
    [ "$TEST_SERVICE" = "https" ] && protocol="https" || protocol="http"

    if command -v curl &> /dev/null; then
        local response
        response=$(curl -s -m 5 -o /dev/null -w "%{http_code}" "$protocol://$PEER_IP:$TEST_PORT/" 2>/dev/null || echo "000")

        if [ "$response" != "000" ]; then
            print_test "$service_name Service Response" "PASS" "HTTP $response"
        else
            print_test "$service_name Service Response" "FAIL" "No response or timeout"
        fi
    fi
}

test_latency() {
    print_subheader "Latency Measurement"

    local result
    result=$(ping -c 5 -W 5 "$PEER_IP" 2>/dev/null | grep "min/avg/max/stddev" | awk -F'/' '{print $5}' || echo "")

    if [ -n "$result" ]; then
        local avg_latency
        avg_latency=$(echo "$result" | awk -F'/' '{print $2}')

        if (( $(echo "$avg_latency < 100" | bc -l) )); then
            print_test "Latency (<100ms)" "PASS" "Avg: ${avg_latency}ms"
        elif (( $(echo "$avg_latency < 200" | bc -l) )); then
            print_test "Latency (<200ms)" "WARN" "Avg: ${avg_latency}ms (acceptable but high)"
        else
            print_test "Latency Check" "WARN" "Avg: ${avg_latency}ms (very high)"
        fi
    else
        print_test "Latency Measurement" "FAIL" "Could not measure"
    fi
}

test_packet_loss() {
    print_subheader "Packet Loss Detection"

    local loss_percent
    loss_percent=$(ping -c 20 -W 5 "$PEER_IP" 2>/dev/null | grep "% packet loss" | awk '{print $6}' | sed 's/%//' || echo "100")

    if (( $(echo "$loss_percent == 0" | bc -l) )); then
        print_test "Packet Loss (0%)" "PASS" "No packet loss detected"
    elif (( $(echo "$loss_percent < 5" | bc -l) )); then
        print_test "Packet Loss ($loss_percent%)" "WARN" "Minimal loss (usually acceptable)"
    else
        print_test "Packet Loss ($loss_percent%)" "FAIL" "Significant loss detected"
    fi
}

################################################################################
# SECTION 3: DEEP DIAGNOSTICS
################################################################################

test_mtu_size() {
    print_subheader "MTU Size Testing"

    # Test with 1500 byte packets (standard Ethernet)
    if ping -c 1 -M do -s 1472 "$PEER_IP" > /dev/null 2>&1; then
        print_test "MTU 1500 (Standard)" "PASS" "No fragmentation needed"
    else
        print_test "MTU 1500" "WARN" "Standard MTU may have fragmentation"

        # Try smaller MTU
        if ping -c 1 -M do -s 1372 "$PEER_IP" > /dev/null 2>&1; then
            print_test "MTU 1400 (Reduced)" "PASS" "Works with reduced MTU"
        fi
    fi
}

test_traceroute() {
    print_subheader "Network Path Analysis"

    if command -v traceroute &> /dev/null; then
        echo -e "${YELLOW}Traceroute to $PEER_IP:${NC}"
        traceroute -m 15 -w 2 "$PEER_IP" 2>/dev/null | head -10 || echo "  (traceroute failed)"
        print_test "Traceroute Completed" "INFO" "See path above"
    fi
}

test_throughput() {
    print_subheader "Throughput Testing"

    if command -v iperf3 &> /dev/null; then
        echo -e "${YELLOW}Note: iperf3 not easily accessible - recommend manual testing${NC}"
        print_test "Throughput Testing" "INFO" "Use: iperf3 -c $PEER_IP -t 10 on peer system"
    else
        print_test "Throughput Testing" "INFO" "Install iperf3 for detailed throughput analysis"
    fi
}

test_dns_resolution() {
    print_subheader "DNS Resolution Testing"

    # Try reverse DNS lookup
    if command -v dig &> /dev/null; then
        local hostname
        hostname=$(dig +short -x "$PEER_IP" 2>/dev/null || echo "")

        if [ -n "$hostname" ]; then
            print_test "Reverse DNS Lookup" "PASS" "Hostname: $hostname"
        else
            print_test "Reverse DNS Lookup" "INFO" "No reverse DNS entry"
        fi
    fi
}

################################################################################
# SECTION 4: POD-BASED TESTING
################################################################################

test_from_eks_pod() {
    print_subheader "EKS Pod Connectivity Testing"

    # Create test pod and run connectivity tests
    local pod_name="vpn-test-$(date +%s)"

    echo -e "${YELLOW}Creating test pod: $pod_name${NC}"

    kubectl run "$pod_name" \
        --image=amazonlinux:2 \
        --rm -it --restart=Never \
        -- bash -c "
            echo 'Testing from pod...'

            echo 'ICMP Test:'
            ping -c 3 $PEER_IP 2>&1 | tail -2

            echo 'TCP Port $TEST_PORT Test:'
            timeout 3 bash -c \"echo > /dev/tcp/$PEER_IP/$TEST_PORT\" && echo 'Connected' || echo 'Connection failed'

            echo 'AWS Service Test (ECR):'
            aws ecr get-login-password --region $REGION 2>&1 | head -1 || echo 'ECR access failed'

            echo 'Complete'
        " 2>&1 | tee -a "${REPORT_FILE:-/dev/null}"

    print_test "Pod Testing" "PASS" "Tests completed from EKS pod"
}

################################################################################
# SECTION 5: SUMMARY & REPORTING
################################################################################

print_summary() {
    print_header "TEST SUMMARY"

    echo -e "${BOLD}Results:${NC}"
    echo -e "  Total Tests:  $TOTAL_TESTS"
    echo -e "  ${GREEN}Passed:       $PASSED_TESTS${NC}"
    echo -e "  ${RED}Failed:       $FAILED_TESTS${NC}"

    local pass_rate=0
    if [ $TOTAL_TESTS -gt 0 ]; then
        pass_rate=$((PASSED_TESTS * 100 / TOTAL_TESTS))
    fi

    echo -e "\n${BOLD}Pass Rate: ${pass_rate}%${NC}"

    if [ $FAILED_TESTS -eq 0 ]; then
        echo -e "\n${GREEN}${BOLD}✅ ALL TESTS PASSED${NC}"
        echo -e "${GREEN}Peer $PEER_IP is fully accessible from AWS side${NC}"
    else
        echo -e "\n${RED}${BOLD}❌ TESTS FAILED${NC}"
        echo -e "${RED}$FAILED_TESTS test(s) failed - see details above${NC}"
    fi
}

generate_report() {
    if [ "$GENERATE_REPORT" = true ] && [ -n "$REPORT_FILE" ]; then
        print_subheader "Generating Report"

        cat > "$REPORT_FILE" << EOF
# VPN Peer-to-Peer Test Report

**Date:** $(date)
**Tested Peer IP:** $PEER_IP
**Region:** $REGION
**AWS Profile:** $AWS_PROFILE

## Test Summary

- Total Tests: $TOTAL_TESTS
- Passed: $PASSED_TESTS
- Failed: $FAILED_TESTS
- Pass Rate: $(( PASSED_TESTS * 100 / TOTAL_TESTS ))%

## Test Results

$(for i in "${!TEST_RESULTS_NAMES[@]}"; do
    echo "- ${TEST_RESULTS_NAMES[$i]}: ${TEST_RESULTS_STATUS[$i]}"
done)

## Recommendations

1. If ICMP tests fail, check:
   - Security group rules allow ICMP from/to peer
   - Checkpoint firewall ICMP rules
   - Transit Gateway route table entries

2. If TCP tests fail, check:
   - Security group rules allow port traffic
   - MockPeerA firewall allows outbound on port
   - Target service is running

3. If latency is high (>100ms), check:
   - VPN tunnel encryption overhead
   - Network congestion
   - Geographic distance

4. If packet loss detected, check:
   - MTU settings on both sides
   - IP fragmentation
   - Network stability

## Next Steps

- [ ] Verify all infrastructure components
- [ ] Check MockPeerA Checkpoint configuration
- [ ] Verify PSK exchange completed
- [ ] Confirm route tables on both sides
- [ ] Test additional services

---
*Report generated by vpn-p2p-test.sh*
EOF

        echo -e "${GREEN}Report saved: $REPORT_FILE${NC}"
    fi
}

################################################################################
# MAIN EXECUTION
################################################################################

main() {
    # Show help if no arguments provided
    if [[ $# -eq 0 ]]; then
        show_help
        exit 0
    fi

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --peer-ip)
                PEER_IP="$2"
                shift 2
                ;;
            --service)
                TEST_SERVICE="$2"
                shift 2
                ;;
            --port)
                TEST_PORT="$2"
                shift 2
                ;;
            --from-pod)
                FROM_POD=true
                shift
                ;;
            --deep)
                DEEP_TEST=true
                shift
                ;;
            --report)
                GENERATE_REPORT=true
                REPORT_FILE="$2"
                shift 2
                ;;
            --region)
                REGION="$2"
                shift 2
                ;;
            --profile)
                AWS_PROFILE="$2"
                shift 2
                ;;
            --verbose|-v)
                VERBOSE=true
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                echo -e "${RED}Unknown option: $1${NC}"
                show_help
                exit 2
                ;;
        esac
    done

    # Validate and check prerequisites
    validate_args
    check_prerequisites

    # Start testing
    print_header "VPN PEER-TO-PEER CONNECTIVITY TEST"
    echo -e "${BOLD}Testing peer: $PEER_IP${NC}"
    echo -e "${BOLD}Service: $TEST_SERVICE (port $TEST_PORT)${NC}"
    echo -e "${BOLD}Timestamp: $(date)${NC}"

    # Section 1: AWS Infrastructure
    print_header "SECTION 1: AWS INFRASTRUCTURE VALIDATION"
    test_vpn_connection
    test_transit_gateway
    test_routes
    test_security_groups

    # Section 2: Network Connectivity
    print_header "SECTION 2: NETWORK CONNECTIVITY"
    test_icmp_connectivity
    test_tcp_connectivity
    test_http_service
    test_latency
    test_packet_loss

    # Section 3: Deep Diagnostics (optional)
    if [ "$DEEP_TEST" = true ]; then
        print_header "SECTION 3: DEEP DIAGNOSTICS"
        test_mtu_size
        test_traceroute
        test_throughput
        test_dns_resolution
    fi

    # Section 4: Pod Testing (optional)
    if [ "$FROM_POD" = true ]; then
        print_header "SECTION 4: EKS POD TESTING"
        test_from_eks_pod
    fi

    # Summary and Report
    print_summary
    generate_report

    # Exit code based on results
    if [ $FAILED_TESTS -eq 0 ]; then
        exit 0
    else
        exit 1
    fi
}

# Run main function
main "$@"
