# Wikipedia Analytics Dashboard - Complete User Guide

**Version**: 2.0  
**Last Updated**: January 15, 2026  
**Dashboard URL**: `http://your-ec2-ip:8501`

---

## 📊 Overview

**Wikipedia Analytics Dashboard** là một real-time analytics platform được xây dựng với **Streamlit**, cung cấp insights vào hoạt động toàn cầu của Wikipedia. Dashboard kết hợp cả **Speed Layer** (real-time) và **Batch Layer** (historical) theo Lambda Architecture.

### Key Features:
- ✅ **Real-time Updates**: Auto-refresh mỗi 8 giây
- ✅ **30-Minute Window**: Theo dõi hoạt động gần đây
- ✅ **Multiple Dimensions**: Server, language, user, namespace analysis
- ✅ **Interactive Visualizations**: 15+ charts với Plotly
- ✅ **Historical Analytics**: Deep insights từ Spark batch processing

---

## 🏠 Dashboard Structure

Dashboard có 2 pages chính:

### 1. Main Page: Real-time Analytics
**Purpose**: Monitor live Wikipedia activity trong 30-minute window

**Data Source**: PostgreSQL tables (Speed Layer)
- `realtime_traffic_volume`
- `realtime_recent_changes`

**Refresh**: Auto-refresh every 8 seconds

### 2. Historical Analytics Page
**Purpose**: Deep analysis của historical data

**Data Source**: PostgreSQL tables (Batch Layer)
- `historical_hourly_patterns`
- `historical_hourly_trends`
- `historical_top_contributors`
- `historical_language_distribution`
- `historical_server_rankings`

**Refresh Behavior**: 
- ⏰ **Auto-update**: Charts refresh theo batch processor schedule (mặc định: **mỗi 1 giờ**)
- 🔄 **Manual refresh**: F5 hoặc click browser refresh
- 📊 **Data freshness**: Historical data lag 1-2 hours behind real-time

**⚠️ Important Timing Notes:**

```
Real-time Dashboard (Page 1):
└─ Updates: Every 8 seconds
└─ Data age: <1 minute
└─ Use for: Live monitoring

Historical Dashboard (Page 2):
└─ Updates: Every 1 hour (when batch job runs)
└─ Data age: 1-2 hours behind
└─ Use for: Trends, patterns, deep analysis
```

**Expected Update Timeline:**

```
6:00 PM - Start system
6:00 PM - Batch processor first run (immediate)
6:03 PM - Historical tables populated ✅
6:03 PM - Dashboard page 2 shows data ✅
7:03 PM - Batch processor second run
7:06 PM - Historical tables updated with new hour
8:03 PM - Third run...
```

**Configuration:**

Theo mặc định trong `docker-compose.yml`:
```yaml
BATCH_INTERVAL_SECONDS=3600  # 1 hour
BATCH_DAYS=2                 # Process last 2 days
```

**Để tăng tần suất update (edit `.env`):**
```bash
# Update every 15 minutes (for testing)
BATCH_INTERVAL_SECONDS=900

# Update every 6 hours (for production)
BATCH_INTERVAL_SECONDS=21600
```

**Trigger manual update:**
```bash
docker exec wiki-batch-processor python processing/batch_job.py --days 2
# Charts sẽ update sau 2-5 phút
```

---

## 📈 Main Page Components

### A. KPI Cards (Top Row)

Hiển thị 4 metrics chính trong real-time:

#### 1. Events (window)
```sql
Query: SELECT SUM(event_count) FROM realtime_traffic_volume
       WHERE window_start >= NOW() - INTERVAL '30 MINUTES'
```
**Meaning**: Tổng số events đã xử lý trong 30 phút gần nhất

**Typical Values**: 10,000 - 30,000 events

**What it indicates**:
- High (>25k): Peak activity period (afternoon UTC)
- Medium (10-25k): Normal activity
- Low (<10k): Off-peak hours (late night UTC)

#### 2. Volume (window)
```sql
Query: SELECT SUM(total_bytes) FROM realtime_traffic_volume
       WHERE window_start >= NOW() - INTERVAL '30 MINUTES'
```
**Meaning**: Tổng số bytes đã được changed (added/deleted) trên Wikipedia

**Display**: Megabytes (MB)

**Important**: Đây là content changes, không phải database size!

**What it indicates**:
- High volume: Major updates, new articles
- Low volume: Minor edits, typo fixes

#### 3. Live Velocity
```sql
Query: SELECT (event_count / 10.0) as events_per_second
       FROM realtime_traffic_volume
       ORDER BY window_start DESC LIMIT 1
```
**Meaning**: Current processing rate (events/second)

**Typical Values**: 5-20 events/second

**What it indicates**:
- System throughput
- Real-time load on processors
- Useful for capacity planning

#### 4. Top Server
```sql
Query: SELECT server_name FROM realtime_recent_changes
       WHERE event_time >= NOW() - INTERVAL '30 MINUTES'
       GROUP BY server_name
       ORDER BY COUNT(*) DESC LIMIT 1
```
**Meaning**: Wikipedia server với most edits

**Common Values**:
- `www.wikidata.org`: Wikidata edits (very active)
- `en.wikipedia.org`: English Wikipedia
- `commons.wikimedia.org`: Media files

---

### B. Dynamic Analysis Section

**Purpose**: Flexible analysis với switchable view

#### Chart: Edits by Server (Bar Chart)
```sql
SELECT server_name, COUNT(*) AS total_edits, SUM(ABS(bytes_changed)) AS total_bytes
FROM realtime_recent_changes
WHERE event_time >= NOW() - INTERVAL '30 MINUTES'
GROUP BY server_name
ORDER BY total_edits DESC LIMIT 12
```

**Visualization**:
- X-axis: Server name
- Y-axis: Edit count
- Color: Màu unique per server

**Insights**:
- **www.wikidata.org** thường dominates (data edits)
- **en.wikipedia.org** có nhiều human edits
- Smaller wikis appear lower

---

### C. Time Series Block (2 Charts Side-by-Side)

#### Chart 1: Traffic Volume (Area Chart)
```sql
SELECT window_start, total_bytes, event_count, avg_bytes_per_event
FROM realtime_traffic_volume
WHERE window_start >= NOW() - INTERVAL '30 MINUTES'
ORDER BY window_start DESC LIMIT 500
```

**Visualization**:
- X-axis: Time (window_start)
- Y-axis: Bytes changed
- Type: Area chart (filled)

**Patterns to observe**:
- Spikes: Major article updates or bot runs
- Valleys: Low activity periods
- Smooth curves: Steady human activity

#### Chart 2: Content Velocity (Line Chart)
```sql
SELECT window_start, (event_count / 10.0) as events_per_second
FROM realtime_traffic_volume
WHERE window_start >= NOW() - INTERVAL '30 MINUTES'
ORDER BY window_start DESC
```

**Visualization**:
- X-axis: Time
- Y-axis: Events/second
- Type: Line chart

**Insights**:
- Steady rate: System healthy
- Sudden drops: Potential producer issues
- Sudden spikes: Major events or bot activity

---

### D. Server & Language Overview (2 Charts)

#### Chart 1: Top Servers (Bar Chart with Color Scale)
```sql
SELECT server_name, COUNT(*) AS total_edits, SUM(ABS(bytes_changed)) AS total_bytes
FROM realtime_recent_changes
WHERE event_time >= NOW() - INTERVAL '30 MINUTES'
GROUP BY server_name
ORDER BY total_edits DESC LIMIT 12
```

**Visualization**:
- Bars: Edit count
- Color gradient: Total bytes (Viridis scale)
- Sorted: Descending by edits

**Reading the chart**:
- Tall + dark green: High edit count + large changes
- Tall + light green: Many small edits
- Short bars: Less active wikis

#### Chart 2: Language Breakdown (Bar Chart)
```sql
SELECT SPLIT_PART(server_name, '.', 1) as language,
       COUNT(*) AS total_count,
       SUM(ABS(bytes_changed)) AS total_bytes
FROM realtime_recent_changes
WHERE event_time >= NOW() - INTERVAL '30 MINUTES'
GROUP BY language
ORDER BY total_count DESC LIMIT 12
```

**Common Languages**:
- `en`: English (usually #1-2)
- `www`: Wikidata/Commons
- `de`, `fr`, `es`, `ja`: Major European + Asian languages

**Insights**:
- Global activity distribution
- Language-specific peak hours
- Multilingual bot activity

---

### E. Quality & Impact Analysis (2 Charts)

#### Chart 1: Edit Severity (Pie Chart)
```sql
SELECT 
    CASE 
        WHEN ABS(bytes_changed) > 1000 THEN 'Major'
        WHEN ABS(bytes_changed) > 100 THEN 'Moderate'
        ELSE 'Minor' 
    END as edit_type, 
    COUNT(*) AS total_count
FROM realtime_recent_changes
WHERE event_time >= NOW() - INTERVAL '30 MINUTES'
GROUP BY edit_type
```

**Categories**:
- **Major**: >1000 bytes changed (new articles, major rewrites)
- **Moderate**: 100-1000 bytes (substantial edits)
- **Minor**: <100 bytes (typos, small fixes)

**Typical Distribution**:
- Minor: 60-70% (most edits are small)
- Moderate: 20-30%
- Major: 5-10%

#### Chart 2: Content Volume Change (Bar Chart)
```sql
SELECT 
    CASE WHEN length_diff >= 0 THEN 'Addition' ELSE 'Deletion' END as change_type, 
    SUM(ABS(length_diff)) AS total_bytes, 
    COUNT(*) AS count
FROM realtime_recent_changes
WHERE event_time >= NOW() - INTERVAL '30 MINUTES'
GROUP BY change_type
```

**Insights**:
- **Additions > Deletions**: Wikipedia growing
- **Equal**: Maintenance/cleanup period
- **Deletions > Additions**: Rare, indicates vandalism cleanup

---

### F. Leaderboards & Namespaces

#### Chart 1: Most Edited Pages (Table)
```sql
SELECT title, server_name, COUNT(*) AS total_edits, SUM(ABS(bytes_changed)) AS total_bytes
FROM realtime_recent_changes
WHERE event_time >= NOW() - INTERVAL '30 MINUTES'
GROUP BY title, server_name
ORDER BY total_edits DESC LIMIT 12
```

**Columns**:
- `title`: Article name
- `server_name`: Which wiki
- `Edits`: Number of times edited
- `Bytes`: Total content changed

**Common Patterns**:
- **Wikidata items**: Q-numbers (e.g., Q12345)
- **Hot topics**: Current events, breaking news
- **Bot targets**: Template pages, category pages

#### Chart 2: Namespace Distribution (Bar Chart)
```sql
SELECT SPLIT_PART(title, ':', 1) as namespace, COUNT(*) AS total_count
FROM realtime_recent_changes
WHERE event_time >= NOW() - INTERVAL '30 MINUTES'
AND title LIKE '%:%'
GROUP BY namespace
ORDER BY total_count DESC LIMIT 20
```

**Common Namespaces**:
- `User`: User pages
- `Talk`: Article discussion
- `Wikipedia`: Meta pages
- `Template`: Template edits
- `Category`: Categorization

**Why important**: Indicates what type of work is happening (content vs maintenance)

---

### G. User Engagement Distribution (Histogram)
```sql
SELECT "user", COUNT(*) AS total_edits
FROM realtime_recent_changes
WHERE event_time >= NOW() - INTERVAL '30 MINUTES'
GROUP BY "user"
HAVING COUNT(*) >= 10  -- USER_THRESHOLD
```

**Visualization**: Histogram of edit counts per user

**Insights**:
- **Long tail**: Few power users, many casual editors
- **Bots**: Users với 50+ edits in 30 min
- **Humans**: Typically 1-10 edits per 30 min

---

### H. The Battlefield (Live Edits Scatter)
```sql
SELECT * FROM realtime_recent_changes
WHERE event_time >= NOW() - INTERVAL '30 MINUTES'
ORDER BY event_time DESC LIMIT 400
```

**Visualization**: Scatter plot with:
- X-axis: Time
- Y-axis: length_diff (positive = addition, negative = deletion)
- Size: Impact (abs(bytes_changed))
- Color: Green = Addition, Red = Deletion

**How to read**:
- **Large green dots**: Major content additions
- **Large red dots**: Major deletions (vandalism cleanup?)
- **Scattered above zero**: Net positive (growth)
- **Scattered below zero**: Net negative (cleanup)

**Interactive**: Hover to see title, user, server

---

## 📊 Historical Analytics Page

### A. Overview Trends

#### Chart: Last 48 Hours Trends (Line Chart)
```sql
SELECT * FROM historical_hourly_trends ORDER BY hour_bucket
```

**Metrics Displayed**:
- **total_events**: Raw event count per hour
- **events_24h_avg**: 24-hour moving average
- **total_bytes**: Hourly data volume

**Insights**:
- **Moving average smooths noise**: See true trends
- **Daily patterns**: Peak hours vs off-peak
- **Anomalies**: Sudden spikes or drops

---

### B. Hourly Activity Timeline

#### Chart: Edit Activity by Hour (Bar Chart)
```sql
SELECT * FROM historical_hourly_patterns ORDER BY hour_bucket
```

**Metrics**:
- `human_events`: Human-made edits
- `bot_events`: Bot-made edits

**Visualization**: Stacked bar chart

**Typical Patterns**:
- **Human peak**: 12:00-20:00 UTC (Europe/Americas)
- **Bot activity**: More consistent 24/7
- **Bot/Human ratio**: Usually 30-70%

---

### C. Top Contributors (Table)

```sql
SELECT * FROM historical_top_contributors ORDER BY edit_count DESC LIMIT 50
```

**Columns**:
- `user`: Username
- `is_bot`: Boolean
- `edit_count`: Total edits
- `total_bytes`: Content contributed
- `pages_created`: New articles

**Insights**:
- Identify power users
- Bot vs human productivity
- Content creators vs editors

---

### D. Language Distribution (Table)

```sql
SELECT * FROM historical_language_distribution ORDER BY edit_count DESC
```

**Columns**:
- `language`: Language code
- `project`: wikipedia/wikidata/commons
- `edit_count`, `total_bytes`, `bot_edits`, `new_pages`

**Geographic Insights**:
- **en**: English (largest)
- **de, fr, es**: Major European
- **ja, zh**: Asian languages
- **ar**: Arabic

---

### E. Server Rankings (Table)

```sql
SELECT * FROM historical_server_rankings ORDER BY rank
```

**Columns**:
- `server_name`: Full server URL
- `rank`: 1-50 ranking
- `percentile`: Performance percentile
- `edit_count`, `total_bytes`, `unique_users`

**Insights**:
- **www.wikidata.org**: Usually #1 (data edits)
- **en.wikipedia.org**: #2-3 (content edits)
- **Unique users**: Indicates community size

---

## 🔧 Technical Details

### Dashboard Configuration

**Hardcoded Constants** (in `dashboard/app.py`):
```python
REFRESH_RATE = 8  # seconds
LOOKBACK_MINUTES = 30  # minutes
TOP_N = 12  # items in rankings
RECENT_LIMIT = 400  # events for scatter plot
USER_THRESHOLD = 10  # minimum edits for histogram
```

### Database Queries Performance

**Real-time Queries**:
```
Traffic volume: <50ms
Recent changes: <100ms
Aggregations: <300ms
Total page load: ~500ms
```

**Historical Queries**:
```
Hourly patterns: <100ms (low row count)
Top contributors: <200ms
Language distribution: <150ms
```

### Auto-Refresh Mechanism

```python
# At end of app.py
time.sleep(REFRESH_RATE)
try:
    st.rerun()  # Streamlit 1.30+
except:
    st.experimental_rerun()  # Fallback
```

---

## 🎯 Use Cases & Interpretation Guide

### Use Case 1: Monitoring System Health

**Check These:**
- ✅ Live Velocity: Should be 5-20 events/s
- ✅ Events (window): Should increase steadily
- ✅ Traffic Volume: No sudden drops to zero

**Red Flags**:
- ❌ Velocity = 0 for >5 minutes → Producer down
- ❌ Events stopped growing → Processor issue
- ❌ Database query errors → RDS connectivity

### Use Case 2: Content Trend Analysis

**Analyze**:
- Most Edited Pages: What topics are trending?
- Language Breakdown: Which communities are active?
- Edit Severity: Major updates or minor fixes?

**Example Insights**:
- Spike in "Ukraine" edits → News event
- High bot activity → Maintenance period
- Many minor edits → Vandalism cleanup

### Use Case 3: Capacity Planning

**Monitor**:
- Live Velocity trends over time
- Consumer lag (via Kafka tools)
- Database CPU and connections

**Scaling Triggers**:
- Sustained velocity >15 events/s → Consider adding replicas
- Consumer lag >5000 → Add processors
- DB CPU >70% → Upgrade RDS instance

---

## 🐛 Troubleshooting

### Issue: Dashboard shows "No data"

**Diagnosis**:
```bash
# Check database
psql -c "SELECT COUNT(*) FROM realtime_recent_changes;"

# Should return >0
```

**Solutions**:
1. Verify processing containers running
2. Check Kafka producer logs
3. Restart processing: `docker compose restart processing`

### Issue: Dashboard slow/laggy

**Possible Causes**:
- Too many concurrent users
- Database under load
- Network latency

**Solutions**:
1. Increase `REFRESH_RATE` to 15-30s
2. Reduce `RECENT_LIMIT` to 200
3. Add database indexes (already done)
4. Scale up RDS instance

### Issue: Charts not updating

**Check**:
1. Auto-refresh working? (Check logs)
2. Database connection active?
3. Recent data in tables?

**Solution**:
```bash
# Restart dashboard
docker compose restart dashboard
docker compose logs -f dashboard
```

---

## 📚 Advanced Features

### Custom SQL Queries

Dashboard connects to PostgreSQL, có thể extend với custom queries:

```python
# In dashboard/utils.py
custom_df = load_data("""
    SELECT server_name, AVG(bytes_changed) as avg_change
    FROM realtime_recent_changes
    WHERE event_time >= NOW() - INTERVAL '1 HOUR'
    GROUP BY server_name
    ORDER BY avg_change DESC
""")
```

### Exporting Data

```python
import pandas as pd

# Export to CSV
df = load_data("SELECT * FROM historical_hourly_patterns")
df.to_csv("hourly_patterns.csv", index=False)
```

### Custom Visualizations

```python
import plotly.graph_objects as go

fig = go.Figure()
fig.add_trace(go.Scatter(x=df['time'], y=df['value'], mode='lines'))
st.plotly_chart(fig)
```

---

## 🎨 Dashboard Customization

### Changing Colors

Edit `dashboard/utils.py`:
```python
def apply_custom_css():
    st.markdown("""
    <style>
        .metric-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            /* Change gradient colors */
        }
    </style>
    """, unsafe_allow_html=True)
```

### Adding New Charts

1. Add query in main section
2. Create Plotly figure
3. Call `st.plotly_chart(fig)`

---

## 📊 Performance Benchmarks

**Dashboard Load Time**:
```
First load: 2-3 seconds
Refresh: 0.5-1 seconds
Concurrent users: 10-20 (RDS limited)
```

**Query Performance**:
```
Simple aggregations: <100ms
Complex joins: <300ms
Full table scans: <1s (with retention)
```

---

**Document Version**: 2.0  
**Status**: Complete ✅  
**Next Update**: When new features added

    *   **Source:** `realtime_edits_severity`

9.  **Content Volume Change** (Bar Chart)
    *   **Title:** "Additions vs Deletions"
    *   **Metric:** Tổng số bytes được thêm vào so với bị xóa đi.
    *   **Dimension:** Loại thay đổi (Thêm/Xóa).
    *   **Source:** `realtime_content_volume_change`

### E. Leaderboards & Distribution

10. **Most Edited Pages** (Table)
    *   **Columns:** Tiêu đề trang, Server, Số chỉnh sửa, Bytes.
    *   **Insight:** Xác định các chủ đề đang thịnh hành hoặc gây tranh cãi ("Edit wars").
    *   **Source:** `realtime_content_leaderboard`

11. **Namespace Distribution** (Bar Chart)
    *   **Title:** "Edits by Namespace"
    *   **Metric:** Số lượng theo namespace (Main, Talk, User, v.v.).
    *   **Source:** `realtime_namespace_distribution`

### F. User Engagement

12. **User Engagement Distribution** (Histogram)
    *   **Title:** "Users with >= {N} edits"
    *   **Metric:** Phân phối tần suất số lượng chỉnh sửa của người dùng.
    *   **Filter:** Được điều khiển bởi thanh trượt "Power User Threshold".
    *   **Insight:** Xác định "Power Users" và các mô hình tương tác.
    *   **Source:** `realtime_user_stats`

### G. Live Monitoring ("The Battlefield")

13. **The Battlefield** (Scatter Plot)
    *   **Title:** "Edits Scattering (Size = Impact)"
    *   **X-Axis:** Thời gian sự kiện.
    *   **Y-Axis:** Chênh lệch độ dài (dòng thêm/xóa).
    *   **Bubble Size:** Tác động (Số bytes thay đổi tuyệt đối).
    *   **Color:** Xanh (Thêm), Đỏ (Xóa).
    *   **Insight:** Trực quan hóa các chỉnh sửa cá nhân trong thời gian thực, làm nổi bật các thay đổi nội dung lớn hoặc xóa hàng loạt.
    *   **Source:** `realtime_recent_changes`

14. **Blacklist Monitor** (Table)
    *   **Input:** Nhập văn bản để lọc từ khóa.
    *   **Function:** Lọc luồng dữ liệu thô trực tiếp cho các từ khóa cụ thể trong Tiêu đề hoặc Tên người dùng.
    *   **Source:** `realtime_recent_changes`

---

## 5. Xử lý dữ liệu (Spark Streaming)
Tất cả dữ liệu được xử lý bởi `processing/stream_job.py` sử dụng **Spark Structured Streaming**.

- **Windowing:** Hầu hết các tổng hợp sử dụng tumbling windows (mặc định: 1 phút) để nhóm các sự kiện.
- **Watermarking:** Được sử dụng để xử lý dữ liệu đến muộn.
- **Output:** Kết quả được ghi vào các bảng **PostgreSQL** (`realtime_*`) để dashboard truy vấn.
