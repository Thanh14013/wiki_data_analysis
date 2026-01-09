#!/bin/bash
# scripts/run_docker.sh

# Di chuyển ra thư mục gốc
cd "$(dirname "$0")/.."

echo "🛠  Building project structure..."

# 1. Bật Infrastructure
docker-compose -f infrastructure/docker/docker-compose.yml up -d
echo "⏳ Waiting for Kafka & Postgres..."
sleep 15

# 2. Chạy Producer (Background)
echo "📡 Starting Ingestion..."
export PYTHONPATH=$PYTHONPATH:$(pwd)
python3 ingestion/producer.py > logs/producer.log 2>&1 &

# 3. Chạy Spark Job (Background)
echo "🔥 Starting Spark Processing..."
# Lưu ý: Cần add packages JDBC và Kafka vào lệnh submit
PACKAGES="org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.postgresql:postgresql:42.6.0,org.apache.commons:commons-pool2:2.11.1"

python3 processing/stream_job.py --packages $PACKAGES > logs/spark.log 2>&1 &

echo "✅ System is running!"