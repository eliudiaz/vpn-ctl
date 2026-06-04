#!/usr/bin/env python3
"""
VPN Pool Validation Script

Validates the VPN pool implementation is working correctly.
Run this after deployment to verify functionality.

Usage:
    python scripts/validate-vpn-pool.py [--check-aws] [--dry-run]

Options:
    --check-aws: Also verify against actual AWS resources
    --dry-run:   Don't make any changes, just report
"""

import sys
import argparse
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "pulumi"))

from vpn_registry import VpnRegistry, VpnPoolEntry
from vpn_attachment import VpnAttachmentManager, VpnAttachmentExecutor
import logging
import json

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)


class VpnPoolValidator:
    """Validates VPN pool implementation."""

    def __init__(self, check_aws=False, dry_run=False):
        self.check_aws = check_aws
        self.dry_run = dry_run
        self.registry = VpnRegistry()
        self.manager = VpnAttachmentManager(self.registry)
        self.executor = VpnAttachmentExecutor(self.registry)
        self.errors = []
        self.warnings = []
        self.tests_passed = 0
        self.tests_failed = 0

    def log_pass(self, message: str):
        """Log passing test."""
        logger.info(f"✅ {message}")
        self.tests_passed += 1

    def log_fail(self, message: str):
        """Log failing test."""
        logger.error(f"❌ {message}")
        self.tests_failed += 1
        self.errors.append(message)

    def log_warn(self, message: str):
        """Log warning."""
        logger.warning(f"⚠️  {message}")
        self.warnings.append(message)

    def validate_registry_file(self) -> bool:
        """Validate registry file exists and is valid."""
        logger.info("\n" + "=" * 80)
        logger.info("1. REGISTRY FILE VALIDATION")
        logger.info("=" * 80)

        registry_path = Path("config/vpn-pool.yaml")

        if not registry_path.exists():
            self.log_fail(f"Registry file not found: {registry_path}")
            return False

        self.log_pass(f"Registry file exists: {registry_path}")

        try:
            data = self.registry.data
            self.log_pass(f"Registry YAML is valid")
        except Exception as e:
            self.log_fail(f"Registry YAML parsing failed: {e}")
            return False

        # Check structure
        if 'vpns' not in data:
            self.log_fail("Registry missing 'vpns' key")
            return False

        self.log_pass("Registry structure is valid")
        return True

    def validate_vpn_entries(self) -> bool:
        """Validate all VPN entries in registry."""
        logger.info("\n" + "=" * 80)
        logger.info("2. VPN ENTRY VALIDATION")
        logger.info("=" * 80)

        vpns = self.registry.get_all_vpns()
        logger.info(f"Found {len(vpns)} VPNs in registry")

        if not vpns:
            self.log_warn("No VPNs in registry yet (normal for new deployment)")
            return True

        all_valid = True

        for i, vpn in enumerate(vpns, 1):
            logger.info(f"\nVPN {i}: {vpn.vpn_id}")

            # Check required fields
            required = ['vpn_id', 'customer_gateway_id', 'state', 'tunnel_profile']
            for field in required:
                value = getattr(vpn, field, None)
                if not value:
                    self.log_fail(f"  Missing {field}")
                    all_valid = False
                else:
                    self.log_pass(f"  {field}: {value}")

            # Check state is valid
            valid_states = ['attached', 'detached', 'orphaned']
            if vpn.state not in valid_states:
                self.log_fail(f"  Invalid state: {vpn.state} (must be {valid_states})")
                all_valid = False
            else:
                self.log_pass(f"  State is valid: {vpn.state}")

            # Check tunnel IPs if attached
            if vpn.state == 'attached':
                if not vpn.tunnel1_ip or not vpn.tunnel2_ip:
                    self.log_warn(f"  Tunnel IPs missing for attached VPN")
                else:
                    self.log_pass(f"  Tunnel IPs: {vpn.tunnel1_ip}, {vpn.tunnel2_ip}")

            # Check preserved_count
            if vpn.preserved_count < 0:
                self.log_fail(f"  Invalid preserved_count: {vpn.preserved_count}")
                all_valid = False
            elif vpn.preserved_count > 0:
                self.log_pass(f"  VPN reused {vpn.preserved_count} times")

        return all_valid

    def validate_attachment_logic(self) -> bool:
        """Validate attachment decision logic."""
        logger.info("\n" + "=" * 80)
        logger.info("3. ATTACHMENT LOGIC VALIDATION")
        logger.info("=" * 80)

        # Test decision for non-existent peer
        decision = self.manager.decide("test-peer", "checkpoint_r80")
        if decision.action == 'create':
            self.log_pass("Decision for new peer is 'create'")
        else:
            self.log_fail(f"Decision for new peer should be 'create', got '{decision.action}'")
            return False

        # Test decision for existing attached peer
        attached = self.registry.get_attached_vpns()
        if attached:
            vpn = attached[0]
            decision = self.manager.decide(vpn.peer_name, vpn.tunnel_profile)
            if decision.action == 'attach':
                self.log_pass(f"Decision for existing attached peer is 'attach'")
            else:
                self.log_fail(f"Decision should be 'attach', got '{decision.action}'")
                return False

        # Test decision for detached peer
        detached = [v for v in self.registry.get_all_vpns() if v.state == 'detached']
        if detached:
            vpn = detached[0]
            decision = self.manager.decide(vpn.peer_name or "reuse-peer", vpn.tunnel_profile)
            if decision.action == 'attach':
                self.log_pass(f"Decision for detached VPN is 'attach'")
            else:
                self.log_warn(f"Decision for detached VPN should be 'attach'")

        self.log_pass("Attachment logic is working correctly")
        return True

    def validate_pool_stats(self) -> bool:
        """Validate pool statistics."""
        logger.info("\n" + "=" * 80)
        logger.info("4. POOL STATISTICS")
        logger.info("=" * 80)

        stats = self.registry.get_stats()

        logger.info(f"Total VPNs: {stats['total']}")
        logger.info(f"  Attached: {stats['attached']}")
        logger.info(f"  Detached: {stats['detached']}")
        logger.info(f"  Orphaned: {stats['orphaned']}")
        logger.info(f"Total preservations: {stats['total_preservations']}")

        if stats['total'] == 0:
            self.log_warn("No VPNs in pool (normal for new deployment)")
            return True

        if stats['attached'] + stats['detached'] + stats['orphaned'] != stats['total']:
            self.log_fail("Stats don't add up (attached + detached + orphaned != total)")
            return False

        self.log_pass("Pool statistics are consistent")
        return True

    def validate_aws_sync(self) -> bool:
        """Validate registry matches AWS resources (if --check-aws)."""
        if not self.check_aws:
            logger.info("\n" + "=" * 80)
            logger.info("5. AWS SYNC CHECK (Skipped)")
            logger.info("=" * 80)
            logger.info("Use --check-aws flag to validate against AWS")
            return True

        logger.info("\n" + "=" * 80)
        logger.info("5. AWS SYNC VALIDATION")
        logger.info("=" * 80)

        try:
            import boto3
        except ImportError:
            self.log_fail("boto3 not installed, cannot check AWS")
            return False

        try:
            ec2 = boto3.client('ec2', region_name='us-east-2')
            response = ec2.describe_vpn_connections()
            aws_vpns = {v['VpnConnectionId']: v for v in response['VpnConnections']}

            logger.info(f"Found {len(aws_vpns)} VPNs in AWS")

            # Check each VPN in registry exists in AWS
            registry_vpns = self.registry.get_all_vpns()
            for vpn in registry_vpns:
                if vpn.vpn_id in aws_vpns:
                    self.log_pass(f"VPN {vpn.vpn_id} exists in AWS")
                else:
                    self.log_fail(f"VPN {vpn.vpn_id} missing in AWS (orphaned)")

            return True

        except Exception as e:
            self.log_fail(f"AWS sync check failed: {e}")
            return False

    def print_summary(self):
        """Print validation summary."""
        logger.info("\n" + "=" * 80)
        logger.info("VALIDATION SUMMARY")
        logger.info("=" * 80)

        total = self.tests_passed + self.tests_failed
        percentage = (self.tests_passed / total * 100) if total > 0 else 0

        logger.info(f"Tests Passed: {self.tests_passed}")
        logger.info(f"Tests Failed: {self.tests_failed}")
        logger.info(f"Success Rate: {percentage:.1f}%")

        if self.warnings:
            logger.info(f"\nWarnings ({len(self.warnings)}):")
            for warning in self.warnings:
                logger.info(f"  • {warning}")

        if self.errors:
            logger.info(f"\nErrors ({len(self.errors)}):")
            for error in self.errors:
                logger.info(f"  • {error}")

        logger.info("=" * 80)

        if self.tests_failed == 0:
            logger.info("✅ All validation checks passed!")
            return 0
        else:
            logger.info("❌ Some validation checks failed!")
            return 1

    def run_all(self) -> int:
        """Run all validation checks."""
        logger.info("=" * 80)
        logger.info("VPN POOL VALIDATION")
        logger.info("=" * 80)
        logger.info(f"Mode: {'DRY-RUN' if self.dry_run else 'Normal'}")
        logger.info(f"AWS Check: {'Enabled' if self.check_aws else 'Disabled'}")

        self.validate_registry_file()
        self.validate_vpn_entries()
        self.validate_attachment_logic()
        self.validate_pool_stats()
        self.validate_aws_sync()

        return self.print_summary()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Validate VPN Pool implementation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python validate-vpn-pool.py              # Basic validation
  python validate-vpn-pool.py --check-aws  # Also verify AWS resources
  python validate-vpn-pool.py --dry-run    # Don't make changes
        """
    )

    parser.add_argument('--check-aws', action='store_true',
                        help='Validate registry matches AWS resources')
    parser.add_argument('--dry-run', action='store_true',
                        help='Don\'t make any changes')

    args = parser.parse_args()

    validator = VpnPoolValidator(check_aws=args.check_aws, dry_run=args.dry_run)
    exit_code = validator.run_all()

    sys.exit(exit_code)


if __name__ == '__main__':
    main()
