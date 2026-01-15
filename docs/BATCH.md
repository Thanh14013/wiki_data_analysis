# Batch Layer (Historical Analytics) - Technical Documentation

## 📊 Overview

Batch Layer xử lý dữ liệu historical từ Data Lake (S3) sử dụng Apache Spark, tạo ra deep analytics views cho long-term insights. Theo Lambda Architecture, layer này tối ưu cho **high accuracy**, **complex computations**, và **comprehensive analysis** hơn là low latency.

---

## 🏗️ Architecture Components

```
┌──────────┐     ┌─────────────────┐     ┌─────────────┐     ┌──────────────┐
│  Kafka   │────▶│ Batch Ingestion │────▶│ S3 Data Lake│────▶│Spark Processor│
│(Redpanda)│     │  (Archiver)     │     │  (Parquet)  │     │  (PySpark)   │
└──────────┘     └─────────────────┘     └─────────────┘     └──────┬───────┘
                         │                                            │
                    Buffer 5000                                  Analytics
                    events/60s                                        │
                                                                      ▼
                                                             ┌──────────────────┐
                                                             │  PostgreSQL RDS  │
                                                             │ Historical Tables│
                                                             └──────────────────┘
```

---

## 🔄 Component 1: Batch Ingestion (`ingestion/batch_job.py`)

**Vai trò**: Archive raw events từ Kafka vào S3 Data Lake dưới dạng Parquet files, làm nguồn dữ liệu cho Spark batch processing.

### A. Architecture Details

**Consumer Configuration:**
```python
Consumer Group: wiki-batch-archiver-group
Topic: wiki-raw-events
Auto Offset Reset: latest (chỉ lấy new data)
Deserializer: JSON
```

**Why separate consumer group?**
- Độc lập với Speed Layer (không ảnh hưởng lẫn nhau)
- Có thể reprocess từ đầu mà không ảnh hưởng real-time
- Kafka tracks offset riêng cho mỗi group

### B. Buffering Strategy

**Micro-batching approach:**
```python
BATCH_SIZE = 5000 events
TIMEOUT_SEC = 60 seconds

Trigger conditions (OR logic):
1. Buffer reaches 5000 events → Flush immediately
2. 60 seconds passed since last flush → Flush current buffer

Purpose: Optimize S3 writes (giảm API calls, giảm chi phí)
```

**Example Timeline:**
```
T+0s:    Buffer = 0, start collecting
T+30s:   Buffer = 2500 events (chưa flush)
T+45s:   Buffer = 5000 events → FLUSH to S3
T+45.5s: Buffer reset, continue collecting
T+105s:  Buffer = 800 events, 60s timeout → FLUSH to S3
```

### C. Data Format & Schema

**Input (from Kafka):**
```json
{
  "timestamp": 1705334400,  // int64 epoch seconds
  "user": "John",
  "title": "Python (programming)",
  "server_name": "en.wikipedia.org",
  "type": "edit",
  "bytes_changed": 500,
  "is_bot": false,
  "is_new_page": false,
  "language": "en",
  "project": "wikipedia",
  "log_params": {"key": "value"},  // Mixed types handled
  ...
}
```

**Critical Type Handling:**
```python
# Problem: timestamp có thể là string hoặc int từ producer
# Solution: Force convert to int64 before buffering
if not isinstance(event['timestamp'], int):
    event['timestamp'] = int(event['timestamp'])

# Problem: log_params có thể là dict, list, hoặc string
# Solution: Normalize to JSON string
if isinstance(x, (dict, list)):
    return json.dumps(x, ensure_ascii=False)
```

**Output Format (Parquet):**
```
Compression: Snappy (fast compression/decompression)
Version: 2.6 (compatible với Spark 3.x)
Schema: Inferred from DataFrame
Encoding: Dictionary encoding for strings (automatic)
```

### D. S3 Storage Structure

**Partitioning Strategy:**
```
s3://wiki-data-lake-prod-1407/raw_data/raw_events/
├── year=2026/
│   ├── month=01/
│   │   ├── wiki_events_20260115_070916.parquet
│   │   ├── wiki_events_20260115_071420.parquet
│   │   ├── wiki_events_20260115_071520.parquet
│   │   └── ...
│   └── month=02/
│       └── ...
└── year=2027/
    └── ...
```

**Benefits của partitioning:**
- Spark có thể **partition pruning** (chỉ đọc data cần thiết)
- Query theo ngày/tháng rất nhanh
- Cleanup dễ dàng (xóa theo month)
- Tuân thủ Hive partitioning convention

**File naming convention:**
```
Format: wiki_events_{YYYYMMDD}_{HHMMSS}.parquet
Example: wiki_events_20260115_071420.parquet

Timestamp: UTC time khi file được tạo
Unique: Đảm bảo không overwrite
```

### E. Write Process

**Local vs S3:**

```python
if data_lake_path.startswith("s3://") or data_lake_path.startswith("s3a://"):
    # Production: S3 upload
    1. Convert DataFrame to PyArrow Table
    2. Write to in-memory buffer (BytesIO)
    3. Upload buffer to S3 via boto3
    4. Log success with full S3 path
else:
    # Development: Local filesystem
    1. Create directory structure
    2. Write Parquet directly to disk
    3. Log local path
```

**S3 Client Configuration:**
```python
# IAM Role on EC2 (Production - Recommended)
- Không cần access keys
- Automatic credential rotation
- Permissions managed centrally

# Explicit credentials (Development/Testing)
- AWS_ACCESS_KEY_ID
- AWS_SECRET_ACCESS_KEY
- Manual key rotation required
```

**Write Performance:**
```
File size: ~500KB - 5MB per file (5000 events)
Compression ratio: 5-10x (JSON → Parquet)
Write latency: 
  - Local: 50-200ms
  - S3: 500ms - 2s (network dependent)
Throughput: 2000-10000 events/second
```

### F. Error Handling & Reliability

**Retry Strategy:**
```python
# Kafka consumer auto-commit AFTER successful write
# If S3 write fails:
1. Log error with full traceback
2. Buffer is NOT cleared
3. Kafka offset NOT committed
4. Next poll will retry same events

Risk: Memory overflow nếu S3 down lâu
Mitigation: Container restart, offset manual reset
```

**Data Quality Checks:**
```python
# Before write:
1. DataFrame not empty
2. Schema validation (implicit in PyArrow)
3. Type consistency (timestamp as int64)

# After write:
1. Log record count
2. Verify S3 object exists (could be added)
```

**Monitoring Metrics:**
```
Success metrics:
- ✅ Uploaded N records to s3://bucket/path
- File count per hour
- Data volume written (MB/hour)

Failure metrics:
- ❌ S3 Upload Failed: {error}
- Failed write attempts
- Time since last successful write
```

---

## 🎯 Component 2: Batch Processor (`processing/batch_job.py`)

**Vai trò**: Đọc data từ S3 Data Lake, chạy complex analytics với Spark, ghi kết quả vào PostgreSQL historical tables.

### A. Spark Session Configuration

**Dependencies Management:**
```python
Spark Version: 3.5.1
Scala Version: 2.12
Hadoop Version: 3.3.4

Required JARs:
1. spark-sql-kafka-0-10_2.12:3.5.1  # Kafka integration
2. postgresql:42.6.0                  # JDBC driver
3. commons-pool2:2.11.1               # Connection pooling
4. hadoop-aws:3.3.4                   # S3 support
5. aws-java-sdk-bundle:1.12.262       # AWS SDK

Auto-download: Maven Central (first run takes 3-5 mins)
```

**Spark Configuration:**
```python
Master: local[*]  # Use all available cores
App Name: WikiDataPipeline-Batch

Optimizations:
- spark.sql.adaptive.enabled = true
  → Dynamic partition coalescing
  → Runtime query optimization
  
- spark.sql.adaptive.coalescePartitions.enabled = true
  → Reduce partitions after shuffle
  
- spark.sql.shuffle.partitions = 200
  → Default parallelism for joins/aggregations

Log Level: WARN (reduce noise)
```

**S3 Access Configuration:**
```python
# S3A FileSystem (Hadoop 3.x)
fs.s3a.impl = org.apache.hadoop.fs.s3a.S3AFileSystem

# Credentials Provider Chain
Priority:
1. Instance Profile (EC2 IAM Role) ← Recommended
2. Environment variables
3. Explicit config in code

# Performance tuning (could be added):
fs.s3a.connection.maximum = 100
fs.s3a.threads.max = 64
fs.s3a.fast.upload = true
```

### B. Data Reading Strategy

**Path Pattern:**
```python
# Before fix: s3a://.../raw_events (không tìm thấy data)
# After fix:  s3a://.../raw_events/*/* (wildcard partitions)

Pattern: year=*/month=*
Example matches:
- year=2026/month=01/*.parquet
- year=2026/month=02/*.parquet
- year=2027/month=01/*.parquet

basePath: s3a://.../raw_events
→ Spark tự động detect partition columns (year, month)
```

**Schema Handling:**
```python
.option("mergeSchema", "true")
→ Handle schema evolution
→ Merge schemas from multiple files
→ Add new columns as nullable

Example:
File 1: (timestamp, user, title)
File 2: (timestamp, user, title, new_column)
Result: All columns merged, new_column nullable
```

**Timestamp Conversion:**
```python
# Parquet has: timestamp as int64 (epoch seconds)
# Spark needs: timestamp as TimestampType

Convert:
df = df.withColumn("timestamp", 
                   col("timestamp").cast("timestamp"))

Purpose: Enable time-based operations:
- date_trunc("hour", timestamp)
- Filter by date ranges
- Window functions with time ordering
```

**Date Filtering:**
```python
days_back = 1  # Configurable parameter

Filter logic:
cutoff_date = datetime.now() - timedelta(days=days_back)
df = df.filter(col("timestamp") >= cutoff_date)

Purpose:
- Process only recent data
- Incremental processing (daily job)
- Reduce compute cost
```

### C. Analytics Computations

#### 1. **Hourly Patterns** (`historical_hourly_patterns`)

**Purpose**: Time-series của edit activity mỗi giờ

```python
Aggregation:
df.withColumn("hour_bucket", date_trunc("hour", col("timestamp")))
  .groupBy("hour_bucket")
  .agg(
      count("*").alias("total_events"),
      sum("bytes_changed").alias("total_bytes"),
      avg("bytes_changed").alias("avg_bytes"),
      count(col("is_bot") == True).alias("bot_events"),
      count(col("is_bot") == False).alias("human_events")
  )
  .orderBy("hour_bucket")

Output: 24-168 rows (1-7 days of hourly data)
```

**Use case**: Dashboard time-series chart

#### 2. **Hourly Trends** (`historical_hourly_trends`)

**Purpose**: Hourly metrics với 24-hour moving average

```python
Step 1: Calculate hourly aggregates
hourly_trends = df.groupBy(date_trunc("hour", "timestamp"))
                  .agg(total_events, total_bytes, bot_count, ...)

Step 2: Add moving averages
window_spec = Window.orderBy("hour_bucket").rowsBetween(-23, 0)

result = hourly_trends.withColumn(
    "events_24h_avg", avg("total_events").over(window_spec)
).withColumn(
    "bytes_24h_avg", avg("total_bytes").over(window_spec)
)

Window explanation:
- rowsBetween(-23, 0): Current row + previous 23 rows = 24 hours
- Sliding window for smoothing trends
```

**Use case**: Trend analysis với noise reduction

#### 3. **Top Contributors** (`historical_top_contributors`)

**Purpose**: Identify most active users/bots

```python
df.groupBy("user", "is_bot")
  .agg(
      count("*").alias("edit_count"),
      sum("bytes_changed").alias("total_bytes"),
      count(col("is_new_page") == True).alias("pages_created")
  )
  .orderBy(desc("edit_count"))
  .limit(100)

Output: Top 100 users ranked by edit count
```

**Use case**: Leaderboard, power user identification

#### 4. **Language Distribution** (`historical_language_distribution`)

**Purpose**: Edit activity across languages/projects

```python
df.groupBy("language", "project")
  .agg(
      count("*").alias("edit_count"),
      sum("bytes_changed").alias("total_bytes"),
      count(col("is_bot") == True).alias("bot_edits"),
      count(col("is_new_page") == True).alias("new_pages")
  )
  .orderBy(desc("edit_count"))

Output: ~50-200 rows (active language-project combinations)
```

**Use case**: Global activity heatmap, language comparison

#### 5. **Server Rankings** (`historical_server_rankings`)

**Purpose**: Rank wikis by activity với percentile scores

```python
Step 1: Aggregate by server
server_stats = df.groupBy("server_name", "language", "project")
                 .agg(
                     count("*").alias("edit_count"),
                     sum("bytes_changed").alias("total_bytes"),
                     countDistinct("user").alias("unique_users")
                 )

Step 2: Add rankings
window_spec = Window.orderBy(desc("edit_count"))

ranked = server_stats.withColumn("rank", row_number().over(window_spec))
                     .withColumn("percentile", percent_rank().over(window_spec))
                     .filter(col("rank") <= 50)

Output: Top 50 servers với rank và percentile
```

**Use case**: Server comparison, identify most active wikis

### D. Write to PostgreSQL

**JDBC Write Configuration:**
```python
df.write \
  .format("jdbc") \
  .option("url", "jdbc:postgresql://host:5432/db") \
  .option("dbtable", table_name) \
  .option("user", user) \
  .option("password", password) \
  .option("driver", "org.postgresql.Driver") \
  .mode("overwrite") \  # Replace existing data
  .save()
```

**Write Strategy:**
```
Mode: overwrite
→ Truncate table before insert
→ Historical tables are "views" not append logs
→ Always contain latest batch result

Alternative modes:
- append: Add to existing data (for incremental)
- ignore: Skip if table exists
- error: Fail if table exists (default)
```

**Performance:**
```
Parallelism: Spark partitions → JDBC connections
Default: 200 partitions (may be overkill)
Optimization: Coalesce to 1-10 partitions before write

Write speed: ~1000-10000 rows/second
Depends on:
- Network latency
- Database CPU
- Row size
- Index count
```

### E. Execution Schedule

#### Current Implementation: Docker Compose Loop

**Default Configuration (docker-compose.yml):**
```yaml
batch-processor:
  command: >
    bash -c "while true; do 
      python processing/batch_job.py --days ${BATCH_DAYS:-2}; 
      sleep ${BATCH_INTERVAL_SECONDS:-3600}; 
    done"
  environment:
    - BATCH_DAYS=2              # Process last 2 days
    - BATCH_INTERVAL_SECONDS=3600  # Run every 1 hour
```

**Scheduling Behavior:**

```
Timeline:
T+0s:        Container starts, chạy lần đầu ngay lập tức
T+180s:      Lần đầu hoàn thành (~3 phút cho 10k events)
T+180s:      Sleep 3600s (1 giờ)
T+3780s:     Wake up, chạy lần 2
T+3960s:     Lần 2 hoàn thành
T+3960s:     Sleep 3600s
T+7560s:     Wake up, chạy lần 3
...
```

**⚠️ Important Notes:**
- Lần đầu run NGAY khi container start (không chờ 1 giờ)
- Interval được tính TỪ KHI kết thúc job trước, KHÔNG phải từ lúc bắt đầu
- Nếu job chạy 5 phút → actual interval = 3600s + 300s = ~1h5m giữa 2 lần start

---

#### Tuning Scheduling Frequency

**Option 1: Environment Variables (.env file)**

```bash
# Chạy mỗi 15 phút (cho development/testing)
BATCH_INTERVAL_SECONDS=900
BATCH_DAYS=1  # Reduce lookback window

# Chạy mỗi 6 giờ (cho production với ít data)
BATCH_INTERVAL_SECONDS=21600
BATCH_DAYS=7  # Process longer history

# Chạy mỗi ngày lúc 2 AM (use cron instead)
BATCH_INTERVAL_SECONDS=86400
BATCH_DAYS=7
```

**Restart để apply changes:**
```bash
docker compose restart batch-processor
docker compose logs -f batch-processor  # Verify new interval
```

**Option 2: Manual Trigger (Không đợi interval)**

```bash
# Trigger ngay lập tức, không ảnh hưởng schedule
docker exec wiki-batch-processor python processing/batch_job.py --days 2

# Check kết quả
psql -c "SELECT MAX(hour_bucket) FROM historical_hourly_patterns;"
```

**Option 3: Cron-based Scheduling (Alternative)**

```bash
# Host cron (không dùng docker loop)
# /etc/crontab
0 * * * * docker exec wiki-batch-processor python processing/batch_job.py --days=1

# Hoặc inside container cron
0 */6 * * * cd /app && python processing/batch_job.py --days=3
```

---

#### Frequency Trade-offs

| Interval | Pros | Cons | Use Case |
|---------|------|------|----------|
| **15 min** | • Fresh data<br>• Quick iterations | • High S3 API costs<br>• Wasted compute if no new data | Development, testing |
| **1 hour** ⭐ | • Balanced freshness<br>• Reasonable costs<br>• Smooth dashboard updates | • 1 hour delay for insights | **Production (recommended)** |
| **6 hours** | • Very low costs<br>• Efficient batching | • Stale historical views | Low-traffic sites |
| **Daily** | • Cheapest<br>• Large batch efficiency | • Historical lags 24h | Archive-only mode |

**Cost Example (S3 + Spark):**
```
15-min interval: 96 runs/day × $0.02 = $1.92/day = $58/month
1-hour interval: 24 runs/day × $0.02 = $0.48/day = $14/month ✅
6-hour interval: 4 runs/day × $0.02 = $0.08/day = $2.4/month
```

---

#### Best Practice: Apache Airflow (Future)

**For production-grade orchestration:**

```python
from airflow import DAG
from airflow.providers.docker.operators.docker import DockerOperator
from airflow.sensors.external_task import ExternalTaskSensor
from datetime import datetime, timedelta

default_args = {
    'owner': 'data-team',
    'depends_on_past': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    'wiki_batch_processing',
    default_args=default_args,
    description='Batch process Wikipedia historical data',
    schedule_interval='@hourly',  # Cron: 0 * * * *
    start_date=datetime(2026, 1, 1),
    catchup=False,  # Don't backfill
    max_active_runs=1,  # No concurrent runs
)

# Task 1: Check if S3 has new data
check_s3 = DockerOperator(
    task_id='check_new_s3_data',
    image='wiki-processing:latest',
    command='python scripts/check_s3_freshness.py',
    dag=dag,
)

# Task 2: Run Spark job
process_batch = DockerOperator(
    task_id='run_batch_processor',
    image='wiki-processing:latest',
    command='python processing/batch_job.py --days=1',
    environment={
        'POSTGRES_HOST': '{{ var.value.db_host }}',
        'AWS_REGION': 'us-east-1',
    },
    dag=dag,
)

# Task 3: Data quality checks
validate_output = DockerOperator(
    task_id='validate_historical_tables',
    image='wiki-processing:latest',
    command='python scripts/validate_batch_output.py',
    dag=dag,
)

check_s3 >> process_batch >> validate_output
```

**Benefits:**
- ✅ Dependency management (check S3 before processing)
- ✅ Retry logic với exponential backoff
- ✅ Monitoring dashboard
- ✅ Alerting on failures
- ✅ Backfill support
- ✅ Skip runs if no new data

### F. Performance Characteristics

**Resource Usage:**
```
Spark Driver:
- Memory: 1-2GB
- CPU: 2-4 cores
- Disk: Minimal (streaming read from S3)

Processing Time:
- 10K events: ~30 seconds
- 100K events: ~2-3 minutes
- 1M events: ~15-20 minutes

Bottlenecks:
- S3 read: Network bandwidth
- Aggregations: CPU (DataFrame operations)
- JDBC write: Database connections
```

**Cost Optimization:**
```
EC2 instance sizing:
- Development: t3.medium (2 vCPU, 4GB)
- Production: m5.xlarge (4 vCPU, 16GB)
- High volume: m5.2xlarge (8 vCPU, 32GB)

S3 costs:
- Storage: $0.023/GB/month
- GET requests: $0.0004/1000
- Data transfer: Free to same region EC2

Tip: Use S3 Intelligent-Tiering for auto archival
```

---

## 🔄 End-to-End Batch Flow

### Timeline: Kafka → Dashboard

```
T+0s:        Events arriving in Kafka
T+30s:       Batch ingestion buffering (2500 events)
T+60s:       Buffer timeout → Flush 2500 events to S3
T+61s:       Parquet file written: year=2026/month=01/wiki_events_xxx.parquet
T+3600s:     Batch processor cron triggers (hourly)
T+3610s:     Spark reads S3, processes 50K events
T+3700s:     Aggregations complete (5 tables)
T+3750s:     JDBC writes to PostgreSQL complete
T+3751s:     Dashboard Historical Analytics page ready
T+3760s:     User clicks "Historical Analytics" → sees new data
```

**Total latency: ~1 hour** (configurable: có thể chạy mỗi 15 phút)

---

## 📈 Scalability & Performance

### Current Capacity:

```
Batch Ingestion:
- Throughput: 5000 events/60s = ~83 events/s write to S3
- Kafka lag: Minimal (ingestion faster than stream rate)
- S3 write frequency: 1 file/minute peak, 1 file/5min average

Batch Processor:
- Data volume: 1-7 days of history
- Processing: 100K events in 2-3 minutes
- Tables updated: 5 tables, 300-500 rows total
```

### Scaling Strategies:

**1. Increase Ingestion Frequency:**
```python
Current: 5000 events OR 60s
Optimized: 10000 events OR 120s
→ Fewer S3 files, lower API costs
→ Larger files, better compression
```

**2. Partition Parallelism:**
```python
# Add to Spark config
.config("spark.sql.shuffle.partitions", "50")
.config("spark.default.parallelism", "20")

# Repartition before heavy operations
df = df.repartition(10, "server_name")
```

**3. Incremental Processing:**
```python
# Instead of --days=7 full reprocess
# Track last processed timestamp
last_run = get_last_run_timestamp()
df = df.filter(col("timestamp") > last_run)

# Write in append mode
.mode("append")
```

**4. Separate Compute & Storage:**
```
Current: Spark on same EC2 as other services
Future: 
- Dedicated EMR cluster for Spark jobs
- Spot instances for cost savings
- Auto-scaling based on queue depth
```

---

## 🛡️ Fault Tolerance & Reliability

### Data Durability:

**S3 Storage:**
```
Durability: 99.999999999% (11 nines)
Replication: Cross-AZ automatic
Versioning: Can be enabled (not currently)
Lifecycle: Can auto-archive to Glacier
```

**Recovery Scenarios:**

**1. Batch Ingestion Crash:**
```
Impact: Events không được archived
Recovery: Kafka offset chưa commit → restart sẽ replay
Data Loss: None (events vẫn trong Kafka 24h retention)
```

**2. S3 Write Failure:**
```
Impact: Buffer mất nếu container crash
Mitigation: 
- Kafka offset auto-commit sau write success
- Failed events sẽ được retry từ Kafka
- Max data loss: 1 buffer (5000 events ~2-3 phút)
```

**3. Batch Processor Failure:**
```
Impact: Historical tables không được update
Recovery: Re-run job manually
Data Loss: None (source data vẫn trong S3)
Mitigation: Airflow retry policy
```

**4. S3 Partition Corruption:**
```
Impact: Một partition không đọc được
Recovery: Spark skip bad files với option
Data Loss: Limited to corrupt partition
Prevention: Checksum verification, S3 versioning
```

### Monitoring & Alerts:

**Ingestion Metrics:**
```python
✅ Success:
- "Uploaded N records to s3://..."
- File count per hour (expected: 60-120)
- Kafka consumer lag (<1000)

❌ Failures:
- "S3 Upload Failed: {error}"
- No files written for >5 minutes
- Kafka lag > 10000
```

**Processor Metrics:**
```python
✅ Success:
- "✅ Batch processing completed successfully!"
- "✅ Loaded N records from Data Lake"
- "✅ Wrote N records to table_name"

❌ Failures:
- "⚠️ Data lake path not found"
- "❌ Batch processing failed: {error}"
- Job duration > 30 minutes
```

**Database Health:**
```sql
-- Check last update time
SELECT MAX(hour_bucket) FROM historical_hourly_patterns;

-- Should be within last 2 hours
-- If older → batch processor not running
```

---

## 🔧 Configuration & Tuning

### Environment Variables:

```bash
# S3 Data Lake
DATA_LAKE_PATH=s3a://wiki-data-lake-prod-1407/raw_data
AWS_REGION=us-east-1
S3_BUCKET_NAME=wiki-data-lake-prod-1407
AWS_ACCESS_KEY_ID=  # Empty = use IAM role
AWS_SECRET_ACCESS_KEY=

# Database
POSTGRES_HOST=wiki-pipeline-db.xxx.rds.amazonaws.com
POSTGRES_PORT=5432
POSTGRES_DB=wikidb
POSTGRES_USER=thanh123
POSTGRES_PASSWORD=***

# Spark
SPARK_MASTER=local[*]  # Use all cores
CHECKPOINT_PATH=/tmp/checkpoints
```

### Performance Tuning Parameters:

**Batch Ingestion:**
```python
# Memory vs Latency tradeoff
BATCH_SIZE = 5000     # Standard
BATCH_SIZE = 10000    # Better compression, lower API costs
BATCH_SIZE = 2000     # Lower latency, more files

TIMEOUT_SEC = 60      # Standard
TIMEOUT_SEC = 300     # For low-traffic periods
TIMEOUT_SEC = 30      # For high-frequency updates
```

**Spark Configuration:**
```python
# For large datasets (1M+ events)
.config("spark.executor.memory", "4g")
.config("spark.driver.memory", "2g")
.config("spark.sql.shuffle.partitions", "100")

# For memory-constrained environments
.config("spark.executor.memory", "1g")
.config("spark.driver.memory", "1g")
.config("spark.sql.shuffle.partitions", "20")
```

**JDBC Write Tuning:**
```python
# Reduce partitions before write (avoid too many connections)
df.coalesce(5).write.jdbc(...)

# Batch insert size
.option("batchsize", 10000)

# Isolation level
.option("isolationLevel", "READ_UNCOMMITTED")
```

---

## 📊 Cost Analysis

### Monthly Costs (Assuming 100M events/month):

**S3 Storage:**
```
Data volume: 100M events × 500 bytes/event = 50GB uncompressed
After compression (5x): 10GB
Cost: 10GB × $0.023/GB = $0.23/month

API calls: 
- PUT: 10,000 files × $0.005/1000 = $0.05/month
- GET: 100 Spark reads × $0.0004/1000 = negligible

Total S3: ~$0.30/month
```

**EC2 Compute (t3.medium, on-demand):**
```
Price: $0.0416/hour
Monthly: $0.0416 × 24 × 30 = $29.95/month

Alternative (Spot):
Price: ~$0.012/hour (70% savings)
Monthly: ~$9/month
```

**RDS PostgreSQL (db.t3.micro):**
```
Price: $0.017/hour
Monthly: $0.017 × 24 × 30 = $12.24/month

Storage: 20GB × $0.115/GB = $2.30/month
Total RDS: ~$14.54/month
```

**Total Monthly Cost: ~$44/month** (with on-demand EC2)  
**Optimized: ~$24/month** (with Spot instances)

---

## 🚀 Operational Procedures

### Daily Operations:

**Morning Check:**
```bash
# Check last batch run
docker compose logs batch-processor --tail=50

# Verify data freshness
psql -c "SELECT MAX(hour_bucket) FROM historical_hourly_patterns;"

# Check S3 file count (should increase daily)
aws s3 ls s3://bucket/raw_data/raw_events/year=2026/month=01/ --recursive | wc -l
```

**Weekly Maintenance:**
```bash
# Check S3 storage size
aws s3 ls s3://bucket/raw_data/ --recursive --summarize | grep "Total Size"

# Vacuum historical tables
psql -c "VACUUM ANALYZE historical_hourly_patterns;"
```

**Monthly Tasks:**
```sql
-- Archive old data (optional)
-- Copy old partitions to Glacier
aws s3 sync s3://bucket/raw_data/raw_events/year=2025/ \
            s3://bucket-archive/year=2025/ \
            --storage-class GLACIER

-- Delete after verification
aws s3 rm s3://bucket/raw_data/raw_events/year=2025/ --recursive
```

### Troubleshooting:

**1. No new historical data:**
```bash
# Check batch processor container
docker compose ps batch-processor  # Should be Up

# Check logs
docker compose logs batch-processor --tail=100

# Manual run
docker compose exec batch-processor python processing/batch_job.py --days=1
```

**2. S3 permission errors:**
```bash
# Test S3 access
aws s3 ls s3://bucket/raw_data/

# Check IAM role (on EC2)
aws sts get-caller-identity

# Verify bucket policy
aws s3api get-bucket-policy --bucket wiki-data-lake-prod-1407
```

**3. Spark out of memory:**
```python
# Symptom: "java.lang.OutOfMemoryError: GC overhead limit exceeded"

# Solution 1: Increase memory
.config("spark.driver.memory", "4g")

# Solution 2: Reduce data range
python processing/batch_job.py --days=1  # Instead of --days=7

# Solution 3: Increase partitions
.config("spark.sql.shuffle.partitions", "50")
```

**4. Slow Spark jobs:**
```bash
# Check Spark UI (if enabled)
http://localhost:4040

# Look for:
- Skewed partitions (one partition much larger)
- High GC time (memory pressure)
- Shuffle read/write size (optimize joins)

# Solutions:
- Repartition data: df.repartition(20)
- Broadcast small tables: broadcast(df_small)
- Cache intermediate results: df.cache()
```

---

## 🎯 Future Enhancements

### Short-term (1-3 months):

1. **Schema Evolution**: Properly handle new fields without reprocessing
2. **Data Quality**: Great Expectations integration for validation
3. **Incremental Processing**: Only process new data since last run
4. **Alerting**: Email/Slack notifications on failures

### Medium-term (3-6 months):

1. **Delta Lake**: Replace Parquet với Delta format
   - ACID transactions
   - Time travel queries
   - Schema enforcement
   
2. **Apache Airflow**: Proper orchestration
   - Dependency management
   - Retry logic
   - SLA monitoring
   
3. **AWS EMR**: Dedicated Spark cluster
   - Auto-scaling
   - Spot instances
   - Better performance

### Long-term (6-12 months):

1. **Real-time Sync**: Lambda Layer serving merge
2. **ML Pipeline**: Feature engineering on Spark
3. **Data Catalog**: AWS Glue for metadata management
4. **Query Engine**: Athena/Presto for ad-hoc analysis

---

## 📚 References

- [Apache Spark Documentation](https://spark.apache.org/docs/latest/)
- [Parquet Format Specification](https://parquet.apache.org/docs/)
- [AWS S3 Best Practices](https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance.html)
- [Spark on S3 Performance](https://docs.aws.amazon.com/emr/latest/ReleaseGuide/emr-spark-s3-optimized-committer.html)

---

**Document Version**: 1.0  
**Last Updated**: January 15, 2026  
**Author**: thanh123  
**Status**: Production Ready ✅
