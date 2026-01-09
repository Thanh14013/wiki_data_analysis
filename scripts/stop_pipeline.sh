#!/bin/bash
# scripts/stop_pipeline.sh

# Move to project root
cd "$(dirname "$0")/.."

echo "🛑 Stopping Wiki Data Pipeline..."

# Delete Apps
kubectl delete -f infrastructure/k8s/wiki-app.yaml --ignore-not-found=true

# Delete Kafka
kubectl delete -f infrastructure/k8s/kafka.yaml --ignore-not-found=true

# Delete Infra
kubectl delete -f infrastructure/k8s/zookeeper.yaml --ignore-not-found=true
kubectl delete -f infrastructure/k8s/postgres.yaml --ignore-not-found=true

echo "✅ All K8s resources deleted."
echo "ℹ️  To stop Minikube, run: minikube stop"
