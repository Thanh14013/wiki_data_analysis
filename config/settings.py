"""
Centralized configuration for the Wiki Data Pipeline
Supports multiple environments (dev, prod)
"""
import os
from dataclasses import dataclass, field
from typing import Optional, Dict
from pathlib import Path
from dotenv import load_dotenv

# 1. Load biến môi trường từ file .env ngay khi import module
# override=True để đảm bảo biến trong .env được ưu tiên hơn biến hệ thống cũ
load_dotenv(override=False)

# Xác định thư mục gốc dự án (để tạo đường dẫn tuyệt đối cho Data Lake)
BASE_DIR = Path(__file__).resolve().parent.parent

@dataclass
class KafkaConfig:
    """Kafka connection settings"""
    # Spark yêu cầu format "host1:port1,host2:port2" (String), không phải List
    bootstrap_servers: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    topic_name: str = os.getenv("KAFKA_TOPIC", "wiki-raw-events")
    consumer_group: str = os.getenv("KAFKA_CONSUMER_GROUP", "wiki-consumer-group")

@dataclass
class PostgresConfig:
    """PostgreSQL connection settings"""
    host: str = os.getenv("POSTGRES_HOST", "localhost")
    port: int = int(os.getenv("DB_PORT", "5432"))
    database: str = os.getenv("POSTGRES_DB", "wikidata")
    user: str = os.getenv("POSTGRES_USER", "admin")
    # Default password matches docker-compose stack; override via env in production
    password: str = os.getenv("POSTGRES_PASSWORD", "password123")

    @property
    def jdbc_url(self) -> str:
        """URL dùng cho Spark JDBC"""
        return f"jdbc:postgresql://{self.host}:{self.port}/{self.database}"

    @property
    def connection_string(self) -> str:
        """Connection string dùng cho thư viện Python thường (psycopg2/sqlalchemy)"""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
    
    @property
    def spark_properties(self) -> Dict[str, str]:
        """Dictionary cấu hình dùng trực tiếp trong Spark .option()"""
        return {
            "user": self.user,
            "password": self.password,
            "driver": "org.postgresql.Driver"
        }

@dataclass
class WikiAPIConfig:
    """Wikimedia API settings"""
    stream_url: str = os.getenv("WIKI_STREAM_URL", "https://stream.wikimedia.org/v2/stream/recentchange")
    user_agent: str = "WikiDataPipeline/1.0 (Contact: admin@example.com)"
    timeout: int = 30

@dataclass
class S3Config:
    """AWS S3 Configuration for Batch Layer"""
    bucket_name: str = os.getenv("S3_BUCKET_NAME", "wiki-data-lake-dev")
    region: str = os.getenv("AWS_REGION", "us-east-1")
    # If using IAM Role on EC2, keys are not needed.
    # explicit keys are only for local dev (MinIO or User keys)
    access_key: Optional[str] = os.getenv("AWS_ACCESS_KEY_ID")
    secret_key: Optional[str] = os.getenv("AWS_SECRET_ACCESS_KEY")
    endpoint_url: Optional[str] = os.getenv("S3_ENDPOINT_URL") # For MinIO support


@dataclass
class SparkConfig:
    """Spark application settings"""
    app_name: str = "WikiDataPipeline"
    master: str = os.getenv("SPARK_MASTER", "local[*]")
    log_level: str = "WARN"
    
    # Data Lake paths - Chuyển sang Absolute Path để tránh lỗi Spark
    data_lake_path: str = os.getenv("DATA_LAKE_PATH", "/tmp/datalake/raw_data")
    # Use /tmp for checkpoints to avoid overlayfs issues
    checkpoint_path: str = os.getenv("CHECKPOINT_PATH", f"/tmp/checkpoints_{os.urandom(4).hex()}")
    
    # Streaming settings
    trigger_interval: str = "5 seconds"  # Processing trigger interval
    watermark_delay: str = "10 seconds"    # Late data handling
    window_duration: str = "10 seconds"     # Window for aggregation
    
    # Spark packages configuration
    spark_version: str = "3.5.0" # Khớp với version bạn đang cài
    scala_version: str = "2.12"
    
    @property
    def packages(self) -> str:
        """Auto-generate packages string"""
        pkgs = [
            f"org.apache.spark:spark-sql-kafka-0-10_{self.scala_version}:{self.spark_version}",
            "org.postgresql:postgresql:42.6.0",
            "org.apache.commons:commons-pool2:2.10.0"
        ]
        return ",".join(pkgs)

@dataclass
class Settings:
    """Main settings container"""
    environment: str = os.getenv("ENVIRONMENT", "dev")
    kafka: KafkaConfig = field(default_factory=KafkaConfig)
    postgres: PostgresConfig = field(default_factory=PostgresConfig)
    wiki_api: WikiAPIConfig = field(default_factory=WikiAPIConfig)
    wiki_api: WikiAPIConfig = field(default_factory=WikiAPIConfig)
    spark: SparkConfig = field(default_factory=SparkConfig)
    s3: S3Config = field(default_factory=S3Config)
    
    def validate(self):
        """Kiểm tra các biến quan trọng"""
        if not self.postgres.password:
            print("⚠️ CẢNH BÁO: Chưa cấu hình POSTGRES_PASSWORD trong file .env!")

# Singleton instance
_settings: Optional[Settings] = None

def get_settings() -> Settings:
    """Get or create settings singleton"""
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.validate()
    return _settings

# Usage Example (để test khi chạy trực tiếp file này)
if __name__ == "__main__":
    conf = get_settings()
    print(f"Loaded config for env: {conf.environment}")
    print(f"Data Lake Path: {conf.spark.data_lake_path}")
    print(f"Postgres URL: {conf.postgres.jdbc_url}")