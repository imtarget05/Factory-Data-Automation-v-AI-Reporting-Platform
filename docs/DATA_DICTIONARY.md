# Factory KPI Data Dictionary

> Mọi con số trong dashboard, Excel/PDF và câu trả lời AI đều tính từ 5 file
> `data/raw/*.csv` qua `app/etl/pipeline.py` → `app/etl/kpi_engine.py`.
> File này giải thích **cách đếm** từng cột, kèm công thức và ví dụ đã kiểm chứng
> trên dữ liệu thật (90 ngày, 11,055 dòng production sau quarantine).
> Nguồn duy nhất của sự thật là code — mỗi mục ghi rõ hàm tính.

Quy ước chung:

- `_pct` = phần trăm (đã nhân 100, làm tròn 2 chữ số).
- Tổng theo ngày (`daily_*`) là đơn vị cơ sở; weekly/monthly chỉ là gom nhóm lại.
- Các dòng vi phạm contract (số âm, ngày tương lai, reject > actual) đã bị
  **quarantine trước khi tính** (`app/etl/quarantine.py`), nên KPI không bao giờ
  chứa dữ liệu hỏng.

---

## 1. daily_production — sản lượng theo ngày (90 dòng × 10 cột)

Hàm: `calculate_daily_production` (`app/etl/kpi_engine.py:13`).

| Cột | Công thức | Ý nghĩa |
|---|---|---|
| `Date` | ngày ghi nhận | khóa chính của bảng |
| `Total_Target` | Σ `Target_Qty` trong ngày | kế hoạch |
| `Total_Actual` | Σ `Actual_Qty` trong ngày | thực tế |
| `Total_Good` | Σ `Good_Qty` | hàng đạt |
| `Total_Reject` | Σ `Reject_Qty` | hàng lỗi |
| `Avg_Cycle_Time` | mean `Cycle_Time_sec` | nhịp máy TB (giây) |
| `Total_Records` | số dòng trong ngày | độ phủ dữ liệu |
| `Achievement_Rate_pct` | `Total_Actual / Total_Target × 100` | % hoàn thành kế hoạch |
| `Reject_Rate_pct` | `Total_Reject / Total_Actual × 100` | % lỗi — **alert khi > 5%** |
| `Yield_pct` | `Total_Good / Total_Actual × 100` | % đạt ngay lần đầu |

Ví dụ thật (ngày cuối trong dữ liệu): Target 74,728 → Actual 70,901 →
Achievement **94.9%**, Reject **4.6%**, Yield **95.4%**.

## 2. weekly_production / monthly_production — gom nhóm

Hàm: `calculate_weekly_production`, `calculate_monthly_production`.
Cùng 9 cột như daily nhưng gom theo ISO week (`Year`, `Week`) hoặc tháng
(`Year`, `Month`). Dữ liệu demo: 14 tuần, 3 tháng.

## 3. oee — hiệu suất thiết bị tổng thể (90 dòng × 7 cột)

Hàm: `calculate_oee` (`app/etl/kpi_engine.py:107`).
Công thức chuẩn: **OEE = Availability × Performance × Quality**.

| Cột | Công thức | Ghi chú |
|---|---|---|
| `Total_Time` | `count(Downtime_min)` trong ngày | mỗi bản ghi máy ≈ 10 phút planned time |
| `Downtime_Total` | Σ `Downtime_min` | phút dừng máy |
| `Availability_pct` | `(Total_Time×10 − Downtime_Total) / (Total_Time×10) × 100` | sẵn sàng — **hằng số 10 là giả định demo**, không phải đo thật |
| `Performance_pct` | `Total_Actual / Total_Target × 100` | tốc độ so với kế hoạch |
| `Quality_pct` | `Total_Good / Total_Actual × 100` | = Yield ngày đó |
| `OEE_pct` | `A/100 × P/100 × Q/100 × 100` | tích 3 thành phần |

Ví dụ thật (ngày cuối): A 84.0% × P 94.9% × Q 95.4% → OEE **76.0%**
(target cấu hình `OEE_TARGET = 0.85` — nhà máy demo chưa đạt).

> ⚠️ Trung thực kỹ thuật: `Total_Time×10` giả định mỗi dòng machine.csv tương
> đương 10 phút planned production time. Với dữ liệu giả lập điều này ổn;
> với dữ liệu thật phải thay bằng ca làm việc thực tế từ MES.

## 4. machine_utilization — trạng thái máy theo ngày (1,715 dòng × 12 cột)

Hàm: `calculate_machine_utilization` (`app/etl/kpi_engine.py:171`).
Gom theo (`Date`, `Machine_ID`) — 20 máy × 90 ngày ≈ 1,800 ô, trừ ngày nghỉ.

| Cột | Công thức |
|---|---|
| `Running_Count` / `Idle_Count` / `Maint_Count` | đếm `Status` tương ứng |
| `Failure_Count` | đếm `Status == 'Failure'` — **alert khi > 0** |
| `Total_Downtime` | Σ `Downtime_min` — **alert khi > 30 phút** |
| `Avg_Temperature` / `Avg_Vibration` / `Avg_Power` | mean cảm biến |
| `Total_Readings` | số bản ghi trong ô |
| `Utilization_pct` | `Running_Count / Total_Readings × 100` |

## 5. worker_productivity — năng suất công nhân (4,756 dòng × 10 cột)

Hàm: `calculate_worker_productivity` (`app/etl/kpi_engine.py:204`).
Mỗi dòng là 1 công nhân 1 ngày (200 workers × ~24 ngày công).

| Cột | Công thức |
|---|---|
| `Hours_Worked`, `Units_Produced`, `Defects_Caused`, `Overtime_hrs` | giá trị gốc |
| `Units_per_Hour` | `Units_Produced / Hours_Worked` |
| `Defect_Rate_pct` | `Defects_Caused / Units_Produced × 100` |

## 6. inventory_kpi — tồn kho theo ngày (90 dòng × 8 cột)

Hàm: `calculate_inventory_kpi` (`app/etl/kpi_engine.py:233`).

| Cột | Công thức |
|---|---|
| `Total_Stock` | Σ `Stock_Qty` cuối ngày |
| `Total_Incoming` / `Total_Outgoing` | Σ nhập/xuất — **alert khi `Min_Stock < 200`** |
| `Avg_Stock` / `Min_Stock` | mean/min `Stock_Qty` |
| `Products_Below_Reorder` | đếm SP có `Stock_Qty < Reorder_Point` |
| `Stock_Value` | Σ `Stock_Qty × Unit_Price` (USD) |

Ví dụ thật (ngày cuối): tồn **4,411 đơn vị**, giá trị **$524,669.83**.

## 7. defect_analysis — phân tích lỗi (dict 3 bảng)

Hàm: `calculate_defect_analysis` (`app/etl/kpi_engine.py:268`).

| Bảng | Khóa | Cột chính |
|---|---|---|
| `by_type` (11 dòng) | `Defect_Type` | `Total_Defects`, `Total_Inspected`, `Occurrences`, `Defect_Rate_pct = Total_Defects / Total_Inspected × 100` |
| `by_severity` (8 dòng) | `Severity` | cùng cấu trúc |
| `daily` | `Date` | diễn biến lỗi theo ngày |

`by_type` sắp xếp giảm dần theo `Total_Defects` — dòng đầu là Pareto head
(dùng cho câu "loại lỗi nào chiếm nhiều nhất?").

## 8. Tổng số metric column đếm thế nào

`calculate_all_kpis` trả về **8 nhóm KPI** (không phải 84 nhóm):

| Nhóm | Số cột metric |
|---|---|
| `daily_production` | 10 |
| `weekly_production` | 9 |
| `monthly_production` | 9 |
| `oee` | 7 |
| `machine_utilization` | 12 |
| `worker_productivity` | 10 |
| `inventory_kpi` | 8 |
| `defect_analysis` | 3 + các bảng con theo `Defect_Type`/`Severity` |

Đo trên fixture chuẩn (seed 42, 90 ngày): **65–68 cột** tổng cộng. Con số
thay đổi theo dữ liệu vì `defect_analysis` mở rộng theo số giá trị distinct
của `Defect_Type`/`Severity`.

Tài liệu trước đây ghi "84+" là một ước lượng không chốt được số cố định.
Đã sửa thành số đo được. Xem `docs/RECRUITER-EVIDENCE.md` mục "Claims I could
NOT verify" — con số 84+ nằm trong danh sách đó.
