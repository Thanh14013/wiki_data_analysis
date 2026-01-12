import os
import json
import logging
from datetime import timedelta
from collections import defaultdict
import psycopg2
from psycopg2.extras import execute_values
from quixstreams import Application

# Add parent directory to path
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import get_settings

# Logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("QuixJob")

settings = get_settings()

def get_db_connection():
    """Establish connection to PostgreSQL (RDS)"""
    try:
        conn = psycopg2.connect(settings.postgres.connection_string)
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to DB: {e}")
        return None

def write_to_postgres(table_name, columns, data):
    """Utility to write batch data to Postgres"""
    if not data:
        return
    
    conn = get_db_connection()
    if not conn:
        return

    try:
        cursor = conn.cursor()
        # Create table if not exists (Simplified schema for example)
        # In prod, use migration scripts (Flyway/Liquibase)
        # columns_def = ", ".join([f"{c} TEXT" for c in columns]) 
        # cursor.execute(f"CREATE TABLE IF NOT EXISTS {table_name} (recorded_at TIMESTAMP DEFAULT NOW(), {columns_def})")
        
        # Prepare INSERT statement
        cols_str = ",".join(columns)

        
        query = f"INSERT INTO {table_name} ({cols_str}) VALUES %s"
        
        execute_values(cursor, query, data)
        conn.commit()
        logger.info(f"✅ Wrote {len(data)} records to {table_name}")
        
    except Exception as e:
        logger.error(f"❌ DB Write Error ({table_name}): {e}")
        conn.rollback()
    finally:
        conn.close()

def main():
    logger.info("🚀 Starting Quix Stream Processing Job...")

    # 1. Initialize Quix Application
    app = Application(
        broker_address=settings.kafka.bootstrap_servers,
        consumer_group=settings.kafka.consumer_group,
        auto_offset_reset="latest",
        # security_protocol="PLAINTEXT" # For Internal Redpanda (No SSL) - Removed to fix TypeError
    )

    # 2. Define Topic
    input_topic = app.topic(settings.kafka.topic_name, value_deserializer="json")

    # 3. Define Streaming DataFrame
    sdf = app.dataframe(input_topic)

    # --- Processing Logic (Simplification of Spark Logic for Quix) ---
    # Quix streams 2.0 uses 'TumplingWindow' mechanism
    
    # Example 1: Traffic Volume (10s window)
    # count() and sum() are methods on Windowed Streaming DataFrame
    
    def sink_traffic_volume(result):
        # Result is a dictionary with window_start, window_end, value
        # Make sure result format matches what quix produces
        # For now, let's just log it to verify
        logger.info(f"📈 Traffic Volume: {result}")
        # In real impl: Parse result --> write_to_postgres('realtime_traffic', ...)

    # Note: Quix Streams API is rapidly evolving. 
    # For this robust migration plan, we will keep it simple: 
    # Read message -> Buffer in memory -> Flush to DB every N records (Micro-batching manually)
    # This ensures 100% control over the logic without complexity of Window state management in pure Python if stateless.

    # HOWEVER, Quix is stateful. Let's use the native aggregation if possible.
    # But for simplicity & reliability given 100$ context, let's use a "Process & Aggregate" function.

    buffer = defaultdict(list)
    BATCH_SIZE = 100

    with app.get_consumer() as consumer:
        consumer.subscribe([settings.kafka.topic_name])
        
        logger.info("Listening for messages...")
        
        traffic_data = [] # List of tuples
        recent_changes_data = [] # List of tuples
        
        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                logger.error(f"Consumer error: {msg.error()}")
                continue

            try:
                # Parse JSON
                event = json.loads(msg.value().decode('utf-8'))
                
                # --- Metrics Calculation (In-memory Micro-batch) ---
                
                # 1. Traffic Volume Data
                traffic_data.append((
                    event.get('timestamp'), 
                    event.get('bytes_changed', 0)
                ))

                # 2. Recent Changes Data (Raw Feed)
                # Schema: event_time, user, title, server_name, is_bot, type, bytes_changed, length_diff
                # We need to calculate length_diff = length.new - length.old
                length_new = event.get('length', {}).get('new', 0) or 0
                length_old = event.get('length', {}).get('old', 0) or 0
                length_diff = length_new - length_old
                
                recent_changes_data.append((
                    datetime.datetime.fromtimestamp(event.get('timestamp', 0)), # event_time
                    event.get('user', 'unknown'),
                    event.get('title', 'unknown'),
                    event.get('server_name', 'unknown'),
                    event.get('bot', False), # is_bot
                    event.get('type', 'edit'),
                    event.get('bytes_changed', 0),
                    length_diff
                ))

                # Flush if Batch Size met
                if len(traffic_data) >= BATCH_SIZE:
                    # A. Process Traffic Volume
                    total_bytes = sum(x[1] for x in traffic_data)
                    count_traffic = len(traffic_data)
                    now = datetime.datetime.now()
                    
                    data_traffic = [(now, total_bytes, count_traffic)]
                    write_to_postgres("realtime_traffic_volume", ["window_start", "total_bytes", "event_count"], data_traffic)
                    
                    # B. Process Recent Changes
                    # Columns: event_time, user, title, server_name, is_bot, type, bytes_changed, length_diff
                    write_to_postgres(
                        "realtime_recent_changes", 
                        ["event_time", "\"user\"", "title", "server_name", "is_bot", "type", "bytes_changed", "length_diff"], 
                        recent_changes_data
                    )
                    
                    traffic_data = [] # Reset
                    recent_changes_data = [] # Reset

            except Exception as e:
                logger.error(f"Processing Error: {e}")
                
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Job stopped.")
