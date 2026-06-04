# VPN Health App - Deployment Quick Start

## Prerequisites

- ✅ AWS credentials configured: `~/.aws/credentials` with `default` profile
- ✅ EKS cluster access: `kubectl` configured for asg-plat-dev
- ✅ Docker installed locally
- ✅ Helm 3 installed
- ✅ boto3 Python library installed

## Quick Deployment (3 Steps)

### Step 1: Export Infrastructure Config

Capture current AWS state (VPN IDs, tunnel IPs, routes, etc.):

```bash
vpnctl infra export-config

# Output: infra-config.json with complete infrastructure metadata
```

This generates `infra-config.json` containing:
- Transit Gateway ID and configuration
- EKS cluster info
- VPN connection IDs for each peer
- Tunnel public IPs and status
- TGW attachment IDs
- Route table information
- Test endpoint configuration

### Step 2: Deploy to Kubernetes

Deploy VPN health monitoring service to K8s with Helm:

```bash
# Development environment (1 replica, IRSA role)
vpnctl health deploy --target helm --environment dev

# Production environment (2 replicas, autoscaling)
vpnctl health deploy --target helm --environment prod
```

This performs:
1. ✓ Builds Docker image
2. ✓ Pushes to ECR (infers registry from AWS account)
3. ✓ Creates K8s namespace: `vpn-health`
4. ✓ Creates ConfigMaps: `vpn-peers-config`, `vpn-infra-config`
5. ✓ Creates ServiceAccount: `vpn-health` (with IRSA annotation)
6. ✓ Helm install/upgrade: Deploys pods
7. ✓ Verifies: Waits for rollout status

### Step 3: Verify Deployment

Check that health monitoring is running:

```bash
# Watch pods
kubectl get pods -n vpn-health -w

# View logs
kubectl logs -f deployment/vpn-health -n vpn-health

# Test health endpoint
kubectl port-forward -n vpn-health svc/vpn-health 8080:8080

# In another terminal:
curl http://localhost:8080/health | jq
curl http://localhost:8080/health/peers | jq
```

---

## Common Tasks

### Check Health Status

```bash
# Summary
curl http://localhost:8080/health | jq '.summary'

# All peers
curl http://localhost:8080/health/peers | jq '.peers | keys'

# Specific peer
curl http://localhost:8080/health/peers/vimenca | jq
```

### Refresh Config After Changes

The service watches both files automatically, but force refresh:

```bash
# After updating config/vpn-peers.yaml or infra-config.json
curl -X POST http://localhost:8080/health/refresh | jq
```

### Update Infrastructure Metadata

When AWS resources change (new peer, tunnel IP changed, routes modified):

```bash
# Regenerate config
vpnctl infra export-config

# Trigger pod restart to reload ConfigMaps
kubectl rollout restart deployment/vpn-health -n vpn-health

# Or just wait - app watches for file changes and auto-refreshes
```

### View Service Details

```bash
# Helm status
helm status vpn-health -n vpn-health

# Deployment info
kubectl describe deployment/vpn-health -n vpn-health

# ServiceAccount (verify IRSA annotation)
kubectl get sa vpn-health -n vpn-health -o yaml

# ConfigMaps
kubectl get configmaps -n vpn-health
kubectl get configmap vpn-peers-config -n vpn-health -o yaml
```

### Scale Service

```bash
# Increase replicas
kubectl scale deployment vpn-health --replicas=3 -n vpn-health

# Or update Helm values
helm upgrade vpn-health vpnctl/health/helm/vpn-health \
  -n vpn-health \
  --set replicaCount=3
```

### Redeploy Without Rebuild

```bash
# If image already in ECR, skip rebuild:
vpnctl health deploy --target helm --no-build --no-push
```

---

## Troubleshooting

### Pod won't start: ImagePullBackOff

```bash
# Verify image in ECR
aws ecr list-images --repository-name vpn-health --profile default

# Check pod events
kubectl describe pod -n vpn-health $(kubectl get pods -n vpn-health -o name | head -1)

# May need to provide ECR registry:
vpnctl health deploy --target helm \
  --ecr-registry 123456789.dkr.ecr.us-east-2.amazonaws.com
```

### IRSA not working: Pods can't query AWS

```bash
# Verify ServiceAccount annotation
kubectl get sa vpn-health -n vpn-health -o jsonpath='{.metadata.annotations}'

# Check environment in pod
kubectl exec -it deployment/vpn-health -n vpn-health -- env | grep AWS

# Should show:
# AWS_ROLE_ARN=arn:aws:iam::...
# AWS_WEB_IDENTITY_TOKEN_FILE=/var/run/secrets/...

# If missing, update IRSA role ARN in values/dev.yaml:
# aws.irsaRoleArn: arn:aws:iam::ACCOUNT:role/vpn-health-irsa-dev
```

### ConfigMaps not mounted

```bash
# Verify ConfigMaps exist
kubectl get configmaps -n vpn-health

# Regenerate them:
kubectl create configmap vpn-peers-config \
  --from-file=config/vpn-peers.yaml \
  -n vpn-health --dry-run=client -o yaml | kubectl apply -f -

kubectl create configmap vpn-infra-config \
  --from-file=infra-config.json \
  -n vpn-health --dry-run=client -o yaml | kubectl apply -f -
```

### Health endpoint returns errors

```bash
# Check pod logs
kubectl logs -n vpn-health -l app=vpn-health

# Common issues:
# 1. IRSA role missing EC2 permissions
# 2. infra-config.json not mounted or outdated
# 3. config/vpn-peers.yaml not found

# Refresh both:
vpnctl infra export-config
kubectl create configmap vpn-infra-config --from-file=infra-config.json -n vpn-health -o yaml --dry-run=client | kubectl apply -f -
```

---

## Local Development (Docker)

### Run Locally Without Kubernetes

```bash
# Build and run locally
vpnctl health deploy --target docker --port 8080

# Test
curl http://localhost:8080/health | jq

# Stop
vpnctl health stop
```

This uses:
- AWS_PROFILE=default (local credentials from ~/.aws)
- Mounted config/ directory (read-only)
- Port 8080 on localhost

---

## Architecture at a Glance

```
┌─────────────────────────────────────────────────────────────────┐
│                    VPN Health Monitoring                         │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────────┐         ┌──────────────────────┐
│  vpn-peers.yaml      │         │ infra-config.json    │
│  - Peer definitions  │         │ - Resource IDs       │
│  - Device types      │         │ - Tunnel IPs & status│
│  - CIDRs             │         │ - Routes             │
└──────────────────────┘         └──────────────────────┘
         │                               │
         └─────────┬─────────────────────┘
                   │
          ConfigMaps in K8s
                   │
         ┌─────────▼─────────┐
         │ VPNHealthApp      │
         │ - Watches both    │
         │ - Auto-refreshes  │
         │ - Flask HTTP API  │
         └─────────┬─────────┘
                   │
         ┌─────────▼─────────┐
         │ VPNHealthState    │
         │ - boto3 queries   │
         │ - Resource ID     │
         │ - Direct AWS API  │
         └─────────┬─────────┘
                   │
         ┌─────────▼──────────────────┐
         │ AWS (VPN, TGW, Routes)     │
         │ Using IRSA authentication  │
         └────────────────────────────┘

HTTP API: /health, /health/peers, /health/liveness, /health/readiness
```

---

## Next Steps

1. **Deploy to dev:** `vpnctl health deploy --target helm --environment dev`
2. **Monitor logs:** `kubectl logs -f deployment/vpn-health -n vpn-health`
3. **Set up alerts:** Add Prometheus scraping (optional)
4. **Execute tests:** Add Phase 4 - test endpoint execution (ping/http/tcp/dns)

---

## Reference

- 📖 Full docs: `vpnctl/health/helm/vpn-health/README.md`
- 📊 Implementation details: `IMPLEMENTATION_SUMMARY.md`
- 🚀 CLI commands: `vpnctl --help`
