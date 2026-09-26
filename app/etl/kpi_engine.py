"""
KPI Calculation Engine.
Computes all manufacturing KPIs from cleaned datasets.
"""

import pandas as pd

from app.utils.logging_config import get_logger, log_event

logger = get_logger("kpi", "kpi_engine")


def calculate_daily_production(prod_df: pd.DataFrame) -> pd.DataFrame:
    """Calculate daily production KPIs."""
    if prod_df is None or prod_df.empty:
        return pd.DataFrame()

    daily = (
        prod_df.groupby("Date")
        .agg(
            Total_Target=("Target_Qty", "sum"),
            Total_Actual=("Actual_Qty", "sum"),
            Total_Good=("Good_Qty", "sum"),
            Total_Reject=("Reject_Qty", "sum"),
            Avg_Cycle_Time=("Cycle_Time_sec", "mean"),
            Total_Records=("Actual_Qty", "count"),
        )
        .reset_index()
    )

    daily["Achievement_Rate_pct"] = round(
        (daily["Total_Actual"] / daily["Total_Target"].replace(0, 1)) * 100, 2
    )
    daily["Reject_Rate_pct"] = round(
        (daily["Total_Reject"] / daily["Total_Actual"].replace(0, 1)) * 100, 2
    )
    daily["Yield_pct"] = round((daily["Total_Good"] / daily["Total_Actual"].replace(0, 1)) * 100, 2)
    daily["Date"] = pd.to_datetime(daily["Date"])

    return daily.sort_values("Date")


def calculate_weekly_production(prod_df: pd.DataFrame) -> pd.DataFrame:
    """Calculate weekly production KPIs."""
    if prod_df is None or prod_df.empty:
        return pd.DataFrame()

    df = prod_df.copy()
    df["Date"] = pd.to_datetime(df["Date"])
    df["Week"] = df["Date"].dt.isocalendar().week.astype(int)
    df["Year"] = df["Date"].dt.year

    weekly = (
        df.groupby(["Year", "Week"])
        .agg(
            Total_Target=("Target_Qty", "sum"),
            Total_Actual=("Actual_Qty", "sum"),
            Total_Good=("Good_Qty", "sum"),
            Total_Reject=("Reject_Qty", "sum"),
            Avg_Cycle_Time=("Cycle_Time_sec", "mean"),
        )
        .reset_index()
    )

    weekly["Achievement_Rate_pct"] = round(
        (weekly["Total_Actual"] / weekly["Total_Target"].replace(0, 1)) * 100, 2
    )
    weekly["Reject_Rate_pct"] = round(
        (weekly["Total_Reject"] / weekly["Total_Actual"].replace(0, 1)) * 100, 2
    )

    return weekly


def calculate_monthly_production(prod_df: pd.DataFrame) -> pd.DataFrame:
    """Calculate monthly production KPIs."""
    if prod_df is None or prod_df.empty:
        return pd.DataFrame()

    df = prod_df.copy()
    df["Date"] = pd.to_datetime(df["Date"])
    df["Month"] = df["Date"].dt.month
    df["Year"] = df["Date"].dt.year

    monthly = (
        df.groupby(["Year", "Month"])
        .agg(
            Total_Target=("Target_Qty", "sum"),
            Total_Actual=("Actual_Qty", "sum"),
            Total_Good=("Good_Qty", "sum"),
            Total_Reject=("Reject_Qty", "sum"),
            Avg_Cycle_Time=("Cycle_Time_sec", "mean"),
        )
        .reset_index()
    )

    monthly["Achievement_Rate_pct"] = round(
        (monthly["Total_Actual"] / monthly["Total_Target"].replace(0, 1)) * 100, 2
    )
    monthly["Reject_Rate_pct"] = round(
        (monthly["Total_Reject"] / monthly["Total_Actual"].replace(0, 1)) * 100, 2
    )

    return monthly


def calculate_oee(prod_df: pd.DataFrame, mach_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate Overall Equipment Effectiveness (OEE).
    OEE = Availability × Performance × Quality
    """
    if prod_df is None or mach_df is None:
        return pd.DataFrame()

    # Availability from machine data
    mach_daily = mach_df.copy()
    mach_daily["Date"] = pd.to_datetime(mach_daily["Date"])

    availability = (
        mach_daily.groupby("Date")
        .agg(Total_Time=("Downtime_min", "count"), Downtime_Total=("Downtime_min", "sum"))
        .reset_index()
    )
    availability["Availability_pct"] = round(
        (
            (availability["Total_Time"] * 10 - availability["Downtime_Total"])
            / (availability["Total_Time"] * 10).replace(0, 1)
        )
        * 100,
        2,
    )

    # Performance from production
    prod_daily = prod_df.copy()
    prod_daily["Date"] = pd.to_datetime(prod_daily["Date"])

    performance = (
        prod_daily.groupby("Date")
        .agg(Total_Actual=("Actual_Qty", "sum"), Total_Target=("Target_Qty", "sum"))
        .reset_index()
    )
    performance["Performance_pct"] = round(
        (performance["Total_Actual"] / performance["Total_Target"].replace(0, 1)) * 100, 2
    )

    # Quality
    quality = (
        prod_daily.groupby("Date")
        .agg(Total_Good=("Good_Qty", "sum"), Total_Actual=("Actual_Qty", "sum"))
        .reset_index()
    )
    quality["Quality_pct"] = round(
        (quality["Total_Good"] / quality["Total_Actual"].replace(0, 1)) * 100, 2
    )

    # Merge
    oee_df = availability.merge(performance[["Date", "Performance_pct"]], on="Date", how="outer")
    oee_df = oee_df.merge(quality[["Date", "Quality_pct"]], on="Date", how="outer")

    oee_df["OEE_pct"] = round(
        (oee_df["Availability_pct"] / 100)
        * (oee_df["Performance_pct"] / 100)
        * (oee_df["Quality_pct"] / 100)
        * 100,
        2,
    )

    return oee_df.sort_values("Date")


def calculate_machine_utilization(mach_df: pd.DataFrame) -> pd.DataFrame:
    """Calculate machine utilization rates."""
    if mach_df is None or mach_df.empty:
        return pd.DataFrame()

    mach_daily = mach_df.copy()
    mach_daily["Date"] = pd.to_datetime(mach_daily["Date"])

    util = (
        mach_daily.groupby(["Date", "Machine_ID"])
        .agg(
            Running_Count=("Status", lambda x: (x == "Running").sum()),
            Idle_Count=("Status", lambda x: (x == "Idle").sum()),
            Maint_Count=("Status", lambda x: (x == "Maintenance").sum()),
            Failure_Count=("Status", lambda x: (x == "Failure").sum()),
            Total_Downtime=("Downtime_min", "sum"),
            Avg_Temperature=("Temperature_C", "mean"),
            Avg_Vibration=("Vibration_mm", "mean"),
            Avg_Power=("Power_Usage_pct", "mean"),
        )
        .reset_index()
    )

    util["Total_Readings"] = (
        util["Running_Count"] + util["Idle_Count"] + util["Maint_Count"] + util["Failure_Count"]
    )
    util["Utilization_pct"] = round(
        (util["Running_Count"] / util["Total_Readings"].replace(0, 1)) * 100, 2
    )

    return util.sort_values(["Date", "Machine_ID"])


def calculate_worker_productivity(work_df: pd.DataFrame) -> pd.DataFrame:
    """Calculate worker productivity metrics."""
    if work_df is None or work_df.empty:
        return pd.DataFrame()

    work_daily = work_df.copy()
    work_daily["Date"] = pd.to_datetime(work_daily["Date"])

    productivity = (
        work_daily.groupby(["Date", "Worker_ID", "Line", "Shift"])
        .agg(
            Hours_Worked=("Hours_Worked", "sum"),
            Units_Produced=("Units_Produced", "sum"),
            Defects_Caused=("Defects_Caused", "sum"),
            Overtime_hrs=("Overtime_hrs", "sum"),
        )
        .reset_index()
    )

    productivity["Units_per_Hour"] = round(
        productivity["Units_Produced"] / productivity["Hours_Worked"].replace(0, 1), 1
    )
    productivity["Defect_Rate_pct"] = round(
        (productivity["Defects_Caused"] / productivity["Units_Produced"].replace(0, 1)) * 100, 2
    )

    return productivity.sort_values(["Date", "Worker_ID"])


def calculate_inventory_kpi(inv_df: pd.DataFrame) -> pd.DataFrame:
    """Calculate inventory KPIs including stock levels, turnover, alerts."""
    if inv_df is None or inv_df.empty:
        return pd.DataFrame()

    inv_daily = inv_df.copy()
    inv_daily["Date"] = pd.to_datetime(inv_daily["Date"])

    # Daily inventory summary
    daily_inv = (
        inv_daily.groupby("Date")
        .agg(
            Total_Stock=("Stock_Qty", "sum"),
            Total_Incoming=("Incoming_Qty", "sum"),
            Total_Outgoing=("Outgoing_Qty", "sum"),
            Avg_Stock=("Stock_Qty", "mean"),
            Min_Stock=("Stock_Qty", "min"),
            Products_Below_Reorder=(
                "Stock_Qty",
                lambda x: (x <= inv_daily.loc[x.index, "Reorder_Point"]).sum(),
            ),
        )
        .reset_index()
    )

    stock_values = (
        inv_daily.groupby("Date")
        .apply(lambda g: float((g["Stock_Qty"] * g["Unit_Price"]).sum()), include_groups=False)
        .values
    )
    daily_inv["Stock_Value"] = [round(v, 2) for v in stock_values]

    return daily_inv.sort_values("Date")


def calculate_defect_analysis(qual_df: pd.DataFrame) -> dict:
    """Calculate defect analysis KPIs."""
    if qual_df is None or qual_df.empty:
        return {"by_type": pd.DataFrame(), "by_severity": pd.DataFrame(), "daily": pd.DataFrame()}

    qual_daily = qual_df.copy()
    qual_daily["Date"] = pd.to_datetime(qual_daily["Date"])

    # By defect type
    defect_by_type = (
        qual_daily.groupby("Defect_Type")
        .agg(
            Total_Defects=("Defect_Count", "sum"),
            Total_Inspected=("Inspected_Qty", "sum"),
            Occurrences=("Defect_Count", "count"),
        )
        .reset_index()
    )
    defect_by_type["Defect_Rate_pct"] = round(
        (defect_by_type["Total_Defects"] / defect_by_type["Total_Inspected"].replace(0, 1)) * 100, 2
    )

    # By severity
    defect_by_severity = (
        qual_daily.groupby("Severity")
        .agg(Total_Defects=("Defect_Count", "sum"), Occurrences=("Defect_Count", "count"))
        .reset_index()
    )

    # Daily defect rate
    daily_defect = (
        qual_daily.groupby("Date")
        .agg(Total_Defects=("Defect_Count", "sum"), Total_Inspected=("Inspected_Qty", "sum"))
        .reset_index()
    )
    daily_defect["Defect_Rate_pct"] = round(
        (daily_defect["Total_Defects"] / daily_defect["Total_Inspected"].replace(0, 1)) * 100, 2
    )

    return {
        "by_type": defect_by_type.sort_values("Total_Defects", ascending=False),
        "by_severity": defect_by_severity,
        "daily": daily_defect.sort_values("Date"),
    }


def calculate_all_kpis(datasets: dict[str, pd.DataFrame]) -> dict:
    """Calculate all KPIs from all datasets."""
    kpis = {}

    prod_df = datasets.get("production")
    qual_df = datasets.get("quality")
    inv_df = datasets.get("inventory")
    mach_df = datasets.get("machine")
    work_df = datasets.get("workers")

    log_event(
        logger,
        "kpi_calculation_start",
        component="kpi_engine",
        datasets_available=list(datasets.keys()),
    )

    # Production KPIs
    kpis["daily_production"] = calculate_daily_production(prod_df)
    kpis["weekly_production"] = calculate_weekly_production(prod_df)
    kpis["monthly_production"] = calculate_monthly_production(prod_df)

    # OEE
    kpis["oee"] = calculate_oee(prod_df, mach_df)

    # Machine
    kpis["machine_utilization"] = calculate_machine_utilization(mach_df)

    # Workers
    kpis["worker_productivity"] = calculate_worker_productivity(work_df)

    # Inventory
    kpis["inventory_kpi"] = calculate_inventory_kpi(inv_df)

    # Quality
    kpis["defect_analysis"] = calculate_defect_analysis(qual_df)

    calculated = [
        k for k, v in kpis.items() if v is not None and (not hasattr(v, "empty") or not v.empty)
    ]
    log_event(
        logger, "kpi_calculation_complete", component="kpi_engine", kpis_calculated=calculated
    )
    return kpis
