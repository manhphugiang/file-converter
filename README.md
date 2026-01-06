# File Converter

A microservices-based file conversion platform supporting documents, images, video, and audio formats.

## Features

- **Documents**: DOCX → PDF, PDF → DOCX
- **Images**: PDF → JPG/PNG, JPG/PNG → PDF

## Architecture

```
┌─────────────────┐
│  Nginx Gateway  │ :80
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
┌───▼───┐ ┌───▼────────┐
│Frontend│ │Job Manager │
└───────┘ └─────┬──────┘
                │
        ┌───────┼───────┐
        │       │       │
    ┌───▼───┐ ┌─▼─┐ ┌───▼───┐
    │DocxPDF│ │PDF│ │ Image │
    │Service│ │Docx│ │Service│
    └───────┘ └───┘ └───────┘
                │
        ┌───────┼───────┐
        │       │       │
    ┌───▼───┐ ┌─▼─┐ ┌───▼───┐
    │Postgres│ │Redis│ │ MinIO │
    └───────┘ └───┘ └───────┘
```

## Services

| Service | Description | Base Image |
|---------|-------------|------------|
| `docx-pdf-service` | DOCX → PDF (LibreOffice headless) | python:3.11-slim |
| `pdf-docx-service` | PDF → DOCX (pdf2docx) | python:3.11-slim |
| `image-service` | PDF ↔ JPG/PNG (Pillow + pdf2image) | python:3.11-slim |
| `job-manager` | Central orchestration | python:3.11-slim |
| `monitoring-dashboard` | Cluster monitoring UI | python:3.11-slim |
| `frontend` | React UI | node:18-alpine + nginx:alpine |

## Quick Start

### Docker Compose (Development)

```bash
docker compose -f docker-compose.microservices.yml up -d
open http://localhost
```

### K3s Deployment (Production)

For Raspberry Pi cluster deployment with KEDA autoscaling:

```bash
# Install KEDA
./scripts/install-keda.sh

# Deploy to K3s
./scripts/k3s-deploy.sh
```

See [k3s/README.md](k3s/README.md) for detailed cluster setup.

## Docker Images

Docker Hub: [giangma/fileconverter](https://hub.docker.com/r/giangma/fileconverter)

All images are multi-arch (amd64 + arm64):

```bash
docker pull giangma/fileconverter:frontend-v2.4
docker pull giangma/fileconverter:job-manager-v2.4
docker pull giangma/fileconverter:docx-pdf-service-v2.2
docker pull giangma/fileconverter:pdf-docx-service-v2.1
docker pull giangma/fileconverter:image-service-v2.1
docker pull giangma/fileconverter:monitoring-dashboard-v2.5
```

## Tech Stack

- **Frontend**: React + TypeScript
- **Backend**: FastAPI (Python 3.11-slim)
- **Queue**: Redis
- **Database**: PostgreSQL
- **Storage**: MinIO
- **Gateway**: Nginx
- **Scaling**: KEDA (Kubernetes Event-driven Autoscaling)

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/upload` | POST | Upload file for conversion |
| `/api/status/{job_id}` | GET | Get job status |
| `/api/download/{job_id}` | GET | Download converted file |
| `/api/session/jobs` | GET | List jobs for current session |
| `/api/health` | GET | Health check |

## Supported Conversions

| Input | Output Options |
|-------|----------------|
| DOCX | PDF |
| PDF | DOCX, JPG, PNG |
| JPG/PNG | PDF |

## Environment Variables

```env
DATABASE_URL=postgresql://user:pass@postgres:5432/fileconverter
REDIS_URL=redis://redis:6379/0
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123
MAX_FILE_SIZE=104857600  # 100MB
```

## License

MIT
