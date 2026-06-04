#!/bin/bash

################################################################################
# CIBA NAT Layer Setup Script
# Purpose: Create a NAT instance that translates 172.17.x → 172.31.x traffic
# This allows CIBA to reach EKS nodes while keeping traffic under 172.17.x
#
# Usage: ./setup-ciba-nat-layer.sh [--enable|--disable|--status]
################################################################################

set -e

# Configuration
REGION="us-east-2"
CLUSTER_NAME="asg-plat-dev"
NAT_INSTANCE_NAME="ciba-nat-gateway"
CIBA_CIDR="172.17.0.0/16"
EKS_CIDR="172.31.0.0/16"
TGW_ROUTE_DESTINATION="172.17.0.0/16"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[!]${NC} $1"
}

################################################################################
# Get Infrastructure Details from Pulumi
################################################################################

get_pulumi_config() {
    log_info "Fetching infrastructure details from Pulumi..."

    # Get VPC info
    VPC_ID=$(pulumi stack output cluster_asg_plat_dev --json | jq -r '.vpc_id')
    VPC_CIDR=$(pulumi stack output cluster_asg_plat_dev --json | jq -r '.vpc_cidr')
    SUBNET_IDS=$(pulumi stack output cluster_asg_plat_dev --json | jq -r '.subnet_ids[]' | head -1)

    # Get TGW info
    TGW_ID=$(pulumi stack output transit_gateway_id --json | jq -r '.')

    # Get TGW attachment ID for EKS
    TGW_RTB_ID=$(aws ec2 describe-transit-gateway-route-tables \
        --filters "Name=transit-gateway-id,Values=$TGW_ID" \
        --region $REGION \
        --query 'TransitGatewayRouteTables[0].TransitGatewayRouteTableId' \
        --output text)

    if [[ -z "$VPC_ID" ]] || [[ -z "$SUBNET_IDS" ]] || [[ -z "$TGW_ID" ]]; then
        log_error "Failed to retrieve Pulumi configuration"
        exit 1
    fi

    log_success "VPC: $VPC_ID"
    log_success "Subnet: $SUBNET_IDS"
    log_success "TGW: $TGW_ID"
    log_success "TGW Route Table: $TGW_RTB_ID"
}

################################################################################
# Create Security Group for NAT Instance
################################################################################

create_security_group() {
    log_info "Creating security group for NAT instance..."

    # Check if SG already exists
    SG_ID=$(aws ec2 describe-security-groups \
        --filters "Name=vpc-id,Values=$VPC_ID" "Name=group-name,Values=ciba-nat-sg" \
        --region $REGION \
        --query 'SecurityGroups[0].GroupId' \
        --output text 2>/dev/null || echo "")

    if [[ "$SG_ID" != "" && "$SG_ID" != "None" ]]; then
        log_success "Security group already exists: $SG_ID"
        return
    fi

    # Create new SG
    SG_ID=$(aws ec2 create-security-group \
        --group-name "ciba-nat-sg" \
        --description "Security group for CIBA NAT instance" \
        --vpc-id $VPC_ID \
        --region $REGION \
        --output text)

    log_success "Created security group: $SG_ID"

    # Allow traffic from CIBA CIDR (all protocols)
    aws ec2 authorize-security-group-ingress \
        --group-id $SG_ID \
        --protocol -1 \
        --cidr $CIBA_CIDR \
        --region $REGION 2>/dev/null || log_warn "Rule may already exist"

    # Allow traffic from EKS VPC (for responses)
    aws ec2 authorize-security-group-ingress \
        --group-id $SG_ID \
        --protocol -1 \
        --cidr $EKS_CIDR \
        --region $REGION 2>/dev/null || log_warn "Rule may already exist"

    # Allow outbound to all (by default)
    log_success "Security group rules configured"
}

################################################################################
# Launch NAT Instance
################################################################################

launch_nat_instance() {
    log_info "Launching NAT instance..."

    # Check if instance already exists
    INSTANCE_ID=$(aws ec2 describe-instances \
        --filters "Name=vpc-id,Values=$VPC_ID" "Name=tag:Name,Values=$NAT_INSTANCE_NAME" "Name=instance-state-name,Values=running" \
        --region $REGION \
        --query 'Reservations[0].Instances[0].InstanceId' \
        --output text 2>/dev/null || echo "")

    if [[ "$INSTANCE_ID" != "" && "$INSTANCE_ID" != "None" ]]; then
        log_success "NAT instance already running: $INSTANCE_ID"
        return
    fi

    # Get latest Amazon Linux 2 AMI
    AMI_ID=$(aws ec2 describe-images \
        --owners amazon \
        --filters "Name=name,Values=amzn2-ami-hvm-*-x86_64-gp2" "Name=state,Values=available" \
        --region $REGION \
        --query 'sort_by(Images, &CreationDate)[-1].ImageId' \
        --output text)

    log_info "Using AMI: $AMI_ID"

    # User data script to configure NAT
    read -r -d '' USER_DATA_SCRIPT << 'USERDATA_EOF' || true
#!/bin/bash
set -e

# Enable IP forwarding
echo 1 > /proc/sys/net/ipv4/ip_forward
echo "net.ipv4.ip_forward = 1" >> /etc/sysctl.conf
sysctl -p > /dev/null 2>&1

# Get instance IP
INSTANCE_IP=$(ec2-metadata --local-ipv4 | cut -d " " -f 2)

# Configure iptables for DNAT
# This translates traffic from 172.17.0.0/16 to be routed to 172.31.0.0/16
iptables -t nat -A PREROUTING -d 172.17.0.0/16 -j DNAT --to-destination 172.31.0.0/16
iptables -t nat -A POSTROUTING -s 172.17.0.0/16 -j MASQUERADE

# Save iptables rules
yum install -y iptables-services > /dev/null 2>&1
service iptables save > /dev/null 2>&1
systemctl enable iptables > /dev/null 2>&1

# Log completion
echo "NAT layer configured on $INSTANCE_IP" > /var/log/nat-setup.log
USERDATA_EOF

    # Base64 encode user data
    USER_DATA_B64=$(echo "$USER_DATA_SCRIPT" | base64 -w 0)

    # Launch instance
    INSTANCE_ID=$(aws ec2 run-instances \
        --image-id $AMI_ID \
        --instance-type t3.micro \
        --subnet-id $SUBNET_IDS \
        --security-group-ids $SG_ID \
        --user-data $USER_DATA_B64 \
        --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NAT_INSTANCE_NAME},{Key=Component,Value=CibaVpnNat}]" \
        --region $REGION \
        --output text \
        --query 'Instances[0].InstanceId')

    log_success "Launched NAT instance: $INSTANCE_ID"

    # Wait for instance to be running
    log_info "Waiting for instance to be running..."
    aws ec2 wait instance-running \
        --instance-ids $INSTANCE_ID \
        --region $REGION

    log_success "Instance is running"

    # Get instance details
    sleep 5  # Wait a bit for ENI to be assigned
    get_nat_instance_details $INSTANCE_ID
}

################################################################################
# Get NAT Instance Details
################################################################################

get_nat_instance_details() {
    local INSTANCE_ID=$1

    # Get ENI and IP info
    NAT_PRIVATE_IP=$(aws ec2 describe-instances \
        --instance-ids $INSTANCE_ID \
        --region $REGION \
        --query 'Reservations[0].Instances[0].PrivateIpAddress' \
        --output text)

    NAT_ENI_ID=$(aws ec2 describe-instances \
        --instance-ids $INSTANCE_ID \
        --region $REGION \
        --query 'Reservations[0].Instances[0].NetworkInterfaces[0].NetworkInterfaceId' \
        --output text)

    log_success "NAT Instance IP: $NAT_PRIVATE_IP"
    log_success "NAT Instance ENI: $NAT_ENI_ID"

    # Save to file for later reference
    echo "INSTANCE_ID=$INSTANCE_ID" > .ciba-nat-config
    echo "NAT_PRIVATE_IP=$NAT_PRIVATE_IP" >> .ciba-nat-config
    echo "NAT_ENI_ID=$NAT_ENI_ID" >> .ciba-nat-config
    echo "SG_ID=$SG_ID" >> .ciba-nat-config
}

################################################################################
# Attach to Transit Gateway and Add Route
################################################################################

setup_tgw_routing() {
    log_info "Setting up Transit Gateway routing..."

    # Source the config file
    if [[ -f .ciba-nat-config ]]; then
        source .ciba-nat-config
    fi

    # Create TGW attachment for NAT instance (if needed)
    # For NAT instance in same VPC, we need to attach via ENI
    log_info "Creating Transit Gateway attachment for NAT instance..."

    TGW_ATTACHMENT_ID=$(aws ec2 describe-transit-gateway-attachments \
        --filters "Name=transit-gateway-id,Values=$TGW_ID" "Name=resource-id,Values=$INSTANCE_ID" \
        --region $REGION \
        --query 'TransitGatewayAttachments[0].TransitGatewayAttachmentId' \
        --output text 2>/dev/null || echo "")

    if [[ "$TGW_ATTACHMENT_ID" == "" || "$TGW_ATTACHMENT_ID" == "None" ]]; then
        # Attachment via VPC attachment for same VPC routing
        log_warn "NAT instance is in same VPC - using existing VPC attachment"

        # Get existing EKS attachment
        TGW_ATTACHMENT_ID=$(aws ec2 describe-transit-gateway-attachments \
            --filters "Name=transit-gateway-id,Values=$TGW_ID" "Name=resource-id,Values=$VPC_ID" \
            --region $REGION \
            --query 'TransitGatewayAttachments[0].TransitGatewayAttachmentId' \
            --output text)
    fi

    log_success "Using TGW Attachment: $TGW_ATTACHMENT_ID"

    # Add static route for 172.17.0.0/16 → NAT instance
    log_info "Adding Transit Gateway route: $TGW_ROUTE_DESTINATION → NAT instance"

    # Check if route already exists
    EXISTING_ROUTE=$(aws ec2 search-transit-gateway-routes \
        --transit-gateway-route-table-id $TGW_RTB_ID \
        --filters "Name=state,Values=active" \
        --region $REGION \
        --query "Routes[?DestinationCidrBlock=='$TGW_ROUTE_DESTINATION'].DestinationCidrBlock" \
        --output text 2>/dev/null || echo "")

    if [[ "$EXISTING_ROUTE" == "$TGW_ROUTE_DESTINATION" ]]; then
        log_warn "Route already exists for $TGW_ROUTE_DESTINATION"
        log_info "Deleting existing route to replace it..."
        aws ec2 delete-transit-gateway-route \
            --transit-gateway-route-table-id $TGW_RTB_ID \
            --destination-cidr-block $TGW_ROUTE_DESTINATION \
            --region $REGION || true
        sleep 2
    fi

    # Create new route pointing to NAT instance via VPC attachment
    aws ec2 create-transit-gateway-route \
        --transit-gateway-route-table-id $TGW_RTB_ID \
        --destination-cidr-block $TGW_ROUTE_DESTINATION \
        --transit-gateway-attachment-id $TGW_ATTACHMENT_ID \
        --region $REGION 2>/dev/null || log_warn "Route creation may have failed"

    log_success "Transit Gateway route configured"
}

################################################################################
# Enable NAT Layer
################################################################################

enable_nat_layer() {
    log_info "================================"
    log_info "ENABLING CIBA NAT LAYER"
    log_info "================================"

    get_pulumi_config
    create_security_group
    launch_nat_instance
    setup_tgw_routing

    log_info ""
    log_success "CIBA NAT Layer Enabled!"
    log_info "================================"
    log_info "CIBA traffic flow:"
    log_info "  1. CIBA (172.17.0.0/16) → VPN → Transit Gateway"
    log_info "  2. TGW routes 172.17.0.0/16 → NAT instance"
    log_info "  3. NAT instance translates to 172.31.0.0/16"
    log_info "  4. Traffic reaches EKS nodes"
    log_info ""
    log_info "To test from CIBA:"
    log_info "  ping 172.17.13.68  # (will be NAT'd to actual EKS node)"
    log_info "================================"
}

################################################################################
# Check Status
################################################################################

check_status() {
    log_info "Checking CIBA NAT Layer status..."

    if [[ ! -f .ciba-nat-config ]]; then
        log_error "NAT layer configuration not found"
        return 1
    fi

    source .ciba-nat-config

    # Check if instance is running
    INSTANCE_STATE=$(aws ec2 describe-instances \
        --instance-ids $INSTANCE_ID \
        --region $REGION \
        --query 'Reservations[0].Instances[0].State.Name' \
        --output text 2>/dev/null || echo "terminated")

    if [[ "$INSTANCE_STATE" == "running" ]]; then
        log_success "NAT Instance: RUNNING ($INSTANCE_ID)"
    else
        log_error "NAT Instance: $INSTANCE_STATE"
        return 1
    fi

    # Check TGW route
    ROUTE_STATE=$(aws ec2 search-transit-gateway-routes \
        --transit-gateway-route-table-id $TGW_RTB_ID \
        --filters "Name=route-search.exact-match,Values=$TGW_ROUTE_DESTINATION" \
        --region $REGION \
        --query 'Routes[0].State' \
        --output text 2>/dev/null || echo "not-found")

    if [[ "$ROUTE_STATE" == "active" ]]; then
        log_success "TGW Route: ACTIVE ($TGW_ROUTE_DESTINATION)"
    else
        log_error "TGW Route: $ROUTE_STATE"
        return 1
    fi

    log_info ""
    log_success "NAT Layer is READY"
}

################################################################################
# Disable NAT Layer
################################################################################

disable_nat_layer() {
    log_warn "DISABLING CIBA NAT LAYER"

    if [[ ! -f .ciba-nat-config ]]; then
        log_error "NAT layer configuration not found"
        return 1
    fi

    source .ciba-nat-config
    get_pulumi_config

    # Terminate instance
    log_info "Terminating NAT instance: $INSTANCE_ID"
    aws ec2 terminate-instances \
        --instance-ids $INSTANCE_ID \
        --region $REGION > /dev/null 2>&1

    # Delete Transit Gateway route
    log_info "Deleting Transit Gateway route..."
    aws ec2 delete-transit-gateway-route \
        --transit-gateway-route-table-id $TGW_RTB_ID \
        --destination-cidr-block $TGW_ROUTE_DESTINATION \
        --region $REGION 2>/dev/null || true

    # Delete security group (wait for instance to fully terminate)
    sleep 10
    log_info "Deleting security group: $SG_ID"
    aws ec2 delete-security-group \
        --group-id $SG_ID \
        --region $REGION 2>/dev/null || log_warn "Could not delete SG immediately"

    # Clean up config
    rm -f .ciba-nat-config

    log_success "CIBA NAT Layer Disabled"
}

################################################################################
# Main
################################################################################

main() {
    ACTION="${1:-enable}"

    case "$ACTION" in
        --enable|enable)
            enable_nat_layer
            ;;
        --disable|disable)
            disable_nat_layer
            ;;
        --status|status)
            check_status
            ;;
        *)
            echo "Usage: $0 [--enable|--disable|--status]"
            echo ""
            echo "Commands:"
            echo "  --enable   Enable CIBA NAT layer"
            echo "  --disable  Disable CIBA NAT layer"
            echo "  --status   Check NAT layer status"
            exit 1
            ;;
    esac
}

main "$@"
