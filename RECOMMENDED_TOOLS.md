# Các công cụ Big Data & Stack triển khai được đề xuất
*Trọng tâm: Miễn phí/Freemium & Có khả năng tự động mở rộng (Auto-scaling)*

Hướng dẫn này đề xuất một stack hiện đại hóa cho Wiki Data Pipeline tận dụng các công nghệ **Serverless** và **Cloud Native** để đạt được khả năng mở rộng cao với chi phí tối thiểu (thường bắt đầu miễn phí).

---

## 1. Đề xuất Big Data Stack cốt lõi

### A. Ingestion & Messaging (Thay thế Kafka)

| Công cụ | Loại | Free Tier / Mô hình | Tại sao là ví dụ? |
| :--- | :--- | :--- | :--- |
| **Upstash Kafka** | Serverless Kafka | **Free**: 10k tin nhắn/ngày. | Hoàn toàn serverless. Không cần quản lý brokers/Zookeeper. Scales to zero (Mở rộng về 0). Lý tưởng cho tính chất hướng sự kiện của dự án này. |
| **Confluent Cloud** | Managed Kafka | **Free**: $400/tháng tín dụng (30 ngày đầu) + Always Free Basic. | Dựa trên mức sử dụng. Tiêu chuẩn công nghiệp. Tốt cho sản xuất mạnh mẽ, nhưng gói "Basic" rất phải chăng/miễn phí cho khối lượng thấp. |
| **Redpanda** | Tương thích Kafka API | **Community Edition**: Miễn phí (Self-hosted). | Nhanh hơn 10 lần so với Kafka, binary đơn lẻ (không cần Zookeeper), dễ triển khai trên K8s/Docker. Hoàn hảo nếu duy trì tự host. |

👉 **Khuyến nghị**: **Upstash Kafka** để thiết lập dễ dàng nhất và mô hình chi phí thực sự "scale-to-zero".

### B. Stream Processing (Thay thế Spark Structure Streaming)

| Công cụ | Loại | Free Tier / Mô hình | Tại sao là ví dụ? |
| :--- | :--- | :--- | :--- |
| **Bytewax** | Python Stream Processing | **Open Source**: Miễn phí. | Xây dựng trên Rust, API Python. Rất nhẹ so với Spark. Có thể chạy trên một container nhỏ (hoàn hảo cho Cloud Run). |
| **Quix Streams** | Python Stream Processing | **Free Community Plan**. | Thư viện được thiết kế cho Kafka. API rất pythonic và đơn giản. Xây dựng cho hiệu suất cao. |
| **RisingWave** | Streaming Database | **Free Tier**: Có phiên bản Cloud. | Cơ sở dữ liệu streaming dựa trên SQL. Thay thế "Spark + Postgres". Bạn viết SQL để join các luồng và nó duy trì các materialized views tự động. |

👉 **Khuyến nghị**: **Quix Streams** (nếu code bằng Python) hoặc **RisingWave** (nếu thích SQL). Cả hai đều loại bỏ gánh nặng JVM nặng nề của Spark.

### C. Cơ sở dữ liệu phân tích thời gian thực (Thay thế PostgreSQL)

Postgres rất tuyệt, nhưng các cơ sở dữ liệu OLAP tốt hơn cho phân tích "Big Data" (tổng hợp, chuỗi thời gian).

| Công cụ | Loại | Free Tier / Mô hình | Tại sao là ví dụ? |
| :--- | :--- | :--- | :--- |
| **Tinybird** | Real-time Analytics | **Free**: 10GB xử lý/tháng. | Nhập từ Kafka, hiển thị các điểm cuối API qua SQL. Đảm nhận hoàn toàn vai trò "Dashboard Backend". **Auto-scales**. |
| **ClickHouse Cloud** | OLAP DB | **Free Trial** / dựa trên sử dụng. | OLAP DB mã nguồn mở nhanh nhất. Hoàn hảo cho các biểu đồ "Battlefield" và các tổng hợp lớn. |
| **Neon** | Serverless Postgres | **Free**: 0.5 GB, scale-to-zero. | Nếu vẫn dùng Postgres, Neon là tùy chọn Serverless tốt nhất. Tách biệt lưu trữ/tính toán. Tự động mở rộng tính toán lên/xuống. |

👉 **Khuyến nghị**: **Tinybird**. Nó thay thế nhu cầu về một API backend riêng biệt. Bạn chỉ cần đẩy dữ liệu vào nó, viết SQL, và nó cung cấp cho bạn một API JSON tốc độ cao cho Streamlit dashboard của bạn.

---

## 2. Nền tảng triển khai (Auto-scaling & Miễn phí)

Để đạt được "Auto Scalability" mà không cần quản lý các cụm Kubernetes thủ công, bạn nên sử dụng **Serverless Containers** hoặc **PaaS**.

### Khuyến nghị hàng đầu: Google Cloud Run (GCP)
*   **Mô hình**: Serverless Containers. Bạn cung cấp Docker image, nó chạy nó.
*   **Scaling**: Tự động mở rộng từ **0 đến N** instances dựa trên tải CPU/Request.
*   **Free Tier**: 2 triệu requests/tháng, 360,000 GB-giây, 180,000 vCPU-giây **MIỄN PHÍ mỗi tháng**.
*   **Tại sao sử dụng nó**:
    *   Triển khai `producer` như một Service (hoặc Job).
    *   Triển khai `dashboard` như một Service.
    *   Nó xử lý HTTPS, Load Balancing, và Logging tự động.

### Thay thế: Railway.app
*   **Mô hình**: PaaS. Kết nối GitHub -> Tự động Deploy.
*   **Scaling**: Mở rộng theo chiều dọc (tăng RAM/CPU).
*   **Free**: Chỉ dùng thử (chuyển sang tối thiểu $5/tháng cho đầy đủ tính năng).
*   **Tại sao sử dụng nó**: Cực kỳ tập trung vào Trải nghiệm nhà phát triển. Quản lý "Variables" tốt.

### Thay thế: Render.com
*   **Mô hình**: PaaS.
*   **Free**: Web Services miễn phí (tắt sau khi không hoạt động).
*   **Scaling**: Các gói trả phí hỗ trợ tự động mở rộng instances.

---

## 3. Kiến trúc "V2 hiện đại miễn phí" được đề xuất

Kết hợp các công cụ này để có một stack mạnh mẽ, không cần bảo trì, khả năng mở rộng cao:

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

### Tại sao là stack này?
1.  **Không quản lý Server**: Không EC2, không Droplets, không K8s Nodes để vá lỗi.
2.  **Auto-Scaling**: Cloud Run mở rộng tính toán. Upstash/Tinybird mở rộng lớp dữ liệu.
3.  **Chi phí**:
    *   **Cloud Run**: Có khả năng $0/tháng cho khối lượng công việc này.
    *   **Upstash**: Free tier bao gồm ~300k tin nhắn/tháng.
    *   **Tinybird**: Free tier bao gồm ~10GB dữ liệu.

## 4. Các bước di chuyển (Cách thực hiện)
1.  **Đăng ký**: Tài khoản GCP, Tài khoản Upstash, Tài khoản Tinybird.
2.  **Refactor Producer**: Cập nhật `producer.py` để trỏ đến URL Upstash.
3.  **Refactor Storage**: Thay vì Spark -> Postgres, nhập Kafka topic trực tiếp vào Tinybird.
4.  **Refactor Dashboard**: Cập nhật `app.py` để lấy dữ liệu từ API HTTP của Tinybird (nhanh hơn truy vấn SQL đến Postgres).
5.  **Deploy**:
    *   `gcloud run deploy producer --source .`
    *   `gcloud run deploy dashboard --source .`

Quá trình chuyển đổi này loại bỏ sự phức tạp của Spark và Kubernetes, tập trung hoàn toàn vào Business Logic và Data Value.
