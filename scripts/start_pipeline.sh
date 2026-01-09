#!/bin/bash
set -e

# scripts/start_pipeline.sh

echo "========================================================="
echo "🚀 Starting Wiki Data Pipeline (Kubernetes Mode)"
echo "========================================================="

# Move to project root
cd "$(dirname "$0")/.."

# 1. Check/Start Minikube
echo "🔍 Checking Minikube status..."
if ! minikube status | grep -q "Running"; then
    echo "📦 Starting Minikube..."
    minikube start
else
    echo "✅ Minikube is running."
fi

# 2. Build Docker Image (Fast update)
echo "---------------------------------------------------------"
echo "⚡ Building fast update (wiki-pipeline:v6) from v5..."
eval $(minikube -p minikube docker-env)
docker build -f Dockerfile.fast -t wiki-pipeline:v6 .

# minikube image load is not needed if we build inside minikube env
# minikube image load wiki-pipeline:v6 
echo "✅ Image built (v6)."

# 3. Deploy Infrastructure
echo "---------------------------------------------------------"
echo "🏗  Deploying Infrastructure..."

# Apply Zookeeper & Postgres
kubectl apply -f infrastructure/k8s/zookeeper.yaml
kubectl apply -f infrastructure/k8s/postgres.yaml

# Wait for Zookeeper
echo "Loading Zookeeper..."
kubectl rollout status deployment/zookeeper --timeout=120s

# Apply Kafka
echo "---------------------------------------------------------"
echo "message broker Deploying Kafka..."
kubectl apply -f infrastructure/k8s/kafka.yaml

# Wait for Kafka
echo "⏳ Waiting for Kafka to be ready..."
# Giving it a moment to initialize
sleep 5
kubectl wait --for=condition=ready pod -l app=kafka --timeout=300s

# 4. Deploy Application
echo "---------------------------------------------------------"
echo "🚀 Deploying Applications (Producer & Spark)..."

# Force restart by deleting existing pods (optional but ensures fresh image is used if apply doesn't trigger it)
# We use rollout restart which is cleaner
# kubectl rollout restart deployment/wiki-producer
# kubectl rollout restart deployment/wiki-spark
# BUT, purely apply is fine if image is latest and pull policy Never? 
# Actually, if the deployment is already there, apply might not restart it if yaml hasn't changed.
# So explicit restart is good practice for dev loops.

kubectl apply -f infrastructure/k8s/wiki-app.yaml
kubectl apply -f infrastructure/k8s/dashboard.yaml # Deploy Dashboard
kubectl rollout restart deployment/wiki-producer
kubectl rollout restart deployment/wiki-spark
kubectl rollout restart deployment/wiki-dashboard

echo "---------------------------------------------------------"
echo "✅ Deployment finished!"
echo "📊 Check status:   kubectl get pods"
echo "📜 Check producer: kubectl logs -l app=wiki-producer -f"
echo "📜 Check spark:    kubectl logs -l app=wiki-spark -f"
