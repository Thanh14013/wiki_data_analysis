# Wikipedia Real-time Dashboard Report

Báo cáo này cung cấp một cái nhìn tổng quan toàn diện về bảng điều khiển **Wikipedia Real-time Changes Monitor**. Nó chi tiết hóa từng biểu đồ, số liệu và nguồn dữ liệu được sử dụng để trực quan hóa hoạt động trực tiếp của Wikipedia.

## 1. Tổng quan Dashboard
Dashboard (Bảng điều khiển) là một giao diện phân tích thời gian thực được xây dựng với **Streamlit** và **Plotly**. Nó kết nối với cơ sở dữ liệu **PostgreSQL** được nạp bởi một công việc **Spark Structured Streaming** (Lớp Speed của kiến trúc Lambda).

**Các tính năng chính:**
- **Refresh Rate**: Có thể tùy chỉnh (mặc định: 8s).
- **Lookback Window**: Cửa sổ phân tích có thể điều chỉnh (mặc định: 30 phút).
- **Auto-refresh**: Có thể bật/tắt cập nhật trực tiếp.

---

## 2. Các điều khiển tương tác & Tác động
Thanh bên của dashboard cung cấp một số điều khiển để lọc động và điều chỉnh dữ liệu hiển thị.

| Điều khiển | Loại | Khu vực tác động | Mô tả |
| :--- | :--- | :--- | :--- |
| **Refresh Rate** | Slider (2-60s) | **Hệ thống** | Kiểm soát tần suất dashboard tự động tải lại để lấy dữ liệu mới. |
| **Lookback Window** | Slider (1-180m) | **Tất cả biểu đồ** (trừ Live Monitoring) | Thiết lập phạm vi thời gian cho phân tích (ví dụ: "30 phút qua"). Ảnh hưởng đến tất cả các truy vấn SQL bằng cách lọc `window_start`. |
| **Top N** | Slider (5-50) | **Xếp hạng** | Giới hạn số lượng mục trong các bảng xếp hạng: <br>• *Top Servers* (Biểu đồ 6) <br>• *Top Languages* (Biểu đồ 7) <br>• *Most Edited Pages* (Biểu đồ 10) |
| **Recent events** | Slider (50-1000) | **Live Monitoring** | Giới hạn số lượng sự kiện thô được lấy cho *The Battlefield* (Biểu đồ 13) và *Blacklist Monitor* (Biểu đồ 14). |
| **Dynamic Chart Type** | Dropdown | **Dynamic Analysis** | Chuyển đổi hiển thị trong Phần A giữa: <br>• *Server* (Bar Chart) <br>• *User Type* (Pie Chart) <br>• *Action* (Area Chart) |
| **Blacklist Keyword** | Text Input | **Blacklist Monitor** | Lọc bảng *Blacklist Monitor* (Biểu đồ 14) để chỉ hiển thị các sự kiện khớp với từ khóa (trong Tiêu đề hoặc Người dùng). |
| **Power User Threshold** | Slider (1-100) | **User Engagement** | Lọc *User Engagement Histogram* (Biểu đồ 12) để chỉ hiển thị những người dùng có ít nhất số lượng chỉnh sửa này. |

---

## 3. Các chỉ số hiệu suất chính (KPIs)
Nằm ở đầu dashboard, các số liệu này cung cấp hình ảnh tức thì về hoạt động của hệ thống trong lookback window đã chọn.

| KPI | Mô tả | Bảng nguồn |
| :--- | :--- | :--- |
| **Events (window)** | Tổng số sự kiện thay đổi được xử lý trong window hiện tại. | `realtime_traffic_volume` |
| **Volume (window)** | Tổng kích thước thay đổi nội dung tính bằng Megabytes (MB). | `realtime_traffic_volume` |
| **Live Velocity** | Tốc độ xử lý hiện tại tính bằng **sự kiện mỗi giây**. | `realtime_content_velocity` |
| **Top Server** | Server Wikipedia cụ thể (ví dụ: `en.wikipedia`) có nhiều chỉnh sửa nhất. | `realtime_server_activity` |

---

## 4. Trực quan hóa & Biểu đồ

### A. Phần Dynamic Analysis
Một phần linh hoạt được điều khiển bởi dropdown "Dynamic Chart Type" trong thanh bên.

1.  **Edits by Server** (Bar Chart)
    *   **Metric:** Tổng số lượng chỉnh sửa trên mỗi server.
    *   **Dimension:** Tên Server.
    *   **Insight:** Xác định phiên bản ngôn ngữ/dự án nào đang hoạt động tích cực nhất.
    *   **Source:** `realtime_server_activity`

2.  **User Type Distribution** (Pie Chart)
    *   **Metric:** Tỷ lệ phần trăm chỉnh sửa bởi "Bot" so với "Human".
    *   **Dimension:** Loại người dùng (User Type).
    *   **Insight:** Tỷ lệ hoạt động tự động so với hoạt động hữu cơ.
    *   **Source:** `realtime_user_distribution`

3.  **Action Breakdown Over Time** (Area Chart)
    *   **Metric:** Số lượng hành động (chỉnh sửa, mới, log, v.v.).
    *   **Dimension:** Thời gian (trục x), Loại hành động (màu sắc).
    *   **Insight:** Xu hướng về *loại* hoạt động đang diễn ra trên nền tảng.
    *   **Source:** `realtime_action_breakdown`

### B. Time Series Analysis
Hai biểu đồ cạnh nhau theo dõi khối lượng và tốc độ theo thời gian.

4.  **Traffic Volume** (Area Chart)
    *   **Title:** "Bytes Changed Over Time"
    *   **Metric:** Tổng số bytes thay đổi.
    *   **X-Axis:** Thời gian (Window Start).
    *   **Source:** `realtime_traffic_volume`

5.  **Content Velocity** (Line Chart)
    *   **Title:** "Events per Second"
    *   **Metric:** Tốc độ thông lượng.
    *   **Insight:** Tải hệ thống và các đợt hoạt động cao điểm.
    *   **Source:** `realtime_content_velocity`

### C. Server & Language Overview
Giải quyết câu hỏi "ở đâu" của các chỉnh sửa.

6.  **Top Servers** (Bar Chart)
    *   **Title:** "Server Activity"
    *   **Metrics:** Độ dài thanh = Tổng số chỉnh sửa; Màu sắc = Tổng số Bytes.
    *   **Insight:** Tương quan khối lượng hoạt động với việc sử dụng kích thước dữ liệu.
    *   **Source:** `realtime_server_activity`

7.  **Language Breakdown** (Bar Chart)
    *   **Title:** "Top Languages"
    *   **Metrics:** Độ dài thanh = Số lượng; Màu sắc = Tổng số Bytes.
    *   **Insight:** Các ngôn ngữ chiếm ưu thế (ví dụ: `en`, `fr`, `de`).
    *   **Source:** `realtime_language_breakdown`

### D. Quality & Impact
Tập trung vào bản chất của các thay đổi.

8.  **Edit Severity** (Pie Chart)
    *   **Title:** "Major vs Minor"
    *   **Metric:** Tỷ lệ các chỉnh sửa được gắn cờ là "Minor" (Nhỏ).
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
