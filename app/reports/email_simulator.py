"""
Email Alert Simulator — Module 7 (Alert) enhancement.
Simulates sending email alerts when critical conditions are met.
In production, replace with SMTP/ SendGrid / AWS SES.
"""
import os
import smtplib
import logging
from datetime import datetime
from typing import Dict, List, Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [EMAIL] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "data", "exports", "email_alerts.log"
        )),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("email_simulator")


class EmailAlertSimulator:
    """
    Simulates email alerts for manufacturing monitoring.
    In real deployment, configure SMTP settings below.
    """
    
    # SMTP Configuration (set these for real email sending)
    SMTP_SERVER = os.getenv("SMTP_SERVER", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    FROM_EMAIL = os.getenv("FROM_EMAIL", "alerts@smartfactory.com")
    TO_EMAILS = os.getenv("TO_EMAILS", "manager@smartfactory.com").split(",")
    
    def __init__(self, simulate: bool = True):
        """
        Args:
            simulate: If True, logs alerts instead of sending real emails.
                      Set to False and configure SMTP for real sending.
        """
        self.simulate = simulate
        self.sent_count = 0
    
    def send_alert(self, alert: Dict) -> bool:
        """Send an email alert for a given alert dict."""
        level = alert.get("level", "INFO")
        category = alert.get("category", "General")
        message = alert.get("message", "")
        timestamp = alert.get("timestamp", datetime.now().isoformat())
        
        subject = f"[{level}] Smart Factory Alert - {category}"
        
        body = f"""
========================================
SMART MANUFACTURING PLATFORM - ALERT
========================================

Level:     {level}
Category:  {category}
Time:      {timestamp}
Message:   {message}

---
This is an automated alert from Smart Factory Alpha.
"""

        if self.simulate:
            # Simulation mode: log to file and console
            logger.info(f"[{level}] {category}: {message}")
            self.sent_count += 1
            return True
        
        # Real email sending mode
        try:
            msg = MIMEMultipart()
            msg["From"] = self.FROM_EMAIL
            msg["To"] = ", ".join(self.TO_EMAILS)
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))
            
            with smtplib.SMTP(self.SMTP_SERVER, self.SMTP_PORT) as server:
                server.starttls()
                server.login(self.SMTP_USER, self.SMTP_PASSWORD)
                server.send_message(msg)
            
            logger.info(f"Email sent: {subject}")
            self.sent_count += 1
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False
    
    def send_batch(self, alerts: List[Dict], max_alerts: int = 5) -> int:
        """Send email alerts for critical/warning alerts only."""
        sent = 0
        # Prioritize CRITICAL, then WARNING
        sorted_alerts = sorted(alerts, 
            key=lambda a: {"CRITICAL": 0, "WARNING": 1, "INFO": 2}.get(a.get("level", "INFO"), 3))
        
        for alert in sorted_alerts[:max_alerts]:
            if self.send_alert(alert):
                sent += 1
        
        return sent
    
    def get_summary(self) -> Dict:
        """Get email sending summary."""
        return {
            "total_sent": self.sent_count,
            "mode": "simulation" if self.simulate else "live",
            "log_file": "data/exports/email_alerts.log"
        }


# Quick test
if __name__ == "__main__":
    simulator = EmailAlertSimulator(simulate=True)
    
    test_alerts = [
        {"level": "CRITICAL", "category": "Machine", 
         "message": "Machine M-08 is in FAILURE state!",
         "timestamp": datetime.now().isoformat()},
        {"level": "WARNING", "category": "Quality",
         "message": "Reject rate 6.2% exceeds threshold 5%",
         "timestamp": datetime.now().isoformat()},
        {"level": "WARNING", "category": "Inventory",
         "message": "Low stock: Running Shoe A1 - only 150 units remaining",
         "timestamp": datetime.now().isoformat()},
    ]
    
    sent = simulator.send_batch(test_alerts)
    print(f"\nSent {sent} email alerts (simulated)")
    print(f"Summary: {simulator.get_summary()}")