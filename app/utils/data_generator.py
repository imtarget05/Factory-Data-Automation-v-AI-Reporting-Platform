"""
Synthetic Data Generator for Smart Manufacturing Platform.
Generates realistic factory data for 90 days across 5 datasets.
"""
import os
import random
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from faker import Faker
from app.utils.config import (
    DATA_RAW_DIR, PRODUCTION_LINES, MACHINES, PRODUCTS, WORKERS, DEFAULT_SHIFTS
)

fake = Faker()
np.random.seed(42)
random.seed(42)


def generate_production_data(days: int = 90, rows_per_day: int = 500) -> pd.DataFrame:
    """Generate production records."""
    records = []
    start_date = datetime(2026, 1, 1)
    
    for d in range(days):
        date = start_date + timedelta(days=d)
        if date.weekday() >= 5:  # Weekend - lower production
            multiplier = 0.6
        else:
            multiplier = 1.0
        
        for _ in range(rows_per_day):
            line = random.choice(PRODUCTION_LINES)
            product = random.choice(PRODUCTS)
            shift = random.choice(DEFAULT_SHIFTS)
            machine = random.choice(MACHINES)
            worker = random.choice(WORKERS)
            
            target = int(np.random.normal(500, 50) * multiplier)
            actual = int(target * np.random.uniform(0.85, 1.05))
            good_qty = int(actual * np.random.uniform(0.92, 0.99))
            reject_qty = actual - good_qty
            
            records.append({
                "Date": date.strftime("%Y-%m-%d"),
                "Line": line,
                "Shift": shift,
                "Product": product,
                "Machine_ID": machine,
                "Worker_ID": worker,
                "Target_Qty": target,
                "Actual_Qty": actual,
                "Good_Qty": good_qty,
                "Reject_Qty": reject_qty,
                "Cycle_Time_sec": round(np.random.uniform(30, 120), 1),
                "Created_At": datetime.now().isoformat()
            })
    
    return pd.DataFrame(records)


def generate_quality_data(days: int = 90, rows_per_day: int = 100) -> pd.DataFrame:
    """Generate quality inspection records."""
    records = []
    start_date = datetime(2026, 1, 1)
    defect_types = ["Scratch", "Color Mismatch", "Size Error", "Material Defect", 
                    "Stitching Issue", "Sole Detachment", "Label Error", "Packaging Damage"]
    
    for d in range(days):
        date = start_date + timedelta(days=d)
        for _ in range(rows_per_day):
            records.append({
                "Date": date.strftime("%Y-%m-%d"),
                "Product": random.choice(PRODUCTS),
                "Line": random.choice(PRODUCTION_LINES),
                "Defect_Type": random.choice(defect_types),
                "Defect_Count": int(np.random.exponential(3) + 1),
                "Inspected_Qty": int(np.random.normal(200, 30)),
                "Severity": random.choices(["Minor", "Major", "Critical"], weights=[0.6, 0.3, 0.1])[0],
                "Inspector_ID": random.choice(WORKERS),
                "Created_At": datetime.now().isoformat()
            })
    
    return pd.DataFrame(records)


def generate_inventory_data(days: int = 90) -> pd.DataFrame:
    """Generate inventory level records."""
    records = []
    start_date = datetime(2026, 1, 1)
    
    base_stock = {p: random.randint(300, 2000) for p in PRODUCTS}
    reorder_points = {p: random.randint(150, 500) for p in PRODUCTS}
    max_stock = {p: random.randint(2000, 5000) for p in PRODUCTS}
    
    for d in range(days):
        date = start_date + timedelta(days=d)
        daily_demand = {p: np.random.poisson(20 + hash(p) % 30) for p in PRODUCTS}
        daily_production = {p: np.random.poisson(15 + hash(p) % 25) for p in PRODUCTS}
        
        for product in PRODUCTS:
            product_demand = daily_demand[product]
            product_prod = daily_production[product]
            
            # Simulate stock changes
            if d == 0:
                stock = base_stock[product]
            else:
                stock = records[-len(PRODUCTS)]["Stock_Qty"] if len(records) >= len(PRODUCTS) else base_stock[product]
            
            stock = stock + product_prod - product_demand
            stock = max(0, min(stock, max_stock[product]))
            
            records.append({
                "Date": date.strftime("%Y-%m-%d"),
                "Product": product,
                "Stock_Qty": stock,
                "Incoming_Qty": product_prod,
                "Outgoing_Qty": product_demand,
                "Reorder_Point": reorder_points[product],
                "Max_Capacity": max_stock[product],
                "Unit_Price": round(random.uniform(10, 150), 2),
                "Supplier": fake.company(),
                "Created_At": datetime.now().isoformat()
            })
    
    return pd.DataFrame(records)


def generate_machine_data(days: int = 90, rows_per_day: int = 200) -> pd.DataFrame:
    """Generate machine status and performance records."""
    records = []
    start_date = datetime(2026, 1, 1)
    statuses = ["Running", "Idle", "Maintenance", "Failure"]
    status_weights = [0.75, 0.12, 0.08, 0.05]
    
    for d in range(days):
        date = start_date + timedelta(days=d)
        for _ in range(rows_per_day):
            machine = random.choice(MACHINES)
            status = random.choices(statuses, weights=status_weights)[0]
            
            if status == "Running":
                speed = np.random.uniform(85, 100)
                temp = np.random.uniform(65, 85)
                vibration = np.random.uniform(0.5, 3.0)
                power = np.random.uniform(70, 95)
            elif status == "Idle":
                speed = 0
                temp = np.random.uniform(40, 60)
                vibration = np.random.uniform(0.1, 0.5)
                power = np.random.uniform(5, 15)
            elif status == "Maintenance":
                speed = 0
                temp = np.random.uniform(25, 35)
                vibration = np.random.uniform(0, 0.2)
                power = 0
            else:  # Failure
                speed = 0
                temp = np.random.uniform(30, 50)
                vibration = np.random.uniform(5, 15)
                power = 0
            
            downtime = int(np.random.exponential(10)) if status in ["Maintenance", "Failure"] else 0
            
            records.append({
                "Date": date.strftime("%Y-%m-%d"),
                "Machine_ID": machine,
                "Status": status,
                "Speed_RPM": round(speed, 1),
                "Temperature_C": round(temp, 1),
                "Vibration_mm": round(vibration, 2),
                "Power_Usage_pct": round(power, 1),
                "Downtime_min": downtime,
                "Line": random.choice(PRODUCTION_LINES),
                "Created_At": datetime.now().isoformat()
            })
    
    return pd.DataFrame(records)


def generate_worker_data(days: int = 90) -> pd.DataFrame:
    """Generate worker productivity records."""
    records = []
    start_date = datetime(2026, 1, 1)
    
    for d in range(days):
        date = start_date + timedelta(days=d)
        for worker in WORKERS:
            if random.random() < 0.3:  # Skip some workers each day
                continue
            attendance = random.choice(["Present", "Present", "Present", "Absent", "Leave"])
            if attendance != "Present":
                continue
            
            hrs_worked = round(np.random.uniform(6, 10), 1)
            units_produced = int(np.random.normal(80, 15) * (hrs_worked / 8))
            defects = int(np.random.exponential(2))
            
            records.append({
                "Date": date.strftime("%Y-%m-%d"),
                "Worker_ID": worker,
                "Line": random.choice(PRODUCTION_LINES),
                "Shift": random.choice(DEFAULT_SHIFTS),
                "Hours_Worked": hrs_worked,
                "Units_Produced": units_produced,
                "Defects_Caused": defects,
                "Attendance": attendance,
                "Overtime_hrs": round(max(0, np.random.normal(0.5, 0.8)), 1),
                "Created_At": datetime.now().isoformat()
            })
    
    return pd.DataFrame(records)


def generate_all_data(days: int = 90):
    """Generate all 5 datasets and save to raw CSV files."""
    os.makedirs(DATA_RAW_DIR, exist_ok=True)
    
    print("Generating production data...")
    prod_df = generate_production_data(days)
    prod_df.to_csv(os.path.join(DATA_RAW_DIR, "production.csv"), index=False)
    print(f"  -> {len(prod_df)} records saved")
    
    print("Generating quality data...")
    qual_df = generate_quality_data(days)
    qual_df.to_csv(os.path.join(DATA_RAW_DIR, "quality.csv"), index=False)
    print(f"  -> {len(qual_df)} records saved")
    
    print("Generating inventory data...")
    inv_df = generate_inventory_data(days)
    inv_df.to_csv(os.path.join(DATA_RAW_DIR, "inventory.csv"), index=False)
    print(f"  -> {len(inv_df)} records saved")
    
    print("Generating machine data...")
    mach_df = generate_machine_data(days)
    mach_df.to_csv(os.path.join(DATA_RAW_DIR, "machine.csv"), index=False)
    print(f"  -> {len(mach_df)} records saved")
    
    print("Generating worker data...")
    work_df = generate_worker_data(days)
    work_df.to_csv(os.path.join(DATA_RAW_DIR, "workers.csv"), index=False)
    print(f"  -> {len(work_df)} records saved")
    
    print(f"\nTotal records generated: {len(prod_df) + len(qual_df) + len(inv_df) + len(mach_df) + len(work_df)}")
    print(f"Data saved to: {DATA_RAW_DIR}")
    
    return {
        "production": prod_df,
        "quality": qual_df,
        "inventory": inv_df,
        "machine": mach_df,
        "workers": work_df
    }


if __name__ == "__main__":
    generate_all_data()