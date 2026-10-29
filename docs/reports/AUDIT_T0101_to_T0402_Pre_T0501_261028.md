# KIỂM TOÁN NGHIỆM THU T0101–T0402 / PRE-T0501

- **Project:** ETT_GRID_VIS_2026 v2.0 · **Audit date:** 2026-10-28 (UTC+07:00).
- **Decision:** **NO-GO cho nghiệm thu/release T0501**; có thể bắt đầu hotfix có kiểm soát sau phê duyệt AMBER.
- **Baseline:** `origin/main@23405f5`; contract nguồn: AGENTS.md trên main, không phải tên kế hoạch cũ trong Charter.
- **Isolation:** Nhánh `audit/pre-T0501-integration-check`, audit merge HEAD `9cf7d61`.
- **Method:** Fetch all/prune → topology/diff → trial merges → static contract/UI audit → pytest → runtime probes.
- **Scope note:** Danh sách yêu cầu có **11 task**, không phải 10: 3 WP01 + 3 WP02 + 3 WP03 + 2 WP04.
- **Evidence:** `C:\Users\duy62\AppData\Local\Temp\ETT-pre-T0501-audit-20261028-215556`.
- **Worktree:** `C:\Users\duy62\AppData\Local\Temp\ETT-pre-T0501-audit-20261028-215556\worktree`.
- Không push, reset hoặc sửa lịch sử main/sáu nhánh gốc; chỉ tạo merge commits thử trên nhánh audit.

## 1. Phạm vi refs và bảng nghiệm thu task

| Alias | Nhánh remote đã fetch | SHA đầu nhánh |
|---|---|---|
| B1 | feat/T0101_download-ett-dataset | 70f8217 |
| B2 | feat/T0102_feature-engineering-v2 | 1f504af |
| B3 | feat/T0103-deep-eda | fa46f22 |
| B4 | feat/T0201_T0202_T0203 | 3ec0807 |
| B5 | feat/T0301_T0302_T0303-story1-operational-dashboard | 4344905 |
| B6 | feat/T0401_T0402-story2-safety-risk-dashboard | d0c1100 |

Các B1→B4 kế thừa tuần tự; B5/B6 cùng kế thừa base Story 1 `b0a3f2c` nhưng có refactor song song.
Không diễn giải số lượng commit trong diff tích lũy là số lượng công việc riêng của từng thành viên.

| Task | Branch | Artifacts / implementation thực có | Test / evidence | Đánh giá |
|---|---|---|---|---|
| T0101 | B1 | Clean 17.420×14; preprocessing CLI | 37 PASS | PASS trong phạm vi ETTh1. |
| T0102 | B2 | Grid features 17.420×23; feature_builder | 47 PASS | PASS; shares null đúng policy. |
| T0103 | B3 | Notebook 18 cells; output/figures/missing_matrix.png | Outputs lưu: 0 error; audit trước có run-all | WARN: đường dẫn hình đã chuyển, notebook hardcode kernel tại ROOT/.venv. |
| T0201 | B4 | Hàm STL/profile; CLI chỉ export hourly_quantiles | 2 PASS trong suite engine | FAIL: thiếu export STL và tên quantile không theo AGENTS. |
| T0202 | B4 | lag_matrix Parquet; helper records matrix | 2 PASS; probe ETTm1 lag 2h đạt | FAIL contract JSON envelope/tên chuẩn, không phải lỗi dấu lag đã xác minh. |
| T0203 | B4 | breach_events 18 cột gồm center/Z-score | 3 PASS; counterexample last-point sai | FAIL: thời lượng mẫu cuối giả định và schema lệch. |
| T0301 | B5 | Calendar chart function | Story 1 tests dùng fixture | FAIL deliverable wireframe chưa tìm thấy; chart không thay wireframe. |
| T0302 | B5 | STL panels + quantile fan chart functions | Figure smoke fan đạt; STL fixture tests đạt | FAIL E2E: producer CLI không cấp STL. |
| T0303 | B5 | Stacked bar + lag heatmap + KPIs | 2 tests FAIL trong Story 1 | FAIL: negative loads bị clip, empty/KPI policy chưa đúng. |
| T0401 | B6 | OT threshold + barcode functions | Story 2 tests PASS; smoke empty events đạt | WARN: gap/null có thể bị nối bởi line sau dropna, chưa có browser visual audit. |
| T0402 | B6 | Small multiples, scatter/LOESS, boxplots, KPIs | Story 2 tests PASS; counterexamples KPI | FAIL: UI tính LOESS, thermal KPI cộng chồng, shared zoom chỉ trong figure. |

PASS module không đồng nghĩa mọi dataset/edge case đã đủ DoD; hiện clean/features sản xuất chỉ có ETTh1.
Không có WP02 artifacts được tracking trong bất kỳ B1..B6; cần generate/verify khi triển khai, không nhất thiết phải commit binary.

## 2. Git topology, trial merges và guardrails

Trial merges thực hiện trên worktree audit, theo B1→B2→B3→B4→B5→B6.
B1..B5 merge không conflict; lần đầu B6 xung đột tại đúng hai tệp:

| File | Nguyên nhân | Hành động kiểm toán |
|---|---|---|
| app.py | B5 refactor Story 1 và B6 tích hợp Story 2 cùng sửa entry point từ base chung | Lưu log, abort lần lỗi; retry chọn bản B6 để chạy thử. |
| src/visuals/__init__.py | Hai nhánh tổ chức lại exports chung | Chọn bản B6 chứa cả hai nhóm exports trong audit merge. |

Lựa chọn trên **chỉ phục vụ mô phỏng**, không phê duyệt logic B6 hoặc giải quyết release trên nhánh gốc.
`src/visuals/charts_manager.py`, `app_manager.py`, `tests/test_visuals_story1.py` giống nhau ở B5/B6.
Do đó hai lỗi Story 1 không được quy thành lỗi do lựa chọn conflict resolution ở audit.

**RED:** `git diff merge-base(origin/main,branch)..branch` cho raw/charter/references rỗng ở cả sáu refs.
Baseline raw/charter/references/clean ở workspace gốc được hash để xác minh bất biến cuối audit.
Không kết luận mọi commit lịch sử trước main tuân RED: main đã chứa các cập nhật Charter được duyệt từ phiên trước.

**AMBER:** B3 thêm statsmodels==0.15.0 và missingno==0.5.2; có xác nhận người dùng trong lịch sử hội thoại.
B4..B6 kế thừa thay đổi đó, không phải ba lượt cài tự ý độc lập. Audit không cài/nâng package.
B5/B6 thêm app.py từ công việc Story UI; không thấy bằng chứng xác nhận AMBER tạo entry point trong nguồn đã khảo sát.
Ghi **approval evidence missing**, không khẳng định một người cụ thể tự ý sửa khi chưa đủ bằng chứng ngoài repo.

**SCOPE:** Mã src/tests hợp nhất không còn import Torch hoặc tensor dataloader; main baseline vẫn có consumer legacy.
requirements vẫn khai báo torch>=2.0.0; scripts/download_dataset.py còn mô tả/log/User-Agent tên Informer benchmark.
Đây là scope/dependency drift còn tồn tại, không chứng minh engine hiện tại đang training/GPU.

## 3. Ma trận producer → consumer / contracts

| Giao diện | Producer thực tế | Consumer thực tế | Khớp / lệch với AGENTS |
|---|---|---|---|
| WP01 clean | clean_ett.parquet, 14 cột | feature_builder và common.load_feature_input | Khớp dataset/timestamp/f32/nullable ratio; không normalize OT. |
| WP01 features | grid_features.parquet, 23 cột | WP02 nhận cả clean hoặc features, gọi build_grid_features | Khớp season/hour; Dry/Wet là month bins có metadata, không khẳng định khí hậu. |
| STL/profile | build_load_profiles_stl có bảng 14 cột long-form | charts_manager.build_stl_panels cần timestamp/observed/trend/seasonal/residual | Hàm tồn tại, nhưng run_engine/export_load_profiling không gọi lưu bảng này. |
| Quantiles | hourly_quantiles.parquet, 13 cột | app loader và fan dùng cùng tên/cột | Khớp nhau nhưng sai tên chuẩn quantile_bands.parquet; Q2.5/Q97.5 cho 95% đúng. |
| Lag | lag_matrix.parquet, 9 cột long-form | app_manager.build_lag_heatmap cần load_variable/lag_hour/correlation | Khớp producer hiện tại, lệch chuẩn lag_correlation_matrix.json envelope 6×13. |
| Thermal | breach_events.parquet, 18 cột | charts_safety/app_safety dùng threshold/start/end/duration/degree_hours | Core columns khớp; tên chuẩn thermal_breach_events.parquet và 11 cột bị lệch. |
| Z-score | Six extra columns + event_center_timestamp trong breach artifact | Chưa có contract consumer riêng được thống nhất | Không tự thêm 7 cột vào fixed event contract; cần artifact bổ sung/version decision. |
| LOESS | Không có producer/artifact LOESS đã xuất | build_scatter_loess nhận loess_df hoặc tính lowess fallback | Thiếu producer/schema và vi phạm decoupling khi fallback. |

### CLI engine smoke trên dữ liệu thật (chỉ output trong audit Temp)

`python scripts/run_statistical_engine.py --input <audit-worktree>/data/processed/grid_features.parquet --out <evidence>/engine-artifacts`

- Exit code 0; hourly_quantiles: **432×13**, 21.600 bytes; lag_matrix: **312×9**, 7.645 bytes.
- breach_events: **0×18**, 4.732 bytes; ETTh1 thực không breach, bảng rỗng là kết quả đúng, không giả dữ liệu.
- Không sinh load_profiles_stl.parquet, quantile_bands.parquet, thermal_breach_events.parquet hoặc lag_correlation_matrix.json.
- Float metrics Arrow float32, integer count/hour int32, timestamps ns; các schema hiện tại nội bộ round-trip được.
- Metadata có schema_version/source hash/seed/generated_at/timezone/parameters; quantile min sample chưa thành policy rõ.
- JSON helper ghi chuẩn có sẵn trong common, nhưng lag CLI không dùng helper đó để xuất envelope AGENTS.
- Quy tắc `corr(load(t), OT(t+k giờ))` căn timestamp đúng; probe ETTm1 trễ 8 mẫu đạt peak 2 giờ.

## 4. Semantic counterexamples — lỗi không được suite hiện tại bắt

| Severity | Reproduction / file location | Kết quả và tác động |
|---|---|---|
| P0 | thermal_risk.py:144–157; input duy nhất OT=96 tại t0 | Sinh 2 events duration=1h, end=t0+1h dù hỗ trợ mẫu cuối chưa biết; AGENTS cấm event thời lượng giả cho điểm cô lập. |
| P0 | app_safety.py:588–591; OT=[96,100,80] | Events 85°C=26°C·h, 95°C=6°C·h; KPI cộng thành 32, double-count hai ngưỡng thay vì báo riêng. |
| P0 | app.py:79–120; load_features(pathA,1), load_features(pathB,2) | Kết quả marker 1 rồi 1, expected second=2; `_path` và `_mtime` đều bị Streamlit loại khỏi cache key. |
| P0 | app_safety.py:207–222,351–357; app.py:565 gọi không loess_df | LOWESS thực sự chạy trong render path; fallback binned mean cũng không phải artifact tiền tính. |
| P1 | app_manager.py:67–74; HUFL=-5, HULL=10 | clip(lower=0) tạo tỷ trọng 0/100% thay null/cảnh báo; vi phạm preserve physical values/composition policy. |
| P1 | app_manager.py:359–362; frame rỗng | ot_mean=0, ot_max=0, warn_pct=0; thiếu dữ liệu thành số liệu giả, không Unknown/null. |
| P1 | app.py:106 so với 130,231–235 | load_stl nhận thư mục artifacts rồi lấy parent; đọc output/load_profiles_stl.parquet thay vì output/artifacts/load_profiles_stl.parquet. |
| P1 | app.py:444–459 | Features lọc season nhưng events chỉ lọc dataset; KPI/shading có thể không cùng phạm vi. Date Range chưa có. |
| P1 | app_safety.build_small_multiples / charts_safety.build_ot_threshold_chart | dropna rồi nối line, không chèn break theo gap; shared_xaxes chỉ trong sáu subplots, không tự đồng bộ figure OT riêng. |

Thermal gap/missing cũng đóng event nhưng mọi sample vẫn được nhân full cadence; cần kiểm thử support interval, không chỉ censored flag.
Z-score hiện dataset-level tại event center (metadata có nói), khác window-local diagnosis; không gọi là chứng minh thủ phạm.

## 5. UI decoupling, integration API và visual QA

- src/visuals/app_manager.py và app_safety.py là **chart/KPI libraries**, không có render_manager_dashboard/render_safety_dashboard.
- render_story1/render_story2 nằm trong root app.py; st.set_page_config chỉ xuất hiện một lần tại root, không có duplicate ở hai module.
- Vấn đề thực là ownership/shared entry point và conflict, không phải giả định cả hai module gọi set_page_config.
- Shared filters hiện dataset/season/variable; dataset options hardcode ba IDs dù artifacts chỉ ETTh1; chưa có Date Range contract.
- UI có đọc Parquet, nhưng calendar tính quantiles 1%/99% và groupby; stacked tính hourly fractions trên render path.
- Các phép aggregation này cần được phân loại/light-budget hoặc tiền tính theo strict policy; LOESS chắc chắn phải chuyển offline.
- Calendar OT palette tô crimson theo percentile-relative scale, nên OT thấp hơn 85 vẫn có thể mang màu Critical; cần absolute threshold semantics.
- Lag heatmap dùng crimson cho hệ số âm, trái quy ước crimson chỉ Critical; đổi diverging palette không gắn cảnh báo nhiệt.
- Có navy/teal/slate, grid #E2E8F0 và fan bands 50/80/95 alpha 0.28/0.20/0.14, wide-before-narrow: điểm tích cực.
- Nhiều title chỉ là nhãn chart (“Lag Cross-Correlation Heatmap”, “Joint Scatter & LOESS”), chưa phải insight theo filter có bằng chứng.
- Không tìm thấy file wireframe/T0301 độc lập trong refs; Charter là yêu cầu, không phải bản wireframe đã bàn giao.
- Chưa audit WCAG contrast/grayscale/colorblind bằng ảnh browser; test Figure properties không chứng nhận accessibility.

## 6. Automated tests, smoke và performance evidence

| Module | PASS | FAIL | ERROR / SKIP |
|---|---:|---:|---|
| test_preprocess | 37 | 0 | 0 / 0 |
| test_feature_builder | 47 | 0 | 0 / 0 |
| test_statistical_engine | 7 | 0 | 0 / 0 |
| test_visuals_story1 | 29 | 2 | 0 / 0 |
| test_visuals_story2 | 15 | 0 | 0 / 0 |
| **Total** | **135** | **2** | **0 / 0** |

Lệnh trong worktree audit dùng interpreter `.venv` workspace gốc: `python -m pytest tests/ -v --tb=short -p no:cacheprovider`.
Kết quả terminal: **29,78 giây**, 137 tests; thêm JUnit trong evidence, không thêm tests/probe vào nhánh gốc.
Failures: TestT0303StackedBar.test_raises_on_empty_after_filter; TestT0303LagHeatmap.test_colorscale_diverges_around_zero.
Lỗi thứ hai là thiếu property zmid=0 dù zmin/zmax đã đối xứng; phân biệt assertion/API issue với số liệu correlation sai.

Figure construct+serialize smoke 9 chart types chạy không ImportError/KeyError/FileNotFoundError, 0,01–0,45s/chart trên ETTh1.
STL chỉ được kiểm tra qua fixture test, không thể smoke chart STL từ artifact CLI không tồn tại.
AppTest “as merged” không exception/error, nhưng cảnh báo thiếu ba WP02 artifacts; cold ≈3,72s, không đạt bằng chứng SLA.
Sau copy ba artifacts sinh thử **chỉ vào audit worktree**, Story1 cold≈2,42s, warm≈0,67s; vẫn thiếu STL.
Story2 selection≈0,82s, không exception/error; có warning API use_column_width/use_container_width trên Streamlit hiện cài.
Một probe selector ban đầu lỗi do encoding chuỗi trong shell; đã chạy lại bằng widget option thực, không quy lỗi đó cho app.
Đây là AppTest/server timing một máy, không phải browser paint/filter benchmark hay chứng nhận SLA đầy đủ cho ba dataset.

## 7. Go/No-Go checklist và kế hoạch mở khóa T0501

**Quyết định NO-GO cho merge/release tích hợp hiện tại.** Có thể triển khai hotfix rồi lặp lại audit theo thứ tự:

- [ ] **B / P0:** Sửa thermal support intervals; mẫu cuối cô lập không tạo duration giả; tests hourly/15m/gap/null/censoring.
- [ ] **B / P0:** Chốt contract canonical AGENTS cho quantile/lag/events; producer/consumer/tests đổi cùng commit hoặc migration có duyệt.
- [ ] **B / P0:** Xuất load_profiles_stl.parquet từ engine CLI, metadata period/robust; thêm smoke E2E reconstruction và artifact availability.
- [ ] **B+D / P0:** Chốt schema LOESS/Z-score riêng, tiền tính outside UI; bỏ lowess/binned fallback trong chart render.
- [ ] **C+D / P0:** Cache args có hash path/source-version/mtime thực; thêm test đổi path/mtime và source version.
- [ ] **D / P0:** KPI duration/Degree-Hours theo threshold riêng, không cộng chồng; missing artifact khác empty no-event hợp lệ.
- [ ] **C / P1:** Không clip negative loads; fix empty-filter contract, null KPIs, zmid test và palette semantic.
- [ ] **C+D / P1:** Shared date/dataset/season scope cho features/events/profiles; thống nhất selection xuyên figure và gap visibility.
- [ ] **E / P1:** Bàn giao wireframe What–Why–How; thống nhất ownership app.py và review conflict resolution B5/B6.
- [ ] **E / AMBER:** Xác nhận tạo/sửa app.py và manifest; dọn Torch/deep-learning wording theo task được duyệt, không tự gỡ package.
- [ ] **QA:** Full pytest 0 failures + edge probes được đưa thành regression; cold/warm/filter benchmark đủ dataset, có browser visual QA.

### Khung app.py đề xuất — kế hoạch, chưa triển khai trong audit

1. Một composition root gọi st.set_page_config đúng một chỗ, không side effects cấu hình khi import chart libraries.
2. Artifact registry canonical + validators/version/source-hash và status missing/empty/invalid riêng, loaders cache theo nguồn thực.
3. Shared FilterState(dataset, season, start, end, threshold, variable), dataset options lấy từ artifacts thay hardcode availability.
4. Hai renderer nhận cùng filtered artifact bundle, không tự ETL/STL/quantiles/lag/LOESS hoặc tính risk nặng.
5. Offline engine chạy trước, schema nhất quán; UI dựng Plotly và slice nhẹ, null/Unknown hiển thị trung thực.
6. Test entrypoint + selection sync + cache invalidation; đo cold/warm <2s trên dữ liệu đại diện, không dùng “docstring SLA” làm bằng chứng.

## 8. Evidence, reproducibility và giới hạn kiểm toán

Evidence files: topology.json, refs-before.txt, baseline.json, pytest-merged.xml/.txt, test-groups.json,
engine-smoke.txt, engine-artifacts/, runtime-probes.json, apptest-with-generated.json, apptest-story2.json.
Sáu refs remote được pin SHA ở §1; main và branch heads gốc phải giữ nguyên trong lần xác minh cuối.
Audit source snapshot chứa merge commits thử; generated WP02 files chỉ ở Temp/audit worktree, không sinh vào workspace gốc.
Báo cáo được lưu trong workspace người dùng và copy vào audit worktree để thuận tiện xem xét; chưa commit báo cáo/push nhánh audit.
Không chạy lại notebook T0103 trong worktree khác vì notebook yêu cầu kernel ROOT/.venv cố định; kiểm tra outputs/metadata đã lưu, không báo run-all mới.
Không xác minh approval ngoài repo/hội thoại, provenance raw từ Internet hoặc tiêu chuẩn an toàn kỹ thuật bên ngoài.
**Acceptance summary:** WP01 nền tảng dùng được; WP02/UI có blockers semantics/contracts/cache; T0501 cần hotfix và phê duyệt trước release.