# --- SỬA DÒNG NÀY ---
# Đổi từ python:3.10-slim sang python:3.10-slim-bookworm để dùng Debian Stable (có Java 17)
FROM python:3.10-slim-bookworm

# Thiết lập thư mục làm việc
WORKDIR /app

# Cài đặt các gói hệ thống cần thiết cho Java (Spark cần Java)
# (Giữ nguyên đoạn này)
RUN apt-get update && \
    apt-get install -y openjdk-17-jre-headless procps curl && \
    rm -rf /var/lib/apt/lists/*

# Thiết lập biến môi trường cho Java và Python
ENV JAVA_HOME="/usr/lib/jvm/java-17-openjdk-amd64"
ENV PYTHONPATH="/app"

# Copy file thư viện và cài đặt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir streamlit plotly pandas psycopg2-binary

# Copy toàn bộ code dự án vào ảnh
COPY . .

# Expose port cho Streamlit
EXPOSE 8501

# Mặc định sẽ chạy script help, nhưng có thể override bằng command
CMD ["python3", "--version"]