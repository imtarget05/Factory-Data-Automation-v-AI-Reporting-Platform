#!/usr/bin/env python3
"""
Smart Manufacturing Platform - Streamlit Dashboard
Main entry point for the interactive dashboard.
"""

import os
import sys
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ai.reporting import AIReportGenerator
from app.etl.kpi_engine import calculate_all_kpis
from app.etl.pipeline import run_etl
from app.reports.alert_system import AlertManager
from app.reports.exporter import ReportExporter
from app.utils.config import FACTORY_NAME, PRODUCTION_LINES

# Page configuration
st.set_page_config(
    page_title="Smart Manufacturing Platform",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown(
    """
<style>
    .main-header { font-size: 2rem; font-weight: 700; color: #1a237e; margin-bottom: 1rem; }
    .metric-card { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                   padding: 1.5rem; border-radius: 10px; color: white; text-align: center; }
    .metric-card-green { background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); }
    .metric-card-orange { background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); }
    .metric-card-blue { background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); }
    .alert-critical { background-color: #ffebee; border-left: 4px solid #c62828; padding: 0.5rem; margin: 0.3rem 0; }
    .alert-warning { background-color: #fff8e1; border-left: 4px solid #f9a825; padding: 0.5rem; margin: 0.3rem 0; }
    .section-header { font-size: 1.3rem; font-weight: 600; color: #283593; margin-top: 1.5rem; margin-bottom: 0.8rem; }
    .status-running { color: #2e7d32; font-weight: bold; }
    .status-idle { color: #f9a825; font-weight: bold; }
    .status-maintenance { color: #1565c0; font-weight: bold; }
    .status-failure { color: #c62828; font-weight: bold; }
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_data(ttl=300)
def load_and_compute():
    """Load data, compute KPIs, and generate alerts. Cached for 5 minutes."""
    datasets = run_etl()
    if not datasets:
        return None, None, [], {}

    kpis = calculate_all_kpis(datasets)
    alert_mgr = AlertManager()
    alerts = alert_mgr.check_all(datasets, kpis)
    alert_dicts = [a.to_dict() for a in alerts]

    return datasets, kpis, alert_dicts, alert_mgr.get_summary()


def overview_page(datasets, kpis, alerts, alert_summary):
    """Render the Overview page."""
    st.markdown('<h1 class="main-header">📊 Factory Overview</h1>', unsafe_allow_html=True)

    # Top KPI Cards
    col1, col2, col3, col4 = st.columns(4)

    daily_prod = kpis.get("daily_production")
    today_prod = daily_prod.iloc[-1] if daily_prod is not None and not daily_prod.empty else None

    with col1:
        if today_prod is not None:
            st.markdown(
                f"""
            <div class="metric-card metric-card-green">
                <h3 style="margin:0;font-size:0.9rem">Today's Output</h3>
                <p style="margin:0;font-size:2rem;font-weight:bold">{today_prod["Total_Actual"]:,.0f}</p>
                <p style="margin:0;font-size:0.8rem">Target: {today_prod["Total_Target"]:,.0f}</p>
            </div>
            """,
                unsafe_allow_html=True,
            )

    with col2:
        if today_prod is not None:
            st.markdown(
                f"""
            <div class="metric-card metric-card-orange">
                <h3 style="margin:0;font-size:0.9rem">Achievement</h3>
                <p style="margin:0;font-size:2rem;font-weight:bold">{today_prod["Achievement_Rate_pct"]:.1f}%</p>
                <p style="margin:0;font-size:0.8rem">Target: 100%</p>
            </div>
            """,
                unsafe_allow_html=True,
            )

    with col3:
        if today_prod is not None:
            st.markdown(
                f"""
            <div class="metric-card">
                <h3 style="margin:0;font-size:0.9rem">Reject Rate</h3>
                <p style="margin:0;font-size:2rem;font-weight:bold">{today_prod["Reject_Rate_pct"]:.2f}%</p>
                <p style="margin:0;font-size:0.8rem">Threshold: 5%</p>
            </div>
            """,
                unsafe_allow_html=True,
            )

    with col4:
        oee = kpis.get("oee")
        oee_val = oee.iloc[-1]["OEE_pct"] if oee is not None and not oee.empty else 0
        st.markdown(
            f"""
        <div class="metric-card metric-card-blue">
            <h3 style="margin:0;font-size:0.9rem">OEE Today</h3>
            <p style="margin:0;font-size:2rem;font-weight:bold">{oee_val:.1f}%</p>
            <p style="margin:0;font-size:0.8rem">Target: 85%</p>
        </div>
        """,
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # Two columns for charts
    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown(
            '<p class="section-header">📈 Production Trend (Last 30 Days)</p>',
            unsafe_allow_html=True,
        )
        if daily_prod is not None and len(daily_prod) > 1:
            recent = daily_prod.tail(30)
            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=recent["Date"],
                    y=recent["Total_Actual"],
                    mode="lines+markers",
                    name="Actual",
                    line=dict(color="#4CAF50", width=3),
                    fill="tozeroy",
                    fillcolor="rgba(76, 175, 80, 0.1)",
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=recent["Date"],
                    y=recent["Total_Target"],
                    mode="lines",
                    name="Target",
                    line=dict(color="#FF5722", width=2, dash="dash"),
                )
            )
            fig.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0), hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)

    with col_right:
        st.markdown('<p class="section-header">📊 Reject Rate Trend</p>', unsafe_allow_html=True)
        if daily_prod is not None and len(daily_prod) > 1:
            recent = daily_prod.tail(30)
            fig = go.Figure()
            fig.add_trace(
                go.Bar(
                    x=recent["Date"],
                    y=recent["Reject_Rate_pct"],
                    name="Reject Rate",
                    marker_color=[
                        "#c62828" if v > 5 else "#4CAF50" for v in recent["Reject_Rate_pct"]
                    ],
                )
            )
            fig.add_hline(y=5, line_dash="dash", line_color="red", annotation_text="Threshold (5%)")
            fig.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0), hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)

    # Alerts section
    st.markdown("---")
    st.markdown('<p class="section-header">🔔 Active Alerts</p>', unsafe_allow_html=True)

    if alerts:
        for a in alerts[:8]:
            level = a.get("level", "INFO")
            css_class = "alert-critical" if level == "CRITICAL" else "alert-warning"
            icon = "🚨" if level == "CRITICAL" else "⚠️"
            st.markdown(
                f'<div class="{css_class}">{icon} <b>[{level}]</b> {a["category"]}: {a["message"]}</div>',
                unsafe_allow_html=True,
            )
    else:
        st.info("✅ No active alerts. All systems operating normally.")

    # Worker Productivity Summary
    st.markdown("---")
    st.markdown(
        '<p class="section-header">👷 Worker Productivity (Top 10)</p>', unsafe_allow_html=True
    )
    worker_df = datasets.get("workers")
    if worker_df is not None and not worker_df.empty:
        worker_daily = (
            worker_df.groupby("Worker_ID")
            .agg(
                Hours_Worked=("Hours_Worked", "sum"),
                Units_Produced=("Units_Produced", "sum"),
                Defects_Caused=("Defects_Caused", "sum"),
            )
            .reset_index()
        )
        worker_daily["Units_per_Hour"] = (
            worker_daily["Units_Produced"] / worker_daily["Hours_Worked"].clip(lower=1)
        ).round(1)
        worker_daily["Defect_Rate_pct"] = (
            worker_daily["Defects_Caused"] / worker_daily["Units_Produced"].clip(lower=1) * 100
        ).round(1)
        top_workers = worker_daily.nlargest(10, "Units_per_Hour")

        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                x=top_workers["Worker_ID"],
                y=top_workers["Units_per_Hour"],
                name="Units/Hour",
                marker_color="#4CAF50",
            )
        )
        fig.update_layout(
            height=250,
            margin=dict(l=0, r=0, t=10, b=0),
            yaxis_title="Units per Hour",
            xaxis_title="",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No worker data available.")

    # Machine status summary
    st.markdown("---")
    st.markdown('<p class="section-header">🔧 Machine Status Overview</p>', unsafe_allow_html=True)

    mach_util = kpis.get("machine_utilization")
    if mach_util is not None and not mach_util.empty:
        latest_mach = mach_util[mach_util["Date"] == mach_util["Date"].max()]
        if not latest_mach.empty:
            status_counts = {
                "Running": latest_mach["Running_Count"].sum(),
                "Idle": latest_mach["Idle_Count"].sum(),
                "Maintenance": latest_mach["Maint_Count"].sum(),
                "Failure": latest_mach["Failure_Count"].sum(),
            }
            total = sum(status_counts.values())

            cols = st.columns(5)
            colors = {
                "Running": "#4CAF50",
                "Idle": "#FFC107",
                "Maintenance": "#2196F3",
                "Failure": "#F44336",
            }
            for i, (status, count) in enumerate(status_counts.items()):
                with cols[i]:
                    pct = (count / total * 100) if total > 0 else 0
                    st.markdown(
                        f"""
                    <div style="text-align:center; padding:0.5rem">
                        <p style="font-size:1.5rem; font-weight:bold; color:{colors[status]}; margin:0">{count}</p>
                        <p style="font-size:0.8rem; margin:0">{status} ({pct:.0f}%)</p>
                    </div>
                    """,
                        unsafe_allow_html=True,
                    )

            # Pie chart
            with cols[4]:
                fig = go.Figure(
                    data=[
                        go.Pie(
                            labels=list(status_counts.keys()),
                            values=list(status_counts.values()),
                            marker_colors=list(colors.values()),
                            hole=0.4,
                        )
                    ]
                )
                fig.update_layout(height=150, margin=dict(l=0, r=0, t=0, b=0), showlegend=False)
                st.plotly_chart(fig, use_container_width=True)


def production_page(datasets, kpis):
    """Render the Production page."""
    st.markdown('<h1 class="main-header">🏭 Production Analytics</h1>', unsafe_allow_html=True)

    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        selected_line = st.selectbox("Production Line", ["All"] + PRODUCTION_LINES)
    with col2:
        selected_shift = st.selectbox("Shift", ["All", "Morning", "Afternoon", "Night"])

    prod_df = datasets.get("production")
    if prod_df is not None and not prod_df.empty:
        df = prod_df.copy()
        df["Date"] = pd.to_datetime(df["Date"])

        if selected_line != "All":
            df = df[df["Line"] == selected_line]
        if selected_shift != "All":
            df = df[df["Shift"] == selected_shift]

        # Summary metrics
        total_target = df["Target_Qty"].sum()
        total_actual = df["Actual_Qty"].sum()
        total_good = df["Good_Qty"].sum()
        total_reject = df["Reject_Qty"].sum()

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Target", f"{total_target:,.0f}")
        col2.metric("Total Actual", f"{total_actual:,.0f}")
        col3.metric(
            "Good Products",
            f"{total_good:,.0f}",
            delta=f"{(total_good / total_actual * 100):.1f}%" if total_actual > 0 else "0%",
        )
        col4.metric(
            "Total Reject",
            f"{total_reject:,.0f}",
            delta=f"{(total_reject / total_actual * 100):.1f}%" if total_actual > 0 else "0%",
            delta_color="inverse",
        )

        st.markdown("---")

        # Charts
        col_left, col_right = st.columns(2)

        with col_left:
            st.markdown(
                '<p class="section-header">Daily Production by Line</p>', unsafe_allow_html=True
            )
            daily_line = (
                df.groupby(["Date", "Line"])
                .agg(Actual=("Actual_Qty", "sum"), Target=("Target_Qty", "sum"))
                .reset_index()
            )

            fig = px.bar(daily_line, x="Date", y="Actual", color="Line", title="", height=350)
            fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)

        with col_right:
            st.markdown(
                '<p class="section-header">Production by Product</p>', unsafe_allow_html=True
            )
            by_product = (
                df.groupby("Product")
                .agg(Actual=("Actual_Qty", "sum"), Target=("Target_Qty", "sum"))
                .reset_index()
                .sort_values("Actual", ascending=True)
            )

            fig = px.bar(
                by_product,
                y="Product",
                x="Actual",
                orientation="h",
                height=350,
                color="Actual",
                color_continuous_scale="viridis",
            )
            fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

        # Shift analysis
        st.markdown('<p class="section-header">Shift Performance</p>', unsafe_allow_html=True)
        shift_perf = (
            df.groupby(["Date", "Shift"])
            .agg(
                Actual=("Actual_Qty", "sum"),
                Target=("Target_Qty", "sum"),
                Reject=("Reject_Qty", "sum"),
            )
            .reset_index()
        )
        shift_perf["Achievement"] = (
            shift_perf["Actual"] / shift_perf["Target"].replace(0, 1) * 100
        ).round(1)

        fig = px.line(
            shift_perf, x="Date", y="Achievement", color="Shift", markers=True, height=300
        )
        fig.add_hline(y=90, line_dash="dash", line_color="green", annotation_text="Target 90%")
        fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)


def quality_page(datasets, kpis):
    """Render the Quality page."""
    st.markdown('<h1 class="main-header">✅ Quality Analytics</h1>', unsafe_allow_html=True)

    defect = kpis.get("defect_analysis", {})

    col1, col2 = st.columns(2)

    with col1:
        st.markdown(
            '<p class="section-header">Defects by Type (Pareto)</p>', unsafe_allow_html=True
        )
        by_type = defect.get("by_type")
        if by_type is not None and not by_type.empty:
            by_type["Cumulative_pct"] = (
                by_type["Total_Defects"].cumsum() / by_type["Total_Defects"].sum() * 100
            ).round(1)

            fig = go.Figure()
            fig.add_trace(
                go.Bar(
                    x=by_type["Defect_Type"],
                    y=by_type["Total_Defects"],
                    name="Defects",
                    marker_color="steelblue",
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=by_type["Defect_Type"],
                    y=by_type["Cumulative_pct"],
                    name="Cumulative %",
                    yaxis="y2",
                    line=dict(color="red", width=2),
                    mode="lines+markers",
                )
            )
            fig.update_layout(
                height=350,
                yaxis=dict(title="Defect Count"),
                yaxis2=dict(title="Cumulative %", overlaying="y", side="right", range=[0, 100]),
                margin=dict(l=0, r=0, t=10, b=0),
                hovermode="x unified",
            )
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown(
            '<p class="section-header">Defect Severity Distribution</p>', unsafe_allow_html=True
        )
        by_severity = defect.get("by_severity")
        if by_severity is not None and not by_severity.empty:
            colors = {"Minor": "#4CAF50", "Major": "#FF9800", "Critical": "#F44336"}
            fig = px.pie(
                by_severity,
                values="Total_Defects",
                names="Severity",
                color="Severity",
                color_discrete_map=colors,
                hole=0.4,
                height=350,
            )
            fig.update_traces(textposition="outside", textinfo="percent+label")
            fig.update_layout(margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig, use_container_width=True)

    # Daily defect trend
    st.markdown('<p class="section-header">Daily Defect Rate Trend</p>', unsafe_allow_html=True)
    daily_defect = defect.get("daily")
    if daily_defect is not None and not daily_defect.empty:
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=daily_defect["Date"],
                y=daily_defect["Defect_Rate_pct"],
                mode="lines+markers",
                name="Defect Rate",
                line=dict(color="#F44336", width=2),
                fill="tozeroy",
                fillcolor="rgba(244, 67, 54, 0.1)",
            )
        )
        fig.add_hline(y=5, line_dash="dash", line_color="orange", annotation_text="Warning (5%)")
        fig.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0), hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)

    # Quality heatmap
    qual_df = datasets.get("quality")
    if qual_df is not None and not qual_df.empty:
        st.markdown(
            '<p class="section-header">Defect Heatmap (Product × Defect Type)</p>',
            unsafe_allow_html=True,
        )
        heatmap_data = (
            qual_df.groupby(["Product", "Defect_Type"])["Defect_Count"].sum().unstack(fill_value=0)
        )
        fig = px.imshow(
            heatmap_data, text_auto=True, aspect="auto", color_continuous_scale="Reds", height=400
        )
        fig.update_layout(margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, use_container_width=True)


def inventory_page(datasets, kpis):
    """Render the Inventory page."""
    st.markdown('<h1 class="main-header">📦 Inventory Management</h1>', unsafe_allow_html=True)

    inv_kpi = kpis.get("inventory_kpi")
    if inv_kpi is not None and not inv_kpi.empty:
        latest = inv_kpi.iloc[-1]

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Stock", f"{latest['Total_Stock']:,.0f}")
        col2.metric("Stock Value", f"${latest['Stock_Value']:,.2f}")
        col3.metric(
            "Products Below Reorder",
            f"{latest['Products_Below_Reorder']:.0f}",
            delta="-",
            delta_color="inverse",
        )
        col4.metric("Avg Stock Level", f"{latest['Avg_Stock']:,.0f}")

        st.markdown("---")

        # Stock trend
        st.markdown('<p class="section-header">Total Stock Trend</p>', unsafe_allow_html=True)
        fig = px.line(
            inv_kpi, x="Date", y="Total_Stock", markers=True, labels={"Total_Stock": "Stock Level"}
        )
        fig.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0), hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)

        # Stock by product
        st.markdown(
            '<p class="section-header">Current Stock by Product</p>', unsafe_allow_html=True
        )
        inv_raw = datasets.get("inventory")
        if inv_raw is not None and not inv_raw.empty:
            latest_inv = inv_raw.copy()
            latest_inv["Date"] = pd.to_datetime(latest_inv["Date"])
            latest_date = latest_inv["Date"].max()
            current = latest_inv[latest_inv["Date"] == latest_date]

            current = current.sort_values("Stock_Qty", ascending=True)

            fig = px.bar(
                current,
                y="Product",
                x="Stock_Qty",
                orientation="h",
                color="Stock_Qty",
                color_continuous_scale="RdYlGn",
                text="Stock_Qty",
                height=400,
            )
            fig.add_vline(x=200, line_dash="dash", line_color="red", annotation_text="Alert (200)")
            fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

        # ABC Analysis
        st.markdown(
            '<p class="section-header">ABC Analysis (Stock Value)</p>', unsafe_allow_html=True
        )
        if inv_raw is not None:
            latest_val = inv_raw.copy()
            latest_val["Date"] = pd.to_datetime(latest_val["Date"])
            latest_date = latest_val["Date"].max()
            current_val = latest_val[latest_val["Date"] == latest_date].copy()
            current_val["Stock_Value"] = current_val["Stock_Qty"] * current_val["Unit_Price"]
            current_val = current_val.sort_values("Stock_Value", ascending=False)
            current_val["Cumulative_Value"] = (
                current_val["Stock_Value"].cumsum() / current_val["Stock_Value"].sum() * 100
            )

            def abc_class(val):
                if val <= 70:
                    return "A"
                elif val <= 90:
                    return "B"
                else:
                    return "C"

            current_val["ABC_Class"] = current_val["Cumulative_Value"].apply(abc_class)

            abc_counts = current_val["ABC_Class"].value_counts()

            fig = go.Figure()
            fig.add_trace(
                go.Bar(
                    x=current_val["Product"],
                    y=current_val["Stock_Value"],
                    marker_color=current_val["ABC_Class"].map(
                        {"A": "#c62828", "B": "#f9a825", "C": "#4CAF50"}
                    ),
                    name="Stock Value",
                )
            )
            fig.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig, use_container_width=True)

            st.info(
                f"ABC Classification: A (High Value)={abc_counts.get('A', 0)} items, "
                f"B (Medium)={abc_counts.get('B', 0)} items, C (Low)={abc_counts.get('C', 0)} items"
            )


def machine_page(datasets, kpis):
    """Render the Machine page."""
    st.markdown('<h1 class="main-header">🔧 Machine Monitoring</h1>', unsafe_allow_html=True)

    mach_util = kpis.get("machine_utilization")
    if mach_util is not None and not mach_util.empty:
        latest = mach_util[mach_util["Date"] == mach_util["Date"].max()]

        # Machine status cards
        st.markdown('<p class="section-header">Machine Status</p>', unsafe_allow_html=True)

        mach_raw = datasets.get("machine")
        if mach_raw is not None:
            latest_mach = mach_raw.copy()
            latest_mach["Date"] = pd.to_datetime(latest_mach["Date"])
            latest_date = latest_mach["Date"].max()
            current_mach = latest_mach[latest_mach["Date"] == latest_date]

            status_summary = (
                current_mach.groupby("Machine_ID")["Status"]
                .apply(
                    lambda x: x.value_counts().index[0] if not x.value_counts().empty else "Unknown"
                )
                .reset_index()
            )

            status_colors = {
                "Running": "#4CAF50",
                "Idle": "#FFC107",
                "Maintenance": "#2196F3",
                "Failure": "#F44336",
            }

            cols = st.columns(5)
            for i, (_, row) in enumerate(status_summary.iterrows()):
                with cols[i % 5]:
                    color = status_colors.get(row["Status"], "#999")
                    st.markdown(
                        f"""
                    <div style="padding:0.5rem; margin:0.3rem; border-radius:8px;
                                background:{color}20; border:2px solid {color}; text-align:center">
                        <p style="font-weight:bold; margin:0">{row["Machine_ID"]}</p>
                        <p style="color:{color}; font-weight:bold; margin:0">{row["Status"]}</p>
                    </div>
                    """,
                        unsafe_allow_html=True,
                    )

        st.markdown("---")

        # Utilization chart
        col1, col2 = st.columns(2)

        with col1:
            st.markdown(
                '<p class="section-header">Machine Utilization Rate</p>', unsafe_allow_html=True
            )
            latest_sorted = latest.sort_values("Utilization_pct", ascending=True)
            fig = px.bar(
                latest_sorted,
                y="Machine_ID",
                x="Utilization_pct",
                orientation="h",
                color="Utilization_pct",
                color_continuous_scale="RdYlGn",
                height=400,
                text="Utilization_pct",
            )
            fig.add_vline(x=70, line_dash="dash", line_color="orange", annotation_text="Target 70%")
            fig.update_layout(margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown('<p class="section-header">Downtime Analysis</p>', unsafe_allow_html=True)
            latest_sorted_dt = latest.sort_values("Total_Downtime", ascending=True)
            fig = px.bar(
                latest_sorted_dt,
                y="Machine_ID",
                x="Total_Downtime",
                orientation="h",
                color="Total_Downtime",
                color_continuous_scale="Reds",
                height=400,
                text="Total_Downtime",
            )
            fig.add_vline(x=30, line_dash="dash", line_color="red", annotation_text="Alert (30min)")
            fig.update_layout(margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig, use_container_width=True)

        # Temperature and Vibration
        st.markdown('<p class="section-header">Machine Health Metrics</p>', unsafe_allow_html=True)

        col1, col2 = st.columns(2)

        with col1:
            fig = px.bar(
                latest,
                x="Machine_ID",
                y="Avg_Temperature",
                color="Avg_Temperature",
                color_continuous_scale="RdYlGn_r",
                height=300,
                text_auto=".0f",
            )
            fig.add_hline(y=85, line_dash="dash", line_color="red", annotation_text="Warning 85°C")
            fig.update_layout(margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            fig = px.bar(
                latest,
                x="Machine_ID",
                y="Avg_Vibration",
                color="Avg_Vibration",
                color_continuous_scale="RdYlGn_r",
                height=300,
                text_auto=".1f",
            )
            fig.add_hline(y=8, line_dash="dash", line_color="red", annotation_text="Warning 8mm")
            fig.update_layout(margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig, use_container_width=True)

    # OEE Gauge
    st.markdown("---")
    st.markdown(
        '<p class="section-header">OEE - Overall Equipment Effectiveness</p>',
        unsafe_allow_html=True,
    )

    oee = kpis.get("oee")
    if oee is not None and not oee.empty:
        latest_oee = oee.iloc[-1]

        col1, col2, col3, col4 = st.columns(4)
        col1.metric(
            "OEE",
            f"{latest_oee['OEE_pct']:.1f}%",
            delta=f"{latest_oee['OEE_pct'] - 85:.1f}% vs target",
        )
        col2.metric("Availability", f"{latest_oee['Availability_pct']:.1f}%")
        col3.metric("Performance", f"{latest_oee['Performance_pct']:.1f}%")
        col4.metric("Quality", f"{latest_oee['Quality_pct']:.1f}%")

        # OEE Trend
        fig = go.Figure()
        for col_name, color in zip(
            ["OEE_pct", "Availability_pct", "Performance_pct", "Quality_pct"],
            ["#1a237e", "#4CAF50", "#FF9800", "#F44336"],
        ):
            fig.add_trace(
                go.Scatter(
                    x=oee["Date"],
                    y=oee[col_name],
                    mode="lines",
                    name=col_name.replace("_pct", ""),
                    line=dict(width=2, color=color),
                )
            )
        fig.add_hline(y=85, line_dash="dash", line_color="green", annotation_text="OEE Target 85%")
        fig.update_layout(height=350, margin=dict(l=0, r=0, t=10, b=0), hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)


def ai_report_page(datasets, kpis, alerts):
    """Render the AI Report page."""
    st.markdown('<h1 class="main-header">🤖 AI Executive Report</h1>', unsafe_allow_html=True)

    if st.button("🔄 Generate New Report", type="primary"):
        with st.spinner("Generating AI report..."):
            ai_gen = AIReportGenerator()
            report = ai_gen.generate_report(kpis, alerts, datasets)
            st.session_state["ai_report"] = report
        st.rerun()

    report = st.session_state.get("ai_report")

    if report is None:
        st.info("Click 'Generate New Report' to create an AI-powered executive summary.")
        return

    # Display report
    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown(
            f'<h2 style="color:#1a237e">{report.get("title", "Daily Report")}</h2>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<p style="color:#666"><b>Date:</b> {report.get("date", datetime.now().strftime("%Y-%m-%d"))}</p>',
            unsafe_allow_html=True,
        )
        st.markdown("---")

        st.markdown('<p class="section-header">📋 Executive Summary</p>', unsafe_allow_html=True)
        st.markdown(
            f'<div style="background:#e8eaf6; padding:1rem; border-radius:8px; '
            f'border-left:4px solid #1a237e; font-size:1.1rem">{report.get("summary", "N/A")}</div>',
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown('<p class="section-header">📊 Key Metrics</p>', unsafe_allow_html=True)
        metrics = report.get("key_metrics", {})
        if metrics:
            for k, v in metrics.items():
                st.metric(label=k.replace("_", " ").title(), value=str(v))

    st.markdown("---")

    # Problems, Recommendations, Risks
    col1, col2 = st.columns(2)

    with col1:
        st.markdown('<p class="section-header">⚠️ Problems</p>', unsafe_allow_html=True)
        problems = report.get("problems", [])
        if problems:
            for p in problems:
                severity = p.get("severity", "Medium")
                color = {"High": "#c62828", "Medium": "#f9a825", "Low": "#4CAF50"}.get(
                    severity, "#999"
                )
                st.markdown(
                    f"""
                <div style="padding:0.8rem; margin:0.5rem 0; border-radius:8px;
                           background:{color}10; border-left:4px solid {color}">
                    <b>{p.get("issue", "")}</b><br/>
                    <span style="font-size:0.85rem">Severity: {severity}</span><br/>
                    <span style="font-size:0.85rem">Impact: {p.get("impact", "")}</span>
                </div>
                """,
                    unsafe_allow_html=True,
                )
        else:
            st.success("No significant problems detected.")

        st.markdown('<p class="section-header">🔍 Root Causes</p>', unsafe_allow_html=True)
        causes = report.get("root_causes", [])
        if causes:
            for c in causes:
                st.markdown(
                    f"""
                <div style="padding:0.5rem; margin:0.3rem 0; background:#f5f5f5; border-radius:5px">
                    <b>{c.get("cause", "")}</b><br/>
                    <span style="font-size:0.85rem; color:#666">Evidence: {c.get("evidence", "")}</span>
                </div>
                """,
                    unsafe_allow_html=True,
                )

    with col2:
        st.markdown('<p class="section-header">💡 Recommendations</p>', unsafe_allow_html=True)
        recommendations = report.get("recommendations", [])
        if recommendations:
            for r in recommendations:
                priority = r.get("priority", "Medium")
                color = {"High": "#c62828", "Medium": "#f9a825", "Low": "#4CAF50"}.get(
                    priority, "#999"
                )
                st.markdown(
                    f"""
                <div style="padding:0.8rem; margin:0.5rem 0; border-radius:8px;
                           background:{color}10; border-left:4px solid {color}">
                    <b>{r.get("action", "")}</b><br/>
                    <span style="font-size:0.85rem">Priority: {priority}</span><br/>
                    <span style="font-size:0.85rem">Benefit: {r.get("expected_benefit", "")}</span>
                </div>
                """,
                    unsafe_allow_html=True,
                )
        else:
            st.info("No recommendations at this time.")

        st.markdown('<p class="section-header">🚨 Risks</p>', unsafe_allow_html=True)
        risks = report.get("risks", [])
        if risks:
            for r in risks:
                prob = r.get("probability", "Medium")
                color = {"High": "#c62828", "Medium": "#f9a825", "Low": "#4CAF50"}.get(prob, "#999")
                st.markdown(
                    f"""
                <div style="padding:0.5rem; margin:0.3rem 0; background:#f5f5f5; border-radius:5px">
                    <b>{r.get("risk", "")}</b><br/>
                    <span style="font-size:0.85rem; color:#666">
                        Probability: {prob} | Mitigation: {r.get("mitigation", "")}
                    </span>
                </div>
                """,
                    unsafe_allow_html=True,
                )
        else:
            st.info("No significant risks identified.")


def ai_chat_page(datasets, kpis):
    """Render the AI Chat page."""
    st.markdown(
        '<h1 class="main-header">💬 AI Chat - Ask About Factory Data</h1>', unsafe_allow_html=True
    )

    # Initialize chat history
    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []

    # Display chat history
    for msg in st.session_state["chat_history"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Chat input
    if prompt := st.chat_input("Ask a question about factory data..."):
        # Add user message
        st.session_state["chat_history"].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Generate response
        with st.chat_message("assistant"):
            with st.spinner("Analyzing data..."):
                ai_gen = AIReportGenerator()
                context = {
                    "kpis": {k: str(v) for k, v in kpis.items()},
                    "datasets": {k: str(v.shape) for k, v in datasets.items()},
                }
                response = ai_gen.chat_query(prompt, context)
                st.markdown(response)
                st.session_state["chat_history"].append({"role": "assistant", "content": response})


def export_page(datasets, kpis, alerts):
    """Render the Export page."""
    st.markdown('<h1 class="main-header">📥 Export Reports</h1>', unsafe_allow_html=True)

    st.markdown(
        """
    <div style="background:#e8eaf6; padding:1.5rem; border-radius:10px; margin-bottom:1.5rem">
        <h3 style="margin:0">One-Click Export</h3>
        <p style="color:#666">Generate comprehensive Excel and PDF reports with all KPIs, charts, and AI insights.</p>
    </div>
    """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("📊 Export to Excel", use_container_width=True, type="primary"):
            with st.spinner("Generating Excel report..."):
                exporter = ReportExporter()
                filepath = exporter.export_to_excel(kpis, alerts)
                st.success("✅ Excel report saved!")
                st.info(f"📁 {filepath}")

                # Offer download
                with open(filepath, "rb") as f:
                    st.download_button(
                        label="📥 Download Excel",
                        data=f,
                        file_name=os.path.basename(filepath),
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                    )

    with col2:
        if st.button("📄 Export to PDF", use_container_width=True, type="primary"):
            with st.spinner("Generating PDF report..."):
                exporter = ReportExporter()
                ai_report = st.session_state.get("ai_report")
                filepath = exporter.export_to_pdf(kpis, alerts, ai_report)
                st.success("✅ PDF report saved!")
                st.info(f"📁 {filepath}")

                with open(filepath, "rb") as f:
                    st.download_button(
                        label="📥 Download PDF",
                        data=f,
                        file_name=os.path.basename(filepath),
                        mime="application/pdf",
                        use_container_width=True,
                    )

    with col3:
        if st.button("📦 Export All (Excel + PDF)", use_container_width=True, type="secondary"):
            with st.spinner("Generating all reports..."):
                exporter = ReportExporter()
                ai_report = st.session_state.get("ai_report")
                result = exporter.export_all(kpis, alerts, ai_report)
                st.success("✅ Reports generated!")
                st.info(f"📁 Excel: {result['excel']}\n📁 PDF: {result['pdf']}")

    # Show sample of what gets exported
    st.markdown("---")
    st.markdown('<p class="section-header">Export Preview</p>', unsafe_allow_html=True)

    daily_prod = kpis.get("daily_production")
    if daily_prod is not None and not daily_prod.empty:
        st.dataframe(daily_prod.tail(10).round(2), use_container_width=True, height=300)


def data_management_page(datasets, kpis):
    """Render the Data Management page."""
    st.markdown('<h1 class="main-header">🗄️ Data Management</h1>', unsafe_allow_html=True)

    if datasets:
        for name, df in datasets.items():
            with st.expander(
                f"📂 {name.upper()} Dataset ({len(df):,} rows × {len(df.columns)} cols)",
                expanded=False,
            ):
                st.dataframe(df.head(20), use_container_width=True, height=300)

                col1, col2 = st.columns(2)
                col1.metric("Rows", f"{len(df):,}")
                col2.metric("Columns", len(df.columns))

                st.markdown("**Column Info:**")
                info_df = pd.DataFrame(
                    {
                        "Column": df.columns,
                        "Type": df.dtypes.astype(str),
                        "Non-Null": df.count().values,
                        "Null": df.isnull().sum().values,
                    }
                )
                st.dataframe(info_df, use_container_width=True, height=200)

    # Run ETL button
    st.markdown("---")
    if st.button("🔄 Re-run ETL Pipeline", type="primary"):
        with st.spinner("Running ETL pipeline..."):
            st.cache_data.clear()
            st.rerun()


# Main app
def user_guide_page():
    """Render the User Guide page for non-technical business users."""
    st.markdown('<h1 class="main-header">📖 Hướng dẫn Sử dụng</h1>', unsafe_allow_html=True)
    st.markdown("**Dành cho người dùng không chuyên về kỹ thuật**")

    with st.expander("🎯 Hệ thống làm gì?", expanded=True):
        st.markdown("""
        - **Tự động đọc file Excel** → tính toán KPI → hiển thị trên Dashboard
        - **AI tự viết báo cáo** mỗi sáng (Summary + Vấn đề + Đề xuất)
        - **Cảnh báo tự động** khi tỷ lệ lỗi >5%, tồn kho <200, máy hỏng
        - **Bạn chỉ cần mở trình duyệt** và xem — không cần mở Excel nữa
        """)

    with st.expander("📊 Cách đọc biểu đồ"):
        st.markdown("""
        | Màu | Ý nghĩa |
        |-----|---------|
        | 🟢 Xanh | Đạt target / An toàn |
        | 🟡 Vàng | Cần cải thiện |
        | 🔴 Đỏ | Cảnh báo / Nguy hiểm |

        **OEE**: >85% = tốt | 70-85% = cần cải thiện | <70% = cảnh báo
        """)

    with st.expander("💬 Cách dùng AI Chat"):
        st.markdown("""
        1. Click trang **💬 AI Chat**
        2. Gõ câu hỏi vào ô text
        3. Click **Gửi** hoặc nhấn Enter

        **Ví dụ:**
        - "Hôm nay tỷ lệ lỗi bao nhiêu?"
        - "Máy nào đang hỏng?"
        - "Tuần này OEE trung bình bao nhiêu?"
        """)

    with st.expander("📥 Cách xuất báo cáo"):
        st.markdown("""
        1. Click trang **📥 Export**
        2. Click **Export Excel** hoặc **Export PDF**
        3. File sẽ tự động tải về
        """)

    with st.expander("⚠️ Cảnh báo tự động"):
        st.markdown("""
        | Loại | Điều kiện | Mức độ |
        |------|-----------|--------|
        | Tỷ lệ lỗi | >5% | ⚠️ WARNING |
        | Tồn kho thấp | <200 units | ⚠️ WARNING |
        | Máy hỏng | Status = Failure | 🔴 CRITICAL |
        | Nhiệt độ cao | >85°C | ⚠️ WARNING |
        | OEE thấp | <85% | ⚠️ WARNING |
        """)

    with st.expander("⏱️ Hiệu quả"):
        st.markdown("""
        | Chỉ số | Trước | Sau | Tiết kiệm |
        |--------|-------|-----|-----------|
        | Thời gian báo cáo/ngày | 2-3 giờ | 5 phút | **95%** |
        | File Excel phải mở | 5 file | 0 file | **100%** |
        | Sai số tính toán | ~5% | 0% | **100%** |
        """)


def main():
    # Initialize session state
    if "data_loaded" not in st.session_state:
        st.session_state["data_loaded"] = False

    # Sidebar
    st.sidebar.image("https://img.icons8.com/fluency/96/factory.png", width=48)
    st.sidebar.title(FACTORY_NAME)
    st.sidebar.markdown("---")

    # Navigation
    page = st.sidebar.radio(
        "Navigation",
        [
            "📊 Overview",
            "🏭 Production",
            "✅ Quality",
            "📦 Inventory",
            "🔧 Machine",
            "🤖 AI Report",
            "💬 AI Chat",
            "📥 Export",
            "🗄️ Data",
            "📖 User Guide",
        ],
        index=0,
    )

    st.sidebar.markdown("---")

    # Load data button
    if st.sidebar.button("🔄 Load / Refresh Data", type="primary", use_container_width=True):
        with st.spinner("Loading factory data..."):
            datasets, kpis, alerts, alert_summary = load_and_compute()
            if datasets:
                st.session_state["datasets"] = datasets
                st.session_state["kpis"] = kpis
                st.session_state["alerts"] = alerts
                st.session_state["alert_summary"] = alert_summary
                st.session_state["data_loaded"] = True
                st.sidebar.success(f"✅ Data loaded ({len(datasets)} datasets)")
                st.rerun()
            else:
                st.sidebar.error("❌ No data found. Generate data first.")

    # Show data status
    if st.session_state.get("data_loaded"):
        st.sidebar.success("📊 Data loaded")
        ds = st.session_state.get("datasets", {})
        for name, df in ds.items():
            st.sidebar.text(f"• {name}: {len(df):,} rows")

    # Data generation option
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🛠️ Quick Actions")

    if st.sidebar.button("🎲 Generate Sample Data (90 days)", use_container_width=True):
        with st.spinner("Generating synthetic data..."):
            from app.utils.data_generator import generate_all_data

            generate_all_data(days=90)
            st.sidebar.success("✅ Data generated! Click 'Load / Refresh Data'")

    # Run scheduler
    if st.sidebar.button("⏰ Start Auto Scheduler", use_container_width=True):
        try:
            from app.scheduler.tasks import ManufacturingScheduler

            scheduler = ManufacturingScheduler()
            scheduler.start()
            st.session_state["scheduler"] = scheduler
            st.sidebar.success("✅ Scheduler started")
        except Exception as e:
            st.sidebar.error(f"❌ Scheduler error: {e}")

    # Alerts summary
    if st.session_state.get("data_loaded"):
        st.sidebar.markdown("---")
        alert_summary = st.session_state.get("alert_summary", {})
        if alert_summary:
            total = alert_summary.get("total", 0)
            st.sidebar.markdown(f"### 🔔 Alerts: {total}")
            by_level = alert_summary.get("by_level", {})
            if by_level.get("CRITICAL", 0) > 0:
                st.sidebar.error(f"🔴 Critical: {by_level['CRITICAL']}")
            if by_level.get("WARNING", 0) > 0:
                st.sidebar.warning(f"🟡 Warning: {by_level['WARNING']}")

    # Main content area
    if not st.session_state.get("data_loaded"):
        st.markdown(
            """
        <div style="text-align:center; padding:4rem">
            <h1 style="color:#1a237e">🏭 Smart Manufacturing Platform</h1>
            <p style="font-size:1.2rem; color:#666; margin:2rem 0">
                Factory Data Automation & AI Reporting Platform<br/>
                <small>Auto-import, Clean, Analyze, Visualize, and Report</small>
            </p>
            <p style="color:#999">
                Click <b>"Generate Sample Data"</b> to create test data,<br/>
                then <b>"Load / Refresh Data"</b> to start.
            </p>
        </div>
        """,
            unsafe_allow_html=True,
        )
        return

    # Route to selected page
    datasets = st.session_state.get("datasets", {})
    kpis = st.session_state.get("kpis", {})
    alerts = st.session_state.get("alerts", [])

    if "Overview" in page:
        overview_page(datasets, kpis, alerts, st.session_state.get("alert_summary", {}))
    elif "Production" in page:
        production_page(datasets, kpis)
    elif "Quality" in page:
        quality_page(datasets, kpis)
    elif "Inventory" in page:
        inventory_page(datasets, kpis)
    elif "Machine" in page:
        machine_page(datasets, kpis)
    elif "AI Report" in page:
        ai_report_page(datasets, kpis, alerts)
    elif "AI Chat" in page:
        ai_chat_page(datasets, kpis)
    elif "Export" in page:
        export_page(datasets, kpis, alerts)
    elif "Data" in page:
        data_management_page(datasets, kpis)
    elif "User Guide" in page:
        user_guide_page()


if __name__ == "__main__":
    main()
