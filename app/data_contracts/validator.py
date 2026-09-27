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
    return report


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
