# VPN Health Helm Chart

Kubernetes Helm chart for deploying the VPN Health Monitoring Service to EKS clusters.

## Features

- **IRSA Support**: Secure AWS API access via IAM Roles for Service Accounts
- **ConfigMap Integration**: Mounts `vpn-peers.yaml` and `infra-config.json` 
- **Health Probes**: Liveness and readiness probes for reliability
- **Multi-Environment**: Separate values files for dev/qa/prod
- **boto3 Integration**: Direct AWS API access (no AWS CLI subprocess calls)

## Prerequisites

1. EKS cluster with IRSA enabled
2. IAM role for VPN Health Service: `vpn-health-irsa-{env}`
3. `kubectl` configured with cluster access
4. `helm` CLI installed
5. Docker image pushed to ECR

## Quick Start

### 1. Create IRSA IAM Role

```bash
# Create IAM role with EC2 permissions for VPN health checks
aws iam create-role \
  --role-name vpn-health-irsa-dev \
  --assume-role-policy-document file://trust-policy.json \
  --profile affinity
```

Trust policy (`trust-policy.json`):
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::ACCOUNT_ID:oidc-provider/oidc.eks.REGION.amazonaws.com/id/EXAMPLEID"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "oidc.eks.REGION.amazonaws.com/id/EXAMPLEID:sub": "system:serviceaccount:vpn-health:vpn-health"
        }
      }
    }
  ]
}
```

### 2. Attach EC2 Permissions

```bash
aws iam put-role-policy \
  --role-name vpn-health-irsa-dev \
  --policy-name vpn-health-ec2-access \
  --policy-document file://ec2-policy.json \
  --profile affinity
```

EC2 policy (`ec2-policy.json`):
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeVpnConnections",
        "ec2:DescribeTransitGateways",
        "ec2:DescribeTransitGatewayAttachments",
        "ec2:DescribeTransitGatewayRouteTables",
        "ec2:SearchTransitGatewayRoutes"
      ],
      "Resource": "*"
    }
  ]
}
```

### 3. Deploy with vpnctl

```bash
# Generate infrastructure config
vpnctl infra export-config --output infra-config.json

# Deploy to Kubernetes
vpnctl health deploy --target helm --environment dev

# Or deploy with custom ECR registry
vpnctl health deploy \
  --target helm \
  --environment prod \
  --ecr-registry 123456789.dkr.ecr.us-east-2.amazonaws.com \
  --namespace vpn-health-prod
```

## Values Configuration

### Default Values (values.yaml)

- `replicaCount`: 1 pod
- `image.tag`: latest
- `service.type`: ClusterIP on port 8080
- `resources.limits`: 500m CPU, 512Mi memory
- `aws.region`: us-east-2

### Environment-Specific Values

**Development** (values/dev.yaml):
```yaml
replicaCount: 1
aws.irsaRoleArn: arn:aws:iam::ACCOUNT_ID:role/vpn-health-irsa-dev
```

**Production** (values/prod.yaml):
```yaml
replicaCount: 2
autoscaling.enabled: true
aws.irsaRoleArn: arn:aws:iam::ACCOUNT_ID:role/vpn-health-irsa-prod
```

## Helm Commands

```bash
# Install
helm install vpn-health . \
  -n vpn-health \
  -f values/dev.yaml

# Upgrade
helm upgrade vpn-health . \
  -n vpn-health \
  -f values/dev.yaml

# View status
helm status vpn-health -n vpn-health

# Uninstall
helm uninstall vpn-health -n vpn-health
```

## Troubleshooting

### Pod won't start: ImagePullBackOff

```bash
# Check image in ECR
aws ecr list-images --repository-name vpn-health --profile affinity

# Update image tag in values
helm upgrade vpn-health . \
  --set image.tag=CORRECT_TAG \
  -n vpn-health
```

### IRSA not working

```bash
# Verify ServiceAccount annotation
kubectl get serviceaccount vpn-health -n vpn-health -o yaml

# Check pod environment
kubectl exec -it deployment/vpn-health -n vpn-health -- env | grep AWS

# Should show:
# AWS_ROLE_ARN=arn:aws:iam::...
# AWS_WEB_IDENTITY_TOKEN_FILE=/var/run/secrets/eks.amazonaws.com/serviceaccount/token
```

### ConfigMaps not mounted

```bash
# Verify ConfigMaps exist
kubectl get configmaps -n vpn-health

# Verify pod volumes
kubectl get pod -n vpn-health -o yaml | grep -A 10 volumes:
```

## Development

### Building and Pushing Image

```bash
# Build
docker build -f vpnctl/health/Dockerfile -t vpn-health:local .

# Tag for ECR
docker tag vpn-health:local REGISTRY/vpn-health:latest

# Push
docker push REGISTRY/vpn-health:latest
```

### Local Testing

```bash
# Test with docker-compose
vpnctl health deploy --target docker --port 8080

# Test endpoints
curl http://localhost:8080/health | jq
curl http://localhost:8080/health/peers | jq
```

## Monitoring

```bash
# View logs
kubectl logs -f deployment/vpn-health -n vpn-health

# Get pod events
kubectl describe pod -n vpn-health

# Check health endpoint
kubectl port-forward -n vpn-health svc/vpn-health 8080:8080
curl http://localhost:8080/health | jq
```
