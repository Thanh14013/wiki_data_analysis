#!/bin/bash
# =====================================================
# Wiki Data Pipeline - Local Development Runner
# Starts all components in the correct order
# =====================================================

set -e  # Exit on error

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
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_ROOT/logs"

# Create logs directory if it doesn't exist
mkdir -p "$LOG_DIR"

# =====================================================
# STEP 1: Check Prerequisites
# =====================================================
log_info "Checking prerequisites..."

check_command() {
    if ! command -v $1 &> /dev/null; then
        log_error "$1 is not installed!"
        exit 1
    fi
}

check_command docker
check_command python3
check_command pip

log_success "All prerequisites met"

# =====================================================
# STEP 2: Start Infrastructure (Docker)
# =====================================================
log_info "Starting infrastructure services..."

cd "$PROJECT_ROOT/infrastructure/docker"

# Check if docker-compose.yml exists, otherwise use root level
if [ -f "docker-compose.yml" ]; then
    COMPOSE_FILE="docker-compose.yml"
else
    cd "$PROJECT_ROOT"
    COMPOSE_FILE="docker-compose.yml"
fi

# Start services
docker-compose -f "$COMPOSE_FILE" up -d

# Wait for services to be ready
log_info "Waiting for services to be ready..."
sleep 10

# Check Kafka
log_info "Checking Kafka..."
until docker exec kafka kafka-topics --list --bootstrap-server localhost:9092 &> /dev/null; do
    log_warning "Kafka not ready, waiting..."
    sleep 5
done
log_success "Kafka is ready"

# Check PostgreSQL
log_info "Checking PostgreSQL..."
until docker exec postgres pg_isready -U admin &> /dev/null; do
    log_warning "PostgreSQL not ready, waiting..."
    sleep 5
done
log_success "PostgreSQL is ready"

# =====================================================
# STEP 3: Initialize Database
# =====================================================
log_info "Initializing database schema..."

docker exec -i postgres psql -U admin -d wikidata < "$PROJECT_ROOT/storage/init.sql"

if [ $? -eq 0 ]; then
    log_success "Database initialized successfully"
else
    log_error "Database initialization failed"
    exit 1
fi

# =====================================================
# STEP 4: Install Python Dependencies
# =====================================================
log_info "Installing Python dependencies..."

cd "$PROJECT_ROOT"

if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt --quiet
    log_success "Dependencies installed"
else
    log_warning "requirements.txt not found, skipping..."
fi

# =====================================================
# STEP 5: Start Components
# =====================================================
log_info "Starting pipeline components..."

# Start Producer
log_info "Starting Wikimedia Producer..."
cd "$PROJECT_ROOT"
nohup python3 -m ingestion.producer > "$LOG_DIR/producer.log" 2>&1 &
PRODUCER_PID=$!
echo $PRODUCER_PID > "$LOG_DIR/producer.pid"
log_success "Producer started (PID: $PRODUCER_PID)"

# Wait a bit for data to start flowing
sleep 5

# Start Stream Processor
log_info "Starting Stream Processor..."
nohup python3 -m processing.stream_job --mode both > "$LOG_DIR/stream_processor.log" 2>&1 &
STREAM_PID=$!
echo $STREAM_PID > "$LOG_DIR/stream_processor.pid"
log_success "Stream Processor started (PID: $STREAM_PID)"

# =====================================================
# STEP 6: Display Status
# =====================================================
echo ""
echo "======================================================================"
log_success "Wiki Data Pipeline Started Successfully!"
echo "======================================================================"
echo ""
log_info "Infrastructure:"
echo "  • Kafka:      http://localhost:9092"
echo "  • PostgreSQL: localhost:5432 (user: admin, db: wikidata)"
echo ""
log_info "Running Components:"
echo "  • Producer:          PID $PRODUCER_PID (logs: $LOG_DIR/producer.log)"
echo "  • Stream Processor:  PID $STREAM_PID (logs: $LOG_DIR/stream_processor.log)"
echo ""
log_info "Useful Commands:"
echo "  • View producer logs:   tail -f $LOG_DIR/producer.log"
echo "  • View processor logs:  tail -f $LOG_DIR/stream_processor.log"
echo "  • Stop all:             $SCRIPT_DIR/stop_all.sh"
echo "  • Run batch job:        python3 -m processing.batch_job --days 7"
echo ""
echo "======================================================================"
log_warning "Press Ctrl+C in terminal or run stop_all.sh to stop the pipeline"
echo "======================================================================"
