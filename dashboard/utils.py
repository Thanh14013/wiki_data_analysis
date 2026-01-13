import os
import sys
import pandas as pd
import psycopg2
import streamlit as st

# Ensure we can import from parent directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import get_settings

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

def apply_custom_css():
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
