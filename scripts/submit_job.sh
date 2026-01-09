#!/bin/bash
# =====================================================
# Submit Spark Job to Cluster
# For production deployment
# =====================================================

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Default values
JOB_TYPE="stream"
MODE="both"
DAYS=7
MASTER="local[*]"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --job)
            JOB_TYPE="$2"
            shift 2
            ;;
        --mode)
            MODE="$2"
            shift 2
            ;;
        --days)
            DAYS="$2"
            shift 2
            ;;
        --master)
            MASTER="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "Submitting Spark Job..."
echo "  Type: $JOB_TYPE"
echo "  Mode: $MODE"
echo "  Master: $MASTER"

cd "$PROJECT_ROOT"

if [ "$JOB_TYPE" == "stream" ]; then
    spark-submit \
        --master "$MASTER" \
        --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1,org.postgresql:postgresql:42.6.0 \
        --conf spark.sql.adaptive.enabled=true \
        processing/stream_job.py --mode "$MODE"
elif [ "$JOB_TYPE" == "batch" ]; then
    spark-submit \
        --master "$MASTER" \
        --packages org.postgresql:postgresql:42.6.0 \
        --conf spark.sql.adaptive.enabled=true \
        processing/batch_job.py --days "$DAYS"
else
    echo "Invalid job type: $JOB_TYPE (must be 'stream' or 'batch')"
    exit 1
fi
