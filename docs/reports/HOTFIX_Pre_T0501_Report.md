# HOTFIX PRE-T0501 — Báo cáo nghiệm thu P0/P1

- **Project:** ETT_GRID_VIS_2026 v2.0; CPU-only visual/statistical analytics.
- **Date:** 2026-10-28 22:38 (UTC+07:00).
- **Branch:** `feat/T0501-pre-integration-hotfix` từ audit merge `9cf7d61` của sáu nhánh.
- **AMBER:** Người dùng xác nhận sửa app.py, exports, requirements và downloader wording.
- **Status:** **PASS cho hotfix regression và AppTest warm/filter trên dữ liệu thật**.
- **Release scope:** Nền tảng sẵn sàng cho T0501; không tự chứng nhận browser accessibility, production reliability hoặc an toàn thiết bị.
- **Working changes:** Chưa commit/push; sáu nhánh gốc và main không bị sửa ref trong tác vụ này.
- **Evidence:** `C:\Users\duy62\AppData\Local\Temp\ETT-T0501-hotfix-20261028-221501`.

## 1. Executive summary & acceptance

| Gate | Kết quả | Bằng chứng |
|---|---|---|
| Full pytest | **150/150 PASS**, 0 failures/errors/skips | tests.xml; 24,50s terminal, 24,435s JUnit. |
| AppTest | **115 lượt**, không exception/error | apptest.json; ba dataset, hai Story, chín view, All/Dry/Wet, date/dataset/view filters. |
| Warm/filter SLA | **max 0,9429s <2s** | Các lượt sau cold, trên .venv local. |
| Cold start | **1,9013s** lần đo cuối | Các lần đo trước có 2,12–2,40s; cold chưa có bảo đảm đa cấu hình. |
| Data completeness | **104.520 dòng**, ba dataset | ETTh1 17.420; ETTh2 17.420; ETTm1 69.680. |
| RED preservation | **PASS** | Raw/charter/references hashes không đổi; git status vùng RED sạch. |
| Canonical artifacts | **PASS** | STL/profile, quantile, lag JSON, event 11 cols; metadata/version/source hash. |

Thay đổi quan trọng: không còn thiếu STL, không còn LOESS tính trong render,
không tạo duration giả cho mẫu cuối, không cộng chồng thermal threshold metrics,
cache phân biệt path/version và negative composition không bị clip.
Hai lỗi test Story 1 trong audit đã được khắc phục bằng logic/fixture đúng scope.

## 2. Data pipeline & hợp đồng

### 2.1 Chuẩn bị ba dataset

Script `scripts/prepare_all_datasets.py` gọi T0101/T0102 riêng từng dataset.
Đầu ra riêng: `data/processed/datasets/<dataset>/clean_ett.parquet` và `grid_features.parquet`.
Sau đó ghép các bảng theo dataset key, **không resample hoặc trộn độ phân giải**.
Clean canonical giữ 14 cột, features giữ 23 cột; timestamp duy nhất trong dataset.
Artifact clean/features cũ đã được sao lưu trước thay thế; scaler lịch sử không thay đổi.
Metadata clean tổng hợp lưu source hashes từng CSV và merge policy; generated_at UTC,
timestamp nguồn vẫn timezone unknown, không thêm Z vào quan sát.

### 2.2 Engine artifacts đã sinh

| Artifact trong output/artifacts | Rows | Schema / kích thước |
|---|---:|---|
| load_profiles_stl.parquet | 941.976 | 14 cột, stl + profile; 17.315.769 bytes. |
| quantile_bands.parquet | 1.296 | 13 cột; 51.977 bytes. |
| lag_correlation_matrix.json | 12 records | Envelope canonical, matrices/counts 6×13; 28.890 bytes. |
| thermal_breach_events.parquet | 0 | 11 cột đúng dtype; 3.614 bytes. |
| lag_matrix.parquet | 936 | Optional long-form view đồng bộ cùng producer cho UI; 14.641 bytes. |
| loess_curves.parquet | 10.800 | Diagnostic schema riêng 8 cột; 81.290 bytes. |
| event_load_zscores.parquet | 0 | Diagnostic schema riêng 4 cột; 2.316 bytes. |

Không sinh alias hourly_quantiles/breach_events lệch contract mới.
Lag JSON có đúng root schema_version/timezone/generated_at/seed/source_hash/records.
Parquet lag là view bổ sung có version/source hash, không thay canonical JSON.
Quantile 95% dùng Q2.5–Q97.5; 80% Q10–Q90; IQR Q25–Q75.
STL daily period 24/96, robust=True; seasonal/trend/low_pass_jump=3 để giảm offline runtime.
Các tham số jump ghi metadata; max reconstruction absolute error thực tế ≈7,63e-6.
Đây là kiểm tra reconstruction, không phải chứng minh trend/residual model tối ưu.
Ba dữ liệu thật đều không breach ≥85°C; bảng events rỗng là đúng, không tăng nhiệt giả để demo.

### 2.3 Thermal support interval

- Chỉ tính hỗ trợ trái khi mẫu tiếp theo hữu hạn OT và cách đúng cadence.
- Mẫu cuối cô lập, trước gap hoặc trước missing không tự được 1h/0,25h.
- Candidate event không có support dương không được export như event duration=0 giả.
- Event có support rồi kết thúc chưa biết được đánh dấu right-censored; end là biên support cuối.
- Degree-Hours tính trên support samples, ngưỡng 85/95°C tổng hợp riêng.
- Event contract 11 cột không nhét thêm center/Z-score; diagnostics chuyển artifact riêng.
- Tests gồm hourly/15m, tail, isolated, gap/missing và double-count counterexamples.

### 2.4 Offline diagnostics mới

LOESS schema: dataset, season, load_variable, load_value, loess_ot, sample_count,
start_timestamp, end_timestamp; season gồm All/Dry/Wet.
Fit deterministic tối đa 1.000 điểm đại diện, frac=0.3; lưu tối đa 200 curve points mỗi nhánh/scope.
Curves là **saved historical reference**, không phải fit lại cho Date Range tùy ý.
Z-score schema: dataset, event_id, load_variable, z_score.
Z-score là event mean so với dataset mean/std(ddof=1), constant/insufficient → null;
không gọi là score nhân quả hoặc chứng minh thủ phạm.
Không có null trong LOESS artifact hiện tại; engine có warning LOWESS divide ở một số bước fit,
nhưng curve values cuối được kiểm tra hữu hạn. Cần giữ warning trong evidence, không coi là lỗi UI.

## 3. Hotfix UI & shared filter contract

### Story 1

- Stacked chart: bỏ clip(lower=0); tier-sample âm/null/mẫu số≤0 bị loại khỏi ratio.
- Chart ghi annotation số invalid tier-samples; không bịa tỷ lệ 0/100% từ tải âm.
- Empty-after-season-filter phát ValueError rõ; fixture title Wet giờ có hàng Wet thực.
- Lag heatmap zmid=0; palette brown/orange–white–navy, không dùng Crimson thermal cho correlation âm.
- OT Calendar scale tuyệt đối, warning từ 85°C, critical từ 95°C; không tô critical theo percentile-relative scale.
- Empty OT KPIs mean/max/warn_pct → NaN hiển thị N/A; denominator warning là số OT hợp lệ.

### Story 2

- Không import/gọi lowess trong visuals; thiếu offline curve chỉ hiện chú thích unavailable.
- KPI warning/critical Degree-Hours và duration_hours riêng, không có total chồng hai ngưỡng.
- Missing artifact → N/A, khác với bảng events hợp lệ rỗng → 0 events.
- Lines giữ missing/NaN và chèn break tại gap; downsampling thực hiện trong segment.
- Null reactive_ratio hợp lệ không bị coi là gap vật lý; lỗi hiệu năng segment explosion đã được sửa.
- Shared axes trong small multiples giữ như cũ; chưa tuyên bố cross-figure browser zoom synchronization hoàn chỉnh.

### app.py foundation

- Một composition root và một set_page_config trong main(), không cấu hình khi import tests.
- Cache loader args `path`, `mtime` không có underscore; version=(mtime_ns,size).
- Cache regression đổi path và version xác nhận không trả dữ liệu cũ.
- STL loader đọc đúng file output/artifacts/load_profiles_stl.parquet, không parent dư.
- Dataset options lấy từ features thực; cả ba lựa chọn đều có dữ liệu.
- View selector chỉ render view đang chọn, không eager build mọi tab ẩn.
- FilterState dùng khoảng [start,end) và dataset/season thống nhất cho observations và STL.
- Events chỉ lấy **complete events toàn bộ support trong scope**; không prorate Degree-Hours.
- Boundary-crossing events bị loại có caption rõ; muốn metric clip chính xác cần offline window-specific integration.
- Fan/lag/LOESS vẫn là lịch sử theo dataset/season, có caption **not recomputed for Date Range**.
- Không thể lấy quantiles/VIF/lag/LOESS của cửa sổ tùy ý từ aggregate full-history mà không tính lại;
  vì vậy không tuyên bố historical references là window-conditioned statistics.

## 4. Kiểm chứng thực thi

Lệnh đã chạy trong .venv:

```powershell
python scripts/prepare_all_datasets.py
python scripts/run_statistical_engine.py --input data/processed/grid_features.parquet --out output/artifacts
python -m pytest tests/ -v --tb=short
python -m pip check
```

Tests có thêm counterexamples trong tests/test_preintegration_hotfix.py.
Bao phủ cache invalidation, canonical schemas/JSON, thermal support, shared profiles/events filters,
negative ratios, null KPIs, calendar absolute colors, no UI lowess và diagnostic/STL export.
T0101 production regression vẫn dùng artifact riêng ETTh1, không bỏ kiểm tra 17.420 mẫu/raw equivalence.
Feature production test kiểm tra combined counts cả ba dataset, tổng 104.520 mẫu.
Legacy downsampling fixture được sửa timestamp tăng thực, không nhân bản cùng key để đo hiệu năng.
Legacy LOESS expectation đổi thành không compute khi thiếu artifact, có test precomputed curve riêng.

**AppTest:** 115 lượt gồm cold, dataset switch, view switch, 81 season/view combinations và ba date filters.
Warm/filter maximum 0,9429s; 0 exceptions và 0 st.error trong tất cả lượt.
Cold cuối 1,9013s; các lượt đo trước hơn 2s được ghi rõ, không chọn warm để thay cold.
Đây là server/AppTest timing trên máy local, chưa đo browser paint/network/mobile hoặc p95 đa phiên.
Runtime warning “missing ScriptRunContext” từ test harness không phải app exception.
Không có package cài/gỡ/nâng; pip check không broken requirements.

## 5. Guardrails, thay đổi và tồn tại

- requirements bỏ torch>=2.0.0 và sửa heading statistical CPU-only theo phê duyệt; không uninstall Torch cục bộ.
- Downloader bỏ wording/User-Agent legacy; không chạy downloader hoặc ghi raw.
- RED raw/charter/references và tài liệu đã có giữ nguyên hash; audit report chưa tracked được giữ nguyên.
- Scripts/src/tests/app thay đổi trong nhánh hotfix; không reset refs các nhánh thành viên/main.
- Raw không staged; artifact clean/features thay đổi có chủ đích theo yêu cầu completeness, backup ngoài Git.
- Producer hỗ trợ clean canonical và derived feature interface; source hashes mới gắn dữ liệu tổng hợp.
- Figures/wireframe/accessibility chưa được sửa hoặc nghiệm thu mới trong hotfix kỹ thuật này.
- T0501 còn cần browser visual QA, tương tác selection xuyên figure, và quyết định biểu diễn event bị cắt cửa sổ.
- Nếu yêu cầu **mọi chart** phản ánh exact Date Range (gồm quantile/lag/LOESS), cần bổ sung artifacts theo window;
  foundation hiện tại trung thực phân biệt windowed observations với historical reference, chưa đáp ứng yêu cầu mở rộng đó.
- Cold-start SLA mọi cấu hình vẫn chưa bảo đảm; warm/filter đạt trên phép đo đã nêu.
- STL chạy offline mất nhiều phút với ba dataset; không bao giờ đưa vào render path để “tiện cập nhật”.

Evidence ngoài Git: tests.xml, apptest.json, app-smoke-log.txt, acceptance.json,
baseline.json, processed-backup/ và app_smoke.py; Temp không phải lưu trữ release bền vững.
**Decision:** GO cho nền tảng hotfix/T0501 tiếp tục phát triển có kiểm soát;
**không** tuyên bố GO cho release cuối, certified safety, exact-window historical aggregates hoặc browser accessibility.