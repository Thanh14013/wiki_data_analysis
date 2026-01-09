#!/bin/bash
set -e

echo "========================================================="
echo "🚀 Starting Wiki Data Pipeline (K8s Mode)"
echo "========================================================="

# 1. Check Minikube
if ! minikube status > /dev/null 2>&1; then
    echo "📦 Starting Minikube..."
    minikube start
else
    echo "✅ Minikube is running."
fi

# 2. Check Pods
echo "---------------------------------------------------------"
echo "🔍 Checking Pods Status..."
kubectl get pods

echo "⏳ Waiting for all pods to be ready (timeout: 300s)..."
kubectl wait --for=condition=ready pod --all --timeout=300s

echo "---------------------------------------------------------"
echo "✅ All Pods are Running!"

# 3. Dashboard Info
echo "---------------------------------------------------------"
echo "� Dashboard Access:"

# Try to get Minikube IP
MINIKUBE_IP=$(minikube ip)
NODE_PORT=$(kubectl get svc wiki-dashboard -o=jsonpath='{.spec.ports[0].nodePort}')

if [ -n "$MINIKUBE_IP" ] && [ -n "$NODE_PORT" ]; then
    echo "URL: http://$MINIKUBE_IP:$NODE_PORT"
    echo ""
    echo "⚠️  If the URL above doesn't work (common in WSL2), use Port Forwarding:"
    echo "   kubectl port-forward svc/wiki-dashboard 8501:8501"
    echo "   Then open: http://localhost:8501"
else
    # Fallback to port-forward instructions
    echo "To access the Dashboard, run this command in a separate terminal:"
    echo "👉  kubectl port-forward svc/wiki-dashboard 8501:8501"
    echo "    Then open: http://localhost:8501"
fi

echo "To check production logs:"
echo "👉  kubectl logs -l app=wiki-producer -f"
echo "To check spark logs:"
echo "👉  kubectl logs -l app=wiki-spark -f"