"""Row/CSV validation against the Phase-2 data contracts (stdlib + pydantic).

``validate_rows`` never raises on bad *data*: every failure is carried by
the returned :class:`ValidationReport` as a ``{row_index, field, value,
rule}`` violation record so callers can quarantine rows. Only programmer
errors raise ``ValueError``: an unknown dataset name, or a missing file in
:meth:`validate_csv`.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field

from pydantic import ValidationError

from app.data_contracts.schemas import DATASET_MODELS

# Filename patterns mirror app/etl/pipeline.py::discover_files so dataset
# inference stays consistent between discovery and validation.
_DATASET_PATTERNS: dict[str, list[str]] = {
    "production": ["production", "prod"],
    "quality": ["quality", "qual"],
    "inventory": ["inventory", "inv", "stock"],
    "machine": ["machine", "mach", "equipment"],
    "workers": ["workers", "worker", "employee", "staff"],
}

_CSV_EXTENSIONS = (".csv", ".xlsx", ".xls")


@dataclass
class ValidationReport:
    """Outcome of validating a batch of rows.

    * ``passed``: one dict per accepted row, holding the *coerced* values
      (e.g. ``"42"`` -> ``42``).
    * ``violations``: one ``{row_index, field, value, rule}`` record per
      failed check; a single bad row may yield several records.
    """

    passed: list[dict] = field(default_factory=list)
    violations: list[dict] = field(default_factory=list)


def infer_dataset(filename: str) -> str:
    """Infer the dataset name from a filename; raise ``ValueError`` if unknown."""
    basename = os.path.basename(filename).lower()
    for ext in _CSV_EXTENSIONS:
        if basename.endswith(ext):
            basename = basename[: -len(ext)]
            break
    for dataset, patterns in _DATASET_PATTERNS.items():
        if dataset in basename or any(p in basename for p in patterns):
            return dataset
    raise ValueError(
        f"Cannot infer dataset from filename {filename!r}; "
        f"known datasets: {sorted(_DATASET_PATTERNS)}"
    )


def validate_rows(dataset: str, rows: list[dict]) -> ValidationReport:
    """Validate ``rows`` against the ``dataset`` contract.

    Raises:
        ValueError: if ``dataset`` is not one of the five known datasets.
    """
    try:
        model = DATASET_MODELS[dataset]
    except KeyError:
        raise ValueError(
            f"Unknown dataset {dataset!r}; known datasets: {sorted(DATASET_MODELS)}"
        ) from None

    report = ValidationReport()
    for index, row in enumerate(rows):
        try:
            report.passed.append(model.model_validate(row).model_dump())
        except ValidationError as exc:
            for err in exc.errors():
                loc = err.get("loc", ())
                field_name = ".".join(str(part) for part in loc) if loc else "__model__"
                if field_name in row:
                    bad_value = row[field_name]
                elif loc and loc[0] in row:
                    bad_value = row[loc[0]]
                else:
                    bad_value = dict(row)
                report.violations.append(
                    {
                        "row_index": index,
                        "field": field_name,
                        "value": bad_value,
                        "rule": f"{err.get('type', '')}: {err.get('msg', '')}",
                    }
                )
        except (TypeError, ValueError) as exc:
            # P0-03: the actual fail-open trigger, and a nastier one than a
            # plain bad value.
            #
            # pydantic raises a bare TypeError -- NOT ValidationError -- when it
            # tries to coerce a float NaN into an int field:
            #
            #     TypeError: 'float' object cannot be interpreted as an integer
            #
            # That happens on the real shipped path, because
            # clean_dataframe() coerces an unparseable cell to NaN with
            # pd.to_numeric(errors="coerce") and then hands the frame on. The
            # caller only caught ValidationError, so this TypeError escaped
            # validate_rows entirely, unwound past apply_contract_gate, and was
            # swallowed by its `except Exception: return df` -- which returned
            # the row as if it had been validated. That is how a malformed
            # record reached KPI arithmetic.
            #
            # Catching it here converts the crash into the violation record the
            # contract promises, so the row is quarantined like any other bad
            # datum. Fail-closed at the pipeline remains as a second line of
            # defence for failures that are genuinely not row-specific, but
            # this one is a data problem and belongs here.
            report.violations.append(
                {
                    "row_index": index,
                    "field": "__coercion__",
                    "value": _safe_repr(row),
                    "rule": f"type_error: {type(exc).__name__}: {exc}",
                }
            )
    return report


def _safe_repr(row: dict) -> dict:
    """Render a row for the quarantine DLQ without letting the repr raise.

    The value being recorded is by definition malformed, so building a string
    out of it is exactly the operation that already failed once. pandas NaT and
    numpy scalars both survive ``repr`` but not every object's ``__str__``, and
    a second exception here would escape a handler whose whole job is to
    contain bad data.
    """
    out = {}
    for key, value in row.items():
        try:
            out[key] = repr(value)
        except Exception:
            out[key] = f"<unrepresentable {type(value).__name__}>"
    return out


def validate_csv(path: str, dataset: str | None = None) -> ValidationReport:
    """Validate a CSV file with the stdlib ``csv`` reader.

    The dataset is inferred from the filename (same patterns as
    ``app/etl/pipeline.py::discover_files``) unless ``dataset`` is given.

    Raises:
        ValueError: if the file does not exist or the dataset is unknown.
    """
    if not os.path.exists(path):
        raise ValueError(f"File not found: {path!r}")
    resolved = dataset if dataset is not None else infer_dataset(path)
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    return validate_rows(resolved, rows)
