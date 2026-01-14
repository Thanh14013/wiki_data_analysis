# Sử dụng Python 3.10 Slim
FROM python:3.10-slim-bookworm

# Thiết lập thư mục làm việc
WORKDIR /app

# Cài đặt các gói hệ thống cơ bản
RUN apt-get update && \
    apt-get install -y procps curl openjdk-11-jre-headless && \
    rm -rf /var/lib/apt/lists/*

# Thiết lập biến môi trường Python
ENV PYTHONPATH="/app"
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