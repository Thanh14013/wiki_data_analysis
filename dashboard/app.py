import os
import sys
import time
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import psycopg2
import streamlit as st

# Ensure we can import from parent directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import get_settings

# --- CONFIGURATION ---
st.set_page_config(
    page_title="Wiki Real-time Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown(
    """
<style>
    .metric-card {
        background-color: #1E1E1E;
        padding: 20px;
        border-radius: 10px;
        border: 1px solid #333;
        text-align: center;
    }
    .metric-value {
        font-size: 32px;
        font-weight: bold;
        color: #4CAF50;
    }
    .metric-label {
        font-size: 14px;
        color: #BBB;
    }
</style>
""",
    unsafe_allow_html=True,
)


def get_db_connection():
    settings = get_settings()
    return psycopg2.connect(settings.postgres.connection_string)


def load_data(query: str, params=None) -> pd.DataFrame:
    conn = get_db_connection()
    try:
        return pd.read_sql(query, conn, params=params)
    except Exception:
        return pd.DataFrame()
    finally:
        conn.close()



# --- SIDEBAR CONTROLS ---
st.sidebar.title("Wiki Analytics 🚀")
refresh_rate = st.sidebar.slider("Refresh Rate (seconds)", 2, 60, 8)
auto_refresh = st.sidebar.checkbox("Auto-refresh", value=True)
lookback_minutes = st.sidebar.slider("Lookback window (minutes)", 1, 180, 30)
top_n = st.sidebar.slider("Top N (leaderboards)", 5, 50, 12)
recent_limit = st.sidebar.slider("Recent events to display", 50, 1000, 400, step=50)

st.sidebar.markdown("### Analysis Controls")
analysis_type = st.sidebar.selectbox("Dynamic Chart Type", ["Server", "User Type", "Action"])
blacklist_keyword = st.sidebar.text_input("Blacklist Monitor (Keyword)", value="")
user_threshold = st.sidebar.slider("Power User Threshold (Edits)", 1, 100, 10)

st.sidebar.divider()
st.sidebar.markdown("### Status")
st.sidebar.success("🟢 System Online")
st.sidebar.info(f"Last updated: {time.strftime('%H:%M:%S')}")

# --- MAIN LAYOUT ---
st.title("Wikipedia Real-time Changes Monitor")
st.caption(f"Live window: last {lookback_minutes} minutes | Auto refresh: {'on' if auto_refresh else 'off'}")

# --- DATA FETCHING ---
interval_param = (lookback_minutes,)

traffic_df = load_data(
    """
    SELECT window_start, total_bytes, event_count, avg_bytes_per_event
    FROM realtime_traffic_volume
    WHERE window_start >= NOW() - make_interval(mins => %s)
    ORDER BY window_start DESC
    LIMIT 500
    """,
    params=interval_param,
)

user_df = load_data(
    """
    SELECT 
        CASE WHEN is_bot THEN 'Bot' ELSE 'Human' END as user_type, 
        COUNT(*) AS total_count
    FROM realtime_recent_changes
    WHERE event_time >= NOW() - make_interval(mins => %s)
    GROUP BY 1
    """,
    params=interval_param,
)

server_df = load_data(
    """
    SELECT server_name, COUNT(*) AS total_edits, SUM(ABS(bytes_changed)) AS total_bytes
    FROM realtime_recent_changes
    WHERE event_time >= NOW() - make_interval(mins => %s)
    GROUP BY server_name
    ORDER BY total_edits DESC
    LIMIT %s
    """,
    params=(lookback_minutes, top_n),
)

# Calculate velocity from traffic volume (assuming 10s window roughly, or just event count trend)
velocity_df = load_data(
    """
    SELECT window_start, (event_count / 10.0) as events_per_second, event_count
    FROM realtime_traffic_volume
    WHERE window_start >= NOW() - make_interval(mins => %s)
    ORDER BY window_start DESC
    LIMIT 500
    """,
    params=interval_param,
)

leaderboard_df = load_data(
    """
    SELECT title, server_name, COUNT(*) AS total_edits, SUM(ABS(bytes_changed)) AS total_bytes
    FROM realtime_recent_changes
    WHERE event_time >= NOW() - make_interval(mins => %s)
    GROUP BY title, server_name
    ORDER BY total_edits DESC
    LIMIT %s
    """,
    params=(lookback_minutes, top_n),
)

action_df = load_data(
    """
    SELECT date_trunc('minute', event_time) as window_start, type as action_type, COUNT(*) AS action_count
    FROM realtime_recent_changes
    WHERE event_time >= NOW() - make_interval(mins => %s)
    GROUP BY 1, 2
    ORDER BY 1 DESC
    LIMIT 500
    """,
    params=interval_param,
)

severity_df = load_data(
    """
    SELECT 
        CASE 
            WHEN ABS(bytes_changed) > 1000 THEN 'Major'
            WHEN ABS(bytes_changed) > 100 THEN 'Moderate'
            ELSE 'Minor' 
        END as edit_type, 
        COUNT(*) AS total_count
    FROM realtime_recent_changes
    WHERE event_time >= NOW() - make_interval(mins => %s)
    GROUP BY 1
    """,
    params=interval_param,
)

volume_change_df = load_data(
    """
    SELECT 
        CASE WHEN length_diff >= 0 THEN 'Addition' ELSE 'Deletion' END as change_type, 
        SUM(ABS(length_diff)) AS total_bytes, 
        COUNT(*) AS count
    FROM realtime_recent_changes
    WHERE event_time >= NOW() - make_interval(mins => %s)
    GROUP BY 1
    """,
    params=interval_param,
)

# Simplified Namespace (heuristic based on colon)
namespace_df = load_data(
    """
    SELECT 
        SPLIT_PART(title, ':', 1) as namespace, 
        COUNT(*) AS total_count
    FROM realtime_recent_changes
    WHERE event_time >= NOW() - make_interval(mins => %s)
    AND title LIKE '%%:%%'
    GROUP BY 1
    ORDER BY total_count DESC
    LIMIT 20
    """,
    params=interval_param,
)

language_df = load_data(
    """
    SELECT 
        SPLIT_PART(server_name, '.', 1) as language, 
        COUNT(*) AS total_count, 
        SUM(ABS(bytes_changed)) AS total_bytes
    FROM realtime_recent_changes
    WHERE event_time >= NOW() - make_interval(mins => %s)
    GROUP BY 1
    ORDER BY total_count DESC
    LIMIT %s
    """,
    params=(lookback_minutes, top_n),
)

user_stats_df = load_data(
    """
    SELECT "user", COUNT(*) AS total_edits
    FROM realtime_recent_changes
    WHERE event_time >= NOW() - make_interval(mins => %s)
    GROUP BY "user"
    """,
    params=interval_param,
)

recent_changes_df = load_data(
    """
    SELECT *
    FROM realtime_recent_changes
    WHERE event_time >= NOW() - make_interval(mins => %s)
    ORDER BY event_time DESC
    LIMIT %s
    """,
    params=(lookback_minutes, recent_limit),
)

# Normalize timestamps for plotting
for df in [traffic_df, velocity_df, action_df]:
    if not df.empty and 'window_start' in df.columns:
        df['window_start'] = pd.to_datetime(df['window_start'])

if not recent_changes_df.empty and 'event_time' in recent_changes_df.columns:
    recent_changes_df['event_time'] = pd.to_datetime(recent_changes_df['event_time'])

# --- KPI ROW ---
kpi1, kpi2, kpi3, kpi4 = st.columns(4)

total_events = int(traffic_df['event_count'].sum()) if not traffic_df.empty else 0
total_bytes = float(traffic_df['total_bytes'].sum()) if not traffic_df.empty else 0
current_velocity = float(velocity_df.iloc[0]['events_per_second']) if not velocity_df.empty else 0
top_server = server_df.iloc[0]['server_name'] if not server_df.empty else "N/A"

with kpi1:
    st.markdown(
        f"""<div class=\"metric-card\"><div class=\"metric-value\">{total_events:,}</div><div class=\"metric-label\">Events (window)</div></div>""",
        unsafe_allow_html=True,
    )
with kpi2:
    st.markdown(
        f"""<div class=\"metric-card\"><div class=\"metric-value\">{total_bytes/1024/1024:.2f} MB</div><div class=\"metric-label\">Volume (window)</div></div>""",
        unsafe_allow_html=True,
    )
with kpi3:
    st.markdown(
        f"""<div class=\"metric-card\"><div class=\"metric-value\">{current_velocity:.1f} /s</div><div class=\"metric-label\">Live Velocity</div></div>""",
        unsafe_allow_html=True,
    )
with kpi4:
    st.markdown(
        f"""<div class=\"metric-card\"><div class=\"metric-value\">{top_server}</div><div class=\"metric-label\">Top Server</div></div>""",
        unsafe_allow_html=True,
    )

st.divider()

# --- DYNAMIC MULTIDIMENSIONAL ANALYSIS ---
st.subheader(f"Dynamic Analysis: By {analysis_type} 📈")

fig_dynamic = None
if analysis_type == "Server" and not server_df.empty:
    fig_dynamic = px.bar(
        server_df,
        x='server_name',
        y='total_edits',
        color='server_name',
        title="Edits by Server",
        template="plotly_dark",
    )
elif analysis_type == "User Type" and not user_df.empty:
    fig_dynamic = px.pie(
        user_df,
        values='total_count',
        names='user_type',
        title="User Type Distribution",
        hole=0.5,
        template="plotly_dark",
    )
elif analysis_type == "Action" and not action_df.empty:
    latest_actions = action_df.sort_values('window_start')
    fig_dynamic = px.area(
        latest_actions,
        x='window_start',
        y='action_count',
        color='action_type',
        title="Action Breakdown Over Time",
        template="plotly_dark",
    )

if fig_dynamic is not None:
    st.plotly_chart(fig_dynamic, use_container_width=True)
else:
    st.info("Waiting for data...")


# --- TIME SERIES BLOCK ---
col_traffic, col_velocity = st.columns(2)

with col_traffic:
    st.subheader("Traffic Volume")
    if not traffic_df.empty:
        traffic_sorted = traffic_df.sort_values('window_start')
        fig = px.area(
            traffic_sorted,
            x='window_start',
            y='total_bytes',
            title="Bytes Changed Over Time",
            template="plotly_dark",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No traffic data yet.")

with col_velocity:
    st.subheader("Content Velocity")
    if not velocity_df.empty:
        vel_sorted = velocity_df.sort_values('window_start')
        fig = px.line(
            vel_sorted,
            x='window_start',
            y='events_per_second',
            title="Events per Second",
            template="plotly_dark",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No velocity data yet.")


# --- SERVER AND LANGUAGE OVERVIEW ---
col_server, col_lang = st.columns(2)

with col_server:
    st.subheader("Top Servers (Edits & Bytes)")
    if not server_df.empty:
        fig = px.bar(
            server_df,
            x='server_name',
            y='total_edits',
            color='total_bytes',
            color_continuous_scale='Viridis',
            labels={'total_bytes': 'Total Bytes'},
            title="Server Activity",
            template="plotly_dark",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Server activity unavailable.")

with col_lang:
    st.subheader("Language Breakdown")
    if not language_df.empty:
        fig = px.bar(
            language_df,
            x='language',
            y='total_count',
            color='total_bytes',
            color_continuous_scale='Bluered',
            title="Top Languages",
            template="plotly_dark",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Language data unavailable.")


# --- QUALITY & IMPACT ---
col_severity, col_volume = st.columns(2)

with col_severity:
    st.subheader("Edit Severity")
    if not severity_df.empty:
        fig = px.pie(
            severity_df,
            names='edit_type',
            values='total_count',
            title="Major vs Minor",
            hole=0.4,
            template="plotly_dark",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No severity stats yet.")

with col_volume:
    st.subheader("Content Volume Change")
    if not volume_change_df.empty:
        fig = px.bar(
            volume_change_df,
            x='change_type',
            y='total_bytes',
            color='count',
            title="Additions vs Deletions",
            template="plotly_dark",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No volume change data yet.")


# --- LEADERBOARDS & NAMESPACES ---
col_leader, col_namespace = st.columns([2, 1])

with col_leader:
    st.subheader("Most Edited Pages")
    if not leaderboard_df.empty:
        st.dataframe(
            leaderboard_df.rename(
                columns={'total_edits': 'Edits', 'total_bytes': 'Bytes', 'server_name': 'Server'}
            ),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Leaderboard will appear when data arrives.")

with col_namespace:
    st.subheader("Namespace Distribution")
    if not namespace_df.empty:
        fig = px.bar(
            namespace_df,
            x='namespace',
            y='total_count',
            title="Edits by Namespace",
            template="plotly_dark",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No namespace data yet.")


# --- USER ENGAGEMENT ---
st.subheader("User Engagement Distribution")
if not user_stats_df.empty:
    filtered_users = user_stats_df[user_stats_df['total_edits'] >= user_threshold]
    fig_hist = px.histogram(
        filtered_users,
        x='total_edits',
        nbins=20,
        title=f"Users with >= {user_threshold} edits",
        template="plotly_dark",
    )
    st.plotly_chart(fig_hist, use_container_width=True)
else:
    st.info("Waiting for user engagement data...")


# --- LIVE MONITORING ---
col_battle, col_blacklist = st.columns([2, 1])

with col_battle:
    st.subheader("⚔️ The Battlefield (Live Edits Impact)")
    if not recent_changes_df.empty:
        recent_changes_df['impact'] = recent_changes_df['bytes_changed'].abs().clip(lower=5, upper=500)
        recent_changes_df['direction'] = recent_changes_df['length_diff'].apply(lambda x: 'Addition' if x > 0 else 'Deletion')
        fig_battle = px.scatter(
            recent_changes_df,
            x='event_time',
            y='length_diff',
            size='impact',
            color='direction',
            hover_data=['title', 'user', 'server_name'],
            color_discrete_map={'Addition': '#00CC96', 'Deletion': '#EF553B'},
            template="plotly_dark",
            title="Edits Scattering (Size = Impact)",
        )
        st.plotly_chart(fig_battle, use_container_width=True)
    else:
        st.info("No live changes yet.")

with col_blacklist:
    st.subheader(f"🛡️ Blacklist Monitor (Keyword: '{blacklist_keyword}')")
    if not recent_changes_df.empty:
        display_cols = ['event_time', 'server_name', 'user', 'title', 'length_diff', 'type']
        if blacklist_keyword:
            mask = recent_changes_df['title'].str.contains(blacklist_keyword, case=False, na=False) | recent_changes_df['user'].str.contains(blacklist_keyword, case=False, na=False)
            monitor_df = recent_changes_df[mask]
        else:
            monitor_df = recent_changes_df.head(20)

        st.dataframe(monitor_df[display_cols], use_container_width=True, hide_index=True)
    else:
        st.info("No recent changes to monitor.")


st.divider()
st.caption("Advanced Wiki Analytics Dashboard v3.0")


# --- AUTO REFRESH ---
if auto_refresh:
    time.sleep(refresh_rate)
    try:
        st.rerun()
    except Exception:
        st.experimental_rerun()
