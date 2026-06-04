.PHONY: help install dev test test-unit test-integration coverage lint format clean doctor

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[1;33m
RED := \033[0;31m
NC := \033[0m # No Color

help:
	@echo "$(BLUE)vpn-ctl Development Makefile$(NC)"
	@echo ""
	@echo "Available targets:"
	@echo ""
	@echo "  $(YELLOW)Installation & Setup$(NC)"
	@echo "    install              Install dependencies"
	@echo "    dev                  Set up development environment"
	@echo ""
	@echo "  $(YELLOW)Testing$(NC)"
	@echo "    test                 Run all tests (unit + integration)"
	@echo "    test-unit            Run unit tests only"
	@echo "    test-integration     Run integration tests only"
	@echo "    coverage             Generate coverage report"
	@echo ""
	@echo "  $(YELLOW)Code Quality$(NC)"
	@echo "    lint                 Run linters (pylint, flake8)"
	@echo "    format               Auto-format code with black and isort"
	@echo "    type-check           Run type checking (mypy)"
	@echo ""
	@echo "  $(YELLOW)CLI & Tools$(NC)"
	@echo "    doctor               Run diagnostic checks"
	@echo "    clean                Clean up build artifacts"
	@echo ""

install:
	@echo "$(BLUE)Installing dependencies...$(NC)"
	pip install -q -r requirements.txt

dev:
	@echo "$(BLUE)Setting up development environment...$(NC)"
	pip install -q -r requirements-dev.txt
	@echo "$(GREEN)✓ Development environment ready$(NC)"
	@echo ""
	@echo "Quick start:"
	@echo "  python -m presentation.cli.main peer add"

test:
	@echo "$(BLUE)Running test suite...$(NC)"
	bash tests/run_tests.sh

test-unit:
	@echo "$(BLUE)Running unit tests...$(NC)"
	pytest tests/unit/ -v --tb=short --color=yes

test-integration:
	@echo "$(BLUE)Running integration tests...$(NC)"
	pytest tests/integration/ -v --tb=short --color=yes

coverage:
	@echo "$(BLUE)Generating coverage report...$(NC)"
	pytest tests/ \
		--cov=infrastructure \
		--cov=application \
		--cov=presentation \
		--cov-report=html \
		--cov-report=term-missing \
		--cov-fail-under=80 \
		-v
	@echo ""
	@echo "$(GREEN)Coverage report: htmlcov/index.html$(NC)"

lint:
	@echo "$(BLUE)Running linters...$(NC)"
	@command -v pylint &> /dev/null || { echo "pylint not installed"; exit 1; }
	@command -v flake8 &> /dev/null || { echo "flake8 not installed"; exit 1; }
	pylint --rc-file=.pylintrc infrastructure/ application/ presentation/ || true
	flake8 --config=.flake8 infrastructure/ application/ presentation/ || true

format:
	@echo "$(BLUE)Formatting code...$(NC)"
	@command -v black &> /dev/null || { echo "black not installed"; exit 1; }
	@command -v isort &> /dev/null || { echo "isort not installed"; exit 1; }
	black infrastructure/ application/ presentation/ tests/
	isort infrastructure/ application/ presentation/ tests/
	@echo "$(GREEN)✓ Code formatted$(NC)"

type-check:
	@echo "$(BLUE)Running type checking...$(NC)"
	@command -v mypy &> /dev/null || { echo "mypy not installed"; exit 1; }
	mypy --config-file=mypy.ini infrastructure/ application/ presentation/ || true

doctor:
	@echo "$(BLUE)Running diagnostic checks...$(NC)"
	@echo ""
	@echo "Checking dependencies:"
	@command -v python &> /dev/null && echo "  $(GREEN)✓ Python$(NC)" || echo "  $(RED)✗ Python$(NC)"
	@command -v pytest &> /dev/null && echo "  $(GREEN)✓ pytest$(NC)" || echo "  $(RED)✗ pytest$(NC)"
	@command -v pulumi &> /dev/null && echo "  $(GREEN)✓ Pulumi$(NC)" || echo "  $(RED)✗ Pulumi (optional)$(NC)"
	@echo ""
	@echo "Checking directories:"
	@[ -d "config/peers" ] && echo "  $(GREEN)✓ config/peers$(NC)" || echo "  $(YELLOW)⚠ config/peers (not created)$(NC)"
	@[ -d "pulumi" ] && echo "  $(GREEN)✓ pulumi$(NC)" || echo "  $(YELLOW)⚠ pulumi (not created)$(NC)"
	@[ -d ".vpnctl" ] && echo "  $(GREEN)✓ .vpnctl state$(NC)" || echo "  $(YELLOW)⚠ .vpnctl state (not created)$(NC)"
	@echo ""
	@echo "Project structure:"
	@echo "  infrastructure/iac_providers/     $(GREEN)✓$(NC) (provider abstraction layer)"
	@echo "  application/services/             $(GREEN)✓$(NC) (business logic layer)"
	@echo "  presentation/cli/                 $(GREEN)✓$(NC) (CLI commands)"
	@echo "  tests/unit/                       $(GREEN)✓$(NC) (unit tests)"
	@echo "  tests/integration/                $(GREEN)✓$(NC) (integration tests)"

clean:
	@echo "$(BLUE)Cleaning up...$(NC)"
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf htmlcov/ .coverage .mypy_cache/ .pytest_cache/ 2>/dev/null || true
	@echo "$(GREEN)✓ Cleanup complete$(NC)"

.DEFAULT_GOAL := help
