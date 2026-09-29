"""
Factory medallion pipeline, orchestrated by Airflow.

    ingest -> validate -> quarantine -> silver -> gold -> marts -> quality checks

Vì sao DAG này tồn tại khi pipeline đã chạy được bằng `run_etl()`:

    `run_etl()` là một lời gọi hàm — nó không cho biết bước nào hỏng, không
    retry được từng bước, và không quan sát được. Khi đường ống dài hơn và
    chạy hằng ngày, ba thứ đó trở thành yêu cầu chứ không phải tiện ích.

Quyết định quan trọng, và lý do:

    * **Mỗi tầng là một task riêng.** Gộp thành một task `run_etl` thì khi
      gold hỏng, ta không biết silver có ổn không, và retry sẽ chạy lại từ
      đầu — tốn tài nguyên mà không thu được thông tin mới.

    * **Idempotency là điều kiện bắt buộc, không phải điều khoản.** Airflow
      retry, backfill, và "clear task" đều chạy lại task. Một task không
      idempotent sẽ nhân bản dữ liệu mỗi lần chạy. Gold và marts đã
      idempotent sẵn; DAG này tận dụng điều đó, và test chứng minh chạy hai
      lần cho kết quả giống nhau.

    * **`quarantine` không chặn DAG.** Hàng vi phạm contract bị lo có chủ
      đích — đó là hành vi mong muốn. Nhưng DAG không được *fail* vì nó, vì
      fail nghĩa là mất toàn bộ lô dữ liệu tốt. Ngược lại, số hàng bị lo
      vượt ngưỡng thì phải fail, vì lúc đó vấn đề là ở nguồn.

    * **Task cuối kiểm chứng, không chỉ báo cáo.** `quality_checks` so kết
      quả với tiêu chí và raise nếu vượt ngưỡng. Một DAG "thành công" mà
      dữ liệu sai thì chỉ là một thông báo sai.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from typing import Any

from airflow import DAG
from airflow.operators.python import PythonOperator

# Đường dẫn tới repo Factory, qua biến môi trường để test và deploy khác
# nhau không phải sửa code.
REPO = os.environ.get(
    "FACTORY_REPO", "/Users/mainguyenbinhtan/Downloads/Projects")
APP_DIR = os.path.join(REPO, "Factory-Data-Automation-v-AI-Reporting-Platform")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

#: Ngưỡng chất lượng. Vượt ngưỡng thì task cuối fail, để cảnh báo nổi lên
#: thay vì chỉ nằm trong log.
MAX_QUARANTINE_RATIO = 0.25
MIN_MART_ROWS = 1
MAX_REJECT_RATE = 0.30

DEFAULT_ARGS = {
    "owner": "manufacturing-data",
    "depends_on_past": False,
    # Retry có backoff, không phải lặp ngay. Retry liên tục cách nhau vài giây
    # chỉ tạo ra nhiều lần thất bại hơn chứ không phục hồi được nguồn.
    "retries": 2,
    "retry_delay": timedelta(seconds=30),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=10),
}


def _log(task_id: str, message: str, **extra: Any) -> None:
    """Log có cấu trúc, có task_id để lọc khi debug."""
    print(json.dumps({"task": task_id, "msg": message, **extra}, default=str))


# ---------------------------------------------------------------------------
# Task: ingest
# ---------------------------------------------------------------------------
def task_ingest(**_: Any) -> dict:
    """
    Nạp và làm sạch file thô.

    Chạy `load_and_clean_all`, không phải `run_etl` — ta muốn ingest và silver
    là hai bước riêng để thấy được lỗi ở đâu.
    """
    from app.etl.pipeline import load_and_clean_all

    started = datetime.utcnow()
    datasets = load_and_clean_all()
    summary = {name: int(len(df)) for name, df in datasets.items()}

    if not datasets:
        raise ValueError("khong co dataset nao duoc nap — kiem tra data/raw/")

    _log("ingest", "da nap va lam sach", datasets=summary,
         elapsed_s=round((datetime.utcnow() - started).total_seconds(), 2))
    return {"datasets": summary, "count": len(datasets)}


# ---------------------------------------------------------------------------
# Task: validate + quarantine
# ---------------------------------------------------------------------------
def task_validate_and_quarantine(**_: Any) -> dict:
    """
    Chạy contract gate trên từng dataset, ghi hàng vi phạm vào quarantine.

    Gate fail-open có chủ đích (xem docstring `apply_contract_gate`): lỗi
    validator không được giống lỗi mất dữ liệu. Vì vậy ta kiểm kết quả ở đây
    thay vì tin validator.
    """
    from app.etl.pipeline import apply_contract_gate, load_and_clean_all
    from app.etl.quarantine import quarantine_summary

    datasets = load_and_clean_all()
    before = {n: len(df) for n, df in datasets.items()}
    after = {}
    dropped = 0

    for name, df in datasets.items():
        gated = apply_contract_gate(df, name)
        after[name] = len(gated)
        dropped += before[name] - len(gated)

    total = sum(after.values())
    ratio = (dropped / total) if total else 0.0
    summary = quarantine_summary()

    _log("validate", "contract gate xong", before=before, after=after,
         dropped=dropped, ratio=round(ratio, 4), quarantine=summary)

    if total == 0:
        raise ValueError("sau contract gate khong con duong nao")

    if ratio > MAX_QUARANTINE_RATIO:
        raise ValueError(
            f"{ratio:.1%} dong bi lo (nguong {MAX_QUARANTINE_RATIO:.0%}) — "
            f"van de o nguon, khong phai o dong du lieu")

    return {"dropped": dropped, "kept": total, "ratio": round(ratio, 4),
            "quarantine": summary}


# ---------------------------------------------------------------------------
# Task: silver -> gold -> marts
# ---------------------------------------------------------------------------
def task_silver_to_gold(**_: Any) -> dict:
    """Chạy ETL tới gold. Idempotent: chạy lại cho cùng kết quả."""
    from app.etl.gold import build_gold
    from app.etl.pipeline import load_and_clean_all

    silver = load_and_clean_all()
    gold = build_gold(silver)
    _log("gold", "gold da dung", datasets=sorted(gold))
    return {"gold_datasets": sorted(gold)}


def task_build_marts(**_: Any) -> dict:
    """
    Gold -> mart -> SQLite.

    `write_sqlite` DROP trước CREATE nên chạy lại không nhân bản — đây là
    điều kiện để Airflow clear-and-rerun được an toàn.
    """
    from app.database.marts import build_all_marts, mart_row_counts
    from app.etl.pipeline import load_and_clean_all

    db_path, marts = build_all_marts(load_and_clean_all())
    counts = mart_row_counts(db_path)

    if any(c < MIN_MART_ROWS for c in counts.values()):
        raise ValueError(f"mart rong: {counts}")

    _log("marts", "mart da dung", db=db_path, counts=counts)
    return {"db_path": db_path, "row_counts": counts}


# ---------------------------------------------------------------------------
# Task: quality checks — task cuối, chứng minh chứ không chỉ báo cáo
# ---------------------------------------------------------------------------
def task_quality_checks(**_: Any) -> dict:
    """
    Kiểm chứng kết quả cuối.

    Đây là task có ý nghĩa nhất của DAG. Mọi task trước đó đều có thể "thành
    công" với dữ liệu sai; task này là nơi điều đó bị bắt.

    Ba kiểm, mỗi kiểm bắt một lỗi khác nhau:
        1. mart có dữ liệu            -> pipeline im lặng
        2. tỷ lệ lỗi hợp lý          -> sàn sản xuất gặp sự cố
        3. good + reject <= actual    -> rò rỉ dữ liệu hoặc double count
    """
    from app.database.marts import build_all_marts, mart_row_counts, query
    from app.etl.pipeline import load_and_clean_all

    db_path, _ = build_all_marts(load_and_clean_all())
    counts = mart_row_counts(db_path)
    checks: dict[str, Any] = {}

    # 1. Mọi mart đều có dữ liệu
    checks["marts_non_empty"] = all(c >= MIN_MART_ROWS for c in counts.values())

    # 2. Tỷ lệ lỗi nằm trong khoảng hợp lý. Quá 30% hoặc bằng 0 đều đáng
    #    ngờ: 0 có thể nghĩa là pipeline im lặng.
    if counts.get("mart_oee", 0) > 0:
        rj = query(db_path,
                   "SELECT SUM(total_reject) AS r, SUM(total_actual) AS a "
                   "FROM mart_oee")
        r = int(rj["r"].iloc[0] or 0)
        a = int(rj["a"].iloc[0] or 0)
        rate = (r / a) if a else 0.0
        checks["reject_rate"] = round(rate, 4)
        checks["reject_rate_plausible"] = 0.0 <= rate <= MAX_REJECT_RATE
    else:
        checks["reject_rate"] = None
        checks["reject_rate_plausible"] = False

    # 3. Tổng tốt + tổng lỗi không vượt tổng thực tế. Rò rỉ dữ liệu hoặc
    #    double count sẽ làm vỡ đúng bất biến này.
    cons = query(db_path,
                 "SELECT SUM(total_good) + SUM(total_reject) AS s, "
                 "       SUM(total_actual) AS a FROM mart_oee")
    s = int(cons["s"].iloc[0] or 0)
    a = int(cons["a"].iloc[0] or 0)
    checks["good_plus_reject"] = s
    checks["total_actual"] = a
    checks["good_plus_reject_le_actual"] = s <= a

    failed = [k for k, v in checks.items() if k.endswith(
        ("_non_empty", "_plausible", "_le_actual")) and v is False]
    if failed:
        raise ValueError(f"quality check that: {failed} — chi tiet: {checks}")

    _log("quality", "tat ca chi so dung", **checks)
    return checks


with DAG(
    dag_id="factory_medallion_daily",
    description="RAW -> SILVER -> GOLD -> MART cho nha may",
    schedule="0 2 * * *",          # 02:00 moi ngay
    start_date=datetime(2026, 1, 1),
    catchup=False,                 # khong backfill qua khu — xem note duoi
    default_args=DEFAULT_ARGS,
    tags=["factory", "medallion", "daily"],
) as dag:
    # catchup=False là quyết định có chủ đích: dữ liệu thô trên đĩa chỉ có
    # vài ngày gần nhất, backfill sẽ tạo ra các phiên chạy thất bại vô nghĩa
    # và làm nhiễu cảnh báo. Khi có dữ liệu lịch sử thì bật lại.

    ingest = PythonOperator(task_id="ingest", python_callable=task_ingest)
    validate = PythonOperator(
        task_id="validate_quarantine",
        python_callable=task_validate_and_quarantine)
    gold = PythonOperator(task_id="gold", python_callable=task_silver_to_gold)
    marts = PythonOperator(task_id="marts", python_callable=task_build_marts)
    quality = PythonOperator(
        task_id="quality_checks", python_callable=task_quality_checks)

    # Quan hệ phụ thuộc. Đây là DAG hình chuỗi, và việc gọi nó là DAG không
    # làm nó trở thành đồ thị phức tạp. Khi nào một bước thực sự chạy song
    # song với bước khác, hãy tách nhánh thật — và lúc đó bằng chứng phải
    # chứng minh cả hai nhánh, không chỉ một.
    ingest >> validate >> gold >> marts >> quality
