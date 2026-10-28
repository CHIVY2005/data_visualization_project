# PROJECT METADATA & CONTEXT

- **Project:** ETT Power Grid Operational Management & Thermal Safety Visual Analytics Dashboard.
- **ID:** `ETT_GRID_VIS_2026` | **Version:** 2.0 | **Target:** Codex / AI coding agents.
- **Mission:** Trực quan hóa dữ liệu & phân tích thống kê ứng dụng; không xây hệ thống dự báo.
- **ROOT:** `F:\Study Materials\specialized_subject\Visualization\Visualization_gr\data_visualization_project`.
- Đường dẫn tương đối dưới đây tính từ ROOT; dùng đường dẫn tuyệt đối khi thao tác file.
- Áp dụng toàn repository; đọc chỉ dẫn thư mục con trước khi sửa; ưu tiên yêu cầu người dùng hiện hành.

| Thuộc tính | Quy định v2.0 |
|---|---|
| Stack mục tiêu | Python 3.11+, Pandas, NumPy, SciPy, Statsmodels, Plotly, Streamlit, Seaborn, Missingno |
| Runtime | CPU-only; zero PyTorch/GPU dependency |
| Dataset | ETTh1, ETTh2: 1h; ETTm1: 15 phút; không trộn trạm/độ phân giải |
| Biến gốc | `date`, `OT`, `HUFL`, `HULL`, `MUFL`, `MULL`, `LUFL`, `LULL` |
| Biến trọng tâm | `OT` (°C); giữ đơn vị và giá trị gốc, không chuẩn hóa mất ý nghĩa nhiệt độ |
| Engine | STL, empirical quantiles, lag cross-correlation 0–12h, LOESS, thermal Degree-Hours |
| Luồng dữ liệu | Raw → ETL → clean Parquet → Statistical Engine → artifacts → Plotly/Streamlit |

## User Stories & phạm vi
- **US-01 / Operational Manager:** Xem chu kỳ tải giờ/mùa, tỷ trọng hữu ích/vô công 3 cấp áp,
  độ trễ nhiệt để điều độ công suất và lập lịch bảo dưỡng.
- **US-02 / Safety & Risk Monitor:** Tra cứu OT ≥85°C / ≥95°C, thời lượng và áp lực nhiệt tích lũy;
  đối chiếu 6 nhánh tải qua Synchronized Small Multiples để khoanh vùng giả thuyết sự cố.
- `[STRICT:SCOPE]` Không triển khai Informer, PyTorch/CUDA, training, attention/decoder,
  checkpoint, benchmark MSE/MAE hoặc User Story nhà nghiên cứu học sâu.
- Đây là dashboard dữ liệu lịch sử; không tự nhận là giám sát trực tiếp hay hệ thống an toàn chứng nhận.
- Ngưỡng 85/95°C là quy ước phân tích dự án; không khẳng định là tiêu chuẩn kỹ thuật phổ quát.

## Lazy-loading references — chỉ đọc phần liên quan khi cần
| Nguồn thực có | Nội dung cần tra |
|---|---|
| `docs/project_charter/▶️[DIEU_HANH] LSTF_INFORMER_VIS_2026 - Project Charter & Sprint Manual.pdf` | Charter v2.0 dù tên file cũ; §1–4: scope/US/methods; §5: sprint; §6: RACI; §7: WBS 16 task; §8: QA/DoD |
| `docs/project_charter/Final Project.pdf` | Yêu cầu học phần, 2 US, wireframe, bàn giao giữa/cuối kỳ |
| `docs/project_charter/ETT_GRID_VIS_2026_Detailed_Tasks_6_Muc.xlsx` | `Progress Overview`, `Detailed Tasks`: 6 nhóm TQH-01..06, tiêu chí và giới hạn diễn giải |
| `docs/project_charter/bang_phan_cong_data_analytics.html` | Checklist 6 nhóm việc, lựa chọn biểu đồ, màu sắc và dashboard |
- Wireframe: tra Charter §4.2.D (What–Why–How), §7/T0301 và yêu cầu học phần §1.3.
- Chưa có file wireframe độc lập; không bịa đường dẫn hoặc coi kế hoạch là sản phẩm đã tồn tại.
- `docs/references/2021_Zhou_Informer_AAAI.pdf` chỉ là lưu trữ lịch sử; không dùng làm kiến trúc v2.0.
- README và AGENTS cũ mô tả v1.0; không khôi phục yêu cầu học sâu từ tài liệu lỗi thời.
- Không tự ánh xạ 6 nhóm TQH sang 16 task; Excel chưa điền owner/deadline không phải quyết định đã duyệt.
- RACI: A=ETL, B=Statistical Analytics, C=Story 1, D=Story 2, E=PM/Visual QA.
- WP01..04: lần lượt A/B/C/D thực thi, E accountable; WP05..06: E R/A; chi tiết tra Charter §6.

# AGENT SCOPE & STRICT GUARDRAILS

## Three-tier boundary model
| Zone | Phạm vi | Hành vi |
|---|---|---|
| 🔴 RED / READ-ONLY | `data/raw/*`, `docs/project_charter/*`, `docs/references/*` | Chỉ đọc; cấm sửa/xóa/đổi tên/ghi đè |
| 🟡 AMBER / CONFIRMATION REQUIRED | `requirements.txt`, `app.py`, cấu hình triển khai | Xin xác nhận trước khi tạo/sửa; task khác không phải phê duyệt ngầm |
| 🟢 GREEN / AUTONOMOUS | `src/data/`, `src/analysis/`, `src/visuals/`, `scripts/`, `notebooks/` | Tự triển khai trong phạm vi task và hợp đồng |
| 🟢 GREEN / GENERATED & QA | `data/processed/`, `output/artifacts/`, `tests/`, `audit/`, `docs/dev_logs/` | Tạo dữ liệu dẫn xuất, kiểm thử, audit; giữ công việc người khác |
- `[STRICT:DATA]` Không biến đổi raw; xuất dữ liệu sạch tại `data/processed/clean_ett.parquet`.
- `[STRICT:ENV]` Kích hoạt `.venv` trước mọi lệnh Python/test; kiểm tra đúng interpreter.
- Tuân thủ `requirements.txt`; cấm tự cài/nâng phiên bản hoặc thêm package ngoài khai báo.
- Stack mục tiêu không đồng nghĩa dependency đã được duyệt; báo thiếu package và xin xác nhận.
- Parquet cần backend được duyệt (ví dụ PyArrow); không tự cài để vượt lỗi môi trường.
- `[STRICT:DECOUPLE]` UI chỉ đọc Parquet/JSON tiền tính toán; phản hồi <2s.
- Không chạy STL, quantiles, lag correlation, LOESS, ETL hoặc tính risk nặng trong luồng giao diện.
- Cho phép lọc/lấy lát dữ liệu nhẹ, dựng biểu đồ và `st.cache_data`; cache theo nguồn/phiên bản artifact.
- `[STRICT:BRANCH]` Sửa trên feature branch; không commit main; không reset/stash/xóa thay đổi có sẵn.
- `[STRICT:SECRETS]` Không đọc/in/commit `.env`, API keys hoặc nội dung xác thực nếu task không cần.
- `[STRICT:EVIDENCE]` Phân biệt hiện trạng, hợp đồng mới, kế hoạch và kết quả đã kiểm chứng.
- Nguồn mâu thuẫn: theo yêu cầu v2.0 hiện hành, ghi rõ khác biệt; không sửa tài liệu gốc để che xung đột.

## Workspace baseline — khảo sát 2026-10-28
- Đã có: `src/data/`, `data/raw/`, `scripts/`, `notebooks/`, `output/`, `tests/`, `docs/`, `.venv/`.
- Chưa có: `src/analysis/`, `src/visuals/`, `data/processed/`, `output/artifacts/`, `audit/`, `app.py`.
- Chưa có script `.py` hoặc test nguồn; `.gitkeep`/`__pycache__` không phải implementation.
- `requirements.txt` chỉ khai báo `python-dotenv`, `kaggle`, `pandas`; chưa đủ stack v2.0.
- Đường dẫn chưa có là **đích triển khai**, không phải thành phần chạy được; tạo khi task yêu cầu.

# DATA INTERFACE CONTRACTS (ARTIFACT SCHEMAS)

## Quy ước chung — hợp đồng v2.0 mới, chưa phải artifacts đã sinh
- Clean đặt ở `data/processed/`; 4 artifacts còn lại đặt ở `output/artifacts/`.
- Dataset ID `dataset`: string thuộc `{ETTh1, ETTh2, ETTm1}`; luôn nhóm theo dataset.
- `timestamp`: `datetime64[ns]`, tăng dần, không trùng trong dataset; đổi raw `date` tại ETL.
- Không gán timezone khi nguồn chưa có; ghi `timezone=unknown` trong Parquet metadata/JSON.
- RFC3339 khi trao đổi timestamp dạng chuỗi đòi offset đã xác minh; không tự thêm `Z`.
- `f32`=`float32`, `i32`=`int32`, `str`=string; khai báo dtype tường minh trước khi ghi.
- Mỗi artifact có metadata: `schema_version=2.0`, dataset, source hash, tham số, seed, thời điểm sinh.
- Giữ schema cố định; thay đổi contract phải đồng bộ producer/consumer/tests, không thêm cột tùy hứng.
- Kiểm tra key, dtype, đơn vị, finite/null, thời gian; ghi file tạm rồi thay thế nguyên tử.
- Missing/constant/không đủ mẫu: trả null có ngữ cảnh chất lượng; không biến thành 0 hay Normal.

## `clean_ett.parquet` — mỗi dòng một mẫu
| Cột | Kiểu / ràng buộc |
|---|---|
| `dataset`, `timestamp` | str, datetime64[ns]; khóa ghép |
| `OT`, `HUFL`, `HULL`, `MUFL`, `MULL`, `LUFL`, `LULL` | f32; OT: °C; đơn vị tải theo nguồn, không tự gán MW/MVar |
| `total_useful_load`, `total_unuseful_load` | f32; lần lượt HUFL+MUFL+LUFL và HULL+MULL+LULL |
| `reactive_ratio` | f32 nullable; total_unuseful_load / total_useful_load; mẫu số ≤0 → null |
| `thermal_regime` | str: Normal / Warning / Critical / Unknown |
| `is_imputed` | bool; mẫu đã nội suy ít nhất một biến |
- Normal: OT<85; Warning: 85≤OT<95; Critical: OT≥95; OT thiếu → Unknown.
- Kiểm toán missing/duplicate/gap; chỉ nội suy khoảng ngắn theo policy; không xóa đỉnh OT hợp lệ.
- Không đồng nhất useful/unuseful với đại lượng vật lý P/Q đã hiệu chuẩn nếu nguồn chưa xác minh.
- Tỷ trọng 100%: tổng cặp hữu ích/vô ích cùng cấp áp; mẫu số ≤0 hoặc tải âm → null/cảnh báo.

## `load_profiles_stl.parquet` — bảng long-form thống nhất
| Cột | Kiểu / ràng buộc |
|---|---|
| `dataset`, `record_type`, `variable` | str; record_type: stl / profile; variable: 7 biến gốc hoặc 2 tổng tải |
| `timestamp` | datetime64[ns] nullable; bắt buộc với stl, null với profile |
| `season`, `hour` | str nullable, i32 nullable (0..23); bắt buộc với profile |
| `observed`, `trend`, `seasonal`, `residual` | f32 nullable; chỉ dùng cho stl |
| `mean`, `median`, `std`, `sample_count` | f32/f32/f32/i32 nullable; chỉ dùng cho profile |
- STL key: dataset+variable+timestamp; profile key: dataset+variable+season+hour; cột không áp dụng=null.
- Kiểm tra observed≈trend+seasonal+residual; daily period: 24 mẫu (1h), 96 mẫu (15m).
- Quy định mùa theo tháng trong constants; không tự gán khí hậu địa phương; lưu STL period/robust trong metadata.

## `quantile_bands.parquet` — phân phối lịch sử theo 24 giờ
| Cột | Kiểu / ràng buộc |
|---|---|
| `dataset`, `variable`, `season`, `hour` | str/str/str/i32; khóa ghép; hour 0..23 |
| `sample_count` | i32 ≥0; thiếu mẫu vẫn giữ bin, thống kê=null |
| `mean`, `q025`, `q10`, `q25`, `q50`, `q75`, `q90`, `q975` | f32 nullable; quantiles tăng không giảm |
- 50% IQR=[q25,q75]; 80%=[q10,q90]; 95%=[q025,q975]; trung vị=q50, mean là đường riêng.
- Charter có chỗ gọi Q5–Q95 là 95%; đó là dải 90%; không kế thừa nhãn sai.
- Đây là empirical historical bands, không phải confidence interval của mean hay prediction interval.
- Lưu cửa sổ lịch sử, phương pháp quantile và ngưỡng cỡ mẫu; không giả dữ liệu lấp giờ trống.

## `thermal_breach_events.parquet` — một đợt liên tục cho mỗi ngưỡng
| Cột | Kiểu / ràng buộc |
|---|---|
| `dataset`, `event_id` | str; khóa ghép duy nhất |
| `threshold_c`, `thermal_regime` | f32 thuộc {85,95}; str Warning / Critical theo ngưỡng sự kiện |
| `start_timestamp`, `end_timestamp` | datetime64[ns]; khoảng [start,end), end là biên kết thúc hỗ trợ mẫu |
| `duration_hours`, `peak_ot`, `degree_hours` | f32; duration>0, peak≥threshold, degree_hours≥0 |
| `sample_count` | i32 >0 |
| `is_right_censored` | bool; True khi chưa quan sát được kết thúc đợt |
- Breach dùng OT≥threshold; đóng event khi dưới ngưỡng hoặc gap/missing; không nối qua khoảng thiếu.
- Giữ bậc thang trái: Δt=1h hoặc 0.25h cho mẫu có hỗ trợ; chặn tại gap; không kéo dài mẫu cuối không biết.
- `degree_hours = Σ max(OT-threshold_c,0) × Δt_hours`; Thermal Stress Index dùng cùng định nghĩa °C·h.
- Mẫu cuối không xác định hỗ trợ → right-censored; điểm cô lập không có thời lượng: không tạo event giả.
- Đợt ≥95 có thể nằm trong đợt ≥85; tổng hợp riêng theo ngưỡng, không cộng chồng duration/Degree-Hours.
- Không có breach → bảng rỗng đúng dtype và thông báo không có sự kiện; cấm nâng nhiệt giả để demo.

## `lag_correlation_matrix.json` — một envelope, nhiều dataset/mùa
- Root keys: `schema_version`, `timezone`, `generated_at`, `seed`, `source_hash`, `records`.
- Mỗi record: `dataset`, `season`, `method`, `load_variables`, `lags_hours`, `correlation_matrix`, `sample_counts`.
- `method`: pearson / spearman; `load_variables`: [HUFL,HULL,MUFL,MULL,LUFL,LULL] đúng thứ tự.
- `lags_hours`: [0,1,...,12]; matrix/counts: shape 6×13; hệ số [-1,1] hoặc null, counts integer ≥0.
- Định nghĩa r(k)=corr(load(t),OT(t+k giờ)); lag dương nghĩa tải đi trước nhiệt độ.
- ETTh: k mẫu; ETTm1: 4k mẫu; căn theo timestamp, không shift mù khi có gap.
- JSON chuẩn: null, cấm NaN/Infinity; constant/thiếu cặp hợp lệ → null, không suy ra không tương quan.
- Tương quan không chứng minh nhân quả; Z-score/LOESS hỗ trợ giả thuyết, không tự kết luận thủ phạm.
- LOESS/Z-score cửa sổ sự cố phải tiền tính ngoài UI; thống nhất schema artifact bổ sung trước triển khai.
- Tên khác trong Charter (`hourly_quantiles.parquet`, `lag_matrix.parquet`, `breach_events.parquet`)
  là tên kế hoạch cũ; dùng 5 tên chuẩn mục này, không âm thầm tạo bản sao lệch schema.

# CODE & VISUALIZATION STANDARDS

- PEP 8; snake_case cho module/hàm/biến, PascalCase cho lớp; type hints đầy đủ mọi hàm trong `src/`.
- `SEED=2026`; dùng `random.seed(SEED)`, `np.random.seed(SEED)` hoặc generator truyền seed; không import Torch.
- Tập trung thresholds 85/95, cadence, STL period, mùa, quantiles, gap policy trong constants/config được duyệt.
- Không magic numbers rải rác; tách ETL / engine / visualization; không import Streamlit vào engine.
- Kiểm thử bằng fixture tổng hợp riêng; không tạo/sửa fixture bên trong raw.
- What–Why–How: mỗi chart chỉ rõ dữ liệu, tác vụ theo US và encoding/interaction; tra Charter §4.2.D.
- US-01: Calendar Heatmap, STL panels, Hourly Quantile Fan, 100% Stacked Bar, Lag Heatmap.
- US-02: OT threshold line/shading, Barcode/Rug, 6 Small Multiples, Joint Scatter+LOESS, regime Boxplots.
- Tufte: bỏ bounding box/3D/shadow/lưới phụ; lưới chính `#E2E8F0`; giữ đơn vị, ngưỡng và ngữ cảnh.
- Action Titles có bằng chứng theo bộ lọc; thiếu dữ liệu → tiêu đề trung thực, không bịa insight.
- Gestalt: proximity/alignment cho KPI/small multiples; shared X/zoom/selection; enclosure cho bands/events.
- Chỉ dùng pop-out nổi bật ở cảnh báo/sự cố; không chồng 7 đường khác thang đo thành spaghetti plot.

| Vai trò màu | Mã / cách dùng |
|---|---|
| OT / tải hữu ích / bối cảnh | Navy `#1E3A8A` / Teal `#0D9488` / Slate `#64748B` |
| Warning / Critical | Amber `#D97706` / Crimson `#DC2626`; chỉ cho ngưỡng/trạng thái tương ứng |
| Dải 50% / 80% / 95% | Blue `#93C5FD`; alpha 0.28 / 0.20 / 0.14; vẽ dải rộng trước |
- Không cặp đỏ–xanh lá cạnh tranh; thêm dash/shape/nhãn, không truyền trạng thái chỉ bằng màu.
- WCAG AA: kiểm tra tương phản chữ thường ≥4.5:1; không mặc định mã màu đạt trên mọi nền.
- Direct labels khi khả thi; giữ legend nếu cần; kiểm tra grayscale, deuteranopia/protanopia.

# STANDARD COMMANDS & WORKFLOW

- Chạy PowerShell tại ROOT; kích hoạt môi trường trước; không tự cài package để sửa lỗi.
| Tác vụ | Lệnh | Trạng thái khi khảo sát |
|---|---|---|
| Kích hoạt | `. .\.venv\Scripts\Activate.ps1` | Có |
| Interpreter/deps | `python -V; python -m pip list` | Có |
| Feature branch | `git switch -c feature/<task-id>-<scope>` | Thay task-id bằng WBS đã xác minh |
| ETL | `python scripts/preprocess_ett.py --data ETTh1 --out data/processed/clean_ett.parquet` | CLI đích; script chưa có |
| Engine | `python scripts/run_statistical_engine.py --input data/processed/clean_ett.parquet --out output/artifacts` | CLI đề xuất mới; script chưa có |
| Dashboard | `python -m streamlit run app.py` | Entry point chưa có; AMBER |
| Tests | `python -m pytest tests/ -v --tb=short` | Chưa có test nguồn; no tests ≠ PASS |
- Trước khi chạy CLI đích: triển khai/xác minh `--help`, dependency đã duyệt, input và contract.
- Workflow: đọc task+nguồn → kiểm tra git/môi trường → báo kế hoạch → sửa tối thiểu → validate → báo kết quả.
- Đo <2s cho load/render/filter trên dữ liệu đại diện; ghi cấu hình, dataset, cold/warm cache riêng.
- Audit lưu dưới `audit/` khi có task; chưa có app/artifacts → ghi BLOCKED/N/A, không đánh dấu PASS.

# DEFINITION OF DONE (DOD) & CHECKLIST

- [ ] **1. Cú pháp / Types:** Code chạy/compile được, PEP 8, type hints, seed/constants đúng; visual rules đã đối chiếu.
- [ ] **2. Tests:** Unit + smoke PASS; bao phủ quantile nesting, STL reconstruction, lag sign/cadence, thermal gaps/boundaries.
- [ ] **3. Guardrails:** Diff thuộc task/feature branch; RED giữ nguyên; AMBER được xác nhận; không thêm dependency/lộ secrets.
- [ ] **4. Contracts:** Đúng tên, key, dtype, metadata, đơn vị; empty/null hợp lệ; UI chỉ đọc artifacts, không tính nặng.
- [ ] **5. SLA / Evidence:** Load/render/filter <2s có số đo; thiếu điều kiện nêu BLOCKED/N/A, không tuyên bố hoàn tất runtime.
- Task chỉ tài liệu: kiểm tra Markdown, 150–250 dòng, tham chiếu tồn tại/đích được gắn nhãn, diff và nhất quán v2.0.
- Kết thúc: tóm tắt file thay đổi, kiểm tra đã chạy, kết quả thực tế và giới hạn còn lại; không tự commit/push.