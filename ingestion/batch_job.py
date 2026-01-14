import os
import json
import logging
import pandas as pd
import boto3
from datetime import datetime
from urllib.parse import urlparse
from kafka import KafkaConsumer
import io

# Add parent directory to path
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import get_settings

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BatchArchiver")

settings = get_settings()


def _parse_datalake_path(data_lake_path: str):
    """Parse data lake path into (bucket, prefix, is_s3)."""
    if data_lake_path.startswith("s3://") or data_lake_path.startswith("s3a://"):
        parsed = urlparse(data_lake_path)
        bucket = parsed.netloc
        prefix = parsed.path.lstrip('/')
        return bucket, prefix, True
    return None, data_lake_path, False

def get_s3_client():
    """Create boto3 client for S3"""
    client_kwargs = {
        'service_name': 's3',
        'region_name': settings.s3.region,
    }
    
    # Only add credentials if explicitly provided (not empty)
    if settings.s3.access_key and settings.s3.secret_key:
        client_kwargs['aws_access_key_id'] = settings.s3.access_key
        client_kwargs['aws_secret_access_key'] = settings.s3.secret_key
    
    # Add endpoint URL if specified (for MinIO)
    if settings.s3.endpoint_url:
        client_kwargs['endpoint_url'] = settings.s3.endpoint_url
    
    return boto3.client(**client_kwargs)


def normalize_log_params(x):
    """Normalize log_params to handle mixed types"""
    if x is None:
        return None
    if isinstance(x, (dict, list)):
        return json.dumps(x, ensure_ascii=False)
    return str(x)


def upload_batch(df: pd.DataFrame):
    """Upload DataFrame to data lake (S3 or local), aligned with batch processor."""
    if df.empty:
        return

    # Normalize log_params before writing to avoid schema conflicts
    if 'log_params' in df.columns:
        df['log_params'] = df['log_params'].apply(normalize_log_params)

    if 'event_time' not in df.columns:
        if 'timestamp' in df.columns:
            df['event_time'] = pd.to_datetime(df['timestamp'], unit='s')
        else:
            df['event_time'] = datetime.utcnow()

    year = datetime.utcnow().strftime("%Y")
    month = datetime.utcnow().strftime("%m")

    bucket, base_prefix, is_s3 = _parse_datalake_path(settings.spark.data_lake_path)
    prefix = f"{base_prefix.rstrip('/')}/raw_events/year={year}/month={month}"

    if is_s3:
        try:
            filename = f"{prefix}/wiki_events_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.parquet"
            buffer = io.BytesIO()
            df.to_parquet(buffer, index=False)
            buffer.seek(0)

            s3 = get_s3_client()
            s3.upload_fileobj(buffer, bucket, filename)
            logger.info(f"✅ Uploaded {len(df)} records to s3://{bucket}/{filename}")
        except Exception as e:
            logger.error(f"❌ S3 Upload Failed: {e}")
    else:
        try:
            target_dir = os.path.join(prefix)
            os.makedirs(target_dir, exist_ok=True)
            filename = os.path.join(target_dir, f"wiki_events_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.parquet")
            df.to_parquet(filename, index=False)
            logger.info(f"✅ Wrote {len(df)} records to {filename}")
        except Exception as e:
            logger.error(f"❌ Local write failed: {e}")

def main():
    logger.info("🚀 Starting Batch Archiver...")
    logger.info(f"   Data lake: {settings.spark.data_lake_path}")
    
    consumer = KafkaConsumer(
        settings.kafka.topic_name,
        bootstrap_servers=settings.kafka.bootstrap_servers,
        group_id="wiki-batch-archiver-group",
        auto_offset_reset='latest',
        value_deserializer=lambda x: json.loads(x.decode('utf-8'))
    )

    buffer = []
    BATCH_SIZE = 100  # Lower for faster testing (was 5000)
    TIMEOUT_SEC = 60  # Or write every 60 seconds
    last_flush_time = datetime.now()

    logger.info("📥 Waiting for events...")
    
    for message in consumer:
        buffer.append(message.value)
        
        # Check buffer limits
        time_diff = (datetime.now() - last_flush_time).total_seconds()
        
        if len(buffer) >= BATCH_SIZE or (time_diff > TIMEOUT_SEC and len(buffer) > 0):
            logger.info(f"📦 Buffering threshold reached ({len(buffer)} events). Flushing to S3...")
            
            df = pd.DataFrame(buffer)

            upload_batch(df)

            buffer = []
            last_flush_time = datetime.now()

if __name__ == "__main__":
    main()
