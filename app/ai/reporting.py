"""
AI Reporting Module — powered by local Qwen2.5 via Ollama.
Zero API costs, fully offline, runs entirely on your machine.
"""
import json
import time
import logging
import pandas as pd
from typing import Dict, List, Optional
from datetime import datetime
from app.ai.local_llm import get_llm
from app.utils.config import FACTORY_NAME
from app.utils.logging_config import get_logger, log_event

logger = get_logger("ai", "reporting")


class AIReportGenerator:
    """Generates AI-powered manufacturing reports using local Qwen model."""
    
    def __init__(self):
        self.llm = get_llm()
    
    def _build_context(self, kpis: Dict, alerts: List[Dict], datasets: Dict) -> str:
        """Build a rich context string from KPIs and alerts."""
        lines = []
        lines.append(f"Factory: {FACTORY_NAME}")
        lines.append(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        
        # Production summary
        daily_prod = kpis.get("daily_production")
        if daily_prod is not None and not daily_prod.empty:
            latest = daily_prod.iloc[-1]
            lines.append(f"\nTODAY'S PRODUCTION:")
            lines.append(f"- Target: {latest['Total_Target']:,.0f}")
            lines.append(f"- Actual: {latest['Total_Actual']:,.0f}")
            lines.append(f"- Achievement: {latest['Achievement_Rate_pct']:.1f}%")
            lines.append(f"- Reject Rate: {latest['Reject_Rate_pct']:.1f}%")
            lines.append(f"- Yield: {latest['Yield_pct']:.1f}%")
        
        # OEE
        oee = kpis.get("oee")
        if oee is not None and not oee.empty:
            latest_oee = oee.iloc[-1]
            lines.append(f"\nOEE:")
            lines.append(f"- Overall: {latest_oee['OEE_pct']:.1f}%")
            lines.append(f"- Availability: {latest_oee['Availability_pct']:.1f}%")
            lines.append(f"- Performance: {latest_oee['Performance_pct']:.1f}%")
            lines.append(f"- Quality: {latest_oee['Quality_pct']:.1f}%")
        
        # Machine status
        mach_util = kpis.get("machine_utilization")
        if mach_util is not None and not mach_util.empty:
            latest_mach = mach_util[mach_util["Date"] == mach_util["Date"].max()]
            if not latest_mach.empty:
                failed = latest_mach[latest_mach["Failure_Count"] > 0]
                high_downtime = latest_mach[latest_mach["Total_Downtime"] > 30]
                lines.append(f"\nMACHINE STATUS:")
                lines.append(f"- Machines with failures: {len(failed)}")
                lines.append(f"- High downtime machines: {len(high_downtime)}")
                if not failed.empty:
                    lines.append(f"- Failed machines: {', '.join(failed['Machine_ID'].tolist())}")
        
        # Quality
        defect = kpis.get("defect_analysis", {})
        if defect:
            by_type = defect.get("by_type")
            if by_type is not None and not by_type.empty:
                top_defect = by_type.iloc[0]
                lines.append(f"\nQUALITY:")
                lines.append(f"- Top defect: {top_defect['Defect_Type']} ({top_defect['Total_Defects']} defects)")
        
        # Inventory
        inv_kpi = kpis.get("inventory_kpi")
        if inv_kpi is not None and not inv_kpi.empty:
            latest_inv = inv_kpi.iloc[-1]
            lines.append(f"\nINVENTORY:")
            lines.append(f"- Total Stock: {latest_inv['Total_Stock']:,.0f}")
            lines.append(f"- Stock Value: ${latest_inv['Stock_Value']:,.2f}")
        
        # Alerts
        if alerts:
            lines.append(f"\nALERTS ({len(alerts)} total):")
            for a in alerts[:10]:
                lines.append(f"- [{a['level']}] {a['category']}: {a['message']}")
        
        return "\n".join(lines)
    
    def generate_report(self, kpis: Dict, alerts: List[Dict], datasets: Dict) -> Dict:
        """Generate AI report from KPIs and alerts using local Qwen."""
        start = time.time()
        context = self._build_context(kpis, alerts, datasets)
        
        if self.llm.available:
            log_event(logger, "llm_report_start", component="ai_reporting",
                      llm_model="qwen2.5", alerts_count=len(alerts))
            prompt = f"""You are a Senior Manufacturing Operations Analyst. Analyze this factory data and provide a structured executive report.

FACTORY DATA:
{context}

Return your analysis as JSON with these exact fields:
- "title": "Daily Manufacturing Performance Report"
- "date": "{datetime.now().strftime('%Y-%m-%d')}"
- "summary": 2-3 sentence executive summary
- "key_metrics": object with production_achievement, reject_rate, oee, inventory_status
- "problems": array of {{"issue", "severity", "impact"}}
- "root_causes": array of {{"cause", "evidence"}}
- "recommendations": array of {{"action", "priority", "expected_benefit"}}
- "risks": array of {{"risk", "probability", "mitigation"}}

Respond ONLY with valid JSON. No markdown, no code blocks, no explanation."""

            system_prompt = "You are a manufacturing analyst. Always respond with valid JSON only."
            report = self.llm.generate_json(prompt, system_prompt)
            elapsed_ms = round((time.time() - start) * 1000, 2)
            if report:
                log_event(logger, "llm_report_success", component="ai_reporting",
                          duration_ms=elapsed_ms, report_keys=list(report.keys()))
                return report
            log_event(logger, "llm_report_fallback", level=logging.WARNING, component="ai_reporting",
                      duration_ms=elapsed_ms, reason="llm_returned_none")
        
        # Fallback: generate a data-driven mock report
        elapsed_ms = round((time.time() - start) * 1000, 2)
        log_event(logger, "data_driven_report", component="ai_reporting",
                  duration_ms=elapsed_ms)
        return self._generate_data_driven_report(kpis, alerts)
    
    def _generate_data_driven_report(self, kpis: Dict, alerts: List[Dict]) -> Dict:
        """Generate a report based purely on actual data (no AI needed)."""
        daily_prod = kpis.get("daily_production")
        latest_prod = daily_prod.iloc[-1] if daily_prod is not None and not daily_prod.empty else None
        
        oee = kpis.get("oee")
        latest_oee = oee.iloc[-1] if oee is not None and not oee.empty else None
        
        problems = []
        recommendations = []
        risks = []
        
        # Data-driven problem detection
        if latest_prod is not None:
            achievement = latest_prod["Achievement_Rate_pct"]
            reject = latest_prod["Reject_Rate_pct"]
            
            if achievement < 90:
                problems.append({
                    "issue": f"Production achievement at {achievement:.1f}% — below 90% target",
                    "severity": "High",
                    "impact": "Missing production targets affects delivery schedules and revenue"
                })
                recommendations.append({
                    "action": "Review production line scheduling and optimize shift allocation",
                    "priority": "High",
                    "expected_benefit": "Improve production achievement to 95%+"
                })
            
            if reject > 5:
                problems.append({
                    "issue": f"Reject rate at {reject:.1f}% exceeds 5% threshold",
                    "severity": "High",
                    "impact": "Increased waste and rework costs"
                })
                recommendations.append({
                    "action": "Conduct root cause analysis on top defect types and implement corrective actions",
                    "priority": "High",
                    "expected_benefit": "Reduce reject rate to below 3%"
                })
        
        if latest_oee is not None and latest_oee["OEE_pct"] < 85:
            problems.append({
                "issue": f"OEE at {latest_oee['OEE_pct']:.1f}% — below 85% world-class target",
                "severity": "Medium",
                "impact": "Reduced overall equipment effectiveness impacts production capacity"
            })
            recommendations.append({
                "action": "Focus on reducing downtime and improving changeover times",
                "priority": "Medium",
                "expected_benefit": "Increase OEE by 5-10 percentage points"
            })
        
        # Convert alerts to problems
        for a in alerts[:5]:
            if a.get("level") in ["CRITICAL", "WARNING"]:
                problems.append({
                    "issue": a["message"],
                    "severity": "High" if a.get("level") == "CRITICAL" else "Medium",
                    "impact": a.get("category", "Unknown")
                })
        
        if not recommendations:
            recommendations.append({
                "action": "Continue monitoring all KPIs and maintain current performance levels",
                "priority": "Low",
                "expected_benefit": "Sustained operational excellence"
            })
        
        if not risks:
            risks.append({
                "risk": "Market demand fluctuations may impact production planning",
                "probability": "Low",
                "mitigation": "Maintain flexible production capacity and safety stock"
            })
        
        # Build summary from actual data
        summary_parts = []
        if latest_prod is not None:
            summary_parts.append(f"Production achievement: {latest_prod['Achievement_Rate_pct']:.1f}% "
                                f"({'meeting' if latest_prod['Achievement_Rate_pct'] >= 90 else 'below'} target)")
            summary_parts.append(f"Reject rate: {latest_prod['Reject_Rate_pct']:.1f}% "
                                f"({'within' if latest_prod['Reject_Rate_pct'] <= 5 else 'exceeding'} threshold)")
        if latest_oee is not None:
            summary_parts.append(f"OEE: {latest_oee['OEE_pct']:.1f}%")
        
        summary = " | ".join(summary_parts) if summary_parts else "Factory data loaded and analyzed."
        
        return {
            "title": "Daily Manufacturing Performance Report",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "summary": summary,
            "key_metrics": {
                "production_achievement": f"{latest_prod['Achievement_Rate_pct']:.1f}%" if latest_prod is not None else "N/A",
                "reject_rate": f"{latest_prod['Reject_Rate_pct']:.1f}%" if latest_prod is not None else "N/A",
                "oee": f"{latest_oee['OEE_pct']:.1f}%" if latest_oee is not None else "N/A",
                "inventory_status": "Normal" if kpis.get("inventory_kpi") is not None else "N/A"
            },
            "problems": problems,
            "root_causes": [
                {
                    "cause": "Machine downtime and process variability",
                    "evidence": "Multiple machines report downtime events and quality defects show pattern variation"
                }
            ] if problems else [],
            "recommendations": recommendations,
            "risks": risks
        }
    
    def chat_query(self, query: str, context: Dict) -> str:
        """Handle AI chat queries about factory data using local Qwen."""
        context_str = json.dumps({
            "kpi_summary": {
                k: str(v.tail(1).to_dict(orient="records") if isinstance(v, pd.DataFrame) and not v.empty else v)
                for k, v in context.get("kpis", {}).items()
            },
            "dataset_shapes": {k: str(v.shape) for k, v in context.get("datasets", {}).items()}
        }, default=str)[:4000]
        
        if self.llm.available:
            prompt = f"""You are a manufacturing data analyst. Answer the question based on the factory data provided.

FACTORY DATA CONTEXT:
{context_str}

USER QUESTION: {query}

Provide a clear, concise answer. If the data doesn't contain enough information, say so."""
            
            response = self.llm.generate(prompt, temperature=0.3)
            if response:
                return response
        
        return self._mock_chat_response(query, context)
    
    def _mock_chat_response(self, query: str, context: Dict) -> str:
        """Generate a mock response when local LLM is unavailable."""
        query_lower = query.lower()
        
        if "downtime" in query_lower or "machine" in query_lower:
            mach_util = context.get("kpis", {}).get("machine_utilization")
            if isinstance(mach_util, pd.DataFrame) and not mach_util.empty:
                latest = mach_util[mach_util["Date"] == mach_util["Date"].max()]
                if not latest.empty:
                    worst = latest.loc[latest["Total_Downtime"].idxmax()]
                    return (f"Machine {worst['Machine_ID']} has the highest downtime "
                           f"with {worst['Total_Downtime']:.0f} minutes. "
                           f"Its utilization is {worst['Utilization_pct']:.1f}%.")
                return "Machine data available but no downtime records found."
            return "Machine data not available."
        
        if "production" in query_lower or "line" in query_lower:
            daily_prod = context.get("kpis", {}).get("daily_production")
            if isinstance(daily_prod, pd.DataFrame) and not daily_prod.empty:
                latest = daily_prod.iloc[-1]
                return (f"Latest production: {latest['Total_Actual']:,.0f} units "
                       f"(target: {latest['Total_Target']:,.0f}, "
                       f"achievement: {latest['Achievement_Rate_pct']:.1f}%, "
                       f"reject rate: {latest['Reject_Rate_pct']:.1f}%).")
            return "Production data not available."
        
        if "reject" in query_lower or "defect" in query_lower or "quality" in query_lower:
            defect = context.get("kpis", {}).get("defect_analysis", {})
            if isinstance(defect, dict):
                by_type = defect.get("by_type")
            elif isinstance(defect, pd.DataFrame):
                by_type = defect
            else:
                by_type = None
            if isinstance(by_type, pd.DataFrame) and not by_type.empty:
                top = by_type.iloc[0]
                return (f"Top defect type: '{top['Defect_Type']}' with {top['Total_Defects']} defects "
                       f"({top['Defect_Rate_pct']:.2f}% rate). "
                       f"Total inspected: {top['Total_Inspected']:,} units.")
            return "Quality data not available."
        
        if "inventory" in query_lower or "stock" in query_lower:
            inv_kpi = context.get("kpis", {}).get("inventory_kpi")
            if isinstance(inv_kpi, pd.DataFrame) and not inv_kpi.empty:
                latest = inv_kpi.iloc[-1]
                return (f"Total inventory: {latest['Total_Stock']:,.0f} units "
                       f"(value: ${latest['Stock_Value']:,.2f}, "
                       f"products below reorder: {latest['Products_Below_Reorder']:.0f}).")
            return "Inventory data not available."
        
        return (f"I've analyzed the factory data. The system tracks production, quality, inventory, "
               f"machine status, and worker productivity across {FACTORY_NAME}. "
               f"Try asking specific questions like 'Which machine has highest downtime?' "
               f"or 'What is the current reject rate?'")