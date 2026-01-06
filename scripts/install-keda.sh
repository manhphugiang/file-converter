#!/bin/bash
# Install KEDA on K3s cluster

set -e

echo "=== Installing KEDA ==="

# Check if helm is installed
if ! command -v helm &> /dev/null; then
    echo "Helm not found. Installing via script..."
    curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
fi

# Add KEDA Helm repo
echo "Adding KEDA Helm repository..."
helm repo add kedacore https://kedacore.github.io/charts
helm repo update

# Install KEDA
echo "Installing KEDA..."
helm install keda kedacore/keda \
    --namespace keda \
    --create-namespace \
    --set resources.operator.requests.memory=64Mi \
    --set resources.operator.requests.cpu=50m \
    --set resources.operator.limits.memory=256Mi \
    --set resources.operator.limits.cpu=200m \
    --set resources.metricServer.requests.memory=64Mi \
    --set resources.metricServer.requests.cpu=50m \
    --set resources.metricServer.limits.memory=256Mi \
    --set resources.metricServer.limits.cpu=200m

echo "Waiting for KEDA to be ready..."
kubectl -n keda wait --for=condition=ready pod -l app=keda-operator --timeout=120s
kubectl -n keda wait --for=condition=ready pod -l app=keda-operator-metrics-apiserver --timeout=120s

echo ""
echo "=== KEDA Installation Complete ==="
kubectl get pods -n keda

echo ""
echo "Now you can deploy the scalers:"
echo "kubectl apply -f k8s/scaling/keda-scalers.yaml"
