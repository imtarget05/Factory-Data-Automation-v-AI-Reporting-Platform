"""Tests for Service Bus Telemetry Consumer."""

import pytest

from app.database.models import ETLRunManifest, SessionLocal, init_db
from app.etl.servicebus_consumer import TelemetryConsumer


@pytest.fixture(autouse=True)
def setup_database():
    init_db()


def test_telemetry_consumer_accepts_valid_message():
    consumer = TelemetryConsumer()
    msg = {
        "id": "telemetry-001",
        "Machine_ID": "CNC-01",
        "Date": "2026-10-01T12:00:00",
        "Line": "Line_A",
        "Speed_RPM": 1500.0,
    }
    result = consumer.process_message(msg)
    assert result["status"] == "accepted"
    assert result["message_id"] == "telemetry-001"
    assert result["machine_id"] == "CNC-01"


def test_telemetry_consumer_deduplicates_messages():
    consumer = TelemetryConsumer()
    msg = {
        "id": "telemetry-repeat",
        "Machine_ID": "CNC-02",
        "Date": "2026-10-01T12:00:00",
        "Line": "Line_B",
    }
    res1 = consumer.process_message(msg)
    res2 = consumer.process_message(msg)
    assert res1["status"] == "accepted"
    assert res2["status"] == "duplicate_skipped"


def test_telemetry_consumer_quarantines_invalid_message():
    consumer = TelemetryConsumer()
    # Missing Date and negative speed
    msg = {
        "id": "telemetry-corrupt-01",
        "Machine_ID": "CNC-03",
        "Speed_RPM": -50.0,
    }
    result = consumer.process_message(msg)
    assert result["status"] == "quarantined"
    assert "Contract violation" in result["reason"]


def test_telemetry_consumer_batch_and_manifest():
    consumer = TelemetryConsumer()
    batch = [
        {
            "id": "batch-1",
            "Machine_ID": "CNC-01",
            "Date": "2026-10-01T12:00:00",
            "Line": "Line_A",
        },
        {
            "id": "batch-2",
            "Machine_ID": "CNC-02",
            # Missing Line
            "Date": "2026-10-01T12:00:00",
        },
        {
            "id": "batch-1",  # duplicate
            "Machine_ID": "CNC-01",
            "Date": "2026-10-01T12:00:00",
            "Line": "Line_A",
        },
    ]
    summary = consumer.process_batch(batch, run_id="test-run-999")
    assert summary["status"] == "SUCCESS"
    assert summary["rows_ingested"] == 1
    assert summary["rows_quarantined"] == 1
    assert summary["duplicates_skipped"] == 1

    # Verify run manifest persisted
    db = SessionLocal()
    manifest = db.query(ETLRunManifest).filter_by(run_id="test-run-999").first()
    assert manifest is not None
    assert manifest.rows_ingested == 1
    assert manifest.rows_quarantined == 1
    db.close()
