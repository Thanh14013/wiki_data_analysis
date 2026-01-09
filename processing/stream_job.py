"""
Real-Time Stream Processing Job (Speed Layer)
Implements Lambda Architecture with advanced analytics

Metrics Calculated:
1. Traffic Volume - Total bytes changed over time
2. User Type Distribution - Bot vs Human ratio
3. Action Breakdown - Edit/New/Log distribution
4. Geolocation/Server - Top active Wiki servers
5. Content Velocity - Events per second
"""
import os
import logging
from typing import Optional
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import (
    from_json, col, window, count, sum as spark_sum, avg,
    to_timestamp, current_timestamp, expr, when, lit
)

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import get_settings
from processing.schemas import ANALYTICS_SCHEMA

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WikiStreamProcessor:
    """
    Real-time Stream Processor for Wikipedia Changes
    Implements Lambda Architecture Speed Layer
    """
    
    def __init__(self, mode: str = "both"):
        """
        Initialize stream processor
        
        Args:
            mode: 'postgres' (dashboard), 'datalake' (historical), or 'both'
        """
        self.settings = get_settings()
        self.mode = mode
        self.spark: Optional[SparkSession] = None
        
    def _create_spark_session(self) -> SparkSession:
        """Create and configure Spark session"""
        spark_version = "3.5.1"
        scala_version = "2.12"
        
        packages = self.settings.spark.packages
        
        os.environ['PYSPARK_SUBMIT_ARGS'] = f'--packages {packages} pyspark-shell'
        
        spark = (
            SparkSession.builder
            .appName(self.settings.spark.app_name + "-Stream")
            .master(self.settings.spark.master)
            .config("spark.sql.streaming.checkpointLocation", self.settings.spark.checkpoint_path)
            .config("spark.sql.adaptive.enabled", "true")
            .config("spark.sql.adaptive.coalescePartitions.enabled", "true")
            .config("spark.sql.shuffle.partitions", "1")  # Optimized for Minikube
            .getOrCreate()
        )
        
        spark.sparkContext.setLogLevel(self.settings.spark.log_level)
        logger.info("✅ Spark Session created successfully")
        return spark
    
    def _read_kafka_stream(self) -> DataFrame:
        """Read streaming data from Kafka"""
        logger.info(f"📡 Connecting to Kafka: {self.settings.kafka.bootstrap_servers}")
        
        return (
            self.spark.readStream
            .format("kafka")
            .option("kafka.bootstrap.servers", self.settings.kafka.bootstrap_servers)
            .option("subscribe", self.settings.kafka.topic_name)
            .option("startingOffsets", "latest")
            .option("maxOffsetsPerTrigger", 10000)  # Rate limiting
            .option("failOnDataLoss", "false")
            .load()
        )
    
    def _parse_events(self, kafka_df: DataFrame) -> DataFrame:
        """Parse JSON events and add timestamp"""
        parsed_df = (
            kafka_df
            .select(from_json(col("value").cast("string"), ANALYTICS_SCHEMA).alias("data"))
            .select("data.*")
        )
        
        # Convert Unix timestamp to Spark timestamp
        clean_df = (
            parsed_df
            .withColumn("event_time", to_timestamp(col("timestamp")))
            .withColumn("processing_time", current_timestamp())
            .filter(col("event_time").isNotNull())
        )
        
        logger.info("✅ Event parsing configured")
        return clean_df
    
    def _calculate_metrics(self, events_df: DataFrame) -> dict:
        """
        Calculate all 5 advanced metrics
        Returns dictionary of DataFrames for each metric
        """
        
        # Apply watermark for late data handling
        events_with_watermark = events_df.withWatermark("event_time", self.settings.spark.watermark_delay)
        
        # ===== METRIC 1: Traffic Volume (Bytes Changed Over Time) =====
        traffic_volume = (
            events_with_watermark
            .groupBy(window(col("event_time"), self.settings.spark.window_duration))
            .agg(
                spark_sum("bytes_changed").alias("total_bytes"),
                count("*").alias("event_count"),
                avg("bytes_changed").alias("avg_bytes_per_event")
            )
            .select(
                col("window.start").alias("window_start"),
                col("window.end").alias("window_end"),
                col("total_bytes"),
                col("event_count"),
                col("avg_bytes_per_event")
            )
            .withColumn("metric_type", lit("traffic_volume"))
        )
        
        # ===== METRIC 2: User Type Distribution (Bot vs Human) =====
        user_type_dist = (
            events_with_watermark
            .groupBy(
                window(col("event_time"), self.settings.spark.window_duration),
                col("is_bot")
            )
            .agg(count("*").alias("user_count"))
            .select(
                col("window.start").alias("window_start"),
                col("window.end").alias("window_end"),
                when(col("is_bot"), "bot").otherwise("human").alias("user_type"),
                col("user_count")
            )
            .withColumn("metric_type", lit("user_distribution"))
        )
        
        # ===== METRIC 3: Action Breakdown (Edit/New/Log) =====
        action_breakdown = (
            events_with_watermark
            .groupBy(
                window(col("event_time"), self.settings.spark.window_duration),
                col("type")
            )
            .agg(count("*").alias("action_count"))
            .select(
                col("window.start").alias("window_start"),
                col("window.end").alias("window_end"),
                col("type").alias("action_type"),
                col("action_count")
            )
            .withColumn("metric_type", lit("action_breakdown"))
        )
        
        # ===== METRIC 4: Geolocation/Server (Top Wiki Servers) =====
        server_activity = (
            events_with_watermark
            .groupBy(
                window(col("event_time"), self.settings.spark.window_duration),
                col("server_name"),
                col("language"),
                col("project")
            )
            .agg(
                count("*").alias("edit_count"),
                spark_sum("bytes_changed").alias("total_bytes")
            )
            .select(
                col("window.start").alias("window_start"),
                col("window.end").alias("window_end"),
                col("server_name"),
                col("language"),
                col("project"),
                col("edit_count"),
                col("total_bytes")
            )
            .withColumn("metric_type", lit("server_activity"))
        )
        
        # ===== METRIC 5: Content Velocity (Events/sec) =====
        # Calculate events per second within each window
        content_velocity = (
            events_with_watermark
            .groupBy(window(col("event_time"), self.settings.spark.window_duration))
            .agg(
                count("*").alias("event_count")
            )
            .select(
                col("window.start").alias("window_start"),
                col("window.end").alias("window_end"),
                col("event_count"),
                # Calculate events per second (window is 1 minute = 60 seconds)
                (col("event_count") / 60.0).alias("events_per_second")
            )
            .withColumn("metric_type", lit("content_velocity"))
        )
        
        # ===== METRIC 6: Content Leaderboard (Most Edited Pages) =====
        content_leaderboard = (
            events_with_watermark
            .groupBy(
                window(col("event_time"), self.settings.spark.window_duration),
                col("title"),
                col("server_name")
            )
            .agg(
                count("*").alias("edit_count"),
                spark_sum("bytes_changed").alias("total_bytes")
            )
            .select(
                col("window.start").alias("window_start"),
                col("window.end").alias("window_end"),
                col("title"),
                col("server_name"),
                col("edit_count"),
                col("total_bytes")
            )
            .withColumn("metric_type", lit("content_leaderboard"))
        )
        
        # ===== METRIC 7: Edits Severity (Major vs Minor) =====
        edits_severity = (
            events_with_watermark
            .groupBy(
                window(col("event_time"), self.settings.spark.window_duration),
                col("is_minor")
            )
            .agg(count("*").alias("count"))
            .select(
                col("window.start").alias("window_start"),
                col("window.end").alias("window_end"),
                when(col("is_minor"), "minor").otherwise("major").alias("edit_type"),
                col("count")
            )
            .withColumn("metric_type", lit("edits_severity"))
        )

        # ===== METRIC 8: Content Volume Change (Additions vs Deletions) =====
        # Calculate length diff: new - old
        volume_change = (
            events_with_watermark
            .withColumn("length_diff", col("length.new") - col("length.old"))
            .groupBy(
                window(col("event_time"), self.settings.spark.window_duration),
                when(col("length_diff") > 0, "addition")
                .when(col("length_diff") < 0, "deletion")
                .otherwise("no_change").alias("change_type")
            )
            .agg(
                spark_sum(expr("abs(length_diff)")).alias("total_bytes"),
                count("*").alias("count")
            )
            .filter(col("change_type") != "no_change")
            .select(
                col("window.start").alias("window_start"),
                col("window.end").alias("window_end"),
                col("change_type"),
                col("total_bytes"),
                col("count")
            )
            .withColumn("metric_type", lit("content_volume_change"))
        )

        # ===== METRIC 9: Namespace Distribution =====
        namespace_dist = (
            events_with_watermark
            .groupBy(
                window(col("event_time"), self.settings.spark.window_duration),
                col("namespace")
            )
            .agg(count("*").alias("count"))
            .select(
                col("window.start").alias("window_start"),
                col("window.end").alias("window_end"),
                col("namespace"),
                col("count")
            )
            .withColumn("metric_type", lit("namespace_distribution"))
        )

        # ===== METRIC 10: Language Breakdown =====
        language_dist = (
            events_with_watermark
            .groupBy(
                window(col("event_time"), self.settings.spark.window_duration),
                col("language")
            )
            .agg(
                count("*").alias("count"),
                spark_sum("bytes_changed").alias("total_bytes")
            )
            .select(
                col("window.start").alias("window_start"),
                col("window.end").alias("window_end"),
                col("language"),
                col("count"),
                col("total_bytes")
            )
            .withColumn("metric_type", lit("language_breakdown"))
        )

        # ===== METRIC 11: Meticulous Users (Histogram Data) =====
        user_stats = (
            events_with_watermark
            .groupBy(
                window(col("event_time"), self.settings.spark.window_duration),
                col("user"),
                col("is_bot")
            )
            .agg(count("*").alias("edit_count"))
            .select(
                col("window.start").alias("window_start"),
                col("window.end").alias("window_end"),
                col("user"),
                col("is_bot"),
                col("edit_count")
            )
            .withColumn("metric_type", lit("user_stats"))
        )

        # ===== METRIC 12: Recent Changes (Raw Feed for Battlefield/Blacklist) =====
        # No aggregation, just selecting relevant columns
        recent_changes = (
            events_with_watermark
            .select(
                col("timestamp"),
                col("event_time"),
                col("user"),
                col("title"),
                col("server_name"),
                col("is_bot"),
                col("type"),
                col("bytes_changed"),
                (col("length.new") - col("length.old")).alias("length_diff")
            )
            .withColumn("metric_type", lit("recent_changes"))
        )
        
        return {
            "traffic_volume": traffic_volume,
            "user_distribution": user_type_dist,
            "action_breakdown": action_breakdown,
            "server_activity": server_activity,
            "content_velocity": content_velocity,
            "content_leaderboard": content_leaderboard,
            "edits_severity": edits_severity,
            "content_volume_change": volume_change,
            "namespace_distribution": namespace_dist,
            "language_breakdown": language_dist,
            "user_stats": user_stats,
            "recent_changes": recent_changes
        }
    
    def _write_to_postgres(self, df: DataFrame, table_name: str):
        """Write DataFrame to PostgreSQL"""
        def write_batch(batch_df, epoch_id):
            if batch_df.isEmpty():
                logger.info(f"⏭️  Epoch {epoch_id}: No data to write to {table_name}")
                return
            
            try:
                batch_df.write \
                    .format("jdbc") \
                    .option("url", self.settings.postgres.jdbc_url) \
                    .option("dbtable", table_name) \
                    .option("user", self.settings.postgres.user) \
                    .option("password", self.settings.postgres.password) \
                    .option("driver", "org.postgresql.Driver") \
                    .mode("append") \
                    .save()
                
                count = batch_df.count()
                logger.info(f"✅ Epoch {epoch_id}: Wrote {count} records to {table_name}")
            except Exception as e:
                logger.error(f"❌ Error writing to {table_name}: {e}")
        
        return write_batch
    
    def _write_to_datalake(self, df: DataFrame, path_suffix: str, partition_col: str = "window_start"):
        """Write DataFrame to Data Lake (Parquet)"""
        output_path = f"{self.settings.spark.data_lake_path}/{path_suffix}"
        checkpoint_path = f"{self.settings.spark.checkpoint_path}/{path_suffix}"
        
        return (
            df.writeStream
            .format("parquet")
            .option("path", output_path)
            .option("checkpointLocation", checkpoint_path)
            .partitionBy(partition_col)
            .outputMode("append")
        )
    
    def start(self):
        """Start the streaming job"""
        logger.info("="*80)
        logger.info("🚀 Starting Wiki Stream Processor (Lambda Architecture)")
        logger.info(f"   Mode: {self.mode.upper()}")
        logger.info(f"   Kafka: {self.settings.kafka.bootstrap_servers}")
        logger.info(f"   Topic: {self.settings.kafka.topic_name}")
        logger.info("="*80)
        
        self.spark = self._create_spark_session()
        queries = []
        
        # Read and parse stream
        kafka_stream = self._read_kafka_stream()
        
        # Read and parse stream
        kafka_stream = self._read_kafka_stream()
        
        events_df = self._parse_events(kafka_stream)
        
        # Calculate all metrics
        metrics = self._calculate_metrics(events_df)
        
        # Start streaming queries based on mode
        
        if self.mode in ["postgres", "both"]:
            logger.info("📊 Starting Postgres writers (Real-time Dashboard)...")
            
            for metric_name, metric_df in metrics.items():
                table_name = f"realtime_{metric_name}"
                query = (
                    metric_df.writeStream
                    .outputMode("update")
                    .foreachBatch(self._write_to_postgres(metric_df, table_name))
                    .trigger(processingTime=self.settings.spark.trigger_interval)
                    .start()
                )
                queries.append(query)
                logger.info(f"   ✅ {metric_name} -> {table_name}")
        
        if self.mode in ["datalake", "both"]:
            logger.info("💾 Starting Data Lake writers (Historical Storage)...")
            
            # Write raw events to data lake
            raw_query = (
                events_df.writeStream
                .format("parquet")
                .option("path", f"{self.settings.spark.data_lake_path}/raw_events")
                .option("checkpointLocation", f"{self.settings.spark.checkpoint_path}/raw_events")
                .partitionBy("event_time")
                .outputMode("append")
                .trigger(processingTime=self.settings.spark.trigger_interval)
                .start()
            )
            queries.append(raw_query)
            logger.info("   ✅ raw_events -> Data Lake")
            
            # Write aggregated metrics
            for metric_name, metric_df in metrics.items():
                partition_col = "window_start"
                if metric_name == "recent_changes":
                    partition_col = "event_time"
                    
                query = self._write_to_datalake(metric_df, f"metrics/{metric_name}", partition_col).start()
                queries.append(query)
                logger.info(f"   ✅ {metric_name} -> Data Lake")
        
        logger.info("="*80)
        logger.info("✅ All streaming queries started successfully!")
        logger.info("   Press Ctrl+C to stop...")
        logger.info("="*80)
        
        # Wait for all queries
        try:
            for query in queries:
                query.awaitTermination()
        except KeyboardInterrupt:
            logger.info("\n🛑 Stopping all queries...")
            for query in queries:
                query.stop()
            logger.info("✅ All queries stopped")
        finally:
            if self.spark:
                self.spark.stop()


def main():
    """Entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Wiki Stream Processor")
    parser.add_argument(
        "--mode",
        choices=["postgres", "datalake", "both"],
        default="both",
        help="Output mode: postgres (dashboard), datalake (historical), or both"
    )
    
    args = parser.parse_args()
    
    processor = WikiStreamProcessor(mode=args.mode)
    processor.start()


if __name__ == "__main__":
    main()
