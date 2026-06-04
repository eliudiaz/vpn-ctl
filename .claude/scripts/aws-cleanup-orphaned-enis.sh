#!/bin/bash
set -euo pipefail

###############################################################################
# AWS EC2 Orphaned Resources Cleanup Script
#
# Purpose: Remove orphaned ENIs and unused security groups from aff-atg
# Location: .claude/scripts/aws-cleanup-orphaned-enis.sh
# Scope: Option A (Conservative) - Only clear orphans, minimal risk
#
# Resources to Delete:
#   1. ENI: eni-01d75d76eb7080228 (orphaned, 172.31.7.7)
#   2. ENI: eni-094723bda8d9ea6a3 (orphaned, 172.31.100.134)
#   3. SG: sg-01b4a0c5bb8f5c912 (multi-provider-nat-vimenca-sg, no usage)
#
# Estimated Savings: $2-4/month
# Risk Level: 🟢 LOW
# Time: ~11 minutes
#
# Usage:
#   ./aws-cleanup-orphaned-enis.sh          # Interactive mode (prompts confirm)
#   ./aws-cleanup-orphaned-enis.sh --force  # Non-interactive (auto-delete)
#   ./aws-cleanup-orphaned-enis.sh --dry-run # Preview only, no actual deletion
###############################################################################

# Configuration
AWS_PROFILE="${AWS_PROFILE:-affinity}"
AWS_REGION="${AWS_REGION:-us-east-2}"
VPC_ID="vpc-0efe6f2c199a72f9a"

# Orphaned resources
ORPHANED_ENI_1="eni-01d75d76eb7080228"
ORPHANED_ENI_2="eni-094723bda8d9ea6a3"
ORPHANED_SG="sg-01b4a0c5bb8f5c912"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default behavior
FORCE_DELETE=false
DRY_RUN=false
CONFIRM_INTERACTIVE=true

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --force)
            FORCE_DELETE=true
            CONFIRM_INTERACTIVE=false
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --help)
            grep "^#" "$0" | grep -v "^#!/" | sed 's/^# *//'
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

###############################################################################
# Functions
###############################################################################

log_header() {
    echo -e "\n${BLUE}=== $1 ===${NC}\n"
}

log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

confirm() {
    if [ "$FORCE_DELETE" = true ]; then
        return 0
    fi

    local prompt="$1"
    local response
    read -p "$prompt (yes/no): " response

    if [[ "$response" =~ ^[Yy][Ee][Ss]$ ]]; then
        return 0
    else
        return 1
    fi
}

aws_cmd() {
    local cmd="$1"
    if [ "$DRY_RUN" = true ]; then
        echo "[DRY-RUN] $cmd"
        return 0
    fi
    eval "$cmd"
}

get_eni_info() {
    local eni_id="$1"
    aws ec2 describe-network-interfaces \
        --network-interface-ids "$eni_id" \
        --region "$AWS_REGION" \
        --profile "$AWS_PROFILE" \
        --query 'NetworkInterfaces[0].[PrivateIpAddresses[0].PrivateIpAddress,Status,Attachment.InstanceId]' \
        --output text 2>/dev/null || echo "NOT_FOUND"
}

get_sg_info() {
    local sg_id="$1"
    aws ec2 describe-security-groups \
        --group-ids "$sg_id" \
        --region "$AWS_REGION" \
        --profile "$AWS_PROFILE" \
        --query 'SecurityGroups[0].[GroupName,IpPermissionsEgress[].Description]' \
        --output text 2>/dev/null || echo "NOT_FOUND"
}

###############################################################################
# Main Cleanup Flow
###############################################################################

main() {
    log_header "EC2 Orphaned Resources Cleanup - Option A (Conservative)"

    if [ "$DRY_RUN" = true ]; then
        log_warning "DRY-RUN MODE: No resources will be deleted"
    fi

    if [ "$FORCE_DELETE" = true ]; then
        log_warning "FORCE MODE: Resources will be deleted without individual confirmation"
    fi

    # ==========================================================================
    # PHASE 1: PRE-CLEANUP VERIFICATION
    # ==========================================================================

    log_header "PHASE 1: Pre-cleanup Verification"

    log_info "Checking ENI: $ORPHANED_ENI_1"
    eni1_info=$(get_eni_info "$ORPHANED_ENI_1")
    if [[ "$eni1_info" == "NOT_FOUND" ]]; then
        log_error "ENI $ORPHANED_ENI_1 not found (already deleted?)"
        ENI1_FOUND=false
    else
        log_success "Found ENI $ORPHANED_ENI_1"
        log_info "  IP: $(echo $eni1_info | awk '{print $1}')"
        log_info "  Status: $(echo $eni1_info | awk '{print $2}')"
        log_info "  Attachment: $(echo $eni1_info | awk '{print $3}' || echo 'NONE')"
        ENI1_FOUND=true
    fi

    log_info "Checking ENI: $ORPHANED_ENI_2"
    eni2_info=$(get_eni_info "$ORPHANED_ENI_2")
    if [[ "$eni2_info" == "NOT_FOUND" ]]; then
        log_error "ENI $ORPHANED_ENI_2 not found (already deleted?)"
        ENI2_FOUND=false
    else
        log_success "Found ENI $ORPHANED_ENI_2"
        log_info "  IP: $(echo $eni2_info | awk '{print $1}')"
        log_info "  Status: $(echo $eni2_info | awk '{print $2}')"
        log_info "  Attachment: $(echo $eni2_info | awk '{print $3}' || echo 'NONE')"
        ENI2_FOUND=true
    fi

    log_info "Checking Security Group: $ORPHANED_SG"
    sg_info=$(get_sg_info "$ORPHANED_SG")
    if [[ "$sg_info" == "NOT_FOUND" ]]; then
        log_error "Security Group $ORPHANED_SG not found (already deleted?)"
        SG_FOUND=false
    else
        log_success "Found Security Group $ORPHANED_SG"
        log_info "  Name: $(echo $sg_info | awk '{print $1}')"
        SG_FOUND=true
    fi

    # Count resources to delete
    RESOURCES_TO_DELETE=0
    [ "$ENI1_FOUND" = true ] && ((RESOURCES_TO_DELETE++))
    [ "$ENI2_FOUND" = true ] && ((RESOURCES_TO_DELETE++))
    [ "$SG_FOUND" = true ] && ((RESOURCES_TO_DELETE++))

    log_info "Total resources to delete: $RESOURCES_TO_DELETE"

    if [ "$RESOURCES_TO_DELETE" -eq 0 ]; then
        log_warning "No resources found to delete"
        return 0
    fi

    # ==========================================================================
    # PHASE 2: USER CONFIRMATION
    # ==========================================================================

    if [ "$CONFIRM_INTERACTIVE" = true ]; then
        log_header "PHASE 2: Confirmation"

        echo -e "${YELLOW}WARNING: You are about to delete the following resources:${NC}"
        [ "$ENI1_FOUND" = true ] && echo "  - ENI: $ORPHANED_ENI_1 (172.31.7.7)"
        [ "$ENI2_FOUND" = true ] && echo "  - ENI: $ORPHANED_ENI_2 (172.31.100.134)"
        [ "$SG_FOUND" = true ] && echo "  - Security Group: $ORPHANED_SG (multi-provider-nat-vimenca-sg)"
        echo ""

        if ! confirm "Proceed with deletion?"; then
            log_error "Cleanup cancelled by user"
            exit 1
        fi
    fi

    # ==========================================================================
    # PHASE 3: DELETE ORPHANED ENIs
    # ==========================================================================

    log_header "PHASE 3: Delete Orphaned ENIs"

    if [ "$ENI1_FOUND" = true ]; then
        log_info "Deleting ENI: $ORPHANED_ENI_1"
        if aws_cmd "aws ec2 delete-network-interface \
            --network-interface-id $ORPHANED_ENI_1 \
            --region $AWS_REGION \
            --profile $AWS_PROFILE"; then
            log_success "ENI $ORPHANED_ENI_1 deleted"
        else
            log_error "Failed to delete ENI $ORPHANED_ENI_1"
        fi
    fi

    if [ "$ENI2_FOUND" = true ]; then
        log_info "Deleting ENI: $ORPHANED_ENI_2"
        if aws_cmd "aws ec2 delete-network-interface \
            --network-interface-id $ORPHANED_ENI_2 \
            --region $AWS_REGION \
            --profile $AWS_PROFILE"; then
            log_success "ENI $ORPHANED_ENI_2 deleted"
        else
            log_error "Failed to delete ENI $ORPHANED_ENI_2"
        fi
    fi

    # ==========================================================================
    # PHASE 4: DELETE ORPHANED SECURITY GROUP
    # ==========================================================================

    log_header "PHASE 4: Delete Orphaned Security Group"

    if [ "$SG_FOUND" = true ]; then
        log_info "Deleting Security Group: $ORPHANED_SG"
        if aws_cmd "aws ec2 delete-security-group \
            --group-id $ORPHANED_SG \
            --region $AWS_REGION \
            --profile $AWS_PROFILE"; then
            log_success "Security Group $ORPHANED_SG deleted"
        else
            log_error "Failed to delete Security Group $ORPHANED_SG"
        fi
    fi

    # ==========================================================================
    # PHASE 5: POST-CLEANUP VERIFICATION
    # ==========================================================================

    if [ "$DRY_RUN" = false ]; then
        log_header "PHASE 5: Post-cleanup Verification"

        log_info "Verifying deletions..."

        sleep 2  # Wait for AWS eventual consistency

        if [ "$ENI1_FOUND" = true ]; then
            if get_eni_info "$ORPHANED_ENI_1" | grep -q "NOT_FOUND" 2>/dev/null; then
                log_success "ENI $ORPHANED_ENI_1 successfully deleted"
            else
                log_warning "ENI $ORPHANED_ENI_1 still exists (may take time to propagate)"
            fi
        fi

        if [ "$ENI2_FOUND" = true ]; then
            if get_eni_info "$ORPHANED_ENI_2" | grep -q "NOT_FOUND" 2>/dev/null; then
                log_success "ENI $ORPHANED_ENI_2 successfully deleted"
            else
                log_warning "ENI $ORPHANED_ENI_2 still exists (may take time to propagate)"
            fi
        fi

        # Verify active instances still exist
        log_info "Verifying active instances still running..."

        snat_instance=$(aws ec2 describe-instances \
            --instance-ids i-0b24f67baa6dd7ef3 \
            --region "$AWS_REGION" \
            --profile "$AWS_PROFILE" \
            --query 'Reservations[0].Instances[0].State.Name' \
            --output text 2>/dev/null)

        if [[ "$snat_instance" == "running" ]]; then
            log_success "SNAT instance (i-0b24f67baa6dd7ef3) is running"
        else
            log_warning "SNAT instance status: $snat_instance"
        fi

        tester_instance=$(aws ec2 describe-instances \
            --instance-ids i-05c40371fbcf6ed71 \
            --region "$AWS_REGION" \
            --profile "$AWS_PROFILE" \
            --query 'Reservations[0].Instances[0].State.Name' \
            --output text 2>/dev/null)

        if [[ "$tester_instance" == "running" ]]; then
            log_success "Vimenca tester instance (i-05c40371fbcf6ed71) is running"
        else
            log_warning "Vimenca tester instance status: $tester_instance"
        fi
    fi

    # ==========================================================================
    # SUMMARY
    # ==========================================================================

    log_header "CLEANUP SUMMARY"

    if [ "$DRY_RUN" = true ]; then
        log_info "DRY-RUN completed (no actual deletions)"
    else
        echo -e "${GREEN}Cleanup completed successfully!${NC}"
        echo ""
        echo "Resources deleted:"
        [ "$ENI1_FOUND" = true ] && echo "  ✅ ENI: $ORPHANED_ENI_1"
        [ "$ENI2_FOUND" = true ] && echo "  ✅ ENI: $ORPHANED_ENI_2"
        [ "$SG_FOUND" = true ] && echo "  ✅ Security Group: $ORPHANED_SG"
        echo ""
        echo "Estimated monthly savings: \$2-4"
        echo "Risk level: 🟢 LOW"
    fi
}

# Run main function
main
