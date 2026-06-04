#!/bin/bash
# Test runner for vpn-ctl system
# Runs unit tests, integration tests, and generates coverage report

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$TEST_DIR")"
COVERAGE_MIN=80

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║         vpn-ctl Test Suite Runner                            ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}❌ pytest not found. Install with: pip install pytest pytest-cov${NC}"
    exit 1
fi

# Function to run tests and report results
run_tests() {
    local test_type=$1
    local test_path=$2
    local description=$3

    echo -e "${YELLOW}Running: ${description}${NC}"
    echo "  Path: ${test_path}"
    echo ""

    if pytest \
        "${test_path}" \
        -v \
        --tb=short \
        --color=yes \
        2>&1; then
        echo -e "${GREEN}✓ ${description} passed${NC}"
        return 0
    else
        echo -e "${RED}✗ ${description} failed${NC}"
        return 1
    fi
}

# Track results
FAILED=0

# 1. Unit Tests
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}PHASE 1: Unit Tests${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if run_tests "unit" "${TEST_DIR}/unit" "Unit Tests"; then
    :
else
    FAILED=$((FAILED + 1))
fi

# 2. Integration Tests
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}PHASE 2: Integration Tests${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if run_tests "integration" "${TEST_DIR}/integration" "Integration Tests"; then
    :
else
    FAILED=$((FAILED + 1))
fi

# 3. Coverage Report
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}PHASE 3: Coverage Analysis${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

pytest \
    "${TEST_DIR}" \
    --cov="${PROJECT_ROOT}/infrastructure" \
    --cov="${PROJECT_ROOT}/application" \
    --cov="${PROJECT_ROOT}/presentation" \
    --cov-report=html \
    --cov-report=term-missing \
    --cov-fail-under=${COVERAGE_MIN} \
    --tb=short \
    --color=yes \
    2>&1 || {
        echo -e "${YELLOW}⚠️  Coverage below ${COVERAGE_MIN}%${NC}"
        FAILED=$((FAILED + 1))
    }

# 4. Summary
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}TEST SUMMARY${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  ✅ All tests passed!                                       ║${NC}"
    echo -e "${GREEN}║  Coverage report: htmlcov/index.html                       ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
    exit 0
else
    echo -e "${RED}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║  ❌ ${FAILED} test phase(s) failed                                 ║${NC}"
    echo -e "${RED}╚══════════════════════════════════════════════════════════════╝${NC}"
    exit 1
fi
