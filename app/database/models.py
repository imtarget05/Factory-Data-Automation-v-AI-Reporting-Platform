"""
Database models for the Smart Manufacturing Platform.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from app.utils.config import DATABASE_URL

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class ProductionRecord(Base):
    __tablename__ = "production_records"

    id = Column(Integer, primary_key=True, index=True)
    Date = Column(DateTime)
    Line = Column(String)
    Shift = Column(String)
    Product = Column(String)
    Machine_ID = Column(String)
    Worker_ID = Column(String)
    Target_Qty = Column(Integer)
    Actual_Qty = Column(Integer)
    Good_Qty = Column(Integer)
    Reject_Qty = Column(Integer)
    Cycle_Time_sec = Column(Float)
    Created_At = Column(DateTime, default=datetime.utcnow)


class QualityRecord(Base):
    __tablename__ = "quality_records"

    id = Column(Integer, primary_key=True, index=True)
    Date = Column(DateTime)
    Product = Column(String)
    Line = Column(String)
    Defect_Type = Column(String)
    Defect_Count = Column(Integer)
    Inspected_Qty = Column(Integer)
    Severity = Column(String)
    Inspector_ID = Column(String)
    Created_At = Column(DateTime, default=datetime.utcnow)


class InventoryRecord(Base):
    __tablename__ = "inventory_records"

    id = Column(Integer, primary_key=True, index=True)
    Date = Column(DateTime)
    Product = Column(String)
    Stock_Qty = Column(Integer)
    Incoming_Qty = Column(Integer)
    Outgoing_Qty = Column(Integer)
    Reorder_Point = Column(Integer)
    Max_Capacity = Column(Integer)
    Unit_Price = Column(Float)
    Supplier = Column(String)
    Created_At = Column(DateTime, default=datetime.utcnow)


class MachineRecord(Base):
    __tablename__ = "machine_records"

    id = Column(Integer, primary_key=True, index=True)
    Date = Column(DateTime)
    Machine_ID = Column(String)
    Status = Column(String)
    Speed_RPM = Column(Float)
    Temperature_C = Column(Float)
    Vibration_mm = Column(Float)
    Power_Usage_pct = Column(Float)
    Downtime_min = Column(Integer)
    Line = Column(String)
    Created_At = Column(DateTime, default=datetime.utcnow)


class WorkerRecord(Base):
    __tablename__ = "worker_records"

    id = Column(Integer, primary_key=True, index=True)
    Date = Column(DateTime)
    Worker_ID = Column(String)
    Line = Column(String)
    Shift = Column(String)
    Hours_Worked = Column(Float)
    Units_Produced = Column(Integer)
    Defects_Caused = Column(Integer)
    Attendance = Column(String)
    Overtime_hrs = Column(Float)
    Created_At = Column(DateTime, default=datetime.utcnow)


class AlertRecord(Base):
    __tablename__ = "alert_records"

    id = Column(Integer, primary_key=True, index=True)
    Level = Column(String)
    Category = Column(String)
    Message = Column(Text)
    Value = Column(Float, nullable=True)
    Threshold = Column(Float, nullable=True)
    Source = Column(String, nullable=True)
    Timestamp = Column(DateTime, default=datetime.utcnow)
    Resolved = Column(Integer, default=0)


class KPIHistory(Base):
    __tablename__ = "kpi_history"

    id = Column(Integer, primary_key=True, index=True)
    Date = Column(DateTime)
    KPI_Name = Column(String)
    KPI_Value = Column(Float)
    Category = Column(String)
    Created_At = Column(DateTime, default=datetime.utcnow)


class ETLRunManifest(Base):
    __tablename__ = "etl_run_manifests"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String, unique=True, index=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    status = Column(String, default="RUNNING")  # RUNNING, SUCCESS, FAILED
    rows_ingested = Column(Integer, default=0)
    rows_quarantined = Column(Integer, default=0)
    checksum_sha256 = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)


class QuarantineRecord(Base):
    __tablename__ = "quarantine_records"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String, index=True, nullable=True)
    source_file = Column(String, index=True)
    row_index = Column(Integer, nullable=True)
    rejection_reason = Column(String)
    raw_payload = Column(Text)
    quarantined_at = Column(DateTime, default=datetime.utcnow)


# Create tables
def init_db():
    Base.metadata.create_all(bind=engine)
    print(f"Database initialized: {DATABASE_URL}")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
