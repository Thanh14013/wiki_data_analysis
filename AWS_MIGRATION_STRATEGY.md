# Chiến lược Di cư lên AWS (AWS Migration Strategy)
*Phiên bản: Cloud-Native với $100 Credit*

Tài liệu này chi tiết hóa kế hoạch chuyển đổi dự án từ môi trường Local (Minikube/Spark) sang hạ tầng AWS (EC2/RDS) nhằm tối ưu hiệu năng và tận dụng gói tín dụng $100.

---

## 1. Tổng quan Kiến trúc

Chúng ta sẽ chuyển từ kiến trúc "Nặng nề" (Heavyweight - JVM based) sang kiến trúc "Nhẹ & Hiệu quả" (Lightweight - Python/C++ Native) để phù hợp với tài nguyên Cloud.

### Sơ đồ chuyển đổi

| Thành phần | Hiện tại (Local/Minikube) | Mới (AWS Production) | Trạng thái thay đổi |
| :--- | :--- | :--- | :--- |
| **Hạ tầng (Infrastructure)** | Kubernetes (Minikube) | **AWS EC2 (t3.medium) + Docker Swarm Mode (Simulated)** | **Giả lập Phân tán**. Sử dụng Docker Compose với `replicas: 3` cho Processing Service để giả lập việc xử lý song song trên nhiều node phân tán. |
| **Quản lý Hàng đợi (Message Queue)** | Apache Kafka + Zookeeper | **Redpanda** | **Thay thế**. Redpanda tương thích 100% Kafka API nhưng viết bằng C++, không cần Zookeeper, tiết kiệm RAM đáng kể. |
| **Xử lý Luồng (Stream Processing)** | Spark Structured Streaming | **Quix Streams** | **Thay thế**. Thay thế Spark (JVM nặng nề) bằng thư viện Python Native (Quix) nhẹ hơn, tốc độ cao hơn cho xử lý JSON/Text. |
| **Lưu trữ (Storage)** | PostgreSQL Container | **RDS PostgreSQL + AWS S3** | **Nâng cấp Lambda Arch**. RDS cho App, S3 cho Data Lake (Lưu trữ dài hạn/ML). |
| **Giao diện (Frontend)** | Streamlit (Local Port) | **Streamlit trên Docker** | **Giữ nguyên code**, thay đổi nơi chạy (Deploy container trên EC2 cùng mạng với Redpanda). |

---

## 2. Chi tiết Kỹ thuật từng thành phần

### 2.1. Hạ tầng Tính toán (Compute Layer) & Giả lập Đa luồng (Distributed Emulation)
*   **Dịch vụ:** AWS EC2
*   **Instance Type:** `t3.medium` (2 vCPUs, 4GB RAM)
*   **Giả lập Phân tán (Distributed Emulation):**
    *   Chúng ta sẽ định nghĩa `processing-worker` với **SCALE = 3** (chạy 3 container song song).
    *   Các workers này sẽ cùng join vào một **Redpanda Consumer Group**.
    *   **Kết quả:** Dữ liệu sẽ được tự động chia tải (Load Balancing) cho 3 workers, giả lập chính xác mô hình Distributed System trong thực tế. Nếu 1 worker chết, 2 worker còn lại tự gánh việc.
*   **Khả năng Mở rộng (Auto Scaling):**
    *   Hệ thống thiết kế theo dạng **Stateless Consumers**.
    *   Nếu tải tăng, có thể dễ dàng khởi chạy thêm EC2 instance mới và chạy thêm các container `processing`.
    *   Nhờ cơ chế Consumer Group của Redpanda/Kafka, các workers mới sẽ tự động chia sẻ tải xử lý mà không cần cấu hình lại.
*   **Khả năng chịu lỗi (Fault Tolerance):**
    *   Sử dụng **Docker Restart Policies** (`restart: always`) để tự khôi phục service nếu crash.
    *   Redpanda đảm bảo dữ liệu không mất (Persist to Disk) ngay cả khi process bị kill.

### 2.2. Lớp Dữ liệu (Layer Data) & Batch Layer (Mới)
*   **Speed Layer (Real-time):**
    *   **AWS RDS PostgreSQL**: Lưu trữ metrics tổng hợp.
    *   Chế độ Backup tự động (Automated Backups) của AWS đảm bảo an toàn dữ liệu 100%.
*   **Batch Layer (Archive/ML):**
    *   **AWS S3 (Simple Storage Service)**: Kho lưu trữ vô tận, giá rẻ.
    *   **Format**: Parquet (Tối ưu cho Machine Learning & Query).
    *   **Cơ chế:** Một service Python (`batch_ingestion`) sẽ đọc từ Redpanda và ghi file vào S3 mỗi 5-10 phút.

### 2.3. Lớp Xử lý (Processing Layer)
Chúng ta sẽ có 2 luồng xử lý song song (Lambda Architecture):
1.  **Vận tốc (Speed):** `quix_job.py` -> Tính toán nhanh -> RDS -> Dashboard.
2.  **Khối lượng (Batch):** `batch_job.py` -> Gom nhóm (Batching) -> S3 -> ML Training (Future).

---

## 3. Kế hoạch Triển khai (Migration Steps)

### Giai đoạn 1: Chuẩn bị Mã nguồn (Local)
1.  [ ] **Tạo `docker-compose.prod.yml`**: Định nghĩa stack Redpanda + Services.
2.  [ ] **Viết `processing/quix_job.py`**: Implement logic Stream Processing.
3.  [ ] **Viết `ingestion/batch_job.py`**: Implement logic ghi file Parquet vào S3.
4.  [ ] **Test Local**: Chạy thử toàn bộ stack với S3 giả lập (MinIO) hoặc skip S3 upload.

### Giai đoạn 2: Thiết lập Hạ tầng (AWS Console)
5.  [ ] Khởi tạo **RDS PostgreSQL**.
6.  [ ] Khởi tạo **AWS S3 Bucket** (VD: `wiki-project-datalake`).
7.  [ ] Khởi tạo **EC2 t3.medium** + IAM Role (Cho phép ghi vào S3).

### Giai đoạn 3: Deploy & Vận hành
8.  [ ] Clone code & Build Docker images.
9.  [ ] Chạy Stack.
10. [ ] Kiểm tra Dashboard & File trong S3.


---

## 4. Ước tính Chi phí (Monthly Cost Breakdown)

| Hạng mục | Cấu hình | Đơn giá ước tính |
| :--- | :--- | :--- |
| **EC2 Instance** | t3.medium (US East N. Virginia) | ~$30.37 / tháng |
| **RDS Instance** | db.t4g.micro (Single AZ) | ~$16.06 / tháng |
| **EBS Storage** | 30GB gp3 | ~$2.40 / tháng |
| **Data Transfer** | Outbound Traffic (Dashboard view) | ~$5.00 - $10.00 |
| **TỔNG CỘNG** | | **~$53 - $60 / tháng** |

> **Kết luận:** Hoàn toàn nằm trong ngân sách $100 Credit cho 1 tháng vận hành.

---
*Tài liệu được tạo ngày 10/01/2026 bởi Antigravity Agents.*
