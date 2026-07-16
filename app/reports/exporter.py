"""
Export Module: Generates PDF and Excel reports.
One-click export for management reports.
"""
import os
import pandas as pd
from io import BytesIO
from datetime import datetime
from typing import Dict, Optional
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image
)
from app.utils.config import DATA_EXPORTS_DIR, FACTORY_NAME


class ReportExporter:
    """Handles export of reports to PDF and Excel."""
    
    def __init__(self):
        os.makedirs(DATA_EXPORTS_DIR, exist_ok=True)
    
    def export_to_excel(self, kpis: Dict, alerts: list, filename: Optional[str] = None) -> str:
        """Export all KPIs and alerts to an Excel file with multiple sheets."""
        if filename is None:
            filename = f"factory_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        filepath = os.path.join(DATA_EXPORTS_DIR, filename)
        
        with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
            # Production KPIs
            if "daily_production" in kpis:
                kpis["daily_production"].to_excel(writer, sheet_name="Daily Production", index=False)
            if "weekly_production" in kpis:
                kpis["weekly_production"].to_excel(writer, sheet_name="Weekly Production", index=False)
            if "monthly_production" in kpis:
                kpis["monthly_production"].to_excel(writer, sheet_name="Monthly Production", index=False)
            
            # OEE
            if "oee" in kpis:
                kpis["oee"].to_excel(writer, sheet_name="OEE", index=False)
            
            # Machine
            if "machine_utilization" in kpis:
                kpis["machine_utilization"].to_excel(writer, sheet_name="Machine Utilization", index=False)
            
            # Workers
            if "worker_productivity" in kpis:
                kpis["worker_productivity"].to_excel(writer, sheet_name="Worker Productivity", index=False)
            
            # Inventory
            if "inventory_kpi" in kpis:
                kpis["inventory_kpi"].to_excel(writer, sheet_name="Inventory", index=False)
            
            # Quality
            defect = kpis.get("defect_analysis", {})
            if defect:
                if "by_type" in defect:
                    defect["by_type"].to_excel(writer, sheet_name="Defects by Type", index=False)
                if "by_severity" in defect:
                    defect["by_severity"].to_excel(writer, sheet_name="Defects by Severity", index=False)
                if "daily" in defect:
                    defect["daily"].to_excel(writer, sheet_name="Daily Defects", index=False)
            
            # Alerts
            if alerts:
                alerts_df = pd.DataFrame(alerts)
                alerts_df.to_excel(writer, sheet_name="Alerts", index=False)
        
        print(f"Excel report saved: {filepath}")
        return filepath
    
    def export_to_pdf(self, kpis: Dict, alerts: list, ai_report: Optional[Dict] = None,
                      filename: Optional[str] = None) -> str:
        """Generate a professional PDF report."""
        if filename is None:
            filename = f"factory_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        
        filepath = os.path.join(DATA_EXPORTS_DIR, filename)
        
        doc = SimpleDocTemplate(
            filepath, pagesize=A4,
            rightMargin=40, leftMargin=40,
            topMargin=40, bottomMargin=40
        )
        
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle', parent=styles['Title'],
            fontSize=20, spaceAfter=20, textColor=colors.HexColor("#1a237e")
        )
        heading_style = ParagraphStyle(
            'CustomHeading', parent=styles['Heading2'],
            fontSize=14, spaceAfter=10, textColor=colors.HexColor("#283593")
        )
        normal_style = styles["Normal"]
        
        elements = []
        
        # Title
        elements.append(Paragraph(f"{FACTORY_NAME}", title_style))
        elements.append(Paragraph(
            f"Daily Manufacturing Report<br/>"
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            styles["Normal"]
        ))
        elements.append(Spacer(1, 20))
        
        # AI Summary
        if ai_report:
            elements.append(Paragraph("Executive Summary", heading_style))
            elements.append(Paragraph(ai_report.get("summary", "N/A"), normal_style))
            elements.append(Spacer(1, 10))
            
            # Key Metrics
            metrics = ai_report.get("key_metrics", {})
            if metrics:
                elements.append(Paragraph("Key Metrics", heading_style))
                metrics_data = [["Metric", "Value"]]
                for k, v in metrics.items():
                    metrics_data.append([k.replace("_", " ").title(), str(v)])
                
                t = Table(metrics_data, colWidths=[200, 200])
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#283593")),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTSIZE', (0, 0), (-1, -1), 10),
                    ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ]))
                elements.append(t)
                elements.append(Spacer(1, 15))
        
        # Production KPIs table
        if "daily_production" in kpis and not kpis["daily_production"].empty:
            elements.append(Paragraph("Daily Production", heading_style))
            prod_data = kpis["daily_production"].tail(7).round(1)
            prod_table = [list(prod_data.columns)] + prod_data.values.tolist()
            
            available_width = 495
            num_cols = len(prod_data.columns)
            col_width = min(70, available_width // max(num_cols, 1))
            t = Table(prod_table, colWidths=[col_width] * num_cols)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#283593")),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTSIZE', (0, 0), (-1, -1), 7),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ]))
            elements.append(t)
            elements.append(Spacer(1, 15))
        
        # Alerts
        if alerts:
            elements.append(Paragraph("Active Alerts", heading_style))
            alert_rows = [["Level", "Category", "Message"]]
            for a in alerts[:10]:
                alert_rows.append([a.get("level", ""), a.get("category", ""), a.get("message", "")[:60]])
            
            t = Table(alert_rows, colWidths=[60, 80, 260])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#c62828")),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ]))
            elements.append(t)
            elements.append(Spacer(1, 15))
        
        # Problems and Recommendations
        if ai_report:
            problems = ai_report.get("problems", [])
            if problems:
                elements.append(Paragraph("Identified Problems", heading_style))
                for p in problems[:5]:
                    elements.append(Paragraph(
                        f"• <b>{p.get('issue', '')}</b> "
                        f"[Severity: {p.get('severity', '')}]<br/>"
                        f"  Impact: {p.get('impact', '')}",
                        normal_style
                    ))
                elements.append(Spacer(1, 10))
            
            recommendations = ai_report.get("recommendations", [])
            if recommendations:
                elements.append(Paragraph("Recommendations", heading_style))
                for r in recommendations[:5]:
                    elements.append(Paragraph(
                        f"• <b>{r.get('action', '')}</b> "
                        f"[Priority: {r.get('priority', '')}]<br/>"
                        f"  Expected Benefit: {r.get('expected_benefit', '')}",
                        normal_style
                    ))
                elements.append(Spacer(1, 10))
        
        # Footer
        elements.append(Spacer(1, 30))
        elements.append(Paragraph(
            f"Smart Manufacturing Platform - Auto-generated Report<br/>"
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=colors.grey)
        ))
        
        doc.build(elements)
        print(f"PDF report saved: {filepath}")
        return filepath
    
    def export_all(self, kpis: Dict, alerts: list, ai_report: Optional[Dict] = None) -> Dict:
        """Export both Excel and PDF reports."""
        return {
            "excel": self.export_to_excel(kpis, alerts),
            "pdf": self.export_to_pdf(kpis, alerts, ai_report),
            "timestamp": datetime.now().isoformat()
        }