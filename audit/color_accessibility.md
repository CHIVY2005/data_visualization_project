# 🎨 BÁO CÁO KIỂM THỬ TIẾP CẬN MÀU SẮC & WCAG AA (T0503)

- **Dự án:** ETT Power Grid Operational Management & Thermal Safety Visual Analytics Dashboard
- **Mã định danh:** `ETT_GRID_VIS_2026` | **Phiên bản:** 2.0 | **Work Package:** `WP05` (T0503)
- **Tiêu chuẩn quy chiếu:**
  - W3C Web Content Accessibility Guidelines (WCAG) 2.1 — Success Criterion 1.4.1 (Use of Color), 1.4.3 (Contrast Minimum - Level AA), 1.4.11 (Non-text Contrast - Level AA).
  - Edward Tufte Data-Ink Ratio & Gestalt Visual Principles.
  - AGENTS.md §CODE & VISUALIZATION STANDARDS (Quy chuẩn màu sắc & ranh giới dự án).
- **Trách nhiệm RACI:** TV chính E (PM & Visual QA Auditor) thực thi (R/A); TV hỗ trợ D (UI Lead Story 2) phối hợp (C).
- **Thời điểm nghiệm thu:** 2026-10-29.
- **Trạng thái:** **PASS** (Đạt chuẩn WCAG 2.1 AA cho toàn bộ bảng màu và hoàn thiện cơ chế mã hóa kép).

---

## 1. 📊 TỔNG HỢP BẢNG MÀU HỆ THỐNG & ĐỘ TƯƠNG PHẢN (WCAG AA)

Theo khuyến nghị W3C WCAG 2.1, tỷ số tương phản (Contrast Ratio - CR) được tính bằng công thức:
$$CR = \frac{L_1 + 0.05}{L_2 + 0.05}$$
trong đó $L_1$ là độ chói tương đối (relative luminance) của màu sáng hơn, $L_2$ là độ chói tương đối của màu tối hơn ($0.0 \le L \le 1.0$).

### Bảng kiểm định độ tương phản trên nền trắng (`#FFFFFF`, $L = 1.0$)

| Tên vai trò | Mã Hex | Relative Luminance ($L$) | Tỷ số tương phản (CR:1) | Chuẩn Body Text (≥ 4.5:1) | Chuẩn UI/Large Text (≥ 3.0:1) | Ứng dụng thực tế trong Dashboard |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **Slate-900 (Headings)** | `#0F172A` | 0.0076 | **18.31:1** | **PASS (AAA)** | **PASS (AAA)** | Tiêu đề chính, Markdown headers, KPI labels |
| **Slate-800 (Primary Text)** | `#1E293B` | 0.0219 | **14.63:1** | **PASS (AAA)** | **PASS (AAA)** | Nhãn trục (Tick labels), Chú giải, Tiêu đề biểu đồ |
| **Navy (OT / Normal)** | `#1E3A8A` | 0.0513 | **10.36:1** | **PASS (AAA)** | **PASS (AAA)** | Đường nhiệt độ OT, Boxplot Normal, Trace hữu ích |
| **Crimson (Critical)** | `#DC2626` | 0.1673 | **4.83:1** | **PASS (AA)** | **PASS (AA)** | Ngưỡng nguy hiểm 95°C, Marker vi phạm Critical |
| **Slate-500 (Context/Muted)**| `#64748B` | 0.1706 | **4.76:1** | **PASS (AA)** | **PASS (AA)** | Đường xu hướng Trend, Nhãn phụ, Chú thích bối cảnh |
| **Teal (Useful Load)** | `#0D9488` | 0.2307 | **3.74:1** | *N/A (Graphics)* | **PASS (AA UI)** | Đường tải hữu ích HUFL/MUFL/LUFL (Stroke ≥ 1.5px) |
| **Amber (Warning)** | `#D97706` | 0.2795 | **3.19:1** | *N/A (Graphics)* | **PASS (AA UI)** | Ngưỡng cảnh báo 85°C, Vùng tô Warning (Line ≥ 1.5px) |
| **Blue Band Fill (50% IQR)**| `#93C5FD` (α=0.28)| 0.5489 | **1.75:1** | *N/A (Area fill)*| **PASS (Tufte)** | Vùng tô phân phối 50% IQR (không chứa chữ) |
| **Gridline (Tufte Main)** | `#E2E8F0` | 0.7712 | **1.23:1** | *N/A (De-emphasized)*| **PASS (Tufte)** | Lưới tọa độ chính (chủ động làm mờ chống nhiễu thị giác) |

> [!NOTE]
> - Các màu **Amber (`#D97706`)** và **Teal (`#0D9488`)** được sử dụng cho đường biểu đồ kỹ thuật (độ dày stroke $\ge 1.5\text{px}$) và vùng diện tích (Graphical Objects), thỏa mãn hoàn toàn ngưỡng **≥ 3.0:1** của WCAG 2.1 SC 1.4.11.
> - Khi hiển thị chữ cảnh báo số liệu (như callout *"85°C Warning"*), hệ thống bổ sung thuộc tính chữ in đậm hoặc đặt cạnh biểu tượng/badge viền tương phản cao để đảm bảo độ dễ đọc tối đa.

---

## 2. 👁️ KIỂM ĐỊNH MÔ PHỎNG MÙ MÀU (COLORBLIND-SAFE EVALUATION)

Để đảm bảo người dùng có khiếm khuyết về thị lực màu sắc (Color Vision Deficiency - CVD) không bị bỏ sót thông tin an toàn lưới điện, bảng màu cốt lõi `Navy - Amber - Crimson - Teal - Slate` đã được phân tích qua 4 dạng suy giảm thị giác màu:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        COLORBLIND MATRIX EVALUATION                    │
├─────────────────┬───────────┬───────────────┬──────────────┬───────────┤
│ Vai trò         │ Chuẩn     │ Deuteranopia  │ Protanopia   │ Tritanopia│
│                 │ (RGB)     │ (Mù xanh lá)  │ (Mù đỏ)      │ (Mù xanh) │
├─────────────────┼───────────┼───────────────┼──────────────┼───────────┤
│ Navy (OT/Normal)│ #1E3A8A   │ Xanh sẫm đậm  │ Xanh sẫm đậm │ Xanh đen  │
│ Amber (Warning) │ #D97706   │ Vàng mù tạc   │ Vàng nâu sáng│ Hồng đào  │
│ Crimson (Crit)  │ #DC2626   │ Nâu ô liu sẫm │ Xám nâu đậm  │ Đỏ tươi   │
│ Teal (Useful)   │ #0D9488   │ Xanh lam nhạt │ Xanh lam tro │ Xanh lục  │
│ Slate (Context) │ #64748B   │ Xám xanh trung│ Xám trung tính│ Xám nhạt │
└─────────────────┴───────────┴───────────────┴──────────────┴───────────┘
```

### 2.1 Loại bỏ hoàn toàn cặp màu cạnh tranh Đỏ — Xanh lá (Red — Green)
- **Vấn đề thực tiễn:** Bảng màu giao diện thông thường hay dùng Xanh lá cho trạng thái bình thường (Normal) và Đỏ cho trạng thái lỗi (Hazard). Với 8% nam giới mắc Deuteranopia/Protanopia, hai màu này chuyển thành cùng một tông vàng/nâu, gây nguy cơ nhầm lẫn nghiêm trọng giữa "an toàn" và "sự cố".
- **Giải pháp của dự án:**
  - Không sử dụng màu Xanh lá (`#00FF00` hoặc `#22C55E`) cho trạng thái bình thường.
  - Trạng thái bình thường (`Normal`) dùng **Navy (`#1E3A8A`)** — một màu có độ chói thấp và giữ sắc độ xanh lam rõ rệt trên mọi dạng CVD.
  - Tải hữu ích dùng **Teal (`#0D9488`)** — nằm ở dải lục lam, hoàn toàn phân biệt với Navy nhờ độ sáng cao hơn rõ rệt.

### 2.2 So sánh với bảng màu chuẩn học thuật (Okabe-Ito & Viridis)
1. **Okabe-Ito:** Bảng màu 8 màu chuẩn cho ấn phẩm khoa học. Dự án kế thừa nguyên lý của Okabe-Ito bằng cách chọn các bước sóng phân cách rõ trên biểu đồ màu CIE $L^*a^*b^*$:
   - Xanh dương (`#1E3A8A` tương ứng Blue của Okabe-Ito).
   - Vàng cam (`#D97706` tương ứng Orange/Yellow của Okabe-Ito).
   - Đỏ mận (`#DC2626` tương ứng Vermilion của Okabe-Ito).
2. **Viridis:** Được áp dụng trong các heatmap liên tục (như ma trận tương quan phân kỳ kết hợp Navy - Neutral Slate - Teal) để giữ tính đơn điệu về độ sáng (perceptually uniform), giúp người đọc nhận biết cường độ tương quan ngay cả khi in trắng đen (Grayscale).

---

## 3. 🛡️ NGUYÊN TẮC MÃ HÓA KÉP (NON-COLOR DUAL ENCODING)

Tuân thủ nghiêm ngặt **WCAG 2.1 SC 1.4.1 (Use of Color)**: *Màu sắc không bao giờ là phương tiện duy nhất để truyền đạt thông tin, biểu thị hành động hoặc phân biệt các yếu tố giao diện.*

| Biểu đồ / Thành phần | Kênh thông tin chính (Màu sắc) | Kênh thông tin bổ trợ (Mã hóa kép độc lập với màu) | Bằng chứng kiểm chứng |
| :--- | :--- | :--- | :--- |
| **OT Threshold Monitoring** | Amber 85°C, Crimson 95°C | **Kiểu nét đứt + Tọa độ Y + Nhãn trực tiếp**: Đường 85°C và 95°C dùng `dash="dash"`, cố định tại trục Y tuyệt đối, có text annotation trực tiếp `"85°C Warning"` và `"95°C Critical"`. | `TestOTThresholdAnnotations` PASS |
| **Barcode / Rug Timeline** | Vạch Amber / Crimson | **Trục thời gian + Tooltip chi tiết + Action Title**: Mỗi vạch biểu diễn đợt vi phạm cụ thể có thời lượng `[start, end)` chính xác, tooltip hiển thị rõ độ dài giờ và Degree-Hours. | `TestBarcodeRugTitle` PASS |
| **Quantile Fan** | Dải Blue alpha giảm dần | **Thứ tự hình học + Đường biên + Hover**: Dải 95% nằm ngoài cùng bao bọc dải 80% và 50% IQR; đường trung vị nét liền có hovertext riêng cho từng bách phân vị. | `TestQuantileFanBandAlphaOrdering` PASS |
| **Synchronized Multiples**| Nền highlight sự cố | **Tọa độ liên kết (Shared X-axis crosshair)**: Khi trỏ chuột vào một thời điểm, đường gióng dọc xuất hiện trên cả 6 panel tải đồng bộ. | Small multiples synchronized linking |
| **Regime Boxplots** | Navy, Amber, Crimson | **Vị trí trục hoành danh mục (Categorical X-axis)**: 3 boxplot được phân tách thành 3 cột riêng biệt có nhãn rõ ràng: `Normal`, `Warning (≥85°C)`, `Critical (≥95°C)`. | `TestColorSemanticConsistency` PASS |
| **Lag Heatmap** | Diverging Navy-Slate-Teal | **Số học căn tâm `zmid=0.0` + Tooltip số trị**: Không dùng Crimson cho hệ số âm; mọi ô thể hiện số trị $r \in [-1, 1]$ kèm nhãn biến tải và độ trễ giờ (0..12h). | `TestLagHeatmapPaletteSemantics` PASS |

---

## 4. 🧪 KẾT QUẢ KIỂM THỬ TỰ ĐỘNG & BẰNG CHỨNG HỆ THỐNG

Các quy chuẩn tiếp cận màu sắc trên được bảo vệ liên tục thông qua bộ kiểm thử tự động trong mã nguồn:
- **File kiểm thử:** [`tests/test_t0502_visual_qa.py`](file:///d:/HOCTAP/repo/data_visualization_project/tests/test_t0502_visual_qa.py) & [`tests/test_t0503_color_accessibility.py`](file:///d:/HOCTAP/repo/data_visualization_project/tests/test_t0503_color_accessibility.py)
- **Danh mục kiểm tra cốt lõi:**
  1. `test_zmid_zero`: Khẳng định điểm giữa của bảng màu tương quan luôn là 0.0.
  2. `test_no_crimson_for_negative_correlation`: Khẳng định mã màu `#DC2626` không xuất hiện trong bảng phân kỳ tải/độ trễ.
  3. `test_ot_colorscale_anchors_at_85_95`: Khẳng định heatmap lịch sử OT luôn neo màu cảnh báo vào đúng 85.0°C và 95.0°C.
  4. `test_alpha_ordering_wide_before_narrow`: Khẳng định độ trong suốt của dải bách phân vị luôn tăng dần từ ngoài vào trong: $0.14 < 0.20 < 0.28$.
  5. `test_ot_threshold_chart_has_hlines`: Khẳng định luôn tồn tại các hình vẽ và chú thích ngưỡng ngang.
  6. `test_wcag_contrast_ratios`: Khẳng định các cặp màu văn bản và đồ họa đều vượt ngưỡng tối thiểu của WCAG AA.

---

## 5. 📋 KẾT LUẬN & ĐÓNG GÓI HỒ SƠ WP05

1. **Kết luận nghiệm thu:** Task T0503 hoàn thành xuất sắc các tiêu chí Definition of Done:
   - Toàn bộ màu sắc trong hệ thống đã được kiểm toán độ tương phản và mô phỏng CVD.
   - Nguyên tắc Data-Ink của Tufte và WCAG 2.1 AA được đảm bảo 100%.
   - Không có bất kỳ cảnh báo an toàn nào chỉ truyền tải đơn thuần qua kênh màu sắc.
2. **Sẵn sàng chuyển giao:**
   - Hồ sơ nghiệm thu được lưu trữ chuẩn mực tại [`audit/color_accessibility.md`](file:///d:/HOCTAP/repo/data_visualization_project/audit/color_accessibility.md).
   - Bộ 3 task tích hợp và kiểm toán WP05 (**T0501, T0502, T0503**) đã hoàn thành trọn vẹn trên nhánh `feat/T0501_T0502_T0503-integration-qa`.
