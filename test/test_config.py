import pytest
from config.settings import get_settings

# Lấy cấu hình một lần dùng chung cho các test
conf = get_settings()

def test_postgres_config():
    """Kiểm tra cấu hình Postgres"""
    # Cách gọi mới: conf.postgres.user thay vì settings.POSTGRES_USER
    assert conf.postgres.user is not None
    assert conf.postgres.database == 'wikidata'
    
    # Kiểm tra URL JDBC có đúng định dạng không
    assert "jdbc:postgresql://" in conf.postgres.jdbc_url
    assert "5432" in conf.postgres.jdbc_url

def test_kafka_config():
    """Kiểm tra cấu hình Kafka"""
    # Cách gọi mới: conf.kafka.bootstrap_servers
    assert '9092' in conf.kafka.bootstrap_servers
    assert conf.kafka.topic_name == 'wiki-raw-events'

def test_spark_paths():
    """Kiểm tra đường dẫn Data Lake (phải là tuyệt đối)"""
    # Đường dẫn phải là dạng chuỗi và không được rỗng
    assert isinstance(conf.spark.data_lake_path, str)
    assert len(conf.spark.data_lake_path) > 0
    
    # Kiểm tra xem có chứa từ khóa 'storage' không (theo cấu trúc thư mục)
    assert 'storage' in conf.spark.data_lake_path

def test_app_settings():
    """Kiểm tra môi trường chạy"""
    assert conf.environment in ['dev', 'prod', 'test']