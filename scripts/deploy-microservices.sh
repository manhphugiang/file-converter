#!/bin/bash

# Microservices Deployment Script
# Usage: ./scripts/deploy-microservices.sh [development|production|full]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_FILE="docker-compose.microservices.yml"
PROJECT_NAME="file-converter"

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_dependencies() {
    log_info "Checking dependencies..."
    
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose is not installed"
        exit 1
    fi
    
    log_success "Dependencies check passed"
}

build_services() {
    log_info "Building microservices..."
    
    # Build all services
    docker-compose -f $COMPOSE_FILE build --parallel
    
    log_success "Services built successfully"
}

deploy_infrastructure() {
    log_info "Deploying infrastructure services..."
    
    # Start infrastructure services first
    docker-compose -f $COMPOSE_FILE up -d postgres redis minio minio-setup
    
    # Wait for services to be ready
    log_info "Waiting for infrastructure services to be ready..."
    sleep 30
    
    # Check infrastructure health
    check_infrastructure_health
    
    log_success "Infrastructure services deployed"
}

deploy_core_services() {
    log_info "Deploying core services..."
    
    # Start core application services
    docker-compose -f $COMPOSE_FILE up -d job-manager docx-pdf-service
    
    # Wait for services to be ready
    log_info "Waiting for core services to be ready..."
    sleep 20
    
    log_success "Core services deployed"
}

deploy_frontend_gateway() {
    log_info "Deploying frontend and gateway..."
    
    # Start frontend and gateway
    docker-compose -f $COMPOSE_FILE up -d frontend nginx-gateway
    
    # Wait for services to be ready
    log_info "Waiting for frontend and gateway to be ready..."
    sleep 15
    
    log_success "Frontend and gateway deployed"
}

deploy_full_services() {
    log_info "Deploying all services including future services..."
    
    # Start all services including those in 'full' profile
    docker-compose -f $COMPOSE_FILE --profile full up -d
    
    log_success "All services deployed"
}

check_infrastructure_health() {
    log_info "Checking infrastructure health..."
    
    # Check PostgreSQL
    if docker-compose -f $COMPOSE_FILE exec -T postgres pg_isready -U converter > /dev/null 2>&1; then
        log_success "PostgreSQL is ready"
    else
        log_warning "PostgreSQL is not ready yet"
    fi
    
    # Check Redis
    if docker-compose -f $COMPOSE_FILE exec -T redis redis-cli ping > /dev/null 2>&1; then
        log_success "Redis is ready"
    else
        log_warning "Redis is not ready yet"
    fi
    
    # Check MinIO
    if docker-compose -f $COMPOSE_FILE exec -T minio curl -f http://localhost:9000/minio/health/live > /dev/null 2>&1; then
        log_success "MinIO is ready"
    else
        log_warning "MinIO is not ready yet"
    fi
}

check_service_health() {
    log_info "Checking service health..."
    
    # Wait a bit for services to start
    sleep 10
    
    # Check if gateway is responding
    if curl -f http://localhost/api/health > /dev/null 2>&1; then
        log_success "Gateway and services are healthy"
        
        # Show service status
        log_info "Service health status:"
        curl -s http://localhost/api/health | python3 -m json.tool || echo "Health check response received"
    else
        log_warning "Services may still be starting up. Check logs if issues persist."
    fi
}

show_service_status() {
    log_info "Service status:"
    docker-compose -f $COMPOSE_FILE ps
    
    echo ""
    log_info "Access URLs:"
    echo "  Frontend: http://localhost"
    echo "  API: http://localhost/api/*"
    echo "  Health Check: http://localhost/api/health"
    echo ""
    
    log_info "Useful commands:"
    echo "  View logs: docker-compose -f $COMPOSE_FILE logs -f [service]"
    echo "  Stop services: docker-compose -f $COMPOSE_FILE down"
    echo "  Restart service: docker-compose -f $COMPOSE_FILE restart [service]"
    echo "  Scale service: docker-compose -f $COMPOSE_FILE up -d --scale docx-pdf-service=3"
}

cleanup() {
    log_info "Cleaning up..."
    docker-compose -f $COMPOSE_FILE down -v
    docker system prune -f
    log_success "Cleanup completed"
}

# Main deployment logic
main() {
    local deployment_type=${1:-development}
    
    log_info "Starting microservices deployment: $deployment_type"
    
    case $deployment_type in
        "development")
            check_dependencies
            build_services
            deploy_infrastructure
            deploy_core_services
            deploy_frontend_gateway
            check_service_health
            show_service_status
            ;;
        "production")
            check_dependencies
            build_services
            deploy_infrastructure
            deploy_core_services
            deploy_frontend_gateway
            check_service_health
            show_service_status
            ;;
        "full")
            check_dependencies
            build_services
            deploy_infrastructure
            deploy_full_services
            check_service_health
            show_service_status
            ;;
        "cleanup")
            cleanup
            ;;
        "status")
            show_service_status
            ;;
        "health")
            check_service_health
            ;;
        *)
            echo "Usage: $0 [development|production|full|cleanup|status|health]"
            echo ""
            echo "Deployment types:"
            echo "  development - Core services (DOCX→PDF only)"
            echo "  production  - Core services with production settings"
            echo "  full        - All services including future ones"
            echo "  cleanup     - Stop and remove all services"
            echo "  status      - Show service status"
            echo "  health      - Check service health"
            exit 1
            ;;
    esac
    
    log_success "Deployment completed: $deployment_type"
}

# Run main function with all arguments
main "$@"