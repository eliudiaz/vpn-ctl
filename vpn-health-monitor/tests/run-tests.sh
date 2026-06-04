#!/bin/bash

# VPN Health Monitor E2E Test Runner
# This script helps run Playwright tests with various options

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
print_header() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

check_dependencies() {
    print_header "Checking dependencies"

    if ! command -v node &> /dev/null; then
        print_error "Node.js is not installed"
        exit 1
    fi
    print_success "Node.js $(node -v)"

    if ! command -v npm &> /dev/null; then
        print_error "npm is not installed"
        exit 1
    fi
    print_success "npm $(npm -v)"
}

install_dependencies() {
    print_header "Installing dependencies"
    npm ci
    print_success "Dependencies installed"
}

install_browsers() {
    print_header "Installing Playwright browsers"
    npx playwright install --with-deps
    print_success "Browsers installed"
}

check_app_availability() {
    print_header "Checking app availability"

    local max_attempts=30
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        if curl -sk https://vpn.assurehub.io > /dev/null 2>&1; then
            print_success "App is available at https://vpn.assurehub.io"
            return 0
        fi

        echo -n "."
        sleep 2
        ((attempt++))
    done

    print_error "App is not available after ${max_attempts} attempts"
    echo "Make sure the app is running at https://vpn.assurehub.io"
    exit 1
}

run_tests() {
    local mode=$1

    case $mode in
        "all")
            print_header "Running all E2E tests"
            npm test
            ;;
        "ui")
            print_header "Running tests in UI mode"
            npm run test:ui
            ;;
        "headed")
            print_header "Running tests in headed mode (visible browser)"
            npm run test:headed
            ;;
        "debug")
            print_header "Running tests in debug mode"
            npm run test:debug
            ;;
        "chromium")
            print_header "Running tests on Chromium"
            npm run test:chromium
            ;;
        "firefox")
            print_header "Running tests on Firefox"
            npm run test:firefox
            ;;
        "webkit")
            print_header "Running tests on WebKit"
            npm run test:webkit
            ;;
        "mobile")
            print_header "Running mobile tests"
            npm run test:mobile
            ;;
        "report")
            print_header "Showing test report"
            npm run test:report
            ;;
        *)
            print_error "Unknown test mode: $mode"
            show_usage
            exit 1
            ;;
    esac
}

show_usage() {
    cat << EOF
${BLUE}VPN Health Monitor E2E Test Runner${NC}

${GREEN}Usage:${NC}
    ./run-tests.sh [OPTIONS] [MODE]

${GREEN}Options:${NC}
    -h, --help          Show this help message
    -i, --install       Install dependencies and browsers
    -c, --check         Check app availability
    --no-check          Skip availability check

${GREEN}Modes:${NC}
    all                 Run all E2E tests (default)
    ui                  Run tests in interactive UI mode
    headed              Run tests with visible browser
    debug               Run tests in debug mode
    chromium            Run tests on Chromium only
    firefox             Run tests on Firefox only
    webkit              Run tests on WebKit only
    mobile              Run mobile device tests
    report              Show HTML test report

${GREEN}Examples:${NC}
    # Run all tests with dependency install
    ./run-tests.sh -i

    # Run tests in UI mode
    ./run-tests.sh ui

    # Run chromium tests only, skip availability check
    ./run-tests.sh --no-check chromium

    # Show test report
    ./run-tests.sh report

EOF
}

# Main script
main() {
    local mode="all"
    local check_app=true
    local install_deps=false

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_usage
                exit 0
                ;;
            -i|--install)
                install_deps=true
                shift
                ;;
            -c|--check)
                check_app=true
                shift
                ;;
            --no-check)
                check_app=false
                shift
                ;;
            all|ui|headed|debug|chromium|firefox|webkit|mobile|report)
                mode=$1
                shift
                ;;
            *)
                print_error "Unknown argument: $1"
                show_usage
                exit 1
                ;;
        esac
    done

    # Check dependencies
    check_dependencies

    # Install dependencies if requested
    if [ "$install_deps" = true ]; then
        install_dependencies
        install_browsers
    fi

    # Check if node_modules exists
    if [ ! -d "node_modules" ]; then
        print_warning "Dependencies not installed, installing now..."
        install_dependencies
        install_browsers
    fi

    # Check app availability
    if [ "$check_app" = true ]; then
        check_app_availability
    fi

    # Run tests
    run_tests "$mode"

    # Show results
    if [ $? -eq 0 ]; then
        print_success "Tests completed successfully"
        if [ "$mode" != "ui" ] && [ "$mode" != "debug" ]; then
            echo ""
            echo "View detailed report: npm run test:report"
        fi
    else
        print_error "Tests failed"
        exit 1
    fi
}

# Run main
main "$@"
