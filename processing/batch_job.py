"""
Batch Processing Job (Batch Layer)
Processes historical data from Data Lake for deep analytics

This job runs periodically to:
1. Read raw events from Data Lake (Parquet)
2. Perform complex aggregations
3. Generate historical insights
4. Write results back to Postgres for historical dashboards
"""
import os
import logging
from datetime import datetime, timedelta
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import (
    col, count, sum as spark_sum, avg, max as spark_max, min as spark_min,
    hour, dayofweek, date_format, desc, row_number, percent_rank, date_trunc
)
from pyspark.sql.window import Window

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import get_settings

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WikiBatchProcessor:
    """
    Batch Processor for Historical Wikipedia Data
    Implements Lambda Architecture Batch Layer
    """
    
    def __init__(self):
        """Initialize batch processor"""
        self.settings = get_settings()
        self.spark: SparkSession = None
        
    def _create_spark_session(self) -> SparkSession:
        """Create Spark session for batch processing"""
        spark_version = "3.5.1"
        scala_version = "2.12"
        hadoop_version = "3.3.4"
        
        # Add hadoop-aws for S3 support
        packages = self.settings.spark.get_packages(spark_version, scala_version)
        packages += f",org.apache.hadoop:hadoop-aws:{hadoop_version}"
        packages += f",com.amazonaws:aws-java-sdk-bundle:1.12.262"
        
        os.environ['PYSPARK_SUBMIT_ARGS'] = f'--packages {packages} pyspark-shell'
        
        builder = (
            SparkSession.builder
            .appName(self.settings.spark.app_name + "-Batch")
            .master(self.settings.spark.master)
            .config("spark.sql.adaptive.enabled", "true")
            .config("spark.sql.adaptive.coalescePartitions.enabled", "true")
            .config("spark.sql.shuffle.partitions", "200")
        )
        
        # Configure S3 access
        builder = builder.config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        builder = builder.config("spark.hadoop.fs.s3a.aws.credentials.provider", 
                                "com.amazonaws.auth.InstanceProfileCredentialsProvider,com.amazonaws.auth.DefaultAWSCredentialsProviderChain")
        
        # If explicit credentials provided
        if self.settings.s3.access_key:
            builder = builder.config("spark.hadoop.fs.s3a.access.key", self.settings.s3.access_key)
            builder = builder.config("spark.hadoop.fs.s3a.secret.key", self.settings.s3.secret_key)
        
        spark = builder.getOrCreate()
        
        spark.sparkContext.setLogLevel(self.settings.spark.log_level)
        logger.info("✅ Spark Session created for batch processing")
        return spark
    
    def _read_datalake(self, days_back: int = 7) -> DataFrame:
        """
        Read data from Data Lake
        
        Args:
            days_back: Number of days of historical data to process
        """
        data_path = f"{self.settings.spark.data_lake_path}/raw_events"
        
        logger.info(f"📂 Reading data from: {data_path}")
        logger.info(f"   Time range: Last {days_back} days")
        
        try:
            df = self.spark.read.parquet(data_path)
            
            # Filter by date if needed
            if days_back > 0:
                cutoff_date = datetime.now() - timedelta(days=days_back)
                df = df.filter(col("event_time") >= cutoff_date)
            
            record_count = df.count()
            logger.info(f"✅ Loaded {record_count:,} records from Data Lake")
            return df
            
        except Exception as e:
            logger.error(f"❌ Error reading from Data Lake: {e}")
            raise
    
    def _calculate_hourly_patterns(self, df: DataFrame) -> DataFrame:
        """Hourly aggregation (time series, not just 0-23 buckets)."""
        logger.info("📊 Calculating hourly activity patterns (time series)...")

        hourly_stats = (
            df.withColumn("hour_bucket", date_trunc("hour", col("event_time")))
            .groupBy("hour_bucket")
            .agg(
                count("*").alias("total_events"),
                spark_sum("bytes_changed").alias("total_bytes"),
                avg("bytes_changed").alias("avg_bytes"),
                count(col("is_bot") == True).alias("bot_events"),
                count(col("is_bot") == False).alias("human_events"),
            )
            .orderBy("hour_bucket")
        )

        return hourly_stats
    
    def _calculate_top_contributors(self, df: DataFrame, top_n: int = 100) -> DataFrame:
        """
        Identify most active users/bots
        """
        logger.info(f"👥 Calculating top {top_n} contributors...")
        
        contributors = (
            df.groupBy("user", "is_bot")
            .agg(
                count("*").alias("edit_count"),
                spark_sum("bytes_changed").alias("total_bytes"),
                count(col("is_new_page") == True).alias("pages_created")
            )
            .orderBy(desc("edit_count"))
            .limit(top_n)
        )
        
        return contributors
    
    def _calculate_language_distribution(self, df: DataFrame) -> DataFrame:
        """
        Analyze edit distribution across languages/wikis
        """
        logger.info("🌍 Calculating language distribution...")
        
        lang_stats = (
            df.groupBy("language", "project")
            .agg(
                count("*").alias("edit_count"),
                spark_sum("bytes_changed").alias("total_bytes"),
                count(col("is_bot") == True).alias("bot_edits"),
                count(col("is_new_page") == True).alias("new_pages")
            )
            .orderBy(desc("edit_count"))
        )
        
        return lang_stats
    
    def _calculate_hourly_trends(self, df: DataFrame) -> DataFrame:
        """Hourly trends with 24-hour moving average."""
        logger.info("📈 Calculating hourly trends...")

        hourly_trends = (
            df.withColumn("hour_bucket", date_trunc("hour", col("event_time")))
            .groupBy("hour_bucket")
            .agg(
                count("*").alias("total_events"),
                spark_sum("bytes_changed").alias("total_bytes"),
                count(col("is_bot") == True).alias("bot_count"),
                count(col("type") == "new").alias("new_pages"),
                count(col("type") == "edit").alias("edits"),
            )
            .orderBy("hour_bucket")
        )

        window_spec = Window.orderBy("hour_bucket").rowsBetween(-23, 0)

        hourly_with_ma = hourly_trends.withColumn(
            "events_24h_avg",
            avg("total_events").over(window_spec)
        ).withColumn(
            "bytes_24h_avg",
            avg("total_bytes").over(window_spec)
        )

        return hourly_with_ma
    
    def _calculate_server_rankings(self, df: DataFrame, top_n: int = 50) -> DataFrame:
        """
        Rank wikis by activity and calculate percentiles
        """
        logger.info(f"🏆 Calculating top {top_n} server rankings...")
        
        server_stats = (
            df.groupBy("server_name", "language", "project")
            .agg(
                count("*").alias("edit_count"),
                spark_sum("bytes_changed").alias("total_bytes"),
                count("user").distinct().alias("unique_users")
            )
        )
        
        # Add percentile rankings
        window_spec = Window.orderBy(desc("edit_count"))
        
        ranked = server_stats.withColumn(
            "rank",
            row_number().over(window_spec)
        ).withColumn(
            "percentile",
            percent_rank().over(window_spec)
        ).filter(col("rank") <= top_n)
        
        return ranked
    
    def _write_to_postgres(self, df: DataFrame, table_name: str):
        """Write DataFrame to PostgreSQL"""
        logger.info(f"💾 Writing to PostgreSQL table: {table_name}")
        
        try:
            df.write \
                .format("jdbc") \
                .option("url", self.settings.postgres.jdbc_url) \
                .option("dbtable", table_name) \
                .option("user", self.settings.postgres.user) \
                .option("password", self.settings.postgres.password) \
                .option("driver", "org.postgresql.Driver") \
                .mode("overwrite") \
                .save()
            
            count = df.count()
            logger.info(f"✅ Wrote {count:,} records to {table_name}")
        except Exception as e:
            logger.error(f"❌ Error writing to {table_name}: {e}")
            raise
    
    def run(self, days_back: int = 7):
        """
        Run batch processing job
        
        Args:
            days_back: Number of days of historical data to process
        """
        logger.info("="*80)
        logger.info("🚀 Starting Wiki Batch Processor (Lambda Architecture - Batch Layer)")
        logger.info(f"   Processing last {days_back} days of data")
        logger.info(f"   Data Lake: {self.settings.spark.data_lake_path}")
        logger.info(f"   Target DB: {self.settings.postgres.jdbc_url}")
        logger.info("="*80)
        
        try:
            # Initialize Spark
            self.spark = self._create_spark_session()
            
            # Read data from Data Lake
            events_df = self._read_datalake(days_back)
            
            # Calculate all analytics
            analytics = {
                "hourly_patterns": self._calculate_hourly_patterns(events_df),
                "hourly_trends": self._calculate_hourly_trends(events_df),
                "top_contributors": self._calculate_top_contributors(events_df),
                "language_distribution": self._calculate_language_distribution(events_df),
                "server_rankings": self._calculate_server_rankings(events_df),
            }
            
            # Write results to Postgres
            logger.info("\n" + "="*80)
            logger.info("💾 Writing results to PostgreSQL...")
            logger.info("="*80)
            
            for name, df in analytics.items():
                table_name = f"historical_{name}"
                self._write_to_postgres(df, table_name)
            
            logger.info("\n" + "="*80)
            logger.info("✅ Batch processing completed successfully!")
            logger.info("="*80)
            
        except Exception as e:
            logger.error(f"❌ Batch processing failed: {e}")
            raise
        finally:
            if self.spark:
                self.spark.stop()
                logger.info("🛑 Spark session stopped")


def main():
    """Entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Wiki Batch Processor")
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="Number of days of historical data to process (default: 1)"
    )
    
    args = parser.parse_args()
    
    processor = WikiBatchProcessor()
    processor.run(days_back=args.days)


if __name__ == "__main__":
    main()
