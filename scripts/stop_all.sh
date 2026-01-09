#!/bin/bash
# =====================================================
# Stop All Pipeline Components
# =====================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_ROOT/logs"

log_info "Stopping Wiki Data Pipeline..."

# Stop Python processes
if [ -f "$LOG_DIR/producer.pid" ]; then
    PID=$(cat "$LOG_DIR/producer.pid")
    if ps -p $PID > /dev/null 2>&1; then
        kill $PID
        log_success "Producer stopped (PID: $PID)"
    fi
    rm "$LOG_DIR/producer.pid"
fi

if [ -f "$LOG_DIR/stream_processor.pid" ]; then
    PID=$(cat "$LOG_DIR/stream_processor.pid")
    if ps -p $PID > /dev/null 2>&1; then
        kill $PID
        log_success "Stream Processor stopped (PID: $PID)"
    fi
    rm "$LOG_DIR/stream_processor.pid"
fi

# Stop Docker services
log_info "Stopping Docker services..."
cd "$PROJECT_ROOT"

if [ -f "docker-compose.yml" ]; then
    docker-compose down
elif [ -f "infrastructure/docker/docker-compose.yml" ]; then
    cd infrastructure/docker
    docker-compose down
fi

log_success "All services stopped successfully!"
