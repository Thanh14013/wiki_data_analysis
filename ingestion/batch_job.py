import os
import json
import logging
import pandas as pd
import boto3
from datetime import datetime
from kafka import KafkaConsumer
import io

# Add parent directory to path
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import get_settings

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BatchS3Archiver")

settings = get_settings()

def get_s3_client():
    """Create boto3 client for S3"""
    return boto3.client(
        's3',
        region_name=settings.s3.region,
        aws_access_key_id=settings.s3.access_key,
        aws_secret_access_key=settings.s3.secret_key,
        endpoint_url=settings.s3.endpoint_url
    )

def upload_to_s3(df: pd.DataFrame, bucket: str, prefix: str):
    """Upload DataFrame as Parquet to S3"""
    if df.empty:
        return
    
    try:
        # Generate filename with timestamp
        filename = f"{prefix}/wiki_events_{datetime.now().strftime('%Y%m%d_%H%M%S')}.parquet"
        
        # Convert to Parquet buffer
        buffer = io.BytesIO()
        df.to_parquet(buffer, index=False)
        buffer.seek(0)
        
        # Upload
        s3 = get_s3_client()
        s3.upload_fileobj(buffer, bucket, filename)
        
        logger.info(f"✅ Uploaded {len(df)} records to s3://{bucket}/{filename}")
        
    except Exception as e:
        logger.error(f"❌ S3 Upload Failed: {e}")

def main():
    logger.info("🚀 Starting Batch S3 Archiver...")
    logger.info(f"   Bucket: {settings.s3.bucket_name}")
    
    consumer = KafkaConsumer(
        settings.kafka.topic_name,
        bootstrap_servers=settings.kafka.bootstrap_servers,
        group_id="wiki-batch-archiver-group",
        auto_offset_reset='latest',
        value_deserializer=lambda x: json.loads(x.decode('utf-8'))
    )

    buffer = []
    BATCH_SIZE = 5000 # Buffer 5000 events before write
    TIMEOUT_SEC = 60  # Or write every 60 seconds
    last_flush_time = datetime.now()

    logger.info("📥 Waiting for events...")
    
    for message in consumer:
        buffer.append(message.value)
        
        # Check buffer limits
        time_diff = (datetime.now() - last_flush_time).total_seconds()
        
        if len(buffer) >= BATCH_SIZE or (time_diff > TIMEOUT_SEC and len(buffer) > 0):
            logger.info(f"📦 Buffering threshold reached ({len(buffer)} events). Flushing to S3...")
            
            # Create DataFrame
            df = pd.DataFrame(buffer)
            
            # Upload
            upload_to_s3(df, settings.s3.bucket_name, "raw_data/year=2026/month=01")
            
            # Reset
            buffer = []
            last_flush_time = datetime.now()

if __name__ == "__main__":
    main()
