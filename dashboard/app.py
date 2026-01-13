import time
import pandas as pd
import plotly.express as px
import streamlit as st
from utils import load_data, apply_custom_css

# --- CONFIGURATION ---
st.set_page_config(
    page_title="Wiki Real-time Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

apply_custom_css()

# --- HARDCODED DEFAULTS (No user controls) ---
REFRESH_RATE = 8
AUTO_REFRESH = True
LOOKBACK_MINUTES = 30
TOP_N = 12
RECENT_LIMIT = 400
ANALYSIS_TYPE = "Server" # Default dynamic chart
USER_THRESHOLD = 10     # Power user threshold

# --- MAIN LAYOUT ---
st.title("Wikipedia Real-time Changes Monitor")
st.caption(f"Live window: last {LOOKBACK_MINUTES} minutes | Auto refresh: 8s")

# --- DATA FETCHING ---
interval_param = (LOOKBACK_MINUTES,)

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

server_df = load_data(
    """
    SELECT server_name, COUNT(*) AS total_edits, SUM(ABS(bytes_changed)) AS total_bytes
    FROM realtime_recent_changes
    WHERE event_time >= NOW() - make_interval(mins => %s)
    GROUP BY server_name
    ORDER BY total_edits DESC
    LIMIT %s
    """,
    params=(LOOKBACK_MINUTES, TOP_N),
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
    params=(LOOKBACK_MINUTES, TOP_N),
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
    params=(LOOKBACK_MINUTES, TOP_N),
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
    params=(LOOKBACK_MINUTES, RECENT_LIMIT),
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
st.subheader(f"Dynamic Analysis: By {ANALYSIS_TYPE} 📈")

if not server_df.empty:
    fig_dynamic = px.bar(
        server_df,
        x='server_name',
        y='total_edits',
        color='server_name',
        title="Edits by Server",
        template="plotly_dark",
    )
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
    filtered_users = user_stats_df[user_stats_df['total_edits'] >= USER_THRESHOLD]
    fig_hist = px.histogram(
        filtered_users,
        x='total_edits',
        nbins=20,
        title=f"Users with >= {USER_THRESHOLD} edits",
        template="plotly_dark",
    )
    st.plotly_chart(fig_hist, use_container_width=True)
else:
    st.info("Waiting for user engagement data...")


# --- LIVE MONITORING ---
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

st.divider()
st.caption("Advanced Wiki Analytics Dashboard v3.0")


# --- AUTO REFRESH ---
time.sleep(REFRESH_RATE)
try:
    st.rerun()
except Exception:
    st.experimental_rerun()
