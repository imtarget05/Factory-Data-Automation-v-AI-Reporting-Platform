"""
ML Models Demo — Random Forest & XGBoost for Manufacturing Predictions

Demonstrates classic ML algorithms applied to factory data:
1. Quality Defect Prediction (Random Forest) — binary classification
2. Machine Downtime Prediction (XGBoost) — binary classification

Metrics: Accuracy, Precision, Recall, F1-score, Confusion Matrix

Usage:
    python notebooks/ml_models_demo.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    confusion_matrix, classification_report
)
from sklearn.preprocessing import LabelEncoder
import warnings
warnings.filterwarnings("ignore")

try:
    from xgboost import XGBClassifier
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False
    print("⚠️  XGBoost not installed. Run: pip install xgboost")


def load_factory_data():
    """Load or generate factory data."""
    from app.utils.data_generator import (
        generate_production_data, generate_quality_data,
        generate_machine_data, generate_inventory_data, generate_worker_data
    )
    print("📊 Generating synthetic factory data (80K+ records)...")
    production = generate_production_data(days=90, rows_per_day=500)
    quality = generate_quality_data(days=90, rows_per_day=100)
    machine = generate_machine_data(days=90, rows_per_day=200)
    inventory = generate_inventory_data(days=90)
    workers = generate_worker_data(days=90)
    print(f"   Production: {len(production)} rows")
    print(f"   Quality:    {len(quality)} rows")
    print(f"   Machine:    {len(machine)} rows")
    print(f"   Inventory:  {len(inventory)} rows")
    print(f"   Workers:    {len(workers)} rows")
    return production, quality, machine, inventory, workers


# ─────────────────────────────────────────────────────────────
# MODEL 1: Quality Defect Prediction (Random Forest)
# ─────────────────────────────────────────────────────────────

def prepare_quality_features(production, quality):
    """Prepare features for quality defect prediction."""
    prod_daily = production.groupby(["Date", "Line", "Shift"]).agg(
        Target_Qty=("Target_Qty", "sum"),
        Actual_Qty=("Actual_Qty", "sum"),
        Good_Qty=("Good_Qty", "sum"),
        Reject_Qty=("Reject_Qty", "sum"),
        Avg_Cycle_Time=("Cycle_Time_sec", "mean"),
        Machine_Count=("Machine_ID", "nunique"),
    ).reset_index()

    prod_daily["Reject_Rate"] = prod_daily["Reject_Qty"] / prod_daily["Actual_Qty"]
    prod_daily["Achievement_Rate"] = prod_daily["Actual_Qty"] / prod_daily["Target_Qty"]

    quality_daily = quality.groupby(["Date", "Line"]).agg(
        Total_Defects=("Defect_Count", "sum"),
        Inspected=("Inspected_Qty", "sum"),
        Critical_Count=("Severity", lambda x: (x == "Critical").sum()),
    ).reset_index()
    quality_daily["Defect_Rate"] = quality_daily["Total_Defects"] / quality_daily["Inspected"]

    merged = prod_daily.merge(quality_daily, on=["Date", "Line"], how="left")
    merged["Total_Defects"] = merged["Total_Defects"].fillna(0)
    merged["Defect_Rate"] = merged["Defect_Rate"].fillna(0)
    merged["Critical_Count"] = merged["Critical_Count"].fillna(0)
    merged["High_Defect"] = (merged["Reject_Rate"] > 0.05).astype(int)

    le_line = LabelEncoder()
    le_shift = LabelEncoder()
    merged["Line_Enc"] = le_line.fit_transform(merged["Line"])
    merged["Shift_Enc"] = le_shift.fit_transform(merged["Shift"])

    features = ["Target_Qty", "Actual_Qty", "Avg_Cycle_Time", "Machine_Count",
                "Reject_Rate", "Achievement_Rate", "Total_Defects", "Inspected",
                "Critical_Count", "Line_Enc", "Shift_Enc"]
    X = merged[features].fillna(0)
    y = merged["High_Defect"]
    return X, y, merged


def train_quality_model(X, y):
    """Train Random Forest for quality defect prediction."""
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    rf = RandomForestClassifier(
        n_estimators=100, max_depth=10, min_samples_split=5,
        random_state=42, n_jobs=-1
    )
    rf.fit(X_train, y_train)
    y_pred = rf.predict(X_test)

    metrics = {
        "accuracy": accuracy_score(y_test, y_pred),
        "precision": precision_score(y_test, y_pred, zero_division=0),
        "recall": recall_score(y_test, y_pred, zero_division=0),
        "f1": f1_score(y_test, y_pred, zero_division=0),
    }
    cm = confusion_matrix(y_test, y_pred)
    importances = dict(zip(X.columns, rf.feature_importances_))
    return rf, metrics, cm, importances, X_test, y_test


# ─────────────────────────────────────────────────────────────
# MODEL 2: Machine Downtime Prediction (XGBoost)
# ─────────────────────────────────────────────────────────────

def prepare_downtime_features(machine):
    """Prepare features for machine downtime prediction."""
    machine["Has_Downtime"] = (machine["Downtime_min"] > 0).astype(int)
    machine["Is_Failure"] = (machine["Status"] == "Failure").astype(int)
    machine["Date"] = pd.to_datetime(machine["Date"])
    machine["DayOfWeek"] = machine["Date"].dt.dayofweek
    machine["Hour"] = machine["Date"].dt.hour

    le_machine = LabelEncoder()
    le_status = LabelEncoder()
    le_line = LabelEncoder()
    machine["Machine_Enc"] = le_machine.fit_transform(machine["Machine_ID"])
    machine["Status_Enc"] = le_status.fit_transform(machine["Status"])
    machine["Line_Enc"] = le_line.fit_transform(machine["Line"])

    features = ["Speed_RPM", "Temperature_C", "Vibration_mm", "Power_Usage_pct",
                "Machine_Enc", "Status_Enc", "Line_Enc", "DayOfWeek"]
    X = machine[features].fillna(0)
    y = machine["Has_Downtime"]
    return X, y, machine


def train_downtime_model(X, y):
    """Train XGBoost for machine downtime prediction."""
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    if XGBOOST_AVAILABLE:
        model = XGBClassifier(
            n_estimators=100, max_depth=6, learning_rate=0.1,
            use_label_encoder=False, eval_metric="logloss",
            random_state=42, n_jobs=-1
        )
        model.fit(X_train, y_train)
    else:
        model = RandomForestClassifier(
            n_estimators=100, max_depth=10, random_state=42, n_jobs=-1
        )
        model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    metrics = {
        "accuracy": accuracy_score(y_test, y_pred),
        "precision": precision_score(y_test, y_pred, zero_division=0),
        "recall": recall_score(y_test, y_pred, zero_division=0),
        "f1": f1_score(y_test, y_pred, zero_division=0),
    }
    cm = confusion_matrix(y_test, y_pred)
    importances = dict(zip(X.columns, model.feature_importances_))
    return model, metrics, cm, importances, X_test, y_test


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def print_metrics(name, metrics, cm, importances):
    """Print formatted metrics."""
    print(f"\n{'='*60}")
    print(f"📊 {name}")
    print(f"{'='*60}")
    print(f"  Accuracy:  {metrics['accuracy']:.2%}")
    print(f"  Precision: {metrics['precision']:.2%}")
    print(f"  Recall:    {metrics['recall']:.2%}")
    print(f"  F1-score:  {metrics['f1']:.2%}")
    print(f"\n  Confusion Matrix:")
    print(f"    TN={cm[0][0]:4d}  FP={cm[0][1]:4d}")
    print(f"    FN={cm[1][0]:4d}  TP={cm[1][1]:4d}")
    print(f"\n  Top 5 Feature Importances:")
    sorted_imp = sorted(importances.items(), key=lambda x: x[1], reverse=True)[:5]
    for feat, imp in sorted_imp:
        print(f"    {feat:25s} {imp:.4f}")


def main():
    print("="*60)
    print("🏭 ML Models Demo — Factory Data Automation Platform")
    print("="*60)

    production, quality, machine, inventory, workers = load_factory_data()

    # Model 1: Quality Defect Prediction
    print("\n\n🔧 MODEL 1: Quality Defect Prediction (Random Forest)")
    print("   Target: Predict if production batch has >5% defect rate")
    X_q, y_q, merged = prepare_quality_features(production, quality)
    print(f"   Features: {X_q.shape[1]} | Samples: {X_q.shape[0]} | Positive: {y_q.mean():.1%}")
    rf_model, rf_metrics, rf_cm, rf_imp, _, _ = train_quality_model(X_q, y_q)
    print_metrics("Random Forest — Quality Defect Prediction", rf_metrics, rf_cm, rf_imp)

    # Model 2: Machine Downtime Prediction
    print("\n\n🔧 MODEL 2: Machine Downtime Prediction (XGBoost)")
    print("   Target: Predict if machine will have downtime >0 min")
    X_d, y_d, machine_feat = prepare_downtime_features(machine)
    print(f"   Features: {X_d.shape[1]} | Samples: {X_d.shape[0]} | Positive: {y_d.mean():.1%}")
    xgb_model, xgb_metrics, xgb_cm, xgb_imp, _, _ = train_downtime_model(X_d, y_d)
    model_name = "XGBoost" if XGBOOST_AVAILABLE else "Random Forest (fallback)"
    print_metrics(f"{model_name} — Machine Downtime Prediction", xgb_metrics, xgb_cm, xgb_imp)

    # Summary
    print("\n\n" + "="*60)
    print("📋 SUMMARY")
    print("="*60)
    print(f"  Model 1 (Quality Prediction — RF):")
    print(f"    Accuracy={rf_metrics['accuracy']:.2%}  F1={rf_metrics['f1']:.2%}")
    print(f"  Model 2 (Downtime Prediction — {model_name}):")
    print(f"    Accuracy={xgb_metrics['accuracy']:.2%}  F1={xgb_metrics['f1']:.2%}")
    print("\n✅ All models trained and evaluated successfully.")


if __name__ == "__main__":
    main()
