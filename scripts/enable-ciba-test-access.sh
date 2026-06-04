#!/bin/bash
#
# Enable CIBA VPN to test connectivity to EKS nodes in asg-plat-dev
# This script is independent of Pulumi and can be revoked anytime
#
# Usage:
#   ./enable-ciba-test-access.sh              # Enable access
#   ./enable-ciba-test-access.sh --disable    # Disable access
#   ./enable-ciba-test-access.sh --status     # Check status
#

set -e

# Configuration
AWS_PROFILE="${AWS_PROFILE:-affinity}"
AWS_REGION="us-east-2"
EKS_CLUSTER="asg-plat-dev"
EKS_VPC_ID="vpc-0efe6f2c199a72f9a"
CIBA_CIDR="172.17.0.0/16"
EKS_NODE_SG="sg-01a8b61064a710745"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  CIBA VPN Test Access Manager${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo ""

# Function to check if rule exists
check_rule_exists() {
    aws ec2 describe-security-groups \
        --group-ids "$EKS_NODE_SG" \
        --region "$AWS_REGION" \
        --query "SecurityGroups[0].IpPermissions[?IpRanges[?CidrIp=='$CIBA_CIDR']]" \
        --output json | grep -q "$CIBA_CIDR" && return 0 || return 1
}

# Function to enable access
enable_access() {
    echo -e "${YELLOW}Enabling CIBA access to EKS nodes...${NC}"
    echo ""
    
    if check_rule_exists; then
        echo -e "${GREEN}✓ CIBA access already enabled${NC}"
        return 0
    fi
    
    echo -e "${BLUE}Adding security group rule:${NC}"
    echo "  - Security Group: $EKS_NODE_SG (eks-cluster-sg-$EKS_CLUSTER)"
    echo "  - Source CIDR: $CIBA_CIDR"
    echo "  - Protocol: All (-1)"
    echo "  - Ports: All"
    echo ""
    
    aws ec2 authorize-security-group-ingress \
        --group-id "$EKS_NODE_SG" \
        --protocol all \
        --cidr "$CIBA_CIDR" \
        --region "$AWS_REGION" \
        --profile "$AWS_PROFILE" \
        2>&1
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Rule added successfully${NC}"
    else
        echo -e "${RED}✗ Failed to add rule${NC}"
        exit 1
    fi
}

# Function to disable access
disable_access() {
    echo -e "${YELLOW}Disabling CIBA access to EKS nodes...${NC}"
    echo ""
    
    if ! check_rule_exists; then
        echo -e "${GREEN}✓ CIBA access already disabled${NC}"
        return 0
    fi
    
    echo -e "${BLUE}Removing security group rule:${NC}"
    echo "  - Security Group: $EKS_NODE_SG"
    echo "  - Source CIDR: $CIBA_CIDR"
    echo ""
    
    aws ec2 revoke-security-group-ingress \
        --group-id "$EKS_NODE_SG" \
        --protocol all \
        --cidr "$CIBA_CIDR" \
        --region "$AWS_REGION" \
        --profile "$AWS_PROFILE" \
        2>&1
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Rule removed successfully${NC}"
    else
        echo -e "${RED}✗ Failed to remove rule${NC}"
        exit 1
    fi
}

# Function to check status
check_status() {
    echo -e "${BLUE}Checking CIBA access status...${NC}"
    echo ""
    
    echo -e "${YELLOW}Configuration:${NC}"
    echo "  - EKS Cluster: $EKS_CLUSTER"
    echo "  - EKS VPC: $EKS_VPC_ID"
    echo "  - Node Security Group: $EKS_NODE_SG"
    echo "  - CIBA CIDR: $CIBA_CIDR"
    echo ""
    
    if check_rule_exists; then
        echo -e "${GREEN}✓ CIBA access is ENABLED${NC}"
        echo ""
        echo -e "${BLUE}EKS Nodes available for CIBA testing:${NC}"
        aws ec2 describe-instances \
            --region "$AWS_REGION" \
            --filters "Name=tag:eks:cluster-name,Values=$EKS_CLUSTER" \
            "Name=instance-state-name,Values=running" \
            --query 'Reservations[*].Instances[*].[PrivateIpAddress, InstanceId, State.Name]' \
            --output text | awk '{print "  - " $1 " (" $2 ")"}'
    else
        echo -e "${RED}✗ CIBA access is DISABLED${NC}"
    fi
}

# Main logic
case "${1:-}" in
    --disable)
        disable_access
        ;;
    --status)
        check_status
        ;;
    --enable|"")
        enable_access
        echo ""
        check_status
        ;;
    --help)
        cat << HELP
Usage: $0 [OPTION]

Options:
  (no option)     Enable CIBA access to EKS nodes
  --enable        Enable CIBA access to EKS nodes
  --disable       Disable CIBA access to EKS nodes
  --status        Check current CIBA access status
  --help          Show this help message

Environment Variables:
  AWS_PROFILE     AWS profile to use (default: affinity)
  AWS_REGION      AWS region (default: us-east-2)

Examples:
  ./enable-ciba-test-access.sh              # Enable access
  ./enable-ciba-test-access.sh --disable    # Disable access
  ./enable-ciba-test-access.sh --status     # Check status

HELP
        ;;
    *)
        echo -e "${RED}Unknown option: $1${NC}"
        echo "Use --help for usage information"
        exit 1
        ;;
esac

echo ""
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
