import os
import sys
import logging
import psycopg2

# Add parent directory to path to import config
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import get_settings

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DB_Init")

def create_tables():
    settings = get_settings()
    
    try:
        # Connect to Database
        logger.info(f"Connecting to database: {settings.postgres.host}...")
        conn = psycopg2.connect(settings.postgres.connection_string)
        conn.autocommit = True
        cursor = conn.cursor()
        
        # 1. realtime_traffic_volume
        logger.info("Creating table: realtime_traffic_volume")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS realtime_traffic_volume (
                window_start TIMESTAMP,
                total_bytes BIGINT,
                event_count INT,
                avg_bytes_per_event FLOAT GENERATED ALWAYS AS (
                    CASE WHEN event_count > 0 THEN total_bytes::FLOAT / event_count ELSE 0 END
                ) STORED
            );
        """)
        
        # 2. realtime_recent_changes
        logger.info("Creating table: realtime_recent_changes")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS realtime_recent_changes (
                event_time TIMESTAMP,
                "user" TEXT,
                title TEXT,
                server_name TEXT,
                is_bot BOOLEAN,
                type TEXT,
                bytes_changed BIGINT,
                length_diff INT
            );
        """)

        # Add indexes for Dashboard performance
        logger.info("Creating indexes...")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_traffic_window ON realtime_traffic_volume(window_start);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_changes_time ON realtime_recent_changes(event_time);")
        
        logger.info("✅ Database initialized successfully!")
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize database: {e}")
        sys.exit(1)
    finally:
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == "__main__":
    create_tables()
