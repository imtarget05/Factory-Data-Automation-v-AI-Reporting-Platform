# Stakeholder Interview — Phỏng vấn 5 Phòng ban

**Dự án:** Smart Manufacturing Platform — AI-Powered Factory Data Automation
**Mục đích:** Thu thập nhu cầu từ 5 phòng ban để thiết kế use case AI phù hợp
**Ngày:** 2026-07-16
**Người phỏng vấn:** Mai Nguyen Binh Tan (AI Intern)

---

## Tổng quan

| # | Phòng ban | Số user stories | Mức độ ưu tiên |
|---|----------|----------------|---------------|
| 1 | Sản xuất (Production) | 3 | Cao |
| 2 | Kiểm soát chất lượng (Quality Control) | 3 | Cao |
| 3 | Kho & Vật tư (Inventory) | 3 | Trung bình |
| 4 | Bảo trì máy (Maintenance) | 3 | Cao |
| 5 | Quản lý nhân sự (HR / Management) | 3 | Trung bình |

---

## 1. Phòng Sản xuất (Production)

**Đối tượng phỏng vấn:** Quản đốc ca sản (Shift Supervisor)

### Vấn đề hiện tại
- Mỗi sáng phải mở 5 file Excel khác nhau để xem sản lượng, tỷ lệ lỗi, OEE
- Phải tự tính Achievement Rate thủ công → dễ sai
- Không biết máy nào đang dừng直到 quản đốc khác báo

### User Stories

| ID | User Story | Acceptance Criteria |
|----|-----------|-------------------|
| US-P1 | **Nhìn tổng quan sản xuất** — Tôi muốn mở 1 trang dashboard thấy ngay sản lượng hôm nay, tỷ lệ đạt, tỷ lệ lỗi, OEE | Dashboard hiển thị real-time, tự cập nhật khi có data mới |
| US-P2 | **So sánh ca sản** — Tôi muốn so sánh performance giữa ca sáng và ca tối | Biểu đồ line chart so sánh 2 ca theo ngày |
| US-P3 | **Nhận cảnh báo tự động** — Tôi muốn nhận alert khi tỷ lệ lỗi >5% hoặc OEE <85% | Alert hiện trên dashboard + log vào hệ thống |

### AI Application
- **AI Report**: Tạo báo cáo điều hành mỗi sáng (Summary + Problems + Recommendations)
- **AI Chat**: "Hôm nay ca nào năng suất thấp nhất?" → AI trả lời + phân tích nguyên nhân

---

## 2. Phòng Kiểm soát Chất lượng (Quality Control)

**Đối tượng phỏng vấn:** QC Manager

### Vấn đề hiện tại
- Phải mở từng sheet để xem loại lỗi nào đang phổ biến
- Không có biểu đồ Pareto tự động → phải tạo tay mỗi tuần
- Phân tích nguyên nhân lỗi mất 1-2 giờ/báo cáo

### User Stories

| ID | User Story | Acceptance Criteria |
|----|-----------|-------------------|
| US-Q1 | **Xem phân tích lỗi** — Tôi muốn thấy Pareto chart các loại defect, biết loại nào chiếm nhiều nhất | Pareto chart tự động, hiển thị % cumulative |
| US-Q2 | **Theo dõi severity** — Tôi muốn biết bao nhiêu lỗi Minor/Major/Critical mỗi ngày | Pie chart severity + trend line |
| US-Q3 | **Dự đoán lỗi** — Tôi muốn dự báo ngày mai tỷ lệ lỗi bao nhiêu dựa trên xu hướng | ML prediction với confidence interval |

### AI Application
- **ML Prediction**: Random Forest dự đoán tỷ lệ lỗi (>5% = High Defect)
- **AI Report**: "Root causes" section phân tích nguyên nhân lỗi chính

---

## 3. Phòng Kho & Vật tư (Inventory)

**Đối tượng phỏng vấn:** Warehouse Supervisor

### Vấn đề hiện tại
- Phải kiểm tra tồn kho thủ công mỗi sáng
- Không biết sản phẩm nào sắp hết → bị thiếu hàng
- Không cóABC analysis tự động

### User Stories

| ID | User Story | Acceptance Criteria |
|----|-----------|-------------------|
| US-I1 | **Xem tồn kho real-time** — Tôi muốn thấy stock level mọi sản phẩm, biết cái nào dưới reorder point | Dashboard hiển thị stock + reorder threshold |
| US-I2 | **ABC Analysis** — Tôi muốn phân loại sản phẩm theo giá trị (A/B/C) | ABC classification + pie chart |
| US-I3 | **Cảnh báo tồn kho** — Tôi muốn nhận alert khi stock <200 hoặc dưới reorder point | Alert WARNING/CRITICAL theo ngưỡng |

### AI Application
- **Alert System**: Tự động cảnh báo tồn kho thấp
- **AI Chat**: "Sản phẩm nào sắp hết hàng?" → AI trả lời + gợi ý reorder

---

## 4. Phòng Bảo trì Máy (Maintenance)

**Đối tượng phỏng vấn:** Maintenance Engineer

### Vấn đề hiện tại
- Không biết máy nào đang chạy bất thường (nhiệt độ cao, rung động lớn)
- Phải chạy xuống nhà máy kiểm tra thủ công
- Machine downtime không được theo dõi real-time

### User Stories

| ID | User Story | Acceptance Criteria |
|----|-----------|-------------------|
| US-M1 | **Theo dõi trạng thái máy** — Tôi muốn thấy mỗi máy đang Running/Idle/Maintenance/Failure | Status cards màu sắc + utilization % |
| US-M2 | **Cảnh báo bất thường** — Tôi muốn nhận alert khi temperature >85°C hoặc vibration >8mm | Alert real-time + log severity |
| US-M3 | **Dự đoán downtime** — Tôi muốn dự báo máy nào có ngưỡng downtime cao để bảo trì sớm | ML prediction (XGBoost) + risk score |

### AI Application
- **ML Prediction**: XGBoost dự đoán downtime từ temperature, vibration, power usage
- **Alert System**: Cảnh báo machine failure + high temperature/vibration

---

## 5. Phòng Quản lý Nhân sự (HR / Management)

**Đối tượng phỏng vấn:** HR Manager / Plant Manager

### Vấn đề hiện tại
- Không có báo cáo tổng hợp cho ban giám đốc
- Phải họp 30 phút mỗi sáng để nghe báo cáo từ các phòng
- Không biết năng suất nhân viên so với trung bình

### User Stories

| ID | User Story | Acceptance Criteria |
|----|-----------|-------------------|
| US-H1 | **Báo cáo điều hành** — Tôi muốn 1 PDF báo cáo tóm tắt tình hình sản xuất hàng ngày | PDF với Summary + Key Metrics + Problems + Recommendations |
| US-H2 | **Năng suất nhân viên** — Tôi muốn so sánh hiệu suất từng nhân viên (units/hour, defect rate) | Dashboard worker productivity + ranking |
| US-H3 | **Xu hướng sản xuất** — Tôi muốn xem trend sản xuất 30 ngày để ra quyết định | Line chart 30 ngày + forecast |

### AI Application
- **AI Report**: Tạo báo cáo PDF tự động mỗi sáng (Executive Summary + Problems + Risks)
- **Dashboard**: Worker productivity ranking + 30-day trend

---

## Tổng hợp Ma trận Nhu cầu vs Giải pháp

| Nhu cầu | Phòng ban | Giải pháp AI | Module |
|---------|----------|-------------|--------|
| Dashboard real-time | Sản xuất, QC, Kho, Bảo trì | Streamlit dashboard 9 trang | Dashboard |
| Cảnh báo tự động | Sản xuất, Kho, Bảo trì | Threshold-based alert system | Alert System |
| Báo cáo điều hành | Quản lý | AI-generated PDF report | AI Report |
| Phân tích lỗi | QC | Pareto chart + severity analysis | Quality page |
| Dự đoán lỗi | QC | Random Forest classification | ML Models |
| Dự đoán downtime | Bảo trì | XGBoost classification | ML Models |
| Tồn kho & reorder | Kho | ABC analysis + stock alerts | Inventory page |
| Năng suất nhân viên | Quản lý | Worker productivity metrics | Worker page |
| Hỏi đáp tự nhiên | Tất cả | AI Chat (NL Q&A) | AI Chat |

---

## Kết luận

5 phòng ban, 15 user stories, tất cả đều được hệ thống Smart Manufacturing Platform hỗ trợ:

| Phòng ban | US đã xử lý | Tỷ lệ |
|----------|------------|-------|
| Sản xuất | 3/3 | 100% |
| Chất lượng | 3/3 | 100% |
| Kho | 3/3 | 100% |
| Bảo trì | 3/3 | 100% |
| Quản lý | 3/3 | 100% |
| **Tổng** | **15/15** | **100%** |

Tài liệu này chứng minh dự án được thiết kế dựa trên nhu cầu thực tế của người dùng nghiệp vụ, không chỉ là bài tập kỹ thuật.
