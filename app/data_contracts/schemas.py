"""Pydantic v2 data contracts for the five factory datasets.

Separation-of-concerns contract (read before touching this file):

* **Contracts REJECT, cleaning FILLS.** A blank cell, ``None``, or a
  non-coercible value on a non-nullable field is a *violation* recorded in
  the :class:`~app.data_contracts.validator.ValidationReport` — it is never
  silently filled, defaulted, clipped, or dropped here. Imputation
  (median fill, ``Unknown_<col>`` fill, clipping negatives, …) lives
  exclusively in the cleaning stage (``app/etl/pipeline.py``), which runs
  *after* validation and quarantines rejected rows first.
* Numeric strings are *coerced* (``"42"`` -> ``42``); anything that cannot
  be coerced to the declared type is a violation.
* Extra/unknown columns are *ignored* (``extra="ignore"``) — they are not
  violations, so additive upstream schema changes never break validation.
* Only the stdlib + pydantic surface is used: no pandas, no numpy.

Column headers match ``scripts/generate_sample_data.py`` (and the
``tests/conftest.py`` fallback seeder) exactly and are used verbatim as
pydantic field names so a ``csv.DictReader`` row validates directly.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

NonEmptyStr = Annotated[str, Field(min_length=1)]

_NON_NULLABLE_MSG = (
    "blank/None on a non-nullable field is a violation "
    "(contracts reject; cleaning fills)"
)


def _not_in_future(value: date) -> date:
    """Reject ISO dates after today (wall-clock comparison, ``date.today``)."""
    if value > date.today():
        raise ValueError(f"Date {value.isoformat()} is in the future")
    return value


CheckedDate = Annotated[date, AfterValidator(_not_in_future)]


class _StrictRow(BaseModel):
    """Shared config: ignore extra columns, strip strings, reject blanks."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    @field_validator("*", mode="before")
    @classmethod
    def _reject_blank_and_none(cls, value: Any) -> Any:
        # Blank strings / None on ANY field are violations. The cleaning
        # stage (not contracts) is responsible for filling them.
        if value is None or (isinstance(value, str) and value.strip() == ""):
            raise ValueError(_NON_NULLABLE_MSG)
        return value


class ProductionRow(_StrictRow):
    """One row of production.csv (target vs actual, good vs reject)."""

    Date: CheckedDate
    Line: NonEmptyStr
    Shift: NonEmptyStr
    Product: NonEmptyStr
    Machine_ID: NonEmptyStr
    Worker_ID: NonEmptyStr
    Target_Qty: Annotated[int, Field(ge=0)]
    Actual_Qty: Annotated[int, Field(ge=0)]
    Good_Qty: Annotated[int, Field(ge=0)]
    Reject_Qty: Annotated[int, Field(ge=0)]
    Cycle_Time_sec: Annotated[float, Field(ge=0)]
    Created_At: NonEmptyStr

    @model_validator(mode="after")
    def _reject_lte_actual(self):
        if self.Reject_Qty > self.Actual_Qty:
            raise ValueError(
                f"Reject_Qty ({self.Reject_Qty}) must be <= Actual_Qty ({self.Actual_Qty})"
            )
        return self


class QualityRow(_StrictRow):
    """One row of quality.csv (defect counts vs inspected quantity)."""

    Date: CheckedDate
    Product: NonEmptyStr
    Line: NonEmptyStr
    Defect_Type: NonEmptyStr
    Defect_Count: Annotated[int, Field(ge=0)]
    Inspected_Qty: Annotated[int, Field(ge=0)]
    Severity: NonEmptyStr
    Inspector_ID: NonEmptyStr
    Created_At: NonEmptyStr

    @model_validator(mode="after")
    def _defect_lte_inspected(self):
        if self.Defect_Count > self.Inspected_Qty:
            raise ValueError(
                f"Defect_Count ({self.Defect_Count}) must be <= "
                f"Inspected_Qty ({self.Inspected_Qty})"
            )
        return self


class InventoryRow(_StrictRow):
    """One row of inventory.csv (stock position per product per day)."""

    Date: CheckedDate
    Product: NonEmptyStr
    Stock_Qty: Annotated[int, Field(ge=0)]
    Incoming_Qty: Annotated[int, Field(ge=0)]
    Outgoing_Qty: Annotated[int, Field(ge=0)]
    Reorder_Point: Annotated[int, Field(ge=0)]
    Max_Capacity: Annotated[int, Field(ge=0)]
    Unit_Price: Annotated[float, Field(ge=0)]
    Supplier: NonEmptyStr
    Created_At: NonEmptyStr


class MachineRow(_StrictRow):
    """One row of machine.csv (telemetry: status, speed, temp, downtime)."""

    Date: CheckedDate
    Machine_ID: NonEmptyStr
    Status: NonEmptyStr
    Speed_RPM: float
    Temperature_C: float
    Vibration_mm: float
    Power_Usage_pct: float
    Downtime_min: Annotated[float, Field(ge=0)]
    Line: NonEmptyStr
    Created_At: NonEmptyStr


class WorkerRow(_StrictRow):
    """One row of workers.csv (attendance, hours, units, defects)."""

    Date: CheckedDate
    Worker_ID: NonEmptyStr
    Line: NonEmptyStr
    Shift: NonEmptyStr
    Hours_Worked: Annotated[float, Field(ge=0, le=24)]
    Units_Produced: Annotated[int, Field(ge=0)]
    Defects_Caused: Annotated[int, Field(ge=0)]
    Attendance: NonEmptyStr
    Overtime_hrs: Annotated[float, Field(ge=0)]
    Created_At: NonEmptyStr


DATASET_MODELS: dict[str, type[_StrictRow]] = {
    "production": ProductionRow,
    "quality": QualityRow,
    "inventory": InventoryRow,
    "machine": MachineRow,
    "workers": WorkerRow,
}
