#!/bin/bash
set -e

# =============================================================================
# Test Pod Deployment for internal-legacy-network VPN (MSSQL)
# =============================================================================
# This script deploys test pods to verify connectivity to legacy MSSQL databases
# Usage: ./test-internal-legacy-network.sh [test-type]
#   test-type: ping, port, mssql, or all (default: all)
# =============================================================================

TEST_TYPE=${1:-all}
NAMESPACE=${NAMESPACE:-default}
TEST_POD_PREFIX="org-legacy-test"
LEGACY_IPS=("192.168.100.8" "192.168.100.11" "192.168.100.12")
LEGACY_NAMES=("APAP-Produccion" "Pruebas" "Produccion")
MSSQL_PORT=1433
MSSQL_USER=${MSSQL_USER:-sa}
MSSQL_PASS=${MSSQL_PASS:-YourPassword}

echo "================================================================================"
echo "ORGANIZATION-LEGACY-NETWORK TEST POD DEPLOYMENT (MSSQL)"
echo "================================================================================"
echo ""
echo "Test Type: $TEST_TYPE"
echo "Namespace: $NAMESPACE"
echo "MSSQL Port: $MSSQL_PORT"
echo "MSSQL User: $MSSQL_USER"
echo "Legacy Databases (MSSQL):"
for i in "${!LEGACY_IPS[@]}"; do
  echo "  ${LEGACY_IPS[$i]} (${LEGACY_NAMES[$i]})"
done
echo ""

# =============================================================================
# TEST 1: PING TEST (ICMP Reachability)
# =============================================================================

if [[ "$TEST_TYPE" == "ping" || "$TEST_TYPE" == "all" ]]; then
  echo "================================================================================"
  echo "TEST 1: PING REACHABILITY"
  echo "================================================================================"

  for i in "${!LEGACY_IPS[@]}"; do
    IP=${LEGACY_IPS[$i]}
    NAME=${LEGACY_NAMES[$i]}
    LOWERCASE_NAME=$(echo "$NAME" | tr '[:upper:]' '[:lower:]' | tr '-' '-' | sed 's/_/-/g')

    echo ""
    echo "Testing ping to $NAME ($IP)..."

    kubectl run "${TEST_POD_PREFIX}-ping-${LOWERCASE_NAME}" \
      --image=alpine:latest \
      --restart=Never \
      --rm=true \
      -i \
      -- ping -c 3 -W 2 "$IP" 2>&1 | tee "/tmp/legacy-ping-${NAME}.log" || true &

    sleep 2
  done

  wait

  echo ""
  echo "Ping test results:"
  for NAME in "${LEGACY_NAMES[@]}"; do
    if [ -f "/tmp/legacy-ping-${NAME}.log" ]; then
      COUNT=$(grep -c 'bytes from' "/tmp/legacy-ping-${NAME}.log" || echo "0")
      if [ "$COUNT" -gt 0 ]; then
        echo "  ✅ $NAME: $COUNT/3 responses received"
      else
        echo "  ❌ $NAME: Timeout or unreachable"
      fi
    fi
  done
fi

# =============================================================================
# TEST 2: PORT CONNECTIVITY TEST (MSSQL Port 1433)
# =============================================================================

if [[ "$TEST_TYPE" == "port" || "$TEST_TYPE" == "all" ]]; then
  echo ""
  echo "================================================================================"
  echo "TEST 2: MSSQL PORT CONNECTIVITY (Port $MSSQL_PORT)"
  echo "================================================================================"

  for i in "${!LEGACY_IPS[@]}"; do
    IP=${LEGACY_IPS[$i]}
    NAME=${LEGACY_NAMES[$i]}
    LOWERCASE_NAME=$(echo "$NAME" | tr '[:upper:]' '[:lower:]' | tr '-' '-' | sed 's/_/-/g')

    echo ""
    echo "Testing MSSQL port to $NAME ($IP:$MSSQL_PORT)..."

    kubectl run "${TEST_POD_PREFIX}-port-${LOWERCASE_NAME}" \
      --image=busybox:latest \
      --restart=Never \
      --rm=true \
      -i \
      -- sh -c "nc -zv -w 3 ${IP} ${MSSQL_PORT}" 2>&1 | tee "/tmp/legacy-port-${NAME}.log" || true &

    sleep 3
  done

  wait

  echo ""
  echo "MSSQL port connectivity results:"
  for NAME in "${LEGACY_NAMES[@]}"; do
    if [ -f "/tmp/legacy-port-${NAME}.log" ]; then
      if grep -q "succeeded" "/tmp/legacy-port-${NAME}.log" 2>/dev/null; then
        echo "  ✅ $NAME: Port $MSSQL_PORT open (MSSQL listening)"
      else
        echo "  ❌ $NAME: Connection refused or timeout"
      fi
    fi
  done
fi

# =============================================================================
# TEST 3: MSSQL DATABASE CONNECTIVITY
# =============================================================================

if [[ "$TEST_TYPE" == "mssql" || "$TEST_TYPE" == "all" ]]; then
  echo ""
  echo "================================================================================"
  echo "TEST 3: MSSQL DATABASE CONNECTIVITY"
  echo "================================================================================"
  echo "Using MSSQL credentials: User=$MSSQL_USER"
  echo ""

  for i in "${!LEGACY_IPS[@]}"; do
    IP=${LEGACY_IPS[$i]}
    NAME=${LEGACY_NAMES[$i]}
    LOWERCASE_NAME=$(echo "$NAME" | tr '[:upper:]' '[:lower:]' | tr '-' '-' | sed 's/_/-/g')

    echo "Testing MSSQL query to $NAME ($IP:$MSSQL_PORT)..."

    # Use sqlcmd from Microsoft's MSSQL tools image
    kubectl run "${TEST_POD_PREFIX}-mssql-${LOWERCASE_NAME}" \
      --image=mcr.microsoft.com/mssql-tools:latest \
      --restart=Never \
      --rm=true \
      -i \
      -- bash -c "sqlcmd -S ${IP},${MSSQL_PORT} -U ${MSSQL_USER} -P ${MSSQL_PASS} -Q 'SELECT 1 AS Connected' 2>&1" \
      2>&1 | tee "/tmp/legacy-mssql-${NAME}.log" || true &

    sleep 4
  done

  wait

  echo ""
  echo "MSSQL connectivity results:"
  for NAME in "${LEGACY_NAMES[@]}"; do
    if [ -f "/tmp/legacy-mssql-${NAME}.log" ]; then
      if grep -qi "Connected" "/tmp/legacy-mssql-${NAME}.log" 2>/dev/null; then
        echo "  ✅ $NAME: MSSQL query executed (Connected)"
      elif grep -q "succeeded" "/tmp/legacy-mssql-${NAME}.log" 2>/dev/null; then
        echo "  ✅ $NAME: Port $MSSQL_PORT reachable (MSSQL listening)"
      elif grep -qi "login failed\|authentication" "/tmp/legacy-mssql-${NAME}.log" 2>/dev/null; then
        echo "  ⏳ $NAME: Port reachable but auth failed (check credentials: $MSSQL_USER)"
      else
        echo "  ❌ $NAME: Connection failed (check port $MSSQL_PORT and firewall)"
      fi
    fi
  done
fi

# =============================================================================
# CLOUDWATCH LOGS ANALYSIS
# =============================================================================

echo ""
echo "================================================================================"
echo "CLOUDWATCH VPC FLOW LOGS ANALYSIS"
echo "================================================================================"
echo ""

CURRENT_TIME=$(date +%s)
START_TIME=$((CURRENT_TIME - 300))  # Last 5 minutes

echo "Querying VPC Flow Logs for traffic to legacy network (192.168.100.0/24)..."
echo ""

LOGS_FOUND=$(aws logs filter-log-events \
  --profile default \
  --region us-east-2 \
  --log-group-name '/aws/vpc/flowlogs/asg-plat-dev' \
  --start-time $((START_TIME * 1000)) \
  --filter-pattern '[ version, account_id, eni, srcip, dstip="192.168.100.*", ...]' \
  --output json 2>/dev/null | jq '.events | length')

if [ "$LOGS_FOUND" -gt 0 ]; then
  echo "Found $LOGS_FOUND log entries for legacy network traffic:"
  echo ""
  aws logs filter-log-events \
    --profile default \
    --region us-east-2 \
    --log-group-name '/aws/vpc/flowlogs/asg-plat-dev' \
    --start-time $((START_TIME * 1000)) \
    --filter-pattern '[ version, account_id, eni, srcip, dstip="192.168.100.*", ...]' \
    --output json 2>/dev/null | jq -r '.events[].message' | while read -r line; do
    if [ ! -z "$line" ]; then
      echo "$line" | awk '{
        printf "  Source IP: %s\n", $4
        printf "  Destination: %s:%s\n", $5, $7
        printf "  Protocol: %s\n", ($8 == "6" ? "TCP" : ($8 == "17" ? "UDP" : "Other"))
        printf "  Bytes: %s | Packets: %s\n", $10, $9
        printf "  Action: %s\n", $13
        printf "  ────────────────────────────\n"
      }'
    fi
  done
else
  echo "⏳ No traffic logs found in last 5 minutes"
  echo "   (This is normal if tests haven't run yet)"
fi

echo ""
echo "================================================================================"
echo "TEST SUMMARY"
echo "================================================================================"
echo ""
echo "Test pods deployed: $(date)"
echo "Results logged to: /tmp/legacy-*.log"
echo ""
echo "Interpretation Guide:"
echo "  ✅ PING Success (3/3)      = Network route working"
echo "  ❌ PING Timeout            = VPN tunnel down or firewall blocking"
echo "  ✅ Port 1433 Open          = MSSQL server listening"
echo "  ❌ Port 1433 Timeout       = MSSQL blocked by firewall or not running"
echo "  ✅ MSSQL Query Success     = Database connected and authenticated"
echo "  ⏳ MSSQL Auth Failed       = Port open but wrong credentials"
echo ""
echo "Next steps:"
echo "  1. Review results above"
echo "  2. Check VPN tunnel status: aws ec2 describe-vpn-connections"
echo "  3. Verify routes: aws ec2 describe-route-tables"
echo "  4. Check firewall allows TCP/$MSSQL_PORT from pod CIDR"
echo "  5. Verify MSSQL server running and credentials correct"
echo ""
echo "MSSQL Credential Notes:"
echo "  - Default: sa user with password"
echo "  - Override: export MSSQL_USER=youruser MSSQL_PASS=yourpass"
echo "  - Windows Auth: Requires Kerberos setup (advanced)"
echo ""
echo "================================================================================"
