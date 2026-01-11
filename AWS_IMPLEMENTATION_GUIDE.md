# Hướng dẫn Thực hiện Chuyển đổi AWS (AWS Implementation Guide)

Tài liệu này hướng dẫn từng bước chi tiết (Step-by-step) để thiết lập hạ tầng trên AWS và chuẩn bị môi trường cho dự án Big Data.

---

## Giai đoạn 1: Chuẩn bị Hạ tầng AWS (AWS Console)

Bước này thực hiện hoàn toàn trên giao diện web của AWS (AWS Management Console).

### 1. Khởi tạo Database (RDS PostgreSQL)
*Chúng ta làm bước này trước vì RDS mất khoảng 10-15 phút để khởi tạo.*

1.  Truy cập **RDS Dashboard** -> Chọn **Create database**.
2.  **Engine options**: Chọn **PostgreSQL**.
3.  **Templates**: Chọn **Production** (hoặc Dev/Test nếu muốn tiết kiệm hơn nữa, nhưng Production ổn định hơn).
4.  **Settings**:
    *   **DB instance identifier**: `wiki-pipeline-db`.
    *   **Master username**: `admin`.
    *   **Master password**: Tự đặt (ví dụ: `Admin123456!`). *Ghi nhớ mật khẩu này*.
5.  **Instance configuration**:
    *   Chọn **Burstable classes**.
    *   Chọn **db.t4g.micro** (Dòng Graviton giá rẻ & mát).
6.  **Storage**:
    *   Allocated storage: `20` GiB.
    *   Storage type: `gp3`.
    *   Enable storage autoscaling: **Tắt** (để kiểm soát chi phí).
7.  **Connectivity**:
    *   **Public access**: Chọn **YES** (Để máy tính của bạn có thể kết nối DB kiểm tra nếu cần, sau này sẽ chặn IP lạ sau).
    *   **VPC security group**: Chọn "Create new" -> Đặt tên `rds-public-access`.
8.  **Additional configuration**:
    *   **Initial database name**: `wikidb` (Quan trọng: Nếu không điền, Postgres không tạo DB mặc định).
9.  Nhấn **Create database**.

### 2. Khởi tạo Object Storage (S3)
1.  Truy cập **S3 Dashboard** -> **Create bucket**.
2.  **Bucket name**: `wiki-data-lake-prod-[số-ngẫu-nhiên]` (Ví dụ: `wiki-data-lake-prod-2026`). Tên phải là duy nhất toàn cầu.
3.  **Region**: Chọn cùng region với EC2/RDS (ví dụ: `us-east-1`).
4.  Các cài đặt khác để mặc định. Nhấn **Create bucket**.

### 3. Khởi tạo Máy chủ (EC2 Instance)
1.  Truy cập **EC2 Dashboard** -> **Launch Instances**.
2.  **Name**: `Wiki-BigData-Server`.
3.  **OS Images**: Chọn **Ubuntu** -> **Ubuntu Server 24.04 LTS (HVM)**.
4.  **Instance Type**: Chọn **t3.medium** (2 vCPU, 4 GiB Memory).
5.  **Key pair (Login)**:
    *   Chọn "Create new key pair".
    *   Name: `wiki-ssh-key`.
    *   Tải file `.pem` về máy (Chỉ tải được 1 lần duy nhất).
6.  **Network settings**:
    *   Check vào **Allow SSH traffic from Anywhere** (Hoặc My IP để an toàn).
    *   Check vào **Allow HTTP traffic from the internet**.
7.  **Configure storage**:
    *   Tăng từ 8 GiB lên **30 GiB** (gp3).
8.  **Advanced details** (Quan trọng cho S3):
    *   **IAM instance profile**: Chọn "Create new IAM profile" -> Tạo role mới có quyền `AmazonS3FullAccess` -> Quay lại chọn Role đó cho EC2. (Bước này giúp code trên EC2 ghi vào S3 mà không cần lưu Access Key/Secret Key trong code).
9.  Nhấn **Launch instance**.

### 4. Cấu hình Bảo mật (Security Group)
Mở các cổng cần thiết để Dashboard và Redpanda hoạt động.

1.  Vào EC2 Dashboard -> **Security Groups**.
2.  Tìm SG đang gắn với EC2 vừa tạo (thường tên là `launch-wizard-...`).
3.  Edit **Inbound rules** -> Add rule:
    *   **Type**: Custom TCP -> **Port range**: `8501` -> **Source**: `0.0.0.0/0` (Cho phép truy cập Dashboard Streamlit từ web).
    *   **(Tùy chọn)** Mở port `8081` nếu muốn xem Redpanda Console.
4.  Nhấn **Save rules**.

---

## Giai đoạn 2: Cài đặt Môi trường (SSH vào Server)

Bạn cần mở Terminal trên máy tính cá nhân để SSH vào EC2.

### 1. Kết nối SSH
```bash
# Cấp quyền cho file key vừa tải
chmod 400 wiki-ssh-key.pem

# Kết nối (Thay 1.2.3.4 bằng Public IP của EC2)
ssh -i wiki-ssh-key.pem ubuntu@1.2.3.4
```

### 2. Cài đặt Docker & Docker Compose
Trên màn hình terminal của EC2, chạy lần lượt:

```bash
# Cập nhật hệ thống
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg

# Cài đặt Docker Engine (Script chính chủ)
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Cấp quyền chạy Docker không cần sudo
sudo usermod -aG docker ubuntu
newgrp docker

# Kiểm tra
docker ps
# (Nếu không báo lỗi permission denied là thành công)
```

### 3. Cài đặt Git & Clone Code
```bash
sudo apt-get install -y git

# Clone dự án của bạn
git clone https://github.com/Thanh14013/wiki_data_analysis.git
cd wiki_data_analysis
```
*(Nếu chưa có GitHub, bạn có thể dùng SCP để copy folder code từ máy lên).*

---

## Giai đoạn 3: Chuẩn bị Cấu hình (Configuration)

### 1. Tạo file biến môi trường (.env)
Tạo file `.env` trên Server để chứa thông tin bảo mật (kết nối RDS mà ta đã tạo ở Giai đoạn 1).

```bash
nano .env
```
Nội dung file `.env` (Điền thông tin thật từ RDS Console):
```ini
# Database Config
DB_HOST=wiki-pipeline-db.xxxxxx.us-east-1.rds.amazonaws.com
DB_PORT=5432
DB_NAME=wikidb
DB_USER=admin
DB_PASSWORD=Admin123456!

# Processing Config
BATCH_INTERVAL=60
S3_BUCKET_NAME=wiki-data-lake-prod-2026
```
Lưu file (`Ctrl+O`, `Enter`, `Ctrl+X`).

### 2. Tạo Docker Networks
```bash
docker network create wiki-network
```

---

## Giai đoạn 4: Bước tiếp theo (Chờ triển khai Code)

Đến đây, hạ tầng đã sẵn sàng:
- [x] Máy chủ EC2 t3.medium đã chạy, có Docker.
- [x] Database RDS Postgres đã online.
- [x] S3 Bucket đã có.
- [x] Đã thiết lập quyền truy cập (IAM Role, Security Group).

**Công việc còn lại (Tôi sẽ viết code cho bạn ở bước sau):**
1.  Tạo `docker-compose.prod.yml`: File này sẽ kéo Redpanda, Quix, Dashboard về chạy.
2.  Viết `processing/quix_job.py`: Code xử lý luồng (thay thế Spark).
3.  Viết `ingestion/batch_job.py`: Code upload S3.
4.  Chạy lệnh thần thánh: `docker compose -f docker-compose.prod.yml up -d`.

---
*Hãy báo cho tôi khi bạn đã thực hiện xong Giai đoạn 1 & 2 (hoặc nếu bạn muốn tôi giả lập các file cấu hình ngay bây giờ).*
