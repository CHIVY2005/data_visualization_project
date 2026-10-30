# 📄 Báo cáo thực thi & nghiệm thu: T0205 — Đồng bộ ETL & Artifacts ba dataset

- **Project:** ETT Power Grid Operational Management & Thermal Safety Visual Analytics Dashboard.
- **ID / Version:** `ETT_GRID_VIS_2026` / 2.0 — CPU-only statistical & visual analytics.
- **Task:** `T0205` — đồng bộ WP01 → WP02 cho ETTh1, ETTh2 và ETTm1.
- **Ngày lập báo cáo:** 2026-10-30 21:37 (UTC+07:00).
- **Branch:** `feat/T0205`, tạo từ HEAD `feat/T0204` theo xác nhận người dùng.
- **HEAD khi kiểm tra:** `8e78dfb`; triển khai T0204 đã commit, T0205 chưa commit.
- **Status:** **PASS** về full pipeline, artifact audit và regression hiện tại.
- **Giới hạn:** Atomicity từng file, không phải transaction toàn bộ artifacts.
- **Commit/push khi thực thi T0205 và lập báo cáo:** Không thực hiện.

**ROOT:** `F:\Study Materials\specialized_subject\Visualization\Visualization_gr\data_visualization_project`.

Tên module/artifact trong bảng được định vị theo thư mục chỉ rõ dưới ROOT.
Báo cáo phân biệt lần triển khai trước và lần kiểm tra lại khi soạn tài liệu.

---

## 1. 📊 EXECUTIVE SUMMARY & ACCEPTANCE MATRIX

T0205 tự động hóa ETL → features → statistical engine → kiểm toán provenance,
trên ba chuỗi độc lập, giữ dataset trong khóa và không resample chéo độ phân giải.
Giữ nguyên hợp đồng LOESS bảy cột của T0204 và ranh giới offline/UI.

| Deliverable / Requirement | Component | Status | Evidence |
|---|---|---|---|
| ETL snapshot ba dataset | `scripts/preprocess_ett.py` | PASS | `--data all`, validate từng chuỗi trước ghép |
| Full orchestration | `scripts/run_statistical_engine.py` | PASS | `--sync-all` đã chạy trên dữ liệu thật |
| Audit độc lập | Cùng engine, `--audit-only` | PASS | Audit bảy artifacts, schema/provenance/arithmetic |
| Clean / features coverage | `data/processed/` | PASS | 104.520 dòng mỗi bảng, 14/23 cột |
| Cadence ETTm1 | Lag, STL, thermal | PASS | Tests lag 4k mẫu, period 96, Δt=0,25h |
| Provenance raw/direct | `src/analysis/common.py` | PASS | Hash normalized raw, byte hashes và immediate lineage |
| LOESS T0204 | `output/artifacts/loess_curves.parquet` | PASS | Bảy cột, ba dataset, tọa độ hữu hạn |
| Full regression | Toàn suite | PASS | 219 tests; 0 failures/errors |
| RED preservation | Raw/charter/references | PASS trong phạm vi tác vụ | Hash raw khớp; diff RED hiện tại rỗng |

Không triển khai dự báo/training/GPU, không đổi UI, không cài dependency.
Đây là dashboard lịch sử, không phải hệ thống giám sát an toàn được chứng nhận.

## 2. 🛡️ PHẠM VI THAY ĐỔI & ĐIỀU PHỐI PIPELINE

### 2.1 Nhánh và bảo toàn nền T0204

Khi bắt đầu, thực tế workspace sạch trên `feat/T0204`, không phải nhánh fix.
Commit `8e78dfb` đã chứa T0204; nhánh fix vẫn ở `cf7639f`.
Người dùng chọn tạo `feat/T0205` từ HEAD T0204 để bảo toàn nền triển khai.
Không reset/stash hoặc đưa commit mới lên nhánh cộng sự/main.

| File dưới ROOT | Thay đổi T0205 |
|---|---|
| `src/data/constants.py` | Expected row counts và path audit mặc định |
| `scripts/preprocess_ett.py` | `run_multi_pipeline`, CLI `--data all`, snapshot ba dataset |
| `scripts/run_statistical_engine.py` | `run_all_datasets`, `audit_artifacts`, CLI sync/audit |
| `src/analysis/common.py` | Raw provenance, attach lineage, JSON round-trip equality |
| `src/analysis/thermal_risk.py` | Metadata coverage theo toàn input, kể cả dataset không có event |
| `tests/test_pipeline_t0205.py` | Chín test cases sau parametrization |
| `audit/t0205_artifacts_sync_audit.json` | Bằng chứng schema/hash/coverage/quality/validation |

`feature_builder.py`, `load_profiling.py` và `lag_correlation.py` đã được đối chiếu;
không sửa thuật toán đang đúng chỉ để tạo diff. Tests mới xác minh các quy tắc này.

### 2.2 Luồng chạy và CLI

Tại ROOT, kích hoạt môi trường trước mọi lệnh Python:

```powershell
. .\.venv\Scripts\Activate.ps1
python scripts/preprocess_ett.py --data all
python scripts/run_statistical_engine.py --sync-all
python scripts/run_statistical_engine.py --audit-only
```

Lệnh đầu chỉ ETL clean; `--sync-all` đã bao gồm ETL nên không bắt buộc chạy cả hai.
`--processed-dir`, `--out`, `--raw-dir`, `--audit` cho phép chỉ định đích rõ ràng.
`--sync-all` và `--audit-only` không được dùng đồng thời.
CLI engine cũ `--input ... --out ...` vẫn chạy thống kê từ clean/features sẵn có;
không tự tuyên bố lệnh cũ thực hiện full raw-lineage audit như chế độ sync mới.

ETL đọc từng CSV, kiểm tra schema/cadence/duplicate/missing riêng từng dataset.
Chỉ ghép sau khi tất cả snapshot hợp lệ; thay thế tệp, không append ngầm.
Giữ null và gap quan sát, không nội suy hoặc nối dữ liệu từ dataset khác.
Feature builder giữ cột dataset, kiểm tra khóa ghép và cadence theo từng nhóm.

## 3. 📦 ARTIFACT CONTRACTS & CADENCE

### 3.1 Inventory thực tế đã đối chiếu với audit

Clean/features nằm trong `data/processed/`; năm tệp còn lại dưới `output/artifacts/`.
Các giá trị bytes dưới đây bao gồm metadata lineage sau đồng bộ T0205.

| Artifact | Vai trò | Rows / records | Cột / root keys | Bytes |
|---|---|---:|---:|---:|
| `clean_ett.parquet` | Canonical clean | 104.520 | 14 | 2.968.841 |
| `grid_features.parquet` | Supplementary features | 104.520 | 23 | 4.022.446 |
| `load_profiles_stl.parquet` | Canonical STL/profile | 941.976 | 14 | 17.317.502 |
| `quantile_bands.parquet` | Canonical empirical bands | 1.296 | 13 | 53.038 |
| `lag_correlation_matrix.json` | Canonical lag envelope | 12 records | 6 root keys | 28.890 |
| `thermal_breach_events.parquet` | Canonical thermal events | 0 | 11 | 4.675 |
| `loess_curves.parquet` | Supplementary T0204 | 10.800 | 7 | 92.762 |

Không tạo alias cũ để thay thế tên canonical. Engine còn tái sinh
`event_load_zscores.parquet`; file này nằm ngoài inventory bảy artifacts T0205.

| Dataset | Cadence | Clean/features | STL/profile | Bands | Lag records | LOESS |
|---|---|---:|---:|---:|---:|---:|
| ETTh1 | 1h | 17.420 | 157.212 | 432 | 4 | 3.600 |
| ETTh2 | 1h | 17.420 | 157.212 | 432 | 4 | 3.600 |
| ETTm1 | 15m | 69.680 | 627.552 | 432 | 4 | 3.600 |

Tổng clean/features: **104.520**. Audit ghi gap_count = 0 cho cả ba dataset.
Raw audit không có duplicate hoặc missing measurement; không có mẫu nội suy.
Event rỗng hợp lệ, metadata vẫn nêu đủ ba dataset; không tạo sự kiện giả.
OT giữ °C; tải giữ giá trị/đơn vị nguồn, không tự gán MW/MVar.
Timestamp dữ liệu là `timestamp[ns]`, timezone unknown, không tự thêm `Z`.

### 3.2 Kiểm chứng bước thời gian và toán học

- Lag định nghĩa `corr(load(t), OT(t+k giờ))`, tải đi trước OT ở lag dương.
- Căn theo timestamp, không shift mù qua gap; ETTh là k mẫu, ETTm1 là 4k mẫu.
- Tests tổng hợp tạo đỉnh đúng 1h ở cả ba dataset và loại một timestamp để kiểm tra gap.
- STL daily period = 24 cho ETTh1/ETTh2 và 96 cho ETTm1.
- Audit kiểm tra metadata period, timestamp coverage và reconstruction trên hàng fit hợp lệ.
- Đẳng thức: `observed ≈ trend + seasonal + residual`, có dung sai số học float32.
- Thermal dùng hỗ trợ mẫu trái, Δt=1h hoặc 0,25h tùy dataset.
- Chỉ có support khi mẫu tiếp theo hữu hạn, cách đúng cadence; không kéo dài điểm cuối.
- Synthetic events xác minh duration và Degree-Hours cho cả 1h/15m.
- Điểm cô lập, trước gap hoặc cuối chuỗi không được tạo duration giả.
- Ngưỡng 85°C/95°C được tổng hợp riêng, không cộng hai tổng chồng lấn.
- Quantile canonical: `q025 ≤ q10 ≤ q25 ≤ q50 ≤ q75 ≤ q90 ≤ q975`.
- Không dùng nhãn q05/q95 sai schema; dải 95% là q025–q975, 80% là q10–q90.
- Đủ 24 bins theo dataset/variable/season; bin rỗng giữ thống kê null có ngữ cảnh.
- LOESS giữ bảy cột, 150 điểm/nhóm, finite coordinates và sample_count ≥10.

## 4. 🔗 PROVENANCE, ATOMIC WRITE & AUDIT EVIDENCE

Audit envelope sinh lúc `2026-10-30T14:34:08.012288+00:00`, status **PASS**.
Khi lập báo cáo, hash và byte size của toàn bộ bảy artifacts vẫn khớp envelope.

### 4.1 Quy tắc hash: không đánh đồng nguồn raw và input trung gian

| Trường / tầng | Ý nghĩa |
|---|---|
| Raw `sha256_bytes` | SHA-256 byte gốc để phát hiện thay đổi tệp |
| Raw `sha256_lf_normalized` | SHA-256 sau CRLF→LF, kiểm tra content-equivalence |
| Clean `source_hash` | Hash tổng hợp JSON sorted của mapping dataset→normalized raw hash |
| Features `source_hash` | SHA-256 byte của clean input cuối cùng |
| Statistical artifacts `source_hash` | SHA-256 byte của features input cuối cùng |
| Parquet `raw_source_hashes`, `raw_bundle_hash` | Raw ancestry rõ ràng, không thay immediate lineage |

Normalized raw SHA-256:

```text
ETTh1 f18de3ad269cef59bb07b5438d79bb3042d3be49bdeecf01c1cd6d29695ee066
ETTh2 a3dc2c597b9218c7ce1cd55eb77b283fd459a1d09d753063f944967dd6b9218b
ETTm1 6ce1759b1a18e3328421d5d75fadcb316c449fcd7cec32820c8dafda71986c9e
```

Raw bundle hash: `142bb790c971601d7ce569a2a8a6711ced54d13d70f2a8fb32114c72e955d22b`.
Raw byte hashes khác normalized hashes do CRLF; cả hai được lưu riêng, không phải lỗi.
Metadata được refresh sẽ đổi byte hash Parquet; pipeline cập nhật lại direct lineage
trước audit để tránh source_hash trỏ bản metadata cũ.

Lag JSON giữ đúng root contract: schema_version, timezone, generated_at, seed,
source_hash, records. Không tự thêm dataset/quality_audit/raw keys vào root.
Coverage, quality và raw ancestry của lag được lưu trong audit envelope.
Parquet có schema_version 2.0, seed 2026, generated_at UTC, parameters, quality_audit.

### 4.2 Nội dung audit và ranh giới đảm bảo

Audit ghi path, bytes, byte hash, rows, columns, dtypes, dataset_rows,
metadata/null counts cho Parquet và record coverage/matrix quality cho lag JSON.
Kiểm tra non-nullable, Inf, quantile nesting, keys, coverage và raw equivalence.
Nullable statistics được giữ theo contract; không xóa mọi null một cách mù quáng.
Audit fail khi ancestry sai; test cố ý sửa metadata fixture xác nhận fail-closed.

Mọi export dùng `.tmp` độc quyền, flush/fsync, round-trip verify rồi `os.replace`.
JSON round-trip so sánh nội dung, encoder từ chối NaN/Infinity.
Tests xác minh replace failure giữ file cũ và không xóa tmp do tiến trình khác sở hữu.
Atomicity chỉ **từng file**; lỗi giữa pipeline có thể để lại bộ artifacts khác phiên bản.
Không có transaction/rollback toàn bộ; cần `--audit-only` đạt PASS trước bàn giao.

## 5. 🧪 TESTING, GUARDRAILS & KẾT QUẢ KIỂM TRA LẠI

- Lệnh: `python -m pytest -q --tb=short`, sau khi kích hoạt `.venv`.
- Lần triển khai lưu trong audit: **219 passed, 8 warnings, 55,55s**.
- Lần chạy lại khi lập báo cáo: **219 passed, 8 warnings, 58,99s**.
- **Failures = 0; Errors = 0**; hai thời lượng là hai lần chạy độc lập.
- Compileall và `git diff --check` đã PASS trong đợt triển khai.
- Chín test cases T0205 bao phủ artifacts, multi-dataset synthetic pipeline,
  lag sign/cadence/gap, STL, thermal support, raw equivalence và atomic JSON failure.
- Các tests T0204 vẫn PASS; không xóa hoặc nới schema LOESS để vượt regression.

Tám cảnh báo pytest là deprecation Pandas/Seaborn/Matplotlib, không phải failure.
Engine thực còn cảnh báo số học LOWESS như T0204; artifact được kiểm tra hữu hạn.
Không đo lại AppTest/browser SLA trong T0205 hoặc khi viết báo cáo này.
Không sửa `app.py`, `requirements.txt`, không cài/nâng package, không tính nặng trong UI.
Raw byte hashes và normalized hashes được xác minh lại; diff RED hiện tại rỗng.
Working tree chưa sạch do code/artifacts T0205; không tự commit/push để làm sạch.

## 6. 🏁 DOD, GIỚI HẠN & HÀNH ĐỘNG TIẾP THEO

- [x] Full ETL/features/engine thực thi cho ba dataset, số dòng/cadence đúng.
- [x] Bảy artifacts được kiểm toán; schema LOESS T0204 bảo toàn.
- [x] Provenance direct/raw rõ ràng, không đổi contract root JSON lag.
- [x] Audit JSON hiện diện; SHA-256 artifacts/raw đối chiếu lại thành công.
- [x] Toàn suite 219/219 PASS, RED zone không bị tác động.
- [ ] Review và commit T0205: chưa thực hiện, theo chỉ dẫn không tự commit.
- [ ] SLA browser/end-to-end: thuộc T0504; không đánh dấu PASS từ regression.

**Audit:** `F:\Study Materials\specialized_subject\Visualization\Visualization_gr\data_visualization_project\audit\t0205_artifacts_sync_audit.json`.
**Tests:** `F:\Study Materials\specialized_subject\Visualization\Visualization_gr\data_visualization_project\tests\test_pipeline_t0205.py`.

Tiếp theo: review diff dữ liệu/metadata T0205, dùng artifacts đã kiểm toán cho T0304,
và benchmark cold/warm/filter trên trình duyệt trong T0504. Không bịa breach để demo.