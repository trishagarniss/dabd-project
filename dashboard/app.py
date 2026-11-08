"""
Dashboard Interaktif Analitik Penerbangan (F-13)
Streamlit Dashboard:
- Visualisasi peta telemetri pesawat
- Metrik bisnis / KPI delay
- Filter dan live refresh
"""

import os
import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="Flight Data Platform Analytics", layout="wide")

st.title("✈️ Global Flight Operations & Delay Prediction Platform")
st.markdown("Platform analitik real-time & batch terintegrasi Machine Learning (TBP DABD).")

# Data Gold Features / Mart
features_file = os.path.join(os.path.dirname(__file__), "..", "data", "gold", "flight_ml_features.csv")
airports_file = os.path.join(os.path.dirname(__file__), "..", "data", "reference", "airports_reference.csv")

if os.path.exists(features_file):
    df_flights = pd.read_csv(features_file)
else:
    df_flights = pd.DataFrame()

# Sidebar Filters (F-13 Requirement: Minimal 2 Filter)
st.sidebar.header("🔍 Filter Parameter")
hour_filter = st.sidebar.slider("Pilih Jam Operasional (Hour of Day)", 0, 23, (0, 23))

if not df_flights.empty:
    filtered_df = df_flights[(df_flights["hour_of_day"] >= hour_filter[0]) & (df_flights["hour_of_day"] <= hour_filter[1])]
    
    # KPI Cards (F-13 Requirement: Minimal 4 Metrik Bisnis)
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Pesawat Terpantau", f"{len(filtered_df):,} unit")
    with col2:
        avg_delay = filtered_df["arrival_delay_min"].mean()
        st.metric("Rata-rata Delay", f"{avg_delay:.1f} menit")
    with col3:
        avg_speed = filtered_df["velocity_kmh"].mean()
        st.metric("Rata-rata Kecepatan", f"{avg_speed:.0f} km/h")
    with col4:
        avg_alt = filtered_df["altitude_m"].mean()
        st.metric("Rata-rata Ketinggian", f"{avg_alt:.0f} m")

    st.subheader("📊 Distribusi Prediksi Delay Kedatangan")
    st.bar_chart(filtered_df.groupby("dest_airport")["arrival_delay_min"].mean().head(10))

    st.subheader("📋 Data Mart Penerbangan (Gold Layer)")
    st.dataframe(filtered_df.head(20), use_container_width=True)
else:
    st.warning("Data mart belum tersedia. Jalankan pipeline feature engineering terlebih dahulu.")
