# Hướng dẫn Sử dụng cho Người dùng Nghiệp vụ

**Hệ thống:** Smart Manufacturing Platform — Tự động hóa dữ liệu & Báo cáo AI
**Đối tượng:** Quản đốc, QC, Kho, Bảo trì, Ban giám đốc
**Phiên bản:** 1.0

---

## Mục lục
1. [Hệ thống làm gì?](#1-hệ-thống-làm-gì)
2. [Cách mở Dashboard](#2-cách-mở-dashboard)
3. [Đọc biểu đồ](#3-đọc-biểu-đồ)
4. [Sử dụng AI Chat](#4-sử dụng-ai-chat)
5. [Xuất báo cáo](#5-xuất-báo-cáo)
6. [Cảnh báo tự động](#6-cảnh-báo-tự-động)
7. [Câu hỏi thường gặp](#7-câu-hỏi-thường-gặp)

---

## 1. Hệ thống làm gì?

Trước đây, mỗi sáng bạn phải:
- Mở 5 file Excel khác nhau
- Copy-paste dữ liệu vào pivot table
- Tính tay Achievement Rate, Reject Rate, OEE
- Viết báo cáo Word rồi gửi email

**Bây giờ:**
- Hệ thống tự động đọc file Excel → tính toán → hiển thị trên Dashboard
- AI tự viết báo cáo tóm tắt (Summary + Vấn đề + Đề xuất)
- Cảnh báo tự động khi có bất thường
- Bạn chỉ cần mở trình duyệt và xem

| Trước | Sau |
|-------|-----|
| 2-3 giờ/ngày làm báo cáo | 5 phút mở Dashboard |
| Dễ sai khi tính tay | Máy tính chính xác 100% |
| Chỉ biết khi sự việc xảy ra | Cảnh báo real-time |

---

## 2. Cách mở Dashboard

### Bước 1: Mở trình duyệt
- Chrome, Firefox, Safari, hoặc Edge đều được
- Nhập địa chỉ: `http://localhost:8501`

### Bước 2: Đăng nhập (nếu có)
- Nhập tên đăng nhập và mật khẩu được cấp

### Bước 3: Chọn trang
Dashboard có 9 trang, mỗi trang cho 1 mục đích:

| Trang | icon | Dùng khi |
|-------|------|---------|
| **Tổng quan** | 📊 | Muốn xem nhanh tình hình hôm nay |
| **Sản xuất** | 🏭 | Muốn xem sản lượng theo ca, theo sản phẩm |
| **Chất lượng** | ✅ | Muốn xem tỷ lệ lỗi, loại lỗi phổ biến |
| **Kho** | 📦 | Muốn xem tồn kho, sản phẩm sắp hết |
| **Máy** | 🔧 | Muốn xem trạng thái máy, nhiệt độ, rung động |
| **AI Report** | 🤖 | Muốn đọc báo cáo AI tóm tắt |
| **AI Chat** | 💬 | Muốn hỏi đáp tự nhiên |
| **Xuất file** | 📥 | Muốn tải Excel hoặc PDF |
| **Dữ liệu** | 🗄️ | Muốn xem dữ liệu thô |

---

## 3. Đọc biểu đồ

### Trang Tổng quan
- **Sản lượng hôm nay**: Số lớn màu xanh = đạt target
- **Tỷ lệ Achievement**: >90% = xanh, 80-90% = vàng, <80% = đỏ
- **OEE**: >85% = tốt, 70-85% = cần cải thiện, <70% = cảnh báo

### Trang Sản xuất
- **Biểu đồ cột**: So sánh sản lượng giữa các Line (A, B, C, D)
- **Biểu đồ đường**: Xu hướng sản lượng 14 ngày
- **Bộ lọc**: Chọn Line hoặc Ca để lọc dữ liệu

### Trang Chất lượng
- **Pareto Chart**: Loại lỗi nào chiếm nhiều nhất (đọc từ trái sang phải)
- **Biểu đồ tròn**: Phân bổ Minor/Major/Critical
- **Heatmap**: Sản phẩm nào hay lỗi loại nào

### Trang Kho
- **Biểu đồ đường**: Xu hướng tồn kho 30 ngày
- **Dải màu**: Vùng xanh = an toàn, vùng đỏ = dưới reorder point
- **ABC Analysis**: A = giá trị cao, C = giá trị thấp

### Trang Máy
- **Status Cards**: 🟢 Running, 🟡 Idle, 🟠 Maintenance, 🔴 Failure
- **Temperature**: >85°C = cảnh báo màu đỏ
- **Vibration**: >8mm = cảnh báo màu đỏ

---

## 4. Sử dụng AI Chat

### Cách hỏi
1. Click trang **💬 AI Chat**
2. Gõ câu hỏi vào ô text
3. Click **Gửi** hoặc nhấn Enter
4. Đọc câu trả lời

### Ví dụ câu hỏi
| Câu hỏi | AI trả lời |
|---------|-----------|
| "Hôm nay tỷ lệ lỗi bao nhiêu?" | "Tỷ lệ lỗi hôm nay là 4.2%, dưới ngưỡng cảnh báo 5%..." |
| "Máy nào đang hỏng?" | "Hiện tại máy CNC-03 đang ở trạng thái Failure..." |
| "Tuần này OEE trung bình bao nhiêu?" | "OEE trung bình tuần này là 82.3%, thấp hơn target 85%..." |
| "Sản phẩm nào tồn kho thấp nhất?" | "Sản phẩm Sport Shoe đang ở 150 units, dưới reorder point 200..." |

### Lưu ý
- AI dựa trên dữ liệu thực trong hệ thống
- Nếu dữ liệu chưa cập nhật, AI sẽ nói "Không tìm thấy dữ liệu"
- Kết quả chỉ mang tính tham khảo, cần xác nhận lại với dữ liệu thô

---

## 5. Xuất báo cáo

### Xuất Excel
1. Click trang **📥 Export**
2. Click nút **"Export Excel"**
3. File sẽ tự động tải về
4. Mở file bằng Excel hoặc Google Sheets

### Xuất PDF
1. Click trang **📥 Export**
2. Click nút **"Export PDF"**
3. File PDF sẽ tải về
4. In ra hoặc gửi email cho cấp trên

### Xuất cả hai
- Click **"Export All"** để tải cả Excel và PDF cùng lúc

---

## 6. Cảnh báo tự động

Hệ thống tự động kiểm tra và cảnh báo khi:

| Loại cảnh báo | Điều kiện | Mức độ |
|-------------|-----------|--------|
| Tỷ lệ lỗi cao | Reject Rate > 5% | ⚠️ WARNING |
| Tỷ lệ lỗi rất cao | Reject Rate > 7.5% | 🔴 CRITICAL |
| Tồn kho thấp | Stock < 200 units | ⚠️ WARNING |
| Tồn kho rất thấp | Stock < 100 units | 🔴 CRITICAL |
| Máy dừng | Downtime > 30 phút | ⚠️ WARNING |
| Máy hỏng | Status = Failure | 🔴 CRITICAL |
| Nhiệt độ cao | Temperature > 90°C | ⚠️ WARNING |
| Rung động lớn | Vibration > 8mm | ⚠️ WARNING |
| OEE thấp | OEE < 85% | ⚠️ WARNING |

### Xem cảnh báo
- Trang **Tổng quan**: Hiển thị danh sách cảnh báoactive
- Trang **Máy**: Status cards màu sắc cho từng máy
- API: `GET /api/v1/alerts` (dành cho IT)

---

## 7. Câu hỏi thường gặp

### Dashboard không加载 data?
- Kiểm tra đã click **"Load / Refresh Data"** chưa
- Nếu chưa có data, click **"Generate Sample Data"** trước

### AI Chat trả lời sai?
- AI dựa trên dữ liệu hiện có trong hệ thống
- Nếu data chưa cập nhật, kết quả có thể chưa chính xác
- Kiểm tra lại dữ liệu thô tại trang **🗄️ Data**

### Muốn thêm dữ liệu thực?
- Đặt file CSV hoặc Excel vào thư mục `data/raw/`
- Tên file phải chứa: `production`, `quality`, `inventory`, `machine`, hoặc `workers`
- Click **"Load / Refresh Data"** để hệ thống tự động nhận diện

### Muốn xem dữ liệu历史?
- Dữ liệu được lưu tự động mỗi ngày trong `data/processed/`
- Mỗi file có timestamp để phân biệt

### Liên hệ hỗ trợ
- IT Helpdesk: [số điện thoại]
- Email: [email]

---

## Đánh giá Hiệu quả

| Chỉ số | Trước (Thủ công) | Sau (AI) | Tiết kiệm |
|--------|-----------------|----------|-----------|
| Thời gian làm báo cáo/ngày | 2-3 giờ | 5 phút | **95%** |
| Số file Excel phải mở | 5 file | 0 file | **100%** |
| Tỷ lệ sai số tính toán | ~5% | 0% | **100%** |
| Thời gian phát hiện bất thường | 4-8 giờ | Real-time | **~100%** |
| Số câu hỏi cần hỏi IT mỗi tuần | 10-15 câu | 0 (hỏi AI) | **~100%** |

---

*Tài liệu này được viết cho người dùng không chuyên về kỹ thuật. Nếu có thắc mắc, liên hệ phòng IT.*
