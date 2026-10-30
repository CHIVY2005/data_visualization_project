# 📄 Báo cáo thực thi & nghiệm thu: T0304 — Notebooks TQH-04 & TQH-05

- **Project:** ETT Power Grid Operational Management & Thermal Safety Visual Analytics Dashboard.
- **ID / Version:** `ETT_GRID_VIS_2026` / 2.0 — CPU-only statistical & visual analytics.
- **Task:** `T0304` — khám phá thống kê sâu và chắt lọc thông điệp trực quan.
- **Ngày lập báo cáo:** 2026-10-30 21:55 (UTC+07:00).
- **Branch:** `feat/T0205`, giữ nguyên nhánh làm việc hiện tại theo phạm vi cho phép.
- **HEAD khi kiểm tra:** `83e9c86`, commit T0205; sản phẩm T0304 chưa commit.
- **Status:** **PASS** về notebook Run-all, provenance inputs và full regression.
- **Giới hạn:** Hình nghiên cứu tĩnh; chưa chứng nhận browser interaction hoặc SLA.
- **Commit/push trong T0304 và tác vụ lập báo cáo:** Không thực hiện.

**ROOT:** `F:\Study Materials\specialized_subject\Visualization\Visualization_gr\data_visualization_project`.

Tên notebook/module/artifact trong các bảng được định vị theo ROOT và thư mục nêu rõ.
Báo cáo phân biệt execution evidence đã lưu với kiểm tra mới khi viết tài liệu.

---

## 1. 📊 EXECUTIVE SUMMARY & ACCEPTANCE MATRIX

T0304 cung cấp hai Jupyter Notebooks độc lập, đọc artifacts đã kiểm toán T0205,
phân tích riêng từng dataset và chuyển quan sát thống kê thành Action Titles.
Không chạy lại statistical engine, không fit LOWESS trong notebook storytelling,
không tự gán nguyên nhân từ tương quan hoặc bịa giá trị quá nhiệt để minh họa.

| Deliverable / Requirement | Component | Status | Evidence |
|---|---|---|---|
| Khám phá thống kê TQH-04 | Notebook 02 | PASS | 7 code cells, 5 hình, tables/outputs đã lưu |
| Storytelling TQH-05 | Notebook 03 | PASS | 7 code cells, 8 hình, Action Titles từ dữ liệu |
| Run-all độc lập | Kernel riêng cho mỗi notebook | PASS | 0 cell errors; interpreter repository `.venv` |
| What–Why–How | Markdown notebook 03 | PASS | Mapping US-01/US-02 và encoding/interaction |
| Tái lập và lineage | Seed/hash checks + metadata | PASS | Seed 2026, input hashes khớp audit T0205 |
| Read-only artifacts/RED | Kiểm tra trước/sau execution | PASS trong phạm vi đo | 12 protected files không đổi |
| Notebook regression | `tests/test_notebooks_t0304.py` | PASS | 3 cases gồm hai notebook và execution audit |
| Full suite hiện tại | Pytest | PASS | 222 passed, 0 failures/errors |
| Browser SLA/accessibility | Không nằm trong nghiệm thu notebook | NOT MEASURED | Không dùng hình tĩnh để chứng nhận UI |

Hai sản phẩm thực tế nằm trong thư mục notebooks:

- `02_tqh04_statistical_analysis.ipynb` — **470.726 bytes**.
- `03_tqh05_insights_visual_storytelling.ipynb` — **905.585 bytes**.

## 2. 🛡️ PHẠM VI, INPUTS & TÍNH TÁI LẬP

### 2.1 File được tạo/cập nhật

| File dưới ROOT | Vai trò |
|---|---|
| `notebooks/02_tqh04_statistical_analysis.ipynb` | Notebook phân tích, có outputs thực thi |
| `notebooks/03_tqh05_insights_visual_storytelling.ipynb` | Notebook visual storytelling, có outputs |
| `scripts/build_t0304_notebooks.py` | Sinh và Run-all hai notebook bằng kernel đúng `.venv` |
| `tests/test_notebooks_t0304.py` | Kiểm tra cấu trúc, output, execution/provenance |
| `audit/t0304_notebook_execution.json` | Thời gian, số cells, interpreter và hashes |
| `notebooks/README.md` | Chuyển handoff kế hoạch thành hướng dẫn sản phẩm đã thực thi |

Không sửa engine/core logic, dashboard, requirements hoặc artifacts nguồn.
Không cài/nâng package. Dùng các package sẵn có trong `.venv`:
Pandas, NumPy, Matplotlib, nbformat, jupyter_client và ipykernel.
Không chạy training/GPU, không thêm dependency Torch.

### 2.2 Sáu artifacts được notebook đọc

| Input | Thư mục dưới ROOT | Quy mô / vai trò |
|---|---|---|
| `clean_ett.parquet` | `data/processed/` | 104.520 dòng, 14 cột; quan sát gốc có đơn vị |
| `load_profiles_stl.parquet` | `output/artifacts/` | 941.976 dòng STL/profile tiền tính |
| `quantile_bands.parquet` | `output/artifacts/` | 1.296 dòng phân vị giờ theo dataset/mùa/biến |
| `lag_correlation_matrix.json` | `output/artifacts/` | 12 records; ma trận/counts 6×13 |
| `thermal_breach_events.parquet` | `output/artifacts/` | Bảng rỗng đúng schema; không tạo breach giả |
| `loess_curves.parquet` | `output/artifacts/` | 10.800 tọa độ LOWESS, schema T0204 bảy cột |

Bootstrap của mỗi notebook đối chiếu sáu file với SHA-256 trong audit T0205.
Execution audit ghi thêm grid_features trong tổng bảy input hashes được bảo toàn;
điều này không có nghĩa notebook đọc grid_features để thực hiện phân tích.
Input hashes được kiểm tra lại khi lập báo cáo và vẫn khớp evidence.

ETTh1/ETTh2: 17.420 mẫu mỗi dataset, cadence 1 giờ.
ETTm1: 69.680 mẫu, cadence 15 phút. Không gộp ba chuỗi vào một phân phối chung.
Seed 2026 được khởi tạo cho random/NumPy ở cả hai notebook.
Kernel mới riêng biệt ngăn notebook 03 phụ thuộc biến đã chạy ở notebook 02.

## 3. 🔬 NOTEBOOK 02 — TQH-04 KHÁM PHÁ THỐNG KÊ SÂU

### 3.1 Thống kê mô tả và phân phối

- Tạo bảng **21 nhóm dataset × variable** cho OT và sáu nhánh tải.
- Bao gồm n hợp lệ, min, max, mean, median, q25/q75, IQR, skewness, kurtosis.
- Kurtosis ghi rõ **excess kurtosis** theo Pandas, không nhầm Pearson kurtosis.
- OT giữ °C; tải giữ đơn vị nguồn chưa xác minh, không tự gán MW/MVar.
- Histogram density tách ba dataset, cùng ngữ cảnh ngưỡng dự án.
- Daily mean/max là tổng hợp mô tả; không gọi là dự báo hoặc thay event support.

### 3.2 Thời gian và các so sánh thăm dò

- OT mean/median/count/std/min/max theo nhóm tháng Dry/Wet.
- Dry là tháng 11–4, Wet là 5–10; không tự gọi mùa hè/đông địa phương.
- Khung 17:00–20:59 được khai báo để **thăm dò**, không phải giờ cao điểm đã xác minh.
- Bảng chênh lệch mean giữa nhóm chỉ là quan sát, không dùng suy ra nhân quả.
- Chu kỳ giờ 0–23, thứ Mon–Sun và tháng 1–12 có bảng n/mean/median/min/max.
- Dải q10–q90 thể hiện 80% lịch sử, không phải confidence interval của mean.
- Mọi phép tổng hợp giữ dataset key, không để cadence 15 phút chi phối pooled mean.

### 3.3 Đỉnh OT, ngưỡng và diagnostics

Notebook xuất top-5 mẫu OT mỗi dataset, timestamp, regime và khoảng cách đến 85°C.
Không đặt ngưỡng “cận nguy hiểm” tùy tiện: khoảng cách là số đo mô tả trực tiếp.
Bảng threshold tách 85°C/95°C, valid samples, số mẫu vượt, tỷ lệ, events,
duration và Degree-Hours đọc từ artifact sự kiện đã tiền tính.
Không nhân count mẫu với cadence để tạo event duration giả cho mẫu cuối/gap.

Kiểm tra nhẹ trên outputs tiền tính:

- STL reconstruction `observed ≈ trend + seasonal + residual` trên hàng hợp lệ.
- Quantile nesting q025 → q10 → q25 → q50 → q75 → q90 → q975.
- Shape ma trận lag 6×13; tọa độ LOESS hữu hạn.
- Bảng coverage diagnostics theo dataset; không fit STL/lag/LOWESS lại.

## 4. 🖥️ NOTEBOOK 03 — TQH-05 INSIGHT & STORYTELLING

### 4.1 What–Why–How cho hai User Stories

| Story / tác vụ | Dữ liệu | Encoding / thông điệp |
|---|---|---|
| US-01: tìm chu kỳ để lập kế hoạch | OT ngày/giờ/nhóm tháng | Calendar Heatmap, Fan 50/80/95%, STL panels trong mapping |
| US-01: xem cơ cấu useful/unuseful | Sáu nhánh chia ba cấp áp | 100% Stacked Bar, loại tỷ lệ không hợp lệ |
| US-01: sàng lọc độ trễ | Pearson/Spearman lịch sử | Lag Heatmap tâm 0, có n/r/k và giới hạn nhân quả |
| US-02: tra cứu ngưỡng/sự kiện | OT gốc và event support | Threshold Line, Barcode/Rug, tổng riêng từng ngưỡng |
| US-02: đối chiếu nhánh | Sáu tải và LOWESS tiền tính | Small Multiples shared X, Joint Scatter + saved curves |

Mapping nêu tương tác dự kiến trong dashboard; các hình notebook là bản tĩnh.
Tỷ trọng dùng Stacked Bar theo contract, không Stacked Area che khuất dấu tải âm.
Tỷ lệ tính từng mẫu hợp lệ rồi mean theo giờ, không âm thầm đổi sang tỷ lệ hai tổng.
Không `.clip(lower=0)`; số mẫu loại được hiển thị theo từng cấp áp.

### 4.2 Action Titles từ bằng chứng, không dùng câu demo

- Tính đỉnh OT/thời điểm và số mẫu ≥85°C theo từng dataset.
- Tính ngày có mean OT cao nhất, phân biệt với instantaneous peak.
- Tìm giờ có IQR OT rộng nhất trong bands Dry và ghi rõ historical reference.
- Event titles nêu số đợt, duration và Degree-Hours riêng cho 85/95°C.
- Lag message nêu nhánh, k giờ, r và số cặp n của |r| lớn nhất trong scope chọn.
- Không đưa câu “98,4°C do quán tính tải kéo dài 3 giờ” khi không có evidence.
- Chọn cực đại |r| là mô tả qua nhiều ô, không phải kiểm định hoặc causal estimate.

### 4.3 Hình nghiên cứu và điều kiện diễn giải

Calendar chọn năm đầu có dữ liệu và ghi năm trên từng panel, ô thiếu giữ masked.
Fan vẽ dải rộng trước, median riêng mean; 95% dùng q025–q975.
Lag heatmap dùng màu phân kỳ với phạm vi −1 đến 1, không dùng Crimson cảnh báo.
OT line giữ ngưỡng dash/dot; event artifact rỗng có thông báo thay barcode giả.
Small multiples dùng daily mean để đọc bối cảnh, không giả làm incident-level view.
Scatter lấy mẫu thưa xác định để hiển thị; LOWESS dùng toàn bộ tọa độ đã lưu,
scope all/ALL, không fit Statsmodels trong notebook storytelling.

## 5. 🧪 RUN-ALL, REGRESSION & BẢO TOÀN WORKSPACE

Execution audit sinh `2026-10-30T14:50:01.773413+00:00`.
Hai notebook đã chạy qua kernel mới bằng interpreter repository `.venv`:

| Notebook | Code cells | Errors | Figures đã lưu | Run-all |
|---|---:|---:|---:|---:|
| 02 — Statistical analysis | 7 | 0 | 5 | 7,468s |
| 03 — Insights/storytelling | 7 | 0 | 8 | 8,235s |

Notebook JSON được validate bằng nbformat; output có bảng HTML và ảnh PNG.
Script ghi notebook/evidence qua `.tmp`, flush/fsync, round-trip rồi replace.
Hash artifacts và 12 protected files được đối chiếu trước/sau execution, không đổi.
Khi viết báo cáo chỉ validate notebook/output đã lưu, **không Run-all lại**.

Regression mới khi lập báo cáo:

```powershell
. .\.venv\Scripts\Activate.ps1
python -m pytest -q --tb=short
```

**222 passed, 8 warnings in 54.56s**; 0 Failures, 0 Errors.
Lần kết thúc triển khai trước đó: 222 PASS trong 42,98s; là lần chạy riêng.
Ba tests mới kiểm tra notebook format/execution/output/hash và execution audit.
Cảnh báo pytest là deprecation Pandas/Seaborn/Matplotlib; không phải cell error.
Kernel execution có cảnh báo TCP transport không mã hóa; không chứng nhận triển khai an toàn.
Đợt triển khai đã compile script/tests và kiểm tra diff; không sửa core engine/UI.

## 6. 🏁 GIỚI HẠN, DOD & HÀNH ĐỘNG TIẾP THEO

Historical analytics không thay certified real-time monitoring hoặc dự báo.
85/95°C là quy ước dự án, không gọi là tiêu chuẩn phổ quát.
Timezone nguồn unknown; giờ chart không tự đổi thành UTC hay local.
Gap counts=0 chỉ xác nhận cadence trong cửa sổ quan sát, không chứng minh cảm biến
hiệu chuẩn đúng hay không thiếu dữ liệu ngoài cửa sổ.
Không có breach thật không chứng minh an toàn tương lai; không nâng nhiệt demo.
Tự tương quan và biến chưa quan sát ngăn diễn giải causal/p-value độc lập ngây thơ.
Browser interaction, accessibility và SLA end-to-end chưa được đo ở T0304.

- [x] Hai notebook thực tồn tại, có seed, outputs, provenance và Run-all không lỗi.
- [x] Thống kê theo dataset, Action Titles dựa trên evidence, giới hạn ghi rõ.
- [x] Toàn suite 222/222 PASS; artifacts nguồn/RED zone được bảo toàn.
- [x] Không cài package, sửa engine hoặc commit/push.
- [ ] Review/commit sản phẩm T0304: chưa thực hiện trong tác vụ báo cáo.
- [ ] T0504: benchmark cache/SLA trên trình duyệt, không dùng hình tĩnh để nghiệm thu.

**Evidence:** `F:\Study Materials\specialized_subject\Visualization\Visualization_gr\data_visualization_project\audit\t0304_notebook_execution.json`.
**Tests:** `F:\Study Materials\specialized_subject\Visualization\Visualization_gr\data_visualization_project\tests\test_notebooks_t0304.py`.
**Rebuild:** `F:\Study Materials\specialized_subject\Visualization\Visualization_gr\data_visualization_project\scripts\build_t0304_notebooks.py`.

Chạy `python scripts/build_t0304_notebooks.py` từ ROOT sau khi kích hoạt `.venv`
để sinh và thực thi lại cả hai notebook; artifacts T0205 phải còn khớp hash audit.