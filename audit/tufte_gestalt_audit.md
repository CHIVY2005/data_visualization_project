# 📐 BÁO CÁO KIỂM TOÁN TỶ LỆ DATA-INK & BỐ CỤC GESTALT (T0502)

- **Dự án:** ETT Power Grid Operational Management & Thermal Safety Visual Analytics Dashboard
- **Mã định danh:** `ETT_GRID_VIS_2026` | **Phiên bản:** 2.0 | **Work Package:** `WP05` (T0502)
- **Tiêu chuẩn quy chiếu:**
  - Edward R. Tufte (The Visual Display of Quantitative Information) — Data-Ink Maximization, Chartjunk Elimination.
  - Các nguyên luật thị giác Gestalt (Proximity, Similarity, Continuity, Closure, Common Fate, Figure-Ground).
  - AGENTS.md §CODE & VISUALIZATION STANDARDS.
- **Trách nhiệm RACI:** TV chính E (PM & Visual QA Auditor) thực thi (R/A); TV hỗ trợ C (Story 1), D (Story 2).
- **Thời điểm nghiệm thu:** 2026-10-29.
- **Trạng thái:** **PASS** (100% biểu đồ tinh giản, loại bỏ chartjunk, tích hợp Action Titles và bố cục Gestalt).

---

## 1. 📊 NGUYÊN LÝ DATA-INK (EDWARD TUFTE) TRÊN CÁC BIỂU ĐỒ

Tỷ lệ Data-Ink được định nghĩa:
$$\text{Data-Ink Ratio} = \frac{\text{Lượng mực dùng để hiển thị dữ liệu thực chất}}{\text{Tổng lượng mực trên toàn biểu đồ}}$$

### Bảng đánh giá cải tiến Trước (Before) và Sau (After)

| Thành phần thị giác | Thiết kế sơ bộ / Lỗi tiềm tàng (Before) | Cải tiến chuẩn hóa Tufte v2.0 (After) | Đánh giá |
| :--- | :--- | :--- | :---: |
| **Khung hộp viền biểu đồ (Bounding Box)** | Khung viền đen/xám đậm bao quanh biểu đồ gây cản trở tầm nhìn | Xóa bỏ hoàn toàn (`showline=False` trên các trục không trọng yếu, nền `plot_bgcolor="white"`). Biểu đồ hòa nhập liền mạch vào canvas. | **PASS** |
| **Hệ thống lưới (Gridlines)** | Lưới phụ dày đặc, màu xám đậm cạnh tranh với đường dữ liệu | Loại bỏ toàn bộ lưới phụ (minor grid). Lưới chính dùng mã màu Slate-200 tinh tế (`#E2E8F0`), mờ nhạt nhưng đủ định hướng mắt. | **PASS** |
| **Dán nhãn trực tiếp (Direct Labeling)** | Chú giải (legend) đặt xa biểu đồ buộc mắt đảo liên tục | Nhãn ngưỡng nhiệt (`85°C Warning`, `95°C Critical`) dán trực tiếp tại biên phải của đường ngưỡng. Subplot titles gắn trực tiếp trên từng panel. | **PASS** |
| **Tránh Spaghetti Plot** | 6 nhánh tải chồng chéo trên một biểu đồ duy nhất gây rối loạn | Tách thành **Synchronized Small Multiples** (6 panel đồng bộ trục X), giúp phân biệt tải hữu ích và vô công rõ ràng. | **PASS** |
| **Dải bách phân vị Quantile Fan** | Độ mờ (alpha) ngẫu nhiên, dễ bị che khuất vùng trung tâm | Áp dụng thứ tự vẽ từ rộng đến hẹp (*wide-before-narrow*) với alpha tăng dần: 95% (0.14) → 80% (0.20) → 50% IQR (0.28). | **PASS** |
| **Biểu đồ cột thành phần tải** | Cắt bỏ tải âm hoặc ép mẫu số gây sai lệch tỷ trọng | Thể hiện đầy đủ thành phần hữu ích/vô ích 3 cấp áp (HU/MU/LU), không clip tải âm, tính toán chính xác tỷ trọng phản kháng. | **PASS** |
| **Dải màu Lag Correlation** | Dùng màu đỏ cho tương quan âm gây nhầm lẫn với cảnh báo sự cố | Dải phân kỳ trung tính Navy - Slate - Teal với điểm giữa `zmid=0.0`. Tuyệt đối không dùng Crimson cho tương quan âm. | **PASS** |

---

## 2. 🧠 ÁP DỤNG CÁC NGUYÊN LUẬT THỊ GIÁC GESTALT

Các nguyên luật tâm lý học thị giác Gestalt được ứng dụng có hệ thống trong giao diện điều hành:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        GESTALT FRAMEWORK IN ETT UI                     │
├───────────────────┬────────────────────────────────────────────────────┤
│ Nguyên luật       │ Triển khai thực tế trong Dashboard                 │
├───────────────────┼────────────────────────────────────────────────────┤
│ 1. Proximity      │ Các thẻ KPI cùng nhóm (Story 1 / Story 2) đặt sát  │
│    (Độ gần)       │ nhau thành hàng ngang 4–5 cột phía trên biểu đồ.   │
├───────────────────┼────────────────────────────────────────────────────┤
│ 2. Similarity     │ Cùng một đại lượng vật lý dùng cùng kiểu mã hóa:   │
│    (Độ tương đồng)│ OT luôn là Navy, Warning luôn là Amber nét đứt,    │
│                   │ Critical luôn là Crimson nét đứt.                  │
├───────────────────┼────────────────────────────────────────────────────┤
│ 3. Common Fate    │ 6 panel của Small Multiples liên kết trục X: zoom, │
│    (Chung số phận)│ pan hoặc trỏ chuột đồng thời di chuyển trên cả 6.  │
├───────────────────┼────────────────────────────────────────────────────┤
│ 4. Closure        │ Các dải bách phân vị tạo thành các vùng đa giác khép│
│    (Tính khép kín)│ kín (enclosure) bao bọc xu hướng trung vị q50.     │
├───────────────────┼────────────────────────────────────────────────────┤
│ 5. Figure-Ground  │ Dữ liệu sự cố (pop-out breach markers) nổi bật rõ   │
│    (Hình - Nền)   │ rệt trên nền xám/trắng mờ của dữ liệu nền.         │
└───────────────────┴────────────────────────────────────────────────────┘
```

---

## 3. 🏷️ CHUẨN HÓA TIÊU ĐỀ HÀNH ĐỘNG (ACTION TITLES)

100% biểu đồ phân tích trong hệ thống đã được nâng cấp từ nhãn tĩnh đơn thuần sang **Action Titles mang bằng chứng định lượng**:

1. **Calendar Heatmap**: Thể hiện giá trị đỉnh OT đạt được trong phạm vi lọc và đối chiếu với ngưỡng 85°C.
2. **STL Decomposition**: Tách bạch rõ thành phần xu thế dài hạn và chu kỳ dao động ngày đêm.
3. **Quantile Fan**: Ghi rõ nguồn gốc dải bách phân vị lịch sử cố định, không bị bóp méo khi chọn Date Range.
4. **Stacked Bar**: Thể hiện tỷ lệ tải hữu ích/vô công 3 cấp áp (HU, MU, LU) theo 24 giờ.
5. **Lag Heatmap**: Khẳng định độ trễ tải dẫn trước nhiệt 0–12 giờ từ ma trận tương quan Pearson lịch sử.
6. **OT Threshold Chart**: Liệt kê chính xác số đợt cảnh báo (Warning) và nguy hiểm (Critical) kèm tổng thời lượng trong scope.
7. **Barcode Timeline**: Tóm tắt số đợt sự cố hoàn chỉnh và áp lực nhiệt tích lũy Degree-Hours (°C·h).
8. **Synchronized Small Multiples**: Nêu rõ 6 nhánh tải với trục thời gian đồng bộ và các đợt sự cố được highlight.
9. **Joint Scatter + LOESS**: Đường hồi quy phi tuyến tính tham chiếu toàn lịch sử, không tự refit sai lệch trong UI.
10. **Regime Boxplots**: Phân bố cụ thể của biến chọn qua 3 chế độ nhiệt Normal, Warning (≥85°C), Critical (≥95°C).

---

## 4. 🏁 KẾT LUẬN NGHIỆM THU T0502

- Báo cáo xác nhận toàn bộ 10/10 biểu đồ của dự án đạt điểm tối đa về tỷ lệ Data-Ink và cấu trúc Gestalt.
- Mã nguồn kiểm thử visual QA regression được lưu tại [`tests/test_t0502_visual_qa.py`](file:///d:/HOCTAP/repo/data_visualization_project/tests/test_t0502_visual_qa.py).
- Hệ thống hoàn toàn sẵn sàng cho việc đóng gói sản phẩm và kiểm tra tiếp cận màu sắc T0503.
