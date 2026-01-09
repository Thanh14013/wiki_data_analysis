# Recommended Big Data Tools & Deployment Stack
*Focus: Free/Freemium & Auto-scaling Capable*

This guide proposes a modernized stack for the Wiki Data Pipeline that leverages **Serverless** and **Cloud Native** technologies to achieve high scalability with minimal cost (often starting free).

---

## 1. Core Big Data Stack Recommendations

### A. Ingestion & Messaging (Replacing Kafka)

| Tool | Type | Free Tier / Model | Why Example? |
| :--- | :--- | :--- | :--- |
| **Upstash Kafka** | Serverless Kafka | **Free**: 10k messages/day. | Truly serverless. No managing brokers/Zookeeper. Scales to zero. Ideal for this project's event-driven nature. |
| **Confluent Cloud** | Managed Kafka | **Free**: $400/month credit (first 30 days) + Always Free Basic. | usage-based. The industry standard. Good for robust production, but "Basic" tier is very affordable/free for low volume. |
| **Redpanda** | Kafka API compatible | **Community Edition**: Free (Self-hosted). | 10x faster than Kafka, single binary (no Zookeeper), easy to deploy on K8s/Docker. Perfect if staying self-hosted. |

👉 **Recommendation**: **Upstash Kafka** for easiest setup and true "scale-to-zero" cost model.

### B. Stream Processing (Replacing Spark Structure Streaming)

| Tool | Type | Free Tier / Model | Why Example? |
| :--- | :--- | :--- | :--- |
| **Bytewax** | Python Stream Processing | **Open Source**: Free. | Built on Rust, Python API. Very lightweight compared to Spark. Can run on a small container (perfect for Cloud Run). |
| **Quix Streams** | Python Stream Processing | **Free Community Plan**. | Library designed for Kafka. Very simple pythonic API. Built for high performance. |
| **RisingWave** | Streaming Database | **Free Tier**: Cloud version available. | SQL-based streaming database. Replaces "Spark + Postgres". You write SQL to join streams and it maintains materialized views automatically. |

👉 **Recommendation**: **Quix Streams** (if coding in Python) or **RisingWave** (if preferring SQL). Both remove the heavy JVM overhead of Spark.

### C. Real-time Analytics Database (Replacing PostgreSQL)

Postgres is great, but OLAP databases are better for "Big Data" analytics (aggregations, time-series).

| Tool | Type | Free Tier / Model | Why Example? |
| :--- | :--- | :--- | :--- |
| **Tinybird** | Real-time Analytics | **Free**: 10GB processed/month. | Ingests from Kafka, exposes API endpoints via SQL. Handles the "Dashboard Backend" role entirely. **Auto-scales**. |
| **ClickHouse Cloud** | OLAP DB | **Free Trial** / usage based. | The fastest open-source OLAP DB. Perfect for "Battlefield" charts and massive aggregations. |
| **Neon** | Serverless Postgres | **Free**: 0.5 GB, scale-to-zero. | If sticking with Postgres, Neon is the best Serverless option. Separates storage/compute. Auto-scales compute up/down. |

👉 **Recommendation**: **Tinybird**. It replaces the need for a separate backend API. You just push data to it, write SQL, and it gives you a high-speed JSON API for your Streamlit dashboard.

---

## 2. Deployment Platforms (Auto-scaling & Free)

To achieve "Auto Scalability" without managing Kubernetes clusters manually, you should use **Serverless Containers** or **PaaS**.

### Top Recommendation: Google Cloud Run (GCP)
*   **Model**: Serverless Containers. You give it a Docker image, it runs it.
*   **Scaling**: Automatically scales from **0 to N** instances based on CPU/Request load.
*   **Free Tier**: 2 million requests/month, 360,000 GB-seconds, 180,000 vCPU-seconds **FREE per month**.
*   **Why use it**:
    *   Deploy `producer` as a Service (or Job).
    *   Deploy `dashboard` as a Service.
    *   It handles HTTPS, Load Balancing, and Logging automatically.

### Alternative: Railway.app
*   **Model**: PaaS. Connect GitHub -> Auto Deploy.
*   **Scaling**: Vertical scaling (increase RAM/CPU).
*   **Free**: Trial only (shifted to $5 min/month for full features).
*   **Why use it**: Extremely focused on Developer Experience. Good "Variables" management.

### Alternative: Render.com
*   **Model**: PaaS.
*   **Free**: Free Web Services (spin down after inactivity).
*   **Scaling**: Paid plans support auto-scaling instances.

---

## 3. Proposed "Modern Free V2" Architecture

Combine these tools for a powerful, zero-maintenance, highly scalable stack:

```mermaid
graph LR
    Wiki[Wiki Stream] -->|Python Script on Cloud Run| Producer[Producer Service]
    
    subgraph "Serverless Ingestion & Storage"
        Producer -->|Events| Upstash[Upstash Kafka (Serverless)]
        Upstash -->|Ingest| Tinybird[Tinybird (Real-time DB)]
    end
    
    subgraph "Presentation"
        Tinybird -->|JSON API| Dashboard[Streamlit on Cloud Run]
    end
    
    subgraph "Alternative Processing"
        Upstash -->|Stream| RisingWave[RisingWave Cloud]
        RisingWave -->|Query| Dashboard
    end
```

### Why this stack?
1.  **No Server Management**: No EC2, no Droplets, no K8s Nodes to patch.
2.  **Auto-Scaling**: Cloud Run scales the compute. Upstash/Tinybird scale the data layer.
3.  **Cost**:
    *   **Cloud Run**: Likely $0/month for this workload.
    *   **Upstash**: Free tier covers ~300k messages/month.
    *   **Tinybird**: Free tier covers ~10GB data.

## 4. Migration Steps (How to execute)
1.  **Sign up**: GCP Account, Upstash Account, Tinybird Account.
2.  **Refactor Producer**: Update `producer.py` to point to Upstash URL.
3.  **Refactor Storage**: Instead of Spark -> Postgres, ingest Kafka topic directly into Tinybird.
4.  **Refactor Dashboard**: Update `app.py` to fetch data from Tinybird HTTP APIs (faster than SQL query to Postgres).
5.  **Deploy**:
    *   `gcloud run deploy producer --source .`
    *   `gcloud run deploy dashboard --source .`

This transition removes the complexity of Spark and Kubernetes, focusing purely on Business Logic and Data Value.
