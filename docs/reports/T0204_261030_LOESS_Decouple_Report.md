# 📄 Báo cáo thực thi & nghiệm thu: T0204 — Offline LOESS & Decouple UI

- **Project:** ETT Power Grid Operational Management & Thermal Safety Visual Analytics Dashboard.
- **ID / Version:** `ETT_GRID_VIS_2026` / 2.0 — CPU-only statistical & visual analytics.
- **Task:** `T0204` — WP02; phạm vi FReq006, FReq011 theo yêu cầu người dùng.
- **Ngày lập báo cáo:** 2026-10-30 20:45 (UTC+07:00).
- **Branch:** `fix/T0501_T0502_T0503-integration-qa`.
- **HEAD khi kiểm tra:** `cf7639f`; thay đổi triển khai T0204 đang ở working tree.
- **Status:** **PASS** về implementation, artifact contract và regression.
- **Giới hạn:** Chưa nghiệm thu SLA trình duyệt/end-to-end; không tự chứng nhận an toàn.
- **AMBER:** Người dùng đã xác nhận đồng bộ các file liên quan trực tiếp, gồm `app.py`.
- **Commit/push trong tác vụ lập báo cáo:** Không thực hiện.

**ROOT:** `F:\Study Materials\specialized_subject\Visualization\Visualization_gr\data_visualization_project`.

Tên module/artifact trong các bảng được định vị theo thư mục nêu rõ dưới ROOT.
Báo cáo này ghi nhận T0204; không sửa các báo cáo lịch sử để che thay đổi schema.

---

## 1. 📊 EXECUTIVE SUMMARY & ACCEPTANCE MATRIX

T0204 chuyển đường tham chiếu LOWESS sang hợp đồng bảy cột thống nhất,
tiền tính sáu nhánh tải đối chiếu OT theo dataset và scope lịch sử.
Dashboard chỉ đọc tọa độ; không fit lại khi đổi Date Range.

“Đa biến” ở đây là sáu quan hệ tải–OT riêng biệt, **không phải** hồi quy đồng thời
sáu đầu vào, không suy luận nhân quả và không xây hệ thống dự báo.

| Deliverable / Requirement | Component | Status | Evidence |
|---|---|---|---|
| Compute offline LOWESS | `src/analysis/thermal_risk.py` | PASS | `compute_loess_curves`, tham số và scope được test |
| Atomic export + provenance | `src/analysis/thermal_risk.py`, helper common | PASS | `.tmp`, verified round-trip, `os.replace`, failure regression |
| Pipeline integration | `scripts/run_statistical_engine.py` | PASS | Engine đã chạy trên features thực, artifact hiện diện |
| Loại producer schema cũ | `src/analysis/diagnostics.py` | PASS | Delegate producer T0204; tránh fit/ghi đè hai lần trong engine |
| Story 2 consumer | `src/visuals/app_safety.py`, `app.py` | PASS | Đọc schema mới, chọn scope, không gọi LOWESS runtime |
| Cache identity/version | Loader hiện có trong `app.py` | PASS | Path/version được hash; regression invalidation |
| Full regression | Toàn suite | PASS | 210 passed, 0 failures/errors; chạy lại khi lập báo cáo |
| Browser SLA <2s | Chưa đo end-to-end | NOT MEASURED | AppTest server-side không thay thế browser benchmark |

## 2. 🛡️ GUARDRAILS & PHẠM VI THAY ĐỔI

### 2.1 File triển khai và tests

| File dưới ROOT | Thay đổi chính |
|---|---|
| `src/data/constants.py` | Path LOESS, frac, iterations, grid, min samples và regime |
| `src/analysis/thermal_risk.py` | Schema, compute và save LOESS với type hints |
| `src/analysis/diagnostics.py` | Bỏ producer LOWESS cũ, delegate producer thống nhất |
| `scripts/run_statistical_engine.py` | Gọi export LOESS; diagnostics không export trùng |
| `src/visuals/app_safety.py` | Chọn tọa độ đã lưu theo dataset/load/scope |
| `app.py` | Dùng `load_feature`, thêm lựa chọn regime tham chiếu |
| `tests/test_visuals_story2.py` | Fixture consumer chuyển sang schema mới |
| `tests/test_loess_t0204.py` | 13 test cases T0204, gồm các trường hợp parametrized |

Không thêm dependency, không sửa requirements và không cài/nâng package.
Python/test chạy trong `.venv`; stack dùng Pandas, NumPy, PyArrow, Statsmodels.
Không dùng Torch/GPU trong logic triển khai.
Hàm compute thiết lập seed 2026 qua helper hiện có.

### 2.2 RED zone và Git

- Không ghi vào raw, charter hoặc references.
- SHA-256 ba CSV raw được đối chiếu lại với evidence T0204 và đều khớp.
- Working tree vẫn có deletion tệp khóa Excel RED zone từ trước tác vụ này.
- Không khôi phục/xóa thêm/stash tệp khóa để làm sạch trạng thái Git.
- Không stage, commit, push hoặc thay đổi nhánh khi lập báo cáo.
- Không tuyên bố working tree sạch: code/artifacts T0204 vẫn chưa commit.

## 3. 🔬 ENGINE LOGIC & ARTIFACT CONTRACT

### 3.1 Input, grouping và thuật toán

Input thực tế: `data/processed/grid_features.parquet`.
Producer cũng hỗ trợ clean input qua bước feature builder hiện có.
Luôn tách `dataset`; không trộn ETTh1/ETTh2 1h với ETTm1 15 phút.

| Dimension | Giá trị/phạm vi |
|---|---|
| `load_feature` | HUFL, HULL, MUFL, MULL, LUFL, LULL |
| `scope_type=all` | `scope_value=ALL` |
| `scope_type=season` | Dry hoặc Wet theo month bins dự án |
| `scope_type=thermal_regime` | Normal, Warning, Critical khi đủ dữ liệu |

Scopes là các lát cắt riêng, **không phải** tích Descartes season×regime.
Mùa là quy ước tháng dự án, không tự nhận là khí hậu đã xác minh.

Các bước compute:

1. Dựng features theo contract; không sửa DataFrame đầu vào.
2. Lấy cặp tải/OT hữu hạn, loại null/Inf khỏi fit.
3. Sắp xếp ổn định tải rồi OT để bảo đảm tính lặp lại.
4. Bỏ nhóm dưới 10 cặp hoặc tải/OT không biến thiên.
5. Fit toàn bộ cặp hợp lệ, giữ trọng số quan sát có tải trùng nhau.
6. Gộp fitted y trung bình tại x trùng để nội suy.
7. Nội suy tuyến tính 150 tọa độ đều từ min(load) đến max(load).
8. Cast float32 và chỉ xuất nhóm có tọa độ hữu hạn.

Tham số LOWESS: `endog=OT`, `exog=load`, `frac=0.2`, `it=3`,
`return_sorted=True`. `n_grid` được kiểm tra trong khoảng 100–200.
Không lấy mẫu giảm đầu vào fit như producer cũ tối đa 1.000 quan sát.
Nhóm không hỗ trợ được bỏ qua; không biến thành đường 0 hoặc dữ liệu giả.

### 3.2 Schema bảy cột đã xuất

| Cột | Arrow / Pandas dtype | Ý nghĩa |
|---|---|---|
| `dataset` | string | ID dataset |
| `load_feature` | string | Nhánh tải được fit |
| `scope_type` | string | all / season / thermal_regime |
| `scope_value` | string | Giá trị scope |
| `x_load` | float32 | Phụ tải gốc, không tự gán MW/MVar |
| `y_ot_smooth` | float32 | OT làm mịn, đơn vị °C |
| `sample_count` | int32 | Số cặp hợp lệ thực sự đưa vào fit |

Các field Arrow đều non-nullable; bảng rỗng vẫn giữ đúng dtype.
Metadata gồm schema_version 2.0, dataset, source hash, seed, generated_at,
timezone unknown, parameters và quality_audit.
Artifact LOESS bổ sung không thay thế năm canonical artifacts của dự án.

### 3.3 Artifact thực tế và nguyên tử ghi

- Output: `output/artifacts/loess_curves.parquet`.
- Số dòng: **10.800**; số nhóm hợp lệ: **72**; mỗi nhóm **150** tọa độ.
- Kích thước: **91.709 bytes**.
- Thời điểm sinh trong metadata: `2026-10-30T13:32:49.374593+00:00`.
- Source hash: `2fd998614a1e8b9ec73cbd5e8ef4c7213bb0f1af9f2e29d821d8bb54e642e65b`.
- Không null, NaN hoặc Inf trong artifact được đọc lại khi lập báo cáo.

| Dataset | Scope thực có | Nhánh/scope | Nhóm | Dòng |
|---|---|---:|---:|---:|
| ETTh1 | ALL, Dry, Wet, Normal | 6 | 24 | 3.600 |
| ETTh2 | ALL, Dry, Wet, Normal | 6 | 24 | 3.600 |
| ETTm1 | ALL, Dry, Wet, Normal | 6 | 24 | 3.600 |

Dữ liệu thật chỉ có Normal; không tạo Warning/Critical giả để đủ danh mục.
Warning/Critical được bao phủ bằng fixture tổng hợp riêng trong tests.
Atomic writer tạo `.tmp` độc quyền, flush/fsync, xác minh round-trip rồi replace.
Test giả lập replace failure xác nhận file cũ nguyên vẹn và dọn tmp thuộc lần ghi.

## 4. 🖥️ UI DECOUPLING & CACHE

Story 2 dùng loader Parquet versioned sẵn có: tham số `path`, `version`,
không có underscore đầu tham số khiến cache bỏ qua nguồn/phiên bản.
UI lọc artifact nhẹ theo dataset và nhánh, rồi chọn đúng scope trước khi vẽ.

- Không chọn regime cụ thể: dùng season nếu có, nếu không dùng all/ALL.
- Chọn Normal/Warning/Critical: dùng tham chiếu regime toàn lịch sử.
- Regime reference không tự điều kiện theo season hoặc Date Range.
- Legend đường cong nêu `scope_type: scope_value` để phân biệt tham chiếu.
- Không có curve phù hợp: hiện chú thích unavailable, không fit dự phòng.
- Nhánh/tập dữ liệu không được nối thành một đường tham chiếu lẫn nhau.
- Schema mới được đồng bộ producer, composition root, chart và fixture.

UI trước T0204 vốn đã bỏ fit runtime; task này chuẩn hóa producer/scopes/schema
và giữ chặt ranh giới đó, không tuyên bố vừa phát hiện một fallback đang chạy.

## 5. 🧪 TESTING & PERFORMANCE EVIDENCE

Lệnh regression chạy lại khi lập báo cáo: `python -m pytest -q --tb=short`.
Kết quả: **210 passed, 8 warnings in 44.85s**; 0 Failures, 0 Errors.
Evidence triển khai trước đó: 210 passed, 8 warnings trong 36,39 giây.
Hai số đo thuộc hai lần chạy, không phải một kết quả mâu thuẫn.

Coverage T0204 gồm:

- Schema/dtype, seed/metadata, tọa độ hữu hạn và production artifact.
- Determinism, không sửa input, không lẫn dataset và các scope.
- Nhóm ít mẫu, constant load, constant OT, empty trả bảng typed empty.
- Finite-pair sample_count và đúng frac/it/return_sorted.
- Tham số sai bị từ chối; atomic failure bảo toàn output trước đó.
- Cache đổi path/version trả nguồn mới.
- Chart dùng scope đã lưu khi monkeypatch cấm fit runtime.
- Kiểm tra source visuals không import Statsmodels.

**AppTest đã đo trong đợt triển khai, không chạy lại khi viết báo cáo:**

| Dataset | LOESS view server-side |
|---|---:|
| ETTh1 | 0,1170s |
| ETTh2 | 0,1212s |
| ETTm1 | 0,1336s |

Ba dataset × bốn lựa chọn regime không exception; tọa độ luôn đọc từ artifact.
Số đo view không bao gồm browser paint/network hoặc cold-start toàn ứng dụng.
Không dùng kết quả này để đánh dấu hoàn tất SLA end-to-end của T0504.

## 6. 🚩 GIỚI HẠN, DOD & HÀNH ĐỘNG TIẾP THEO

Engine thực có cảnh báo số học LOWESS divide; producer bỏ fit không hữu hạn.
Artifact cuối đã xác minh hữu hạn; không coi cảnh báo là đã được xử lý triệt để.
Tám cảnh báo pytest là deprecation Pandas/Seaborn/Matplotlib, không phải failure.
Chạy engine đầy đủ đã tái sinh STL, quantile, lag JSON, event và Z-score artifacts,
bao gồm metadata thời điểm sinh; cần review cùng diff trước khi commit T0204.

- [x] Artifact thực được sinh, đúng schema bảy cột, 150 điểm/nhóm hợp lệ.
- [x] UI đọc dữ liệu tiền tính qua cache, không gọi LOWESS runtime.
- [x] Toàn bộ suite 210/210 PASS, raw SHA-256 khớp evidence trước.
- [x] Báo cáo phân biệt kết quả thực, giới hạn và số đo lịch sử.
- [ ] Browser/end-to-end SLA: tiếp tục đo trong T0504.
- [ ] Commit/review thay đổi T0204: chưa thực hiện trong tác vụ báo cáo.

**Evidence chính:**
`F:\Study Materials\specialized_subject\Visualization\Visualization_gr\data_visualization_project\audit\t0204_loess_validation.json`.

**Test nguồn:**
`F:\Study Materials\specialized_subject\Visualization\Visualization_gr\data_visualization_project\tests\test_loess_t0204.py`.

Tiếp theo: T0205 kiểm toán provenance/quality toàn bộ artifacts theo dataset;
T0304 dùng các tham chiếu đã lưu cho notebooks; T0504 đo cache/SLA đầy đủ.