# K3s Deployment Guide

Deploy File Converter on a 5-node K3s cluster with KEDA autoscaling.

## Cluster Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    master (RPi 8GB)                         │
│  - K3s control plane                                        │
│  - Frontend, Job Manager, Monitoring                        │
│  - Redis                                                    │
│  - MinIO (1 of 4 nodes)                                     │
│  - USB: 29.8GB (/dev/sda)                                   │
└─────────────────────────────────────────────────────────────┘
         │
    ┌────┴────┬────────────┬────────────┬────────────┐
    │         │            │            │            │
┌───▼───┐ ┌───▼───┐   ┌────▼───┐  ┌────▼────────────┐
│worker1│ │worker2│   │worker3 │  │    worker4      │
│RPi 4GB│ │RPi 4GB│   │RPi 4GB │  │  MacBook 8GB    │
│4x A72 │ │4x A72 │   │4x A76  │  │  2x i5 5th Gen  │
│119.5GB│ │59.8GB │   │466.3GB │  │   111.5GB SSD   │
│ arm64 │ │ arm64 │   │ arm64  │  │     amd64       │
│ MinIO │ │ MinIO │   │ MinIO  │  │   PostgreSQL    │
└───────┘ └───────┘   └────────┘  └─────────────────┘
        Conversion Services (KEDA scaled on all workers)
```

Total cluster storage: ~786GB

## Resource Allocation (Horizontal Scaling Strategy)

**Goal**: Maximize throughput by running many small pods. Each pod handles 1 job at a time (CONVERSION_WORKERS=1). Requests can wait - throughput matters more than latency.

### Per-Pod Resource Limits (Conversion Services)
| Service | Memory Req | Memory Limit | CPU Req | CPU Limit | Max Replicas | Node |
|---------|------------|--------------|---------|-----------|--------------|------|
| docx-pdf | 200Mi | 768Mi | 100m | 500m | 2 | Pi workers |
| pdf-docx | 150Mi | 512Mi | 100m | 400m | 2 | Pi workers |
| image | 100Mi | 512Mi | 50m | 400m | 3 | Pi workers |

### Node Capacity Estimate
| Node | RAM | Usable RAM* | Pods @ ~350Mi | Notes |
|------|-----|-------------|---------------|-------|
| worker1 (RPi 4GB) | 4GB | ~3GB | ~8 pods | MinIO uses ~512Mi |
| worker2 (RPi 4GB) | 4GB | ~3GB | ~8 pods | MinIO uses ~512Mi |
| worker3 (RPi 4GB) | 4GB | ~3GB | ~8 pods | MinIO uses ~512Mi |
| worker4 (MacBook 8GB) | 8GB | ~7GB | ~15 pods | PostgreSQL uses ~512Mi |

*After OS, K3s agent, and infrastructure services

### Total Cluster Capacity
- **Conversion pods**: ~40 pods max across all workers
- **Concurrent jobs**: ~40 (1 worker per pod)
- **Queue throughput**: High - KEDA scales up quickly when queue grows

### Master Node (RPi 8GB) - Control Plane Only
| Service | Memory Req | Memory Limit | CPU Req | CPU Limit |
|---------|------------|--------------|---------|-----------|
| Frontend | 32Mi | 128Mi | 25m | 200m |
| Job Manager | 128Mi | 384Mi | 100m | 500m |
| Redis | 64Mi | 192Mi | 25m | 200m |
| Monitoring | 64Mi | 192Mi | 25m | 200m |
| MinIO | 128Mi | 512Mi | 100m | 500m |

---

## Step 1: Prepare Storage

### On master, worker1, worker3 (USB at /dev/sda):
```bash
sudo mkdir -p /mnt/usb
sudo mount /dev/sda /mnt/usb
echo '/dev/sda /mnt/usb ext4 defaults,nofail 0 2' | sudo tee -a /etc/fstab
sudo mkdir -p /mnt/usb/k3s-storage
```

### On worker2 (USB at /dev/sda1):
```bash
sudo mkdir -p /mnt/usb
sudo mount /dev/sda1 /mnt/usb
echo '/dev/sda1 /mnt/usb ext4 defaults,nofail 0 2' | sudo tee -a /etc/fstab
sudo mkdir -p /mnt/usb/k3s-storage
```

### On worker4 (MacBook - internal SSD):
```bash
sudo mkdir -p /var/lib/k3s-storage
```

---

## Step 2: Install K3s

### On master:
```bash
curl -sfL https://get.k3s.io | sh -s - --write-kubeconfig-mode 644

# Get the join token
sudo cat /var/lib/rancher/k3s/server/node-token

# Get master IP
hostname -I | awk '{print $1}'
```

### On worker1, worker2, worker3 (RPi):
```bash
curl -sfL https://get.k3s.io | K3S_URL=https://<MASTER_IP>:6443 K3S_TOKEN=<TOKEN> sh -
```

### On worker4 (MacBook):
```bash
# Install K3s agent
curl -sfL https://get.k3s.io | K3S_URL=https://<MASTER_IP>:6443 K3S_TOKEN=<TOKEN> sh -
```

---

## Step 3: Verify Cluster

On master:
```bash
kubectl get nodes
```

Expected output:
```
NAME      STATUS   ROLES                  AGE   VERSION
master    Ready    control-plane,master   10m   v1.28.x
worker1   Ready    <none>                 5m    v1.28.x
worker2   Ready    <none>                 5m    v1.28.x
worker3   Ready    <none>                 5m    v1.28.x
worker4   Ready    <none>                 5m    v1.28.x
```

---

## Step 4: Label Nodes

```bash
# Label master for control plane workloads
kubectl label nodes master node-role.kubernetes.io/master=true

# Allow master to run pods (remove taint if present)
kubectl taint nodes master node-role.kubernetes.io/master:NoSchedule- 2>/dev/null || true
```

---

## Step 5: Copy Manifests to Master

From your dev machine, copy the k3s folder:
```bash
scp -r k3s/ pi@<MASTER_IP>:~/
```

Then SSH to master:
```bash
ssh pi@<MASTER_IP>
cd ~/k3s
```

---

## Step 6: Install KEDA

```bash
# Install Helm
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# Add KEDA repo
helm repo add kedacore https://kedacore.github.io/charts
helm repo update

# Install KEDA with low resource limits for RPi
helm install keda kedacore/keda \
  --namespace keda \
  --create-namespace \
  --set resources.operator.requests.memory=64Mi \
  --set resources.operator.requests.cpu=50m \
  --set resources.operator.limits.memory=256Mi \
  --set resources.metricServer.requests.memory=64Mi \
  --set resources.metricServer.limits.memory=256Mi

# Wait for KEDA to be ready
kubectl -n keda wait --for=condition=ready pod -l app=keda-operator --timeout=180s
```

---

## Step 7: Deploy Infrastructure

```bash
# Create namespace
kubectl apply -f namespace.yaml

# Deploy ConfigMap (shared environment variables)
kubectl apply -f infrastructure/configmap.yaml

# Deploy PostgreSQL (on worker4 - MacBook SSD)
kubectl apply -f infrastructure/postgres.yaml

# Deploy Redis (on master)
kubectl apply -f infrastructure/redis.yaml

# Deploy MinIO distributed (on master + worker1-3)
kubectl apply -f infrastructure/minio-distributed.yaml

# Wait for infrastructure
echo "Waiting for PostgreSQL..."
kubectl -n file-converter wait --for=condition=ready pod -l app=postgres --timeout=120s

echo "Waiting for Redis..."
kubectl -n file-converter wait --for=condition=ready pod -l app=redis --timeout=60s

echo "Waiting for MinIO (may take 2-3 minutes)..."
sleep 60
kubectl -n file-converter get pods -l app=minio
```

---

## Step 8: Deploy Services

```bash
# Deploy frontend (on master)
kubectl apply -f services/frontend.yaml

# Deploy job-manager (on master)
kubectl apply -f services/job-manager.yaml

# Deploy conversion services (on workers)
kubectl apply -f services/docx-pdf-service.yaml
kubectl apply -f services/pdf-docx-service.yaml
kubectl apply -f services/image-service.yaml
# Note: html-service and markdown-service removed in v2.3

# Wait for services
echo "Waiting for services to start..."
kubectl -n file-converter wait --for=condition=ready pod -l app=frontend --timeout=120s
kubectl -n file-converter wait --for=condition=ready pod -l app=job-manager --timeout=120s
```

---

## Step 9: Deploy Ingress

```bash
kubectl apply -f ingress/ingress.yaml
```

---

## Step 10: Deploy KEDA Scalers

```bash
kubectl apply -f scaling/keda-scalers.yaml

# Verify scalers
kubectl -n file-converter get scaledobjects
```

---

## Step 11: Verify Deployment

```bash
# Check all pods
kubectl -n file-converter get pods -o wide

# Check services
kubectl -n file-converter get svc

# Check pod distribution across nodes
kubectl -n file-converter get pods -o wide | awk '{print $7}' | sort | uniq -c
```

---

## Step 12: Access the Application

Open in browser:
```
http://<MASTER_IP>
```

---

## Troubleshooting

### Check pod logs:
```bash
kubectl -n file-converter logs -l app=job-manager -f
kubectl -n file-converter logs -l app=docx-pdf-service -f
```

### Check pod events:
```bash
kubectl -n file-converter describe pod <pod-name>
```

### Restart a service:
```bash
kubectl -n file-converter rollout restart deployment job-manager
```

### Check MinIO bucket:
```bash
kubectl -n file-converter exec -it minio-0 -- mc alias set local http://localhost:9000 minioadmin minioadmin123
kubectl -n file-converter exec -it minio-0 -- mc ls local/file-converter
```

### Check Redis queues:
```bash
kubectl -n file-converter exec deploy/redis -- redis-cli KEYS "queue:*"
```

### Force scale a service:
```bash
kubectl -n file-converter scale deployment docx-pdf-service --replicas=2
```

---

## KEDA Scaling Behavior

Horizontal scaling strategy: scale up quickly, scale down slowly. Conservative limits for Pi cluster.

| Service | Min | Max | Trigger | Poll | Cooldown | Notes |
|---------|-----|-----|---------|------|----------|-------|
| docx-pdf | 1 | 2 | 2+ jobs | 10s | 30s | CPU-heavy, 1-2 concurrent jobs per Pi |
| pdf-docx | 1 | 2 | 2+ jobs | 10s | 30s | Lightweight |
| image | 1 | 3 | 2+ jobs | 10s | 30s | Moderate CPU |
| video | 1 | 6 | 1+ jobs | 10s | 60s | FFmpeg encoding |

**How it works**:
- Each pod runs 1 worker (CONVERSION_WORKERS=1)
- When queue has 2+ jobs, KEDA adds more pods
- Pods spread across nodes via podAntiAffinity
- Scale down after 30-60s of low queue length

**Apply scalers**:
```bash
kubectl apply -f k3s/scaling/keda-scalers.yaml
```

---

## Docker Images (Multi-arch: amd64 + arm64)

Docker Hub: [giangma/fileconverter](https://hub.docker.com/r/giangma/fileconverter)

```bash
# Pull all images (optional - K3s will auto-pull)
docker pull giangma/fileconverter:frontend-v2.4
docker pull giangma/fileconverter:job-manager-v2.4
docker pull giangma/fileconverter:docx-pdf-service-v2.2
docker pull giangma/fileconverter:pdf-docx-service-v2.1
docker pull giangma/fileconverter:image-service-v2.1
docker pull giangma/fileconverter:monitoring-dashboard-v2.5
```

**Note**: HTML and Markdown services were removed in v2.3.

---

## Optional: Monitoring Dashboard

A custom monitoring dashboard that shows cluster metrics in a user-friendly UI.

### Build and Push (from dev machine):
```bash
cd services
docker buildx build --platform linux/amd64,linux/arm64 \
  -t giangma/fileconverter:monitoring-dashboard-v1.0 \
  -f monitoring-service/Dockerfile --push .
```

### Deploy Monitoring Stack:
```bash
# Deploy namespace and Prometheus stack
kubectl apply -f monitoring/namespace.yaml
kubectl apply -f monitoring/kube-state-metrics.yaml
kubectl apply -f monitoring/prometheus.yaml

# Deploy custom monitoring dashboard
kubectl apply -f monitoring/monitoring-dashboard.yaml

# Wait for pods
kubectl -n monitoring wait --for=condition=ready pod -l app=monitoring-dashboard --timeout=120s
```

### Access Dashboard:
```
http://<MASTER_IP>/monitor
```

### Dashboard Features:
- 🖥️ Cluster overview (nodes, pods, services)
- 🔲 Node status and pod distribution
- 🚀 Service replicas (KEDA scaling visible)
- 📬 Redis queue lengths (real-time)
- 💾 MinIO storage usage
- 🧠 Memory usage per pod
- 📦 Pods by deployment with visual indicators
- Auto-refresh every 5 seconds

### API Endpoints:
```
GET /api/metrics  - All cluster metrics
GET /api/queues   - Redis queue lengths only
GET /api/minio    - MinIO storage stats only
GET /api/health   - Health check
```
