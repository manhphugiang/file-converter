#!/bin/bash
# K3s Deployment Script for File Converter
# Cluster: 1 master (8GB) + 3 workers (4GB each)

set -e

NAMESPACE="file-converter"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K3S_DIR="$SCRIPT_DIR/../k3s"

echo "=== File Converter K3s Deployment ==="

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "Error: kubectl not found. Please install kubectl first."
    exit 1
fi

# Check cluster connection
echo "Checking cluster connection..."
if ! kubectl cluster-info &> /dev/null; then
    echo "Error: Cannot connect to K3s cluster. Check your kubeconfig."
    exit 1
fi

echo "Cluster nodes:"
kubectl get nodes

# Step 1: Create namespace
echo ""
echo "=== Step 1: Creating namespace ==="
kubectl apply -f "$K3S_DIR/namespace.yaml"

# Step 2: Deploy infrastructure
echo ""
echo "=== Step 2: Deploying infrastructure ==="
kubectl apply -f "$K3S_DIR/infrastructure/configmap.yaml"
kubectl apply -f "$K3S_DIR/infrastructure/postgres.yaml"
kubectl apply -f "$K3S_DIR/infrastructure/redis.yaml"
kubectl apply -f "$K3S_DIR/infrastructure/minio-distributed.yaml"

echo "Waiting for infrastructure to be ready..."
kubectl -n $NAMESPACE wait --for=condition=ready pod -l app=postgres --timeout=120s || true
kubectl -n $NAMESPACE wait --for=condition=ready pod -l app=redis --timeout=60s || true
echo "Waiting for MinIO pods (may take a few minutes)..."
sleep 30

# Step 3: Deploy services
echo ""
echo "=== Step 3: Deploying services ==="
kubectl apply -f "$K3S_DIR/services/frontend.yaml"
kubectl apply -f "$K3S_DIR/services/job-manager.yaml"
kubectl apply -f "$K3S_DIR/services/docx-pdf-service.yaml"
kubectl apply -f "$K3S_DIR/services/pdf-docx-service.yaml"
kubectl apply -f "$K3S_DIR/services/image-service.yaml"
kubectl apply -f "$K3S_DIR/services/html-service.yaml"
kubectl apply -f "$K3S_DIR/services/markdown-service.yaml"
kubectl apply -f "$K3S_DIR/services/video-service.yaml"

# Step 4: Deploy ingress
echo ""
echo "=== Step 4: Deploying ingress ==="
kubectl apply -f "$K3S_DIR/ingress/ingress.yaml"

# Step 5: Check if KEDA is installed
echo ""
echo "=== Step 5: Checking KEDA ==="
if kubectl get crd scaledobjects.keda.sh &> /dev/null; then
    echo "KEDA is installed. Deploying scalers..."
    kubectl apply -f "$K3S_DIR/scaling/keda-scalers.yaml"
else
    echo "KEDA not installed. Skipping scalers."
    echo "To install KEDA, run: ./scripts/install-keda.sh"
fi

# Summary
echo ""
echo "=== Deployment Summary ==="
echo ""
echo "Pods:"
kubectl get pods -n $NAMESPACE -o wide
echo ""
echo "Services:"
kubectl get svc -n $NAMESPACE
echo ""
echo "Ingress:"
kubectl get ingress -n $NAMESPACE 2>/dev/null || kubectl get ingressroute -n $NAMESPACE 2>/dev/null || echo "No ingress found"

echo ""
echo "=== Deployment Complete ==="
echo "Access the app at: http://<master-node-ip>"
