"""
Alert System for manufacturing monitoring.
Generates warnings and alerts based on defined thresholds.
"""

from datetime import datetime

import pandas as pd

from app.utils.config import ALERT_DOWNTIME_MIN, ALERT_INVENTORY_MIN, ALERT_REJECT_RATE, OEE_TARGET
from app.utils.logging_config import get_logger, log_event

logger = get_logger("alerts", "alert_system")


class Alert:
    def __init__(
        self,
        level: str,
        category: str,
        message: str,
        timestamp: datetime = None,
        value: float = None,
        threshold: float = None,
        source: str = None,
    ):
        self.level = level  # "INFO", "WARNING", "CRITICAL"
        self.category = category
        self.message = message
        self.timestamp = timestamp or datetime.now()
        self.value = value
        self.threshold = threshold
        self.source = source

    def to_dict(self):
        return {
            "level": self.level,
            "category": self.category,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "value": self.value,
            "threshold": self.threshold,
            "source": self.source,
        }


class AlertManager:
    def __init__(self):
        self.alerts: list[Alert] = []

    def check_production_alerts(self, daily_prod: pd.DataFrame) -> list[Alert]:
        """Check production for alerts."""
        alerts = []
        if daily_prod is None or daily_prod.empty:
            return alerts

        latest = daily_prod.iloc[-1]

        # Reject rate alert
        if latest["Reject_Rate_pct"] > ALERT_REJECT_RATE:
            alerts.append(
                Alert(
                    level="WARNING"
                    if latest["Reject_Rate_pct"] < ALERT_REJECT_RATE * 1.5
                    else "CRITICAL",
                    category="Quality",
                    message=f"Reject rate {latest['Reject_Rate_pct']:.1f}% exceeds threshold {ALERT_REJECT_RATE}%",
                    value=latest["Reject_Rate_pct"],
                    threshold=ALERT_REJECT_RATE,
                    source="Production",
                )
            )

        # Achievement rate alert
        if latest["Achievement_Rate_pct"] < 80:
            alerts.append(
                Alert(
                    level="WARNING",
                    category="Production",
                    message=f"Production achievement only {latest['Achievement_Rate_pct']:.1f}%",
                    value=latest["Achievement_Rate_pct"],
                    threshold=80,
                    source="Production",
                )
            )

        return alerts

    def check_inventory_alerts(self, inv_kpi: pd.DataFrame, inv_raw: pd.DataFrame) -> list[Alert]:
        """Check inventory for alerts."""
        alerts = []
        if inv_kpi is None or inv_raw is None:
            return alerts

        # Low stock products
        latest_inv = inv_raw.copy()
        latest_inv["Date"] = pd.to_datetime(latest_inv["Date"])
        latest_date = latest_inv["Date"].max()
        current_stock = latest_inv[latest_inv["Date"] == latest_date]

        low_stock = current_stock[current_stock["Stock_Qty"] <= ALERT_INVENTORY_MIN]
        for _, row in low_stock.iterrows():
            alerts.append(
                Alert(
                    level="CRITICAL" if row["Stock_Qty"] < ALERT_INVENTORY_MIN * 0.5 else "WARNING",
                    category="Inventory",
                    message=f"Low stock: {row['Product']} - only {row['Stock_Qty']} units remaining",
                    value=row["Stock_Qty"],
                    threshold=ALERT_INVENTORY_MIN,
                    source="Inventory",
                )
            )

        # Products below reorder point
        below_reorder = current_stock[current_stock["Stock_Qty"] <= current_stock["Reorder_Point"]]
        for _, row in below_reorder.iterrows():
            alerts.append(
                Alert(
                    level="WARNING",
                    category="Inventory",
                    message=f"Reorder needed: {row['Product']} ({row['Stock_Qty']} units, reorder at {row['Reorder_Point']})",
                    value=row["Stock_Qty"],
                    threshold=row["Reorder_Point"],
                    source="Inventory",
                )
            )

        return alerts

    def check_machine_alerts(self, mach_df: pd.DataFrame) -> list[Alert]:
        """Check machine data for alerts."""
        alerts = []
        if mach_df is None or mach_df.empty:
            return alerts

        mach = mach_df.copy()
        mach["Date"] = pd.to_datetime(mach["Date"])
        latest_date = mach["Date"].max()
        latest = mach[mach["Date"] == latest_date]

        # High downtime
        high_downtime = latest[latest["Downtime_min"] > ALERT_DOWNTIME_MIN]
        for _, row in high_downtime.iterrows():
            alerts.append(
                Alert(
                    level="CRITICAL" if row["Downtime_min"] > ALERT_DOWNTIME_MIN * 2 else "WARNING",
                    category="Machine",
                    message=f"Machine {row['Machine_ID']}: {row['Downtime_min']}min downtime ({row['Status']})",
                    value=row["Downtime_min"],
                    threshold=ALERT_DOWNTIME_MIN,
                    source=f"Machine_{row['Machine_ID']}",
                )
            )

        # Failure count
        failures = latest[latest["Status"] == "Failure"]
        for _, row in failures.iterrows():
            alerts.append(
                Alert(
                    level="CRITICAL",
                    category="Machine",
                    message=f"Machine {row['Machine_ID']} is in FAILURE state!",
                    source=f"Machine_{row['Machine_ID']}",
                )
            )

        # High temperature or vibration
        high_temp = latest[(latest["Temperature_C"] > 85) & (latest["Status"] == "Running")]
        for _, row in high_temp.iterrows():
            alerts.append(
                Alert(
                    level="WARNING",
                    category="Machine",
                    message=f"Machine {row['Machine_ID']} high temperature: {row['Temperature_C']:.1f}°C",
                    value=row["Temperature_C"],
                    threshold=85,
                    source=f"Machine_{row['Machine_ID']}",
                )
            )

        high_vib = latest[(latest["Vibration_mm"] > 8.0) & (latest["Status"] == "Running")]
        for _, row in high_vib.iterrows():
            alerts.append(
                Alert(
                    level="WARNING",
                    category="Machine",
                    message=f"Machine {row['Machine_ID']} high vibration: {row['Vibration_mm']:.2f}mm",
                    value=row["Vibration_mm"],
                    threshold=8.0,
                    source=f"Machine_{row['Machine_ID']}",
                )
            )

        return alerts

    def check_oee_alerts(self, oee_df: pd.DataFrame) -> list[Alert]:
        """Check OEE for alerts."""
        alerts = []
        if oee_df is None or oee_df.empty:
            return alerts

        latest = oee_df.iloc[-1]

        if latest["OEE_pct"] < OEE_TARGET * 100:
            alerts.append(
                Alert(
                    level="WARNING",
                    category="OEE",
                    message=f"OEE at {latest['OEE_pct']:.1f}% (target: {OEE_TARGET * 100:.0f}%)",
                    value=latest["OEE_pct"],
                    threshold=OEE_TARGET * 100,
                    source="OEE",
                )
            )

        return alerts

    def check_all(self, datasets: dict, kpis: dict) -> list[Alert]:
        """Run all alert checks."""
        self.alerts = []

        production = kpis.get("daily_production")
        inventory_kpi = kpis.get("inventory_kpi")
        oee = kpis.get("oee")

        self.alerts.extend(self.check_production_alerts(production))
        self.alerts.extend(self.check_inventory_alerts(inventory_kpi, datasets.get("inventory")))
        self.alerts.extend(self.check_machine_alerts(datasets.get("machine")))
        self.alerts.extend(self.check_oee_alerts(oee))

        # Sort by severity
        level_order = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
        self.alerts.sort(key=lambda a: (level_order.get(a.level, 99), a.timestamp))

        critical = sum(1 for a in self.alerts if a.level == "CRITICAL")
        warnings = sum(1 for a in self.alerts if a.level == "WARNING")
        log_event(
            logger,
            "alert_check_complete",
            component="alert_system",
            total=len(self.alerts),
            critical=critical,
            warnings=warnings,
        )

        return self.alerts

    def get_summary(self) -> dict:
        """Get alert summary counts."""
        summary = {"CRITICAL": 0, "WARNING": 0, "INFO": 0}
        categories = {}

        for alert in self.alerts:
            summary[alert.level] = summary.get(alert.level, 0) + 1
            categories[alert.category] = categories.get(alert.category, 0) + 1

        return {"total": len(self.alerts), "by_level": summary, "by_category": categories}
