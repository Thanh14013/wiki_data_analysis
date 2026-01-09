"""
Centralized Schema Definitions for Wikimedia Events
Defines the structure of Wikipedia change events
"""
from pyspark.sql.types import (
    StructType, StructField, StringType, BooleanType, 
    LongType, IntegerType, MapType, ArrayType
)


class WikiEventSchema:
    """
    Complete schema for Wikimedia Recent Changes events
    Based on: https://stream.wikimedia.org/v2/stream/recentchange
    """
    
    @staticmethod
    def get_full_schema() -> StructType:
        """
        Full schema with all available fields from Wikimedia stream
        Use this for Data Lake ingestion (raw data)
        """
        return StructType([
            # Core identifiers
            StructField("id", LongType(), True),
            StructField("type", StringType(), True),  # edit, new, log, categorize
            StructField("namespace", IntegerType(), True),
            StructField("title", StringType(), True),
            StructField("comment", StringType(), True),
            StructField("timestamp", LongType(), True),  # Unix timestamp
            
            # User information
            StructField("user", StringType(), True),
            StructField("bot", BooleanType(), True),
            StructField("minor", BooleanType(), True),
            
            # Server/wiki information
            StructField("server_name", StringType(), True),  # e.g., en.wikipedia.org
            StructField("server_url", StringType(), True),
            StructField("wiki", StringType(), True),
            
            # Page information
            StructField("title_url", StringType(), True),
            StructField("parsedcomment", StringType(), True),
            
            # Change details
            StructField("length", StructType([
                StructField("old", IntegerType(), True),
                StructField("new", IntegerType(), True)
            ]), True),
            
            StructField("revision", StructType([
                StructField("old", LongType(), True),
                StructField("new", LongType(), True)
            ]), True),
            
            # Metadata
            StructField("meta", StructType([
                StructField("uri", StringType(), True),
                StructField("request_id", StringType(), True),
                StructField("id", StringType(), True),
                StructField("dt", StringType(), True),  # ISO timestamp
                StructField("domain", StringType(), True),
                StructField("stream", StringType(), True),
                StructField("topic", StringType(), True),
                StructField("partition", IntegerType(), True),
                StructField("offset", LongType(), True)
            ]), True),
            
            # Log-specific fields (for type='log')
            StructField("log_id", LongType(), True),
            StructField("log_type", StringType(), True),
            StructField("log_action", StringType(), True),
            StructField("log_params", MapType(StringType(), StringType()), True),
            
            # Patrolled status
            StructField("patrolled", BooleanType(), True),
            
            # Enriched fields (added by producer)
            StructField("is_bot", BooleanType(), True),
            StructField("is_minor", BooleanType(), True),
            StructField("is_new_page", BooleanType(), True),
            StructField("bytes_changed", IntegerType(), True),
            StructField("language", StringType(), True),
            StructField("project", StringType(), True)
        ])
    
    @staticmethod
    def get_analytics_schema() -> StructType:
        """
        Simplified schema for real-time analytics
        Contains only essential fields needed for dashboard metrics
        """
        return StructType([
            # Essential identifiers
            StructField("timestamp", LongType(), True),
            StructField("type", StringType(), True),
            StructField("user", StringType(), True),
            StructField("server_name", StringType(), True),
            StructField("title", StringType(), True),
            StructField("namespace", IntegerType(), True),
            
            # Flags
            StructField("bot", BooleanType(), True),
            StructField("is_bot", BooleanType(), True),
            StructField("is_minor", BooleanType(), True),
            StructField("is_new_page", BooleanType(), True),
            
            # Metrics
            StructField("bytes_changed", IntegerType(), True),
            
            # Geo/Project info
            StructField("language", StringType(), True),
            StructField("project", StringType(), True),
            
            # Change details (nested)
            StructField("length", StructType([
                StructField("old", IntegerType(), True),
                StructField("new", IntegerType(), True)
            ]), True)
        ])
    
    @staticmethod
    def get_minimal_schema() -> StructType:
        """
        Minimal schema for initial testing
        """
        return StructType([
            StructField("user", StringType(), True),
            StructField("bot", BooleanType(), True),
            StructField("type", StringType(), True),
            StructField("server_name", StringType(), True),
            StructField("timestamp", LongType(), True)
        ])


# For convenience - commonly used schemas
FULL_SCHEMA = WikiEventSchema.get_full_schema()
ANALYTICS_SCHEMA = WikiEventSchema.get_analytics_schema()
MINIMAL_SCHEMA = WikiEventSchema.get_minimal_schema()
