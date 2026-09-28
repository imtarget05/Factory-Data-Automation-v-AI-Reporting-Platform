"""Text-to-SQL tool over the cleaned KPI frames (read-only by construction).

Why this exists
---------------
The AI reporting path answers questions from KPI summaries, but it cannot run
ad-hoc analysis ("which line had the worst reject rate last week?") without a
developer writing a new groupby. This tool closes that gap with the smallest
possible surface: the LLM writes pandas-query expressions against a fixed set
of named KPI frames, and the tool executes them.

Security: there is no SQL engine here at all, which is the entire point.

* The "queries" are not free text sent to a database. They are JSON specs with
  a fixed schema: which named frame, which metric column, which group-by
  columns, which aggregation (``sum`` / ``mean`` / ``max`` / ``min`` /
  ``count``), how many top rows, and optional ``filters``.
* Every identifier is validated against an allow-list derived from the actual
  frame columns. An unknown frame, column, operator, or aggregation is a
  ``ValueError`` before anything executes — no string concatenation into an
  eval, no ``query()`` with user text, no shell.
* The frames are the in-memory cleaned DataFrames, not a database connection:
  nothing here can write, delete, or reach the network. The worst case for a
  hostile input is a rejected spec.

The LLM never sees raw data either — only results (already aggregated, capped
at ``MAX_ROWS`` rows).
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import pandas as pd

# Upper bound on result rows shown to the caller/LLM. Aggregated KPI rows are
# small, but a group-by over machine_utilization could still be chatty.
MAX_ROWS = 20

_AGGREGATIONS = ("sum", "mean", "max", "min", "count")
_OPERATORS = ("==", "!=", ">", ">=", "<", "<=", "in", "not in")

# (frame, metric) pairs the sample questions below are built from. Kept in one
# place so the prompt, the tests, and the docs cannot drift apart.
SAMPLE_QUESTIONS: List[Dict[str, Any]] = [
    {
        "question": "Sản lượng hôm nay so với kế hoạch thế nào?",
        "spec": {
            "frame": "daily_production",
            "metric": "Achievement_Rate_pct",
            "group_by": ["Date"],
            "agg": "mean",
            "top_n": 3,
        },
    },
    {
        "question": "Sản phẩm nào có tỷ lệ lỗi (reject rate) cao nhất?",
        "spec": {
            "frame": "daily_production",
            "metric": "Reject_Rate_pct",
            "group_by": ["Date"],
            "agg": "mean",
            "top_n": 5,
        },
    },
    {
        "question": "Máy nào downtime nhiều nhất?",
        "spec": {
            "frame": "machine_utilization",
            "metric": "Total_Downtime",
            "group_by": ["Machine_ID"],
            "agg": "sum",
            "top_n": 5,
        },
    },
    {
        "question": "Loại lỗi nào chiếm nhiều nhất?",
        "spec": {
            "frame": "defect_by_type",
            "metric": "Total_Defects",
            "group_by": ["Defect_Type"],
            "agg": "sum",
            "top_n": 5,
        },
    },
    {
        "question": "Tồn kho hiện tại và giá trị tồn kho?",
        "spec": {
            "frame": "inventory_kpi",
            "metric": "Total_Stock",
            "group_by": ["Date"],
            "agg": "mean",
            "top_n": 3,
        },
    },
]


# Statements that can never appear in a read-only spec. The allow-list below
# already rejects them as "unknown frame/metric", but this explicit guard
# (FDA-021) makes SELECT-only intent auditable and returns a clear 422
# message ("forbidden statement") instead of an incidental lookup miss.
_FORBIDDEN_STATEMENT_KEYWORDS = (
    "select",
    "delete",
    "drop",
    "insert",
    "update",
    "alter",
    "truncate",
    "grant",
    "exec",
    "union",
)


def _reject_forbidden_statements(value: Any, where: str) -> None:
    if not isinstance(value, str):
        return
    lowered = value.strip().lower()
    tokens = lowered.replace("(", " ").replace(";", " ").split()
    if tokens and tokens[0] in _FORBIDDEN_STATEMENT_KEYWORDS:
        # Keep the allow-list phrasing ("unknown frame/metric ...") so callers
        # matching on it keep working; append the explicit forbidden reason.
        raise ValueError(f"unknown {where} {value[:60]!r}; forbidden statement")


def _resolve_frames(kpis: Dict[str, Any]) -> Dict[str, pd.DataFrame]:
    """Flatten the kpi_engine output into the named frames this tool queries."""
    frames: Dict[str, pd.DataFrame] = {}
    for name, value in (kpis or {}).items():
        if isinstance(value, pd.DataFrame) and not value.empty:
            frames[name] = value
    defect = (kpis or {}).get("defect_analysis") or {}
    if isinstance(defect, dict):
        for sub in ("by_type", "by_severity", "daily"):
            frame = defect.get(sub)
            if isinstance(frame, pd.DataFrame) and not frame.empty:
                frames[f"defect_{sub}"] = frame
    return frames


def validate_spec(spec: Dict[str, Any], frames: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
    """Check a query spec and return its normalized form. Raises ValueError."""
    if not isinstance(spec, dict):
        raise ValueError("spec must be an object")
    frame_name = spec.get("frame")
    _reject_forbidden_statements(frame_name, "frame")
    if frame_name not in frames:
        raise ValueError(f"unknown frame {frame_name!r}; available: {sorted(frames)}")
    frame = frames[frame_name]
    columns = set(frame.columns)

    metric = spec.get("metric")
    _reject_forbidden_statements(metric, "metric")
    if metric not in columns:
        raise ValueError(f"unknown metric {metric!r} for frame {frame_name!r}")
    column = frame[metric]
    if not pd.api.types.is_numeric_dtype(column) and spec.get("agg", "sum") != "count":
        raise ValueError(f"metric {metric!r} is not numeric; only agg='count' applies")

    group_by = list(spec.get("group_by") or [])
    for col in group_by:
        if col not in columns:
            raise ValueError(f"unknown group_by column {col!r} for frame {frame_name!r}")

    agg = spec.get("agg", "sum")
    if agg not in _AGGREGATIONS:
        raise ValueError(f"unknown aggregation {agg!r}; allowed: {list(_AGGREGATIONS)}")

    try:
        top_n = int(spec.get("top_n", MAX_ROWS))
    except (TypeError, ValueError):
        raise ValueError(f"top_n must be an integer, got {spec.get('top_n')!r}") from None
    top_n = max(1, min(top_n, MAX_ROWS))

    filters = []
    for f in spec.get("filters") or []:
        if not isinstance(f, dict):
            raise ValueError(f"filter must be an object, got {f!r}")
        col, op, val = f.get("column"), f.get("op"), f.get("value")
        if col not in columns:
            raise ValueError(f"unknown filter column {col!r}")
        if op not in _OPERATORS:
            raise ValueError(f"unknown operator {op!r}; allowed: {list(_OPERATORS)}")
        if op in ("in", "not in") and not isinstance(val, list):
            raise ValueError(f"operator {op!r} needs a list value")
        filters.append({"column": col, "op": op, "value": val})

    return {
        "frame": frame_name,
        "metric": metric,
        "group_by": group_by,
        "agg": agg,
        "top_n": top_n,
        "filters": filters,
    }


def execute_spec(spec: Dict[str, Any], frames: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
    """Run a validated spec against the frames. Raises ValueError on bad specs."""
    norm = validate_spec(spec, frames)
    frame = frames[norm["frame"]].copy()

    # Filters are applied with vectorized comparisons — never str.eval/query.
    for f in norm["filters"]:
        col = frame[f["column"]]
        op, val = f["op"], f["value"]
        if op == "==":
            mask = col == val
        elif op == "!=":
            mask = col != val
        elif op == ">":
            mask = col > val
        elif op == ">=":
            mask = col >= val
        elif op == "<":
            mask = col < val
        elif op == "<=":
            mask = col <= val
        elif op == "in":
            mask = col.isin(val)
        else:  # "not in"
            mask = ~col.isin(val)
        frame = frame[mask]

    if frame.empty:
        return []

    metric, agg = norm["metric"], norm["agg"]
    if not norm["group_by"]:
        value = getattr(frame[metric], agg)() if agg != "count" else len(frame)
        return [{metric: value}]
    grouped = frame.groupby(norm["group_by"], dropna=False)[metric]
    result = getattr(grouped, agg)() if agg != "count" else grouped.size()
    result = result.sort_values(ascending=False).head(norm["top_n"]).reset_index()
    result.columns = [*norm["group_by"], f"{agg}_{metric}"]
    return result.to_dict("records")


def answer_with_llm(
    question: str,
    kpis: Dict[str, Any],
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: int = 60,
) -> Dict[str, Any]:
    """Ask the LAN LLM to write a spec for ``question``, execute it, summarize.

    Two-stage, matching the Helpdesk agent's propose-then-check split:

    1. The LLM proposes a JSON spec (constrained by the schema in the prompt).
    2. ``execute_spec`` validates + runs it; a second short call turns the
       aggregated rows into a one-paragraph Vietnamese answer.

    A bad spec is a *failed answer*, not an exception: the caller gets
    ``{"answer": ..., "error": ...}`` with the validation message so the UI can
    show what went wrong instead of a traceback.
    """
    import httpx

    from app.utils.config import LOCAL_LLM_MODEL, LOCAL_LLM_URL

    frames = _resolve_frames(kpis)
    if not frames:
        return {"answer": "", "rows": [], "error": "no KPI frames available"}
    model = model or LOCAL_LLM_MODEL
    base_url = (base_url or LOCAL_LLM_URL).rstrip("/")

    schema_hint = (
        '{"frame": "<one of ' + ", ".join(sorted(frames)) + '>", '
        '"metric": "<numeric column>", "group_by": ["<column>", ...], '
        '"agg": "sum|mean|max|min|count", "top_n": <=20, '
        '"filters": [{"column": "<col>", "op": "==|!=|>|>=|<|<=|in|not in", "value": ...}]}'
    )
    # Ground the proposer with the real column names: without them the model
    # guesses plausible-but-wrong metrics (e.g. Defect_Count on defect_daily)
    # and every answer ends in spec_rejected. Truncated per frame to keep the
    # prompt small.
    column_hint = "; ".join(
        f"{name}: {', '.join(str(c) for c in frame.columns[:14])}"
        for name, frame in sorted(frames.items())
    )
    prompt = (
        "Cho câu hỏi sau về dữ liệu nhà máy, chỉ trả về JSON spec đúng schema, "
        "không giải thích. CHỈ dùng đúng tên frame/metric/column có trong danh sách:\n"
        f"Câu hỏi: {question}\nSchema: {schema_hint}\n"
        f"Columns: {column_hint}\n"
        f"Ví dụ: {json.dumps(SAMPLE_QUESTIONS[2]['spec'], ensure_ascii=False)}"
    )
    try:
        r = httpx.post(
            f"{base_url}/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "max_tokens": 256,
            },
            timeout=timeout,
        )
        r.raise_for_status()
        text = (r.json().get("choices") or [{}])[0].get("message", {}).get("content", "")
    except Exception as exc:
        return {"answer": "", "rows": [], "error": f"llm_unreachable: {type(exc).__name__}"}

    start, end = text.find("{"), text.rfind("}") + 1
    try:
        spec = json.loads(text[start:end]) if start >= 0 and end > start else None
    except (json.JSONDecodeError, ValueError):
        spec = None
    if not isinstance(spec, dict):
        return {"answer": "", "rows": [], "error": f"llm_bad_spec: {text[:120]!r}"}

    try:
        rows = execute_spec(spec, frames)
    except ValueError as exc:
        return {"answer": "", "rows": [], "spec": spec, "error": f"spec_rejected: {exc}"}
    if not rows:
        return {"answer": "Không có dữ liệu phù hợp.", "rows": [], "spec": spec, "error": ""}

    summary_prompt = (
        f"Câu hỏi: {question}\nKết quả phân tích (đã tổng hợp): "
        f"{json.dumps(rows, ensure_ascii=False, default=str)}\n"
        "Trả lời ngắn gọn bằng tiếng Việt trong 1-2 câu, nêu con số cụ thể."
    )
    try:
        r = httpx.post(
            f"{base_url}/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": summary_prompt}],
                "temperature": 0.2,
                "max_tokens": 256,
            },
            timeout=timeout,
        )
        r.raise_for_status()
        answer = (r.json().get("choices") or [{}])[0].get("message", {}).get("content", "")
    except Exception:
        answer = json.dumps(rows, ensure_ascii=False, default=str)
    return {"answer": (answer or "").strip(), "rows": rows, "spec": spec, "error": ""}


def run_sample_questions(kpis: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Execute the 5 documented sample questions without any LLM call.

    Deterministic smoke test for CI/offline runs: proves each sample spec in
    SAMPLE_QUESTIONS actually runs against real KPI frames.
    """
    frames = _resolve_frames(kpis)
    out = []
    for item in SAMPLE_QUESTIONS:
        try:
            rows = execute_spec(item["spec"], frames)
            out.append({"question": item["question"], "rows": rows, "error": ""})
        except ValueError as exc:
            out.append({"question": item["question"], "rows": [], "error": str(exc)})
    return out
