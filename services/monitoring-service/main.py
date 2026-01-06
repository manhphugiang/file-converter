"""
Monitoring Service - Aggregates metrics from Redis, MinIO, Node Exporter, and K8s
Works in both K3s (with Node Exporter) and Docker Compose (with psutil)
"""
import os
import asyncio
import httpx
import redis
import socket
import psutil
from minio import Minio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Dict, List, Optional
from datetime import datetime

app = FastAPI(title="File Converter Monitoring")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin123")
MINIO_BUCKET = os.getenv("MINIO_BUCKET_NAME", "file-converter")

# Node exporter endpoints (K3s mode) - will be discovered dynamically
NODE_EXPORTER_PORT = 9100

# Service endpoints to check
SERVICES = [
    {"name": "frontend", "host": "frontend", "port": 3000},
    {"name": "job-manager", "host": "job-manager", "port": 8010},
    {"name": "docx-pdf-service", "host": "docx-pdf-service", "port": 8001},
    {"name": "pdf-docx-service", "host": "pdf-docx-service", "port": 8002},
    {"name": "image-service", "host": "image-service", "port": 8005},
]

# Redis client
redis_client = None
try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    redis_client.ping()
except Exception as e:
    print(f"Redis connection failed: {e}")

# MinIO client
minio_client = None
try:
    minio_client = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False
    )
except Exception as e:
    print(f"MinIO connection failed: {e}")


def check_service_health(host: str, port: int, timeout: float = 0.3) -> bool:
    """Check if a service is reachable via TCP"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def get_system_resources() -> Dict:
    """Get CPU and RAM usage of the host system"""
    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        return {
            "cpu_percent": round(cpu_percent, 1),
            "cpu_count": psutil.cpu_count(),
            "memory_total_gb": round(memory.total / (1024**3), 2),
            "memory_used_gb": round(memory.used / (1024**3), 2),
            "memory_available_gb": round(memory.available / (1024**3), 2),
            "memory_percent": round(memory.percent, 1)
        }
    except Exception as e:
        print(f"System resources error: {e}")
        return {
            "cpu_percent": 0,
            "cpu_count": 0,
            "memory_total_gb": 0,
            "memory_used_gb": 0,
            "memory_available_gb": 0,
            "memory_percent": 0
        }


def get_services_status() -> List[Dict]:
    """Get status of all services by checking their ports"""
    services_status = []
    for svc in SERVICES:
        is_running = check_service_health(svc["host"], svc["port"])
        services_status.append({
            "name": svc["name"],
            "replicas": 1 if is_running else 0,
            "status": "Running" if is_running else "Stopped"
        })
    return services_status


class ClusterMetrics(BaseModel):
    timestamp: str
    nodes: List[Dict]
    node_metrics: Dict[str, Dict]  # Per-node CPU/RAM/disk from node-exporter
    pods: Dict
    cpu: Dict
    memory: Dict
    storage: Dict
    queues: Dict
    minio: Dict
    services: List[Dict]


async def query_prometheus(query: str) -> Optional[Dict]:
    """Query Prometheus API"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{PROMETHEUS_URL}/api/v1/query",
                params={"query": query}
            )
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        print(f"Prometheus query error: {e}")
    return None


def get_redis_queue_stats() -> Dict[str, int]:
    """Get Redis queue lengths"""
    queues = {}
    queue_names = [
        "queue:docx_pdf", "queue:pdf_docx", "queue:pdf_image",
        "queue:image_pdf"
    ]
    if not redis_client:
        return {q.replace("queue:", ""): 0 for q in queue_names}
    try:
        for queue in queue_names:
            # Using ZCARD for sorted sets (priority queue)
            length = redis_client.zcard(queue)
            short_name = queue.replace("queue:", "")
            queues[short_name] = length
    except Exception as e:
        print(f"Redis error: {e}")
    return queues


def get_minio_stats() -> Dict:
    """Get MinIO storage statistics"""
    if not minio_client:
        return {"bucket": MINIO_BUCKET, "object_count": 0, "total_size_mb": 0, "total_size_gb": 0}
    try:
        objects = list(minio_client.list_objects(MINIO_BUCKET, recursive=True))
        total_size = sum(obj.size for obj in objects)
        return {
            "bucket": MINIO_BUCKET,
            "object_count": len(objects),
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "total_size_gb": round(total_size / (1024 * 1024 * 1024), 2)
        }
    except Exception as e:
        print(f"MinIO error: {e}")
        return {"bucket": MINIO_BUCKET, "object_count": 0, "total_size_mb": 0, "total_size_gb": 0}


async def fetch_node_exporter_metrics(host: str) -> Optional[Dict]:
    """Fetch and parse metrics from a node-exporter endpoint"""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"http://{host}:{NODE_EXPORTER_PORT}/metrics")
            if response.status_code != 200:
                return None
            
            text = response.text
            metrics = {}
            
            # Parse CPU metrics (node_cpu_seconds_total)
            cpu_idle = 0
            cpu_total = 0
            for line in text.split('\n'):
                if line.startswith('node_cpu_seconds_total'):
                    if 'mode="idle"' in line:
                        try:
                            cpu_idle += float(line.split()[-1])
                        except:
                            pass
                    try:
                        cpu_total += float(line.split()[-1])
                    except:
                        pass
            
            # Calculate CPU usage percentage
            if cpu_total > 0:
                metrics['cpu_percent'] = round((1 - cpu_idle / cpu_total) * 100, 1)
            else:
                metrics['cpu_percent'] = 0
            
            # Parse memory metrics
            mem_total = 0
            mem_available = 0
            for line in text.split('\n'):
                if line.startswith('node_memory_MemTotal_bytes '):
                    try:
                        mem_total = float(line.split()[-1])
                    except:
                        pass
                elif line.startswith('node_memory_MemAvailable_bytes '):
                    try:
                        mem_available = float(line.split()[-1])
                    except:
                        pass
            
            metrics['memory_total_gb'] = round(mem_total / (1024**3), 2)
            metrics['memory_available_gb'] = round(mem_available / (1024**3), 2)
            metrics['memory_used_gb'] = round((mem_total - mem_available) / (1024**3), 2)
            metrics['memory_percent'] = round((1 - mem_available / mem_total) * 100, 1) if mem_total > 0 else 0
            
            # Parse load average
            for line in text.split('\n'):
                if line.startswith('node_load1 '):
                    try:
                        metrics['load_1m'] = round(float(line.split()[-1]), 2)
                    except:
                        pass
                elif line.startswith('node_load5 '):
                    try:
                        metrics['load_5m'] = round(float(line.split()[-1]), 2)
                    except:
                        pass
            
            # Parse CPU count
            cpu_count = 0
            for line in text.split('\n'):
                if line.startswith('node_cpu_seconds_total') and 'cpu="' in line:
                    try:
                        cpu_num = int(line.split('cpu="')[1].split('"')[0])
                        cpu_count = max(cpu_count, cpu_num + 1)
                    except:
                        pass
            metrics['cpu_count'] = cpu_count
            
            # Parse disk usage (root filesystem)
            disk_total = 0
            disk_free = 0
            for line in text.split('\n'):
                if 'mountpoint="/"' in line:
                    if line.startswith('node_filesystem_size_bytes'):
                        try:
                            disk_total = float(line.split()[-1])
                        except:
                            pass
                    elif line.startswith('node_filesystem_avail_bytes'):
                        try:
                            disk_free = float(line.split()[-1])
                        except:
                            pass
            
            if disk_total > 0:
                metrics['disk_total_gb'] = round(disk_total / (1024**3), 1)
                metrics['disk_used_gb'] = round((disk_total - disk_free) / (1024**3), 1)
                metrics['disk_percent'] = round((1 - disk_free / disk_total) * 100, 1)
            
            return metrics
    except Exception as e:
        print(f"Node exporter fetch error for {host}: {e}")
        return None


async def get_all_node_metrics(node_ips: List[str]) -> Dict[str, Dict]:
    """Fetch metrics from all nodes in parallel"""
    tasks = [fetch_node_exporter_metrics(ip) for ip in node_ips]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    node_metrics = {}
    for ip, result in zip(node_ips, results):
        if isinstance(result, dict):
            node_metrics[ip] = result
        else:
            node_metrics[ip] = None
    
    return node_metrics


@app.get("/api/metrics", response_model=ClusterMetrics)
async def get_metrics():
    """Get all cluster metrics"""
    
    # Get real service status by checking ports
    services_list = get_services_status()
    running_services = [s for s in services_list if s["status"] == "Running"]
    pods_by_deployment = {svc["name"]: svc["replicas"] for svc in services_list}
    
    # Node metrics from node-exporter (K3s mode)
    node_metrics = {}
    node_ips = os.getenv("NODE_IPS", "").split(",")  # e.g., "192.168.1.100,192.168.1.101"
    node_ips = [ip.strip() for ip in node_ips if ip.strip()]
    
    if node_ips:
        node_metrics = await get_all_node_metrics(node_ips)
    
    # For Docker Compose mode (no Prometheus, no node-exporter)
    if not PROMETHEUS_URL:
        nodes = [{"name": "docker-host", "status": "Ready"}]
        pods_by_node = {"docker-host": len(running_services)}
        memory_by_pod = {}
        pod_total = len(running_services)
        
        # Use local psutil if no node-exporter
        if not node_metrics:
            local_resources = get_system_resources()
            node_metrics = {"localhost": local_resources}
    else:
        # K3s mode with Prometheus
        queries = {
            "node_count": 'count(kube_node_info)',
            "node_names": 'kube_node_info',
            "pod_total": 'sum(kube_pod_status_phase{namespace="file-converter", phase="Running"})',
            "pods_by_deployment": 'sum by (deployment) (kube_deployment_status_replicas{namespace="file-converter"})',
            "pods_by_node": 'sum by (node) (kube_pod_info{namespace="file-converter"})',
            "memory_usage": 'sum(container_memory_usage_bytes{namespace="file-converter"}) by (pod)',
        }
        
        results = {}
        for name, query in queries.items():
            results[name] = await query_prometheus(query)
        
        # Parse Prometheus results
        def extract_value(result, default=0):
            try:
                if result and result.get("data", {}).get("result"):
                    return float(result["data"]["result"][0]["value"][1])
            except:
                pass
            return default
        
        def extract_vector(result):
            try:
                if result and result.get("data", {}).get("result"):
                    return result["data"]["result"]
            except:
                pass
            return []
        
        # Build nodes list from Prometheus
        nodes = []
        node_info = extract_vector(results.get("node_names"))
        for n in node_info:
            node_name = n.get("metric", {}).get("node", "unknown")
            internal_ip = n.get("metric", {}).get("internal_ip", "")
            nodes.append({
                "name": node_name,
                "status": "Ready",
                "ip": internal_ip
            })
        
        # Build pods info from Prometheus
        pods_by_deployment = {}
        for item in extract_vector(results.get("pods_by_deployment")):
            deployment = item.get("metric", {}).get("deployment", "unknown")
            count = int(float(item.get("value", [0, 0])[1]))
            pods_by_deployment[deployment] = count
        
        pods_by_node = {}
        for item in extract_vector(results.get("pods_by_node")):
            node = item.get("metric", {}).get("node", "unknown")
            count = int(float(item.get("value", [0, 0])[1]))
            pods_by_node[node] = count
        
        # Update services list from Prometheus
        services_list = []
        for deployment, count in pods_by_deployment.items():
            services_list.append({
                "name": deployment,
                "replicas": count,
                "status": "Running" if count > 0 else "Stopped"
            })
        
        # Memory by pod
        memory_by_pod = {}
        for item in extract_vector(results.get("memory_usage")):
            pod = item.get("metric", {}).get("pod", "unknown")
            mem_bytes = float(item.get("value", [0, 0])[1])
            memory_by_pod[pod] = round(mem_bytes / (1024 * 1024), 1)
        
        pod_total = int(extract_value(results.get("pod_total")))
    
    # Get Redis and MinIO stats
    queue_stats = get_redis_queue_stats()
    minio_stats = get_minio_stats()
    system_resources = get_system_resources()
    
    # Aggregate cluster-wide metrics from node-exporter data
    if node_metrics:
        valid_nodes = [m for m in node_metrics.values() if m]
        if valid_nodes:
            total_cpu_percent = sum(m.get('cpu_percent', 0) for m in valid_nodes) / len(valid_nodes)
            total_memory_gb = sum(m.get('memory_total_gb', 0) for m in valid_nodes)
            total_memory_used_gb = sum(m.get('memory_used_gb', 0) for m in valid_nodes)
            total_cpu_count = sum(m.get('cpu_count', 0) for m in valid_nodes)
            
            cluster_cpu = {
                "cluster_usage_percent": round(total_cpu_percent, 1),
                "cpu_count": total_cpu_count
            }
            cluster_memory = {
                "by_pod_mb": memory_by_pod if 'memory_by_pod' in dir() else {},
                "total_gb": round(total_memory_gb, 2),
                "used_gb": round(total_memory_used_gb, 2),
                "available_gb": round(total_memory_gb - total_memory_used_gb, 2),
                "percent": round((total_memory_used_gb / total_memory_gb) * 100, 1) if total_memory_gb > 0 else 0
            }
        else:
            cluster_cpu = {"cluster_usage_percent": system_resources["cpu_percent"], "cpu_count": system_resources["cpu_count"]}
            cluster_memory = {
                "by_pod_mb": {},
                "total_gb": system_resources["memory_total_gb"],
                "used_gb": system_resources["memory_used_gb"],
                "available_gb": system_resources["memory_available_gb"],
                "percent": system_resources["memory_percent"]
            }
    else:
        cluster_cpu = {"cluster_usage_percent": system_resources["cpu_percent"], "cpu_count": system_resources["cpu_count"]}
        cluster_memory = {
            "by_pod_mb": memory_by_pod if 'memory_by_pod' in dir() else {},
            "total_gb": system_resources["memory_total_gb"],
            "used_gb": system_resources["memory_used_gb"],
            "available_gb": system_resources["memory_available_gb"],
            "percent": system_resources["memory_percent"]
        }
    
    return ClusterMetrics(
        timestamp=datetime.utcnow().isoformat(),
        nodes=nodes,
        node_metrics=node_metrics,
        pods={
            "total": pod_total,
            "by_deployment": pods_by_deployment,
            "by_node": pods_by_node if 'pods_by_node' in dir() else {}
        },
        cpu=cluster_cpu,
        memory=cluster_memory,
        storage={
            "note": "Docker Compose mode" if not PROMETHEUS_URL else "K3s mode"
        },
        queues=queue_stats,
        minio=minio_stats,
        services=services_list
    )


@app.get("/api/health")
async def health():
    return {"status": "healthy", "service": "monitoring"}


@app.get("/api/queues")
async def get_queues():
    """Get Redis queue lengths only"""
    return get_redis_queue_stats()


@app.get("/api/minio")
async def get_minio():
    """Get MinIO stats only"""
    return get_minio_stats()


@app.get("/api/nodes")
async def get_nodes():
    """Get per-node metrics from node-exporter"""
    node_ips = os.getenv("NODE_IPS", "").split(",")
    node_ips = [ip.strip() for ip in node_ips if ip.strip()]
    
    if not node_ips:
        # Fallback to local psutil
        return {"localhost": get_system_resources()}
    
    return await get_all_node_metrics(node_ips)


# Serve static files (React build)
if os.path.exists("/app/static"):
    app.mount("/static", StaticFiles(directory="/app/static/static"), name="static")
    
    @app.get("/")
    async def serve_frontend():
        return FileResponse("/app/static/index.html")
    
    @app.get("/{path:path}")
    async def serve_spa(path: str):
        # Serve index.html for SPA routing (except API routes)
        if path.startswith("api/"):
            return {"detail": "Not Found"}
        file_path = f"/app/static/{path}"
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse("/app/static/index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
