"""
Scheduler for automated daily tasks.
Uses APScheduler to run ETL, report generation, and alerts at scheduled times.
"""

import os
import sys
from datetime import datetime, time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ai.reporting import AIReportGenerator
from app.etl.kpi_engine import calculate_all_kpis
from app.etl.pipeline import run_etl
from app.reports.alert_system import AlertManager
from app.reports.exporter import ReportExporter


class ManufacturingScheduler:
    """Scheduled tasks for automated manufacturing operations."""

    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.alert_manager = AlertManager()
        self.exporter = ReportExporter()
        self.ai_report_generator = AIReportGenerator()

    def morning_pipeline(self):
        """Run at 8:00 AM: Import data, calculate KPIs, check alerts."""
        print(f"\n{'=' * 60}")
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Running Morning Pipeline")
        print(f"{'=' * 60}")

        # Run ETL
        datasets = run_etl()
        if not datasets:
            print("No data found. Skipping pipeline.")
            return

        # Calculate KPIs
        kpis = calculate_all_kpis(datasets)

        # Check alerts
        alerts = self.alert_manager.check_all(datasets, kpis)
        alert_dicts = [a.to_dict() for a in alerts]

        # Generate AI report
        ai_report = self.ai_report_generator.generate_report(kpis, alert_dicts, datasets)

        # Export reports
        self.exporter.export_all(kpis, alert_dicts, ai_report)

        print("Morning Pipeline Complete.\n")
        return datasets, kpis, alerts, ai_report

    def generate_report_task(self):
        """Run at 17:00 PM: Generate end-of-day report."""
        print(f"\n{'=' * 60}")
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Running End-of-Day Report")
        print(f"{'=' * 60}")

        datasets = run_etl()
        if datasets:
            kpis = calculate_all_kpis(datasets)
            alerts = self.alert_manager.check_all(datasets, kpis)
            alert_dicts = [a.to_dict() for a in alerts]
            ai_report = self.ai_report_generator.generate_report(kpis, alert_dicts, datasets)
            exports = self.exporter.export_all(kpis, alert_dicts, ai_report)
            print(f"End-of-Day Report saved: {exports}")

        print("End-of-Day Report Complete.\n")

    def start(self):
        """Start the scheduler with default tasks."""
        # Morning pipeline at 8:00 AM
        self.scheduler.add_job(
            self.morning_pipeline,
            CronTrigger(hour=8, minute=0),
            id="morning_pipeline",
            name="Morning Data Pipeline",
        )

        # End-of-day report at 5:00 PM
        self.scheduler.add_job(
            self.generate_report_task,
            CronTrigger(hour=17, minute=0),
            id="end_of_day_report",
            name="End-of-Day Report",
        )

        # Also run every hour for demo purposes (only if no real schedule is needed)
        self.scheduler.add_job(
            self.morning_pipeline, "interval", hours=1, id="hourly_demo", name="Hourly Demo Run"
        )

        self.scheduler.start()
        print(f"\nScheduler started at {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("  - Morning Pipeline: 08:00 daily")
        print("  - End-of-Day Report: 17:00 daily")
        print("  - Hourly Demo Run (for testing)")

    def stop(self):
        """Stop the scheduler."""
        self.scheduler.shutdown()
        print("Scheduler stopped.")


# For standalone use
if __name__ == "__main__":
    scheduler = ManufacturingScheduler()
    scheduler.start()

    try:
        # Keep the main thread alive
        import time

        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        scheduler.stop()
