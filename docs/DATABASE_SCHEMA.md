# Database Schema Documentation - Wiki Data Analysis System

## 📚 Overview

Tài liệu này liệt kê **chi tiết tất cả các bảng** trong hệ thống Wiki Data Analysis, bao gồm:
- Các database được sử dụng
- Schema của từng bảng
- Nguồn dữ liệu và cơ chế ghi
- Chu kỳ cập nhật
- Mục đích sử dụng

---

## 🗄️ Databases Overview

Hệ thống sử dụng **2 loại database/storage**:

### 1. **PostgreSQL (RDS) - Analytical Database**
- **Endpoint**: `wiki-pipeline-db.cen6acgi49ye.us-east-1.rds.amazonaws.com:5432`
- **Database name**: `wikidb`
- **Region**: `us-east-1`
- **Purpose**: Lưu trữ dữ liệu đã xử lý cho Dashboard và Analytics
- **Tables**: 7 tables (2 realtime + 5 historical)

### 2. **Amazon S3 - Data Lake**
- **Bucket**: `wiki-data-lake-prod-1407`
- **Format**: Parquet files (columnar format)
- **Partitioning**: `raw_events/year=YYYY/month=MM/`
- **Purpose**: Archive raw events cho batch processing
- **Not a traditional database**: Dữ liệu được tổ chức dạng files, không có tables

---

## 📊 PostgreSQL Tables - Complete List

### **A. Real-time Tables (Speed Layer)** 

Các bảng này được cập nhật **real-time** bởi Quix Stream Processor từ Kafka stream.

---

#### 1. `realtime_traffic_volume`

**📝 Mô tả**: Thống kê traffic volume theo thời gian (time-series), hiển thị mức độ hoạt động trên Wikipedia theo từng cửa sổ thời gian.

**🏗️ Schema**:
```sql
CREATE TABLE realtime_traffic_volume (
    window_start TIMESTAMP,           -- Thời điểm bắt đầu cửa sổ
    total_bytes BIGINT,                -- Tổng bytes thay đổi trong window
    event_count INT,                   -- Số lượng events trong window
    avg_bytes_per_event FLOAT          -- Trung bình bytes/event (GENERATED)
        GENERATED ALWAYS AS (
            CASE WHEN event_count > 0 
            THEN total_bytes::FLOAT / event_count 
            ELSE 0 END
        ) STORED
);

-- Index for performance
CREATE INDEX idx_traffic_window ON realtime_traffic_volume(window_start);
```

**📊 Cấu trúc dữ liệu**:
| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `window_start` | TIMESTAMP | Thời điểm bắt đầu window | `2026-01-19 14:30:00` |
| `total_bytes` | BIGINT | Tổng bytes changed | `125000` |
| `event_count` | INT | Số events | `100` |
| `avg_bytes_per_event` | FLOAT | TB bytes/event | `1250.0` |

**✍️ Cơ chế ghi dữ liệu**:

| Thuộc tính | Chi tiết |
|------------|----------|
| **Component ghi** | `processing/quix_job.py` - Quix Stream Processor |
| **Vị trí trong code** | [processing/quix_job.py](../processing/quix_job.py#L158) - Hàm `main()` |
| **Nguồn dữ liệu** | Kafka topic `wiki-raw-events` |
| **Chu kỳ ghi** | **Micro-batch**: Ghi mỗi khi đủ 100 events từ Kafka (~10-30 giây tùy traffic) |
| **Phương thức** | `INSERT` batch sử dụng `psycopg2.extras.execute_values()` |
| **Logic tổng hợp** | Tính tổng `total_bytes` và đếm `event_count` từ buffer 100 events |
| **Retention** | **24 giờ** - Auto cleanup mỗi 100 polls (~2 phút) xóa data cũ hơn 24h |

**🔄 Flow ghi dữ liệu**:
```
Kafka (wiki-raw-events)
    ↓ [consume messages]
Quix Job Buffer (in-memory)
    ↓ [buffer 100 events]
Calculate Aggregations:
    - total_bytes = sum(bytes_changed)
    - event_count = 100
    - window_start = NOW()
    ↓ [execute_values()]
PostgreSQL: realtime_traffic_volume
```

**🎯 Mục đích sử dụng**:
- Dashboard: Real-time traffic chart (line graph theo thời gian)
- Alert system: Phát hiện traffic spikes bất thường
- Capacity planning: Monitor load patterns

**🧹 Cleanup Policy**:
```sql
-- Auto-cleanup trong quix_job.py, chạy mỗi ~2 phút
DELETE FROM realtime_traffic_volume 
WHERE window_start < NOW() - INTERVAL '24 HOURS';
```

---

#### 2. `realtime_recent_changes`

**📝 Mô tả**: Feed raw của các thay đổi gần đây trên Wikipedia, hiển thị chi tiết từng edit/change event.

**🏗️ Schema**:
```sql
CREATE TABLE realtime_recent_changes (
    event_time TIMESTAMP,              -- Thời điểm event xảy ra
    "user" TEXT,                       -- Username (quoted vì "user" là reserved)
    title TEXT,                        -- Tiêu đề bài viết
    server_name TEXT,                  -- Wiki server (vd: en.wikipedia.org)
    is_bot BOOLEAN,                    -- User là bot hay không
    type TEXT,                         -- Loại event: edit/new/log
    bytes_changed BIGINT,              -- Số bytes thay đổi
    length_diff INT                    -- Chênh lệch độ dài (new - old)
);

-- Index for performance
CREATE INDEX idx_changes_time ON realtime_recent_changes(event_time);
```

**📊 Cấu trúc dữ liệu**:
| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `event_time` | TIMESTAMP | Thời điểm event | `2026-01-19 14:30:15` |
| `"user"` | TEXT | Username | `JohnEditor123` |
| `title` | TEXT | Tên bài viết | `Python (programming)` |
| `server_name` | TEXT | Wiki server | `en.wikipedia.org` |
| `is_bot` | BOOLEAN | Bot flag | `false` |
| `type` | TEXT | Event type | `edit` / `new` / `log` |
| `bytes_changed` | BIGINT | Bytes changed | `500` |
| `length_diff` | INT | Length diff | `+250` (có thể âm) |

**✍️ Cơ chế ghi dữ liệu**:

| Thuộc tính | Chi tiết |
|------------|----------|
| **Component ghi** | `processing/quix_job.py` - Quix Stream Processor |
| **Vị trí trong code** | [processing/quix_job.py](../processing/quix_job.py#L162-L166) - Hàm `main()` |
| **Nguồn dữ liệu** | Kafka topic `wiki-raw-events` |
| **Chu kỳ ghi** | **Micro-batch**: Ghi mỗi khi đủ 100 events (~10-30 giây) |
| **Phương thức** | `INSERT` batch với `execute_values()` |
| **Data transformation** | `length_diff = length.new - length.old` được tính khi consume message |
| **Retention** | **24 giờ** - Auto cleanup cùng với `realtime_traffic_volume` |

**🔄 Flow ghi dữ liệu**:
```
Kafka (wiki-raw-events)
    ↓ [consume individual messages]
Quix Job Buffer:
    - Extract: event_time, user, title, server_name, is_bot, type, bytes_changed
    - Calculate: length_diff = length.new - length.old
    - Append to buffer (list of tuples)
    ↓ [when buffer >= 100 events]
Batch INSERT to PostgreSQL
    ↓ [execute_values()]
PostgreSQL: realtime_recent_changes
```

**🎯 Mục đích sử dụng**:
- Dashboard: Recent changes feed (live activity log)
- User activity monitoring: Track specific users/bots
- Content analysis: Xem changes theo wiki/language
- Real-time alerts: Detect vandalism, spam

**🧹 Cleanup Policy**:
```sql
-- Auto-cleanup trong quix_job.py
DELETE FROM realtime_recent_changes 
WHERE event_time < NOW() - INTERVAL '24 HOURS';
```

---

### **B. Historical Tables (Batch Layer)**

Các bảng này được cập nhật **định kỳ** bởi Spark Batch Processor, xử lý dữ liệu lịch sử từ S3 Data Lake.

---

#### 3. `historical_hourly_patterns`

**📝 Mô tả**: Phân tích patterns theo giờ trong ngày (0-23h), aggregated data cho historical analysis.

**🏗️ Schema** (Inferred từ Spark DataFrame):
```sql
-- Schema được tạo tự động bởi Spark JDBC write
CREATE TABLE historical_hourly_patterns (
    hour_bucket TIMESTAMP,             -- Cửa sổ giờ (time-series)
    total_events BIGINT,               -- Tổng số events trong giờ đó
    total_bytes BIGINT,                -- Tổng bytes thay đổi
    avg_bytes DOUBLE PRECISION,        -- Trung bình bytes/event
    bot_events BIGINT,                 -- Số events của bots
    human_events BIGINT                -- Số events của humans
);
```

**📊 Cấu trúc dữ liệu**:
| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `hour_bucket` | TIMESTAMP | Giờ bucket | `2026-01-18 14:00:00` |
| `total_events` | BIGINT | Total events | `5234` |
| `total_bytes` | BIGINT | Total bytes | `2500000` |
| `avg_bytes` | DOUBLE | Avg bytes | `477.5` |
| `bot_events` | BIGINT | Bot events | `3200` |
| `human_events` | BIGINT | Human events | `2034` |

**✍️ Cơ chế ghi dữ liệu**:

| Thuộc tính | Chi tiết |
|------------|----------|
| **Component ghi** | `processing/batch_job.py` - WikiBatchProcessor |
| **Vị trí trong code** | [processing/batch_job.py](../processing/batch_job.py#L139-L152) - `_calculate_hourly_patterns()` |
| **Nguồn dữ liệu** | S3 Data Lake (`s3://wiki-data-lake-prod-1407/raw_events/`) |
| **Chu kỳ ghi** | **Định kỳ** - Chạy theo schedule (mặc định: daily hoặc on-demand) |
| **Thời gian xử lý** | 5-10 phút (tùy volume data) |
| **Phương thức** | Spark JDBC write với `mode="overwrite"` - **thay thế toàn bộ bảng** |
| **Data range** | Mặc định: 7 ngày gần nhất (configurable qua `--days` parameter) |

**🔄 Flow ghi dữ liệu**:
```
S3 Data Lake (Parquet files)
    ↓ [Spark read from s3a://]
PySpark DataFrame:
    - Filter: Last N days
    - date_trunc("hour", timestamp) as hour_bucket
    - GROUP BY hour_bucket
    - AGG: count(*), sum(bytes_changed), avg(bytes_changed)
    - COUNT bot vs human events
    ↓ [Spark JDBC Writer]
PostgreSQL: historical_hourly_patterns (OVERWRITE entire table)
```

**⚠️ Important Notes**:
- **OVERWRITE mode**: Mỗi lần chạy sẽ replace toàn bộ data trong bảng
- **No incremental updates**: Không append, chỉ full refresh
- **Historical timerange**: Chỉ giữ data của N days gần nhất (default 7 days)

**🎯 Mục đích sử dụng**:
- Dashboard: Hourly activity patterns chart
- Trend analysis: So sánh patterns theo ngày
- Bot vs Human ratio analysis

---

#### 4. `historical_hourly_trends`

**📝 Mô tả**: Time-series hourly trends với 24-hour moving average, cho phép phân tích xu hướng theo thời gian.

**🏗️ Schema**:
```sql
CREATE TABLE historical_hourly_trends (
    hour_bucket TIMESTAMP,             -- Cửa sổ giờ
    total_events BIGINT,               -- Tổng events
    total_bytes BIGINT,                -- Tổng bytes
    bot_count BIGINT,                  -- Số bot events
    new_pages BIGINT,                  -- Số trang mới tạo
    edits BIGINT,                      -- Số edits
    events_24h_avg DOUBLE PRECISION,   -- Moving avg events (24h window)
    bytes_24h_avg DOUBLE PRECISION     -- Moving avg bytes (24h window)
);
```

**📊 Cấu trúc dữ liệu**:
| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `hour_bucket` | TIMESTAMP | Hour window | `2026-01-18 15:00:00` |
| `total_events` | BIGINT | Events count | `4521` |
| `total_bytes` | BIGINT | Bytes changed | `2100000` |
| `bot_count` | BIGINT | Bot edits | `2800` |
| `new_pages` | BIGINT | New pages | `45` |
| `edits` | BIGINT | Edit count | `4476` |
| `events_24h_avg` | DOUBLE | 24h MA events | `4350.2` |
| `bytes_24h_avg` | DOUBLE | 24h MA bytes | `2050000.5` |

**✍️ Cơ chế ghi dữ liệu**:

| Thuộc tính | Chi tiết |
|------------|----------|
| **Component ghi** | `processing/batch_job.py` - WikiBatchProcessor |
| **Vị trí trong code** | [processing/batch_job.py](../processing/batch_job.py#L183-L215) - `_calculate_hourly_trends()` |
| **Nguồn dữ liệu** | S3 Data Lake (Parquet) |
| **Chu kỳ ghi** | **Định kỳ** - Schedule based (default: daily) |
| **Phương thức** | Spark JDBC write với `mode="overwrite"` |
| **Special processing** | Sử dụng Spark Window function cho moving average |

**🔄 Flow ghi dữ liệu**:
```
S3 Data Lake
    ↓ [Spark read]
PySpark DataFrame:
    - date_trunc("hour", timestamp) as hour_bucket
    - GROUP BY hour_bucket: count, sum, filters
    - Window function: 
        Window.orderBy("hour_bucket").rowsBetween(-23, 0)
        => Calculate 24-hour moving averages
    - ORDER BY hour_bucket
    ↓ [Spark JDBC]
PostgreSQL: historical_hourly_trends (OVERWRITE)
```

**🎯 Mục đích sử dụng**:
- Dashboard: Trend analysis charts với smoothing
- Anomaly detection: Detect spikes vs 24h average
- Forecasting: Predict future traffic based on trends

---

#### 5. `historical_top_contributors`

**📝 Mô tả**: Top 100 contributors (users/bots) được xếp hạng theo số lượng edits.

**🏗️ Schema**:
```sql
CREATE TABLE historical_top_contributors (
    "user" TEXT,                       -- Username
    is_bot BOOLEAN,                    -- Bot flag
    edit_count BIGINT,                 -- Total edits
    total_bytes BIGINT,                -- Total bytes changed
    pages_created BIGINT               -- Pages created by user
);
```

**📊 Cấu trúc dữ liệu**:
| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `"user"` | TEXT | Username | `InternetArchiveBot` |
| `is_bot` | BOOLEAN | Bot flag | `true` |
| `edit_count` | BIGINT | Edit count | `125000` |
| `total_bytes` | BIGINT | Bytes changed | `50000000` |
| `pages_created` | BIGINT | Pages created | `250` |

**✍️ Cơ chế ghi dữ liệu**:

| Thuộc tính | Chi tiết |
|------------|----------|
| **Component ghi** | `processing/batch_job.py` - WikiBatchProcessor |
| **Vị trí trong code** | [processing/batch_job.py](../processing/batch_job.py#L154-L168) - `_calculate_top_contributors()` |
| **Nguồn dữ liệu** | S3 Data Lake |
| **Chu kỳ ghi** | **Định kỳ** - Schedule based |
| **Limit** | Top 100 contributors only |
| **Phương thức** | Spark JDBC `mode="overwrite"` |

**🔄 Flow ghi dữ liệu**:
```
S3 Data Lake
    ↓ [Spark read]
PySpark DataFrame:
    - GROUP BY user, is_bot
    - AGG: 
        count(*) as edit_count
        sum(bytes_changed) as total_bytes
        count(is_new_page == true) as pages_created
    - ORDER BY edit_count DESC
    - LIMIT 100
    ↓ [Spark JDBC]
PostgreSQL: historical_top_contributors (OVERWRITE, max 100 rows)
```

**🎯 Mục đích sử dụng**:
- Dashboard: Top contributors leaderboard
- Community analysis: Identify key contributors
- Bot vs Human comparison

---

#### 6. `historical_language_distribution`

**📝 Mô tả**: Phân phối edits theo ngôn ngữ và project (wikipedia, wiktionary, etc.).

**🏗️ Schema**:
```sql
CREATE TABLE historical_language_distribution (
    language TEXT,                     -- Language code (en, es, fr, etc.)
    project TEXT,                      -- Project type (wikipedia, wiktionary)
    edit_count BIGINT,                 -- Total edits
    total_bytes BIGINT,                -- Total bytes
    bot_edits BIGINT,                  -- Bot edits count
    new_pages BIGINT                   -- New pages created
);
```

**📊 Cấu trúc dữ liệu**:
| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `language` | TEXT | Language code | `en` |
| `project` | TEXT | Project name | `wikipedia` |
| `edit_count` | BIGINT | Edit count | `2500000` |
| `total_bytes` | BIGINT | Bytes changed | `1200000000` |
| `bot_edits` | BIGINT | Bot edits | `1500000` |
| `new_pages` | BIGINT | New pages | `8500` |

**✍️ Cơ chế ghi dữ liệu**:

| Thuộc tính | Chi tiết |
|------------|----------|
| **Component ghi** | `processing/batch_job.py` - WikiBatchProcessor |
| **Vị trí trong code** | [processing/batch_job.py](../processing/batch_job.py#L170-L184) - `_calculate_language_distribution()` |
| **Nguồn dữ liệu** | S3 Data Lake |
| **Chu kỳ ghi** | **Định kỳ** - Schedule based |
| **Phương thức** | Spark JDBC `mode="overwrite"` |

**🔄 Flow ghi dữ liệu**:
```
S3 Data Lake
    ↓ [Spark read]
PySpark DataFrame:
    - GROUP BY language, project
    - AGG:
        count(*) as edit_count
        sum(bytes_changed) as total_bytes
        count(is_bot == true) as bot_edits
        count(is_new_page == true) as new_pages
    - ORDER BY edit_count DESC
    ↓ [Spark JDBC]
PostgreSQL: historical_language_distribution (OVERWRITE)
```

**🎯 Mục đích sử dụng**:
- Dashboard: Language/project distribution pie chart
- Geo analysis: Wikipedia popularity by region
- Multi-lingual insights

---

#### 7. `historical_server_rankings`

**📝 Mô tả**: Top 50 wiki servers được xếp hạng theo activity, bao gồm percentile rankings.

**🏗️ Schema**:
```sql
CREATE TABLE historical_server_rankings (
    server_name TEXT,                  -- Server domain (en.wikipedia.org)
    language TEXT,                     -- Language code
    project TEXT,                      -- Project type
    edit_count BIGINT,                 -- Total edits
    total_bytes BIGINT,                -- Total bytes
    unique_users BIGINT,               -- Distinct users count
    rank INT,                          -- Ranking position (1-50)
    percentile DOUBLE PRECISION        -- Percentile rank (0.0-1.0)
);
```

**📊 Cấu trúc dữ liệu**:
| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `server_name` | TEXT | Server domain | `en.wikipedia.org` |
| `language` | TEXT | Language | `en` |
| `project` | TEXT | Project | `wikipedia` |
| `edit_count` | BIGINT | Edit count | `3000000` |
| `total_bytes` | BIGINT | Bytes changed | `1500000000` |
| `unique_users` | BIGINT | Unique users | `25000` |
| `rank` | INT | Rank position | `1` |
| `percentile` | DOUBLE | Percentile | `1.0` (top) |

**✍️ Cơ chế ghi dữ liệu**:

| Thuộc tính | Chi tiết |
|------------|----------|
| **Component ghi** | `processing/batch_job.py` - WikiBatchProcessor |
| **Vị trí trong code** | [processing/batch_job.py](../processing/batch_job.py#L217-L242) - `_calculate_server_rankings()` |
| **Nguồn dữ liệu** | S3 Data Lake |
| **Chu kỳ ghi** | **Định kỳ** - Schedule based |
| **Limit** | Top 50 servers only |
| **Phương thức** | Spark JDBC `mode="overwrite"` |
| **Special processing** | Sử dụng Spark Window functions: `row_number()`, `percent_rank()` |

**🔄 Flow ghi dữ liệu**:
```
S3 Data Lake
    ↓ [Spark read]
PySpark DataFrame:
    - GROUP BY server_name, language, project
    - AGG:
        count(*) as edit_count
        sum(bytes_changed) as total_bytes
        countDistinct(user) as unique_users
    - Window function:
        Window.orderBy(desc(edit_count))
        => row_number() as rank
        => percent_rank() as percentile
    - FILTER: rank <= 50
    ↓ [Spark JDBC]
PostgreSQL: historical_server_rankings (OVERWRITE, max 50 rows)
```

**🎯 Mục đích sử dụng**:
- Dashboard: Server rankings leaderboard
- Comparative analysis: Wiki activity comparison
- Community size analysis via unique_users

---

## 🗂️ S3 Data Lake Structure

### Raw Events Storage

**Path structure**:
```
s3://wiki-data-lake-prod-1407/
└── raw_events/
    ├── year=2026/
    │   ├── month=01/
    │   │   ├── wiki_events_20260118_140530.parquet
    │   │   ├── wiki_events_20260118_141645.parquet
    │   │   └── ... (multiple parquet files)
    │   └── month=02/
    └── year=2025/
        └── ...
```

**File Format**: Apache Parquet
- **Compression**: Snappy
- **Version**: 2.6
- **Schema**: All fields from Kafka events + enrichments

**Partitioning Strategy**:
- **By time**: `year=YYYY/month=MM/`
- **Purpose**: Optimize Spark queries by date range
- **Benefits**: Partition pruning reduces scan volume

**✍️ Cơ chế ghi dữ liệu**:

| Thuộc tính | Chi tiết |
|------------|----------|
| **Component ghi** | `ingestion/batch_job.py` - Batch Archiver |
| **Vị trí trong code** | [ingestion/batch_job.py](../ingestion/batch_job.py#L63-L106) - `upload_batch()` |
| **Nguồn dữ liệu** | Kafka topic `wiki-raw-events` |
| **Chu kỳ ghi** | **Micro-batch**: Mỗi 5000 events HOẶC mỗi 60 giây |
| **Phương thức** | PyArrow Parquet writer → boto3 S3 upload |
| **File size** | ~2-5 MB per file (tùy traffic) |
| **Write rate** | ~1-3 files/phút (peak: 5-10 files/phút) |

**🔄 Flow ghi dữ liệu**:
```
Kafka (wiki-raw-events)
    ↓ [consumer: wiki-batch-archiver-group]
In-memory Buffer (list)
    ↓ [buffer until 5000 events OR 60s timeout]
Data Normalization:
    - timestamp → int64
    - log_params → JSON string
    ↓ [pandas DataFrame]
PyArrow Table Conversion
    ↓ [write_table() to BytesIO buffer]
boto3 S3 Client
    ↓ [upload_fileobj()]
S3: s3://wiki-data-lake-prod-1407/raw_events/year=*/month=*/*.parquet
```

**📦 File Example**:
```
Filename: wiki_events_20260118_140530.parquet
Size: 3.2 MB
Records: 5000 events
Columns: 
  - timestamp (int64)
  - user (string)
  - title (string)
  - server_name (string)
  - type (string)
  - bytes_changed (int64)
  - is_bot (bool)
  - is_new_page (bool)
  - language (string)
  - project (string)
  - log_params (string, JSON)
  - ... (20+ fields total)
```

**🎯 Mục đích sử dụng**:
- **Primary storage**: Long-term archive của raw events
- **Batch processing**: Source data cho Spark jobs
- **Reprocessing**: Có thể reprocess lại data cũ nếu cần
- **Data auditing**: Full historical record

---

## 📊 Summary Table - All Tables & Data Sources

| # | Table Name | Database | Type | Writer Component | Source Data | Write Cycle | Retention |
|---|-----------|----------|------|------------------|-------------|-------------|-----------|
| 1 | `realtime_traffic_volume` | PostgreSQL | Real-time | `quix_job.py` | Kafka | ~10-30s (100 events) | 24 hours |
| 2 | `realtime_recent_changes` | PostgreSQL | Real-time | `quix_job.py` | Kafka | ~10-30s (100 events) | 24 hours |
| 3 | `historical_hourly_patterns` | PostgreSQL | Historical | `batch_job.py` (Spark) | S3 Data Lake | Daily/scheduled | Last N days |
| 4 | `historical_hourly_trends` | PostgreSQL | Historical | `batch_job.py` (Spark) | S3 Data Lake | Daily/scheduled | Last N days |
| 5 | `historical_top_contributors` | PostgreSQL | Historical | `batch_job.py` (Spark) | S3 Data Lake | Daily/scheduled | Last N days |
| 6 | `historical_language_distribution` | PostgreSQL | Historical | `batch_job.py` (Spark) | S3 Data Lake | Daily/scheduled | Last N days |
| 7 | `historical_server_rankings` | PostgreSQL | Historical | `batch_job.py` (Spark) | S3 Data Lake | Daily/scheduled | Last N days |
| 8 | **S3 Raw Events** (Parquet) | S3 Data Lake | Archive | `batch_job.py` (Archiver) | Kafka | 60s or 5000 events | Indefinite |

---

## 🔄 Data Flow Summary

### 1. **Real-time Path (Speed Layer)**
```
Wikipedia EventStream
    ↓
Producer (ingestion/producer.py)
    ↓ [filter, enrich, publish]
Kafka/Redpanda (wiki-raw-events topic)
    ↓
Quix Stream Processor (processing/quix_job.py)
    ↓ [micro-batch aggregation]
PostgreSQL RDS:
    - realtime_traffic_volume
    - realtime_recent_changes
    ↓
Streamlit Dashboard (dashboard/app.py)
```

**⏱️ Latency**: <30 seconds end-to-end

---

### 2. **Batch Path (Batch Layer)**
```
Kafka (wiki-raw-events topic)
    ↓
Batch Archiver (ingestion/batch_job.py)
    ↓ [buffer 5000 events or 60s]
S3 Data Lake (Parquet files, partitioned by year/month)
    ↓
Spark Batch Processor (processing/batch_job.py)
    ↓ [complex aggregations, 7 days window]
PostgreSQL RDS:
    - historical_hourly_patterns
    - historical_hourly_trends
    - historical_top_contributors
    - historical_language_distribution
    - historical_server_rankings
    ↓
Streamlit Dashboard (pages/1_Historical_Analytics.py)
```

**⏱️ Latency**: 
- Archive: 1-2 minutes (micro-batch delay)
- Processing: 5-10 minutes (Spark job runtime)
- Total: ~10-15 minutes từ event → historical tables

---

## 🛠️ Database Initialization

**Script**: [scripts/create_tables_rds.py](../scripts/create_tables_rds.py)

**Purpose**: Tạo 2 real-time tables và indexes

**Usage**:
```bash
python scripts/create_tables_rds.py
```

**Tables created**:
- ✅ `realtime_traffic_volume` (with index on window_start)
- ✅ `realtime_recent_changes` (with index on event_time)

**⚠️ Note**: 
- Historical tables được tạo tự động bởi Spark khi chạy lần đầu (Spark JDBC auto-create)
- Nếu cần recreate, có thể DROP tables và chạy lại batch job

---

## 📈 Performance Considerations

### Real-time Tables
- **Write throughput**: ~100-500 inserts/minute (batched)
- **Read queries**: Indexed on time columns → Fast range queries
- **Auto-cleanup**: Giữ data 24h → Prevent unlimited growth
- **Size estimate**: ~10-50 MB per table (steady state)

### Historical Tables
- **Write method**: OVERWRITE entire table (not incremental)
- **Write frequency**: Daily or on-demand
- **Size estimate**: 
  - Patterns/trends: ~1-5 MB
  - Contributors/servers: <1 MB (limited rows)
  - Language distribution: ~500 KB
- **No indexes**: Analytical queries, full table scans acceptable

### S3 Data Lake
- **Storage**: Grows indefinitely (~10-50 GB/month estimate)
- **Cost optimization**: Use S3 lifecycle policies (move to Glacier after 90 days)
- **Query performance**: Parquet columnar format + partitioning → Efficient Spark reads

---

## 🔐 Access Configuration

### PostgreSQL Connection
```python
# From config/settings.py
POSTGRES_HOST = "wiki-pipeline-db.cen6acgi49ye.us-east-1.rds.amazonaws.com"
POSTGRES_PORT = 5432
POSTGRES_DB = "wikidb"
POSTGRES_USER = "thanh123"
POSTGRES_PASSWORD = "<from env or thongtin.txt>"
```

### S3 Access
```python
# From config/settings.py
S3_BUCKET = "wiki-data-lake-prod-1407"
S3_REGION = "us-east-1"

# Authentication:
# 1. EC2 Instance Profile (preferred): admin_thanh123
# 2. AWS credentials from environment
```

---

## 📚 Related Documentation

- **Streaming Layer**: [STREAMING.md](STREAMING.md) - Chi tiết về real-time processing
- **Batch Layer**: [BATCH.md](BATCH.md) - Chi tiết về batch processing & Spark
- **Dashboard**: [DASHBOARD_REPORT.md](DASHBOARD_REPORT.md) - Cách dashboard query các tables
- **System Architecture**: [NEW_SYSTEM_REPORT.md](NEW_SYSTEM_REPORT.md) - Kiến trúc tổng quan

---

## ✅ Checklist - Table Creation

### Initial Setup (One-time)
- [ ] Run `create_tables_rds.py` → Creates realtime tables
- [ ] Run batch archiver → Starts writing to S3
- [ ] Run batch processor → Creates historical tables (auto-create)
- [ ] Verify all 7 tables exist in PostgreSQL

### Verification Queries
```sql
-- List all tables
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public';

-- Check row counts
SELECT COUNT(*) FROM realtime_traffic_volume;
SELECT COUNT(*) FROM realtime_recent_changes;
SELECT COUNT(*) FROM historical_hourly_patterns;
SELECT COUNT(*) FROM historical_hourly_trends;
SELECT COUNT(*) FROM historical_top_contributors;
SELECT COUNT(*) FROM historical_language_distribution;
SELECT COUNT(*) FROM historical_server_rankings;

-- Check indexes
SELECT tablename, indexname FROM pg_indexes 
WHERE schemaname = 'public';
```

---

**Document Version**: 1.0  
**Last Updated**: 2026-01-19  
**Author**: System Documentation  
**Status**: ✅ Complete
