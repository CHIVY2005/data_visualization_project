# AGENTS.md — Quy chuẩn Quản trị Dự án & Hiến pháp Thực thi cho AI Agent (Codex)

> **Dự án:** Long-Sequence Time-Series Forecasting (LSTF) with Informer & Power Grid Operational Dashboard  
> **Mã dự án:** `LSTF_INFORMER_VIS_2026` | **Trạng thái:** Active | **Target LLM:** OpenAI Codex / Claude / Copilot  
> **Nguyên tắc cốt lõi:** Token-Optimized, High-Density Directives, Zero-Redundancy, Decoupled Architecture.

---

## 1. PROJECT METADATA & CONTEXT

### 1.1 Thông số Kỹ thuật & Công nghệ
| Thuộc tính | Chi tiết Quy định |
| :--- | :--- |
| **Domain** | Dự báo Chuỗi thời gian Dài hạn (LSTF) & Trực quan hóa Giám sát Lưới điện |
| **Core Architecture** | Informer (Zhou et al., AAAI-21) [ProbSparse Attention, Distilling, Generative Decoder] |
| **Tech Stack** | Python 3.11+, PyTorch, Streamlit, Plotly, Pandas, NumPy, Scipy, Seaborn |
| **Dataset Chuẩn** | ETT (Electricity Transformer Temperature) — `ETTh1`, `ETTh2` (1h), `ETTm1` (15m) |
| **Target Variable** | `OT` (Oil Temperature - Nhiệt độ dầu trạm biến áp, ngưỡng vật lý tới hạn: **95°C**) |
| **Biến Đặc trưng phụ** | 6 biến công suất tải: `HUFL`, `HULL`, `MUFL`, `MULL`, `LUFL`, `LULL` |
| **Dải Dự báo (Horizons)** | 5 mốc dài hạn tiêu chuẩn: **24, 48, 168, 336, 720 bước** |

### 1.2 Hai User Stories Cốt lõi
- **US-01: Operational Manager (Quản lý Vận hành):** Giám sát OT thời gian thực; phát hiện sớm nguy cơ quá nhiệt. **Yêu cầu UI:** Line Chart tương tác tích hợp vạch ngưỡng 95°C, banner trạng thái pop-out tức thời khi $OT > 95^\circ\text{C}$, thời gian phản hồi dashboard $\le 2\text{s}$.
- **US-02: Deep Learning Researcher (Kỹ sư Học sâu):** Phân tích hiệu năng dự báo đa bước, dải phân vị bất định và ma trận chú ý. **Yêu cầu UI:** Fan Chart / Ribbon Chart (80% & 95% Confidence Intervals), Residuals Scatter/Histogram, Heatmap ma trận ProbSparse Attention, bảng so sánh đối chuẩn MSE/MAE vs Baseline (LSTM, ARIMA).

### 1.3 On-Demand Context References (Lazy-Loading)
- `docs/project_charter/`: Đặc tả chi tiết WBS 16 tasks, phân công RACI, lộ trình 6 tuần.
- `docs/references/2021_Zhou_Informer_AAAI.pdf`: Cơ sở toán học ProbSparse Attention $O(L \ln L)$ & Generative Decoder.
- `docs/project_charter/Final Project.pdf`: Chuẩn yêu cầu đồ án học phần Trực quan hóa dữ liệu.

---

## 2. AGENT SCOPE & STRICT GUARDRAILS

### 2.1 Mô hình Kiểm soát Ranh giới 3 Tầng (Three-Tier Boundary Model)
```
┌──────────────────────────────────────────────────────────────────────────┐
│ 🔴 RED ZONE (STRICT READ-ONLY / FORBIDDEN)                                │
│   - data/raw/*                                                           │
│   - docs/project_charter/*, docs/references/*                            │
│   - checkpoints gốc baseline (models/checkpoints_baseline/*)             │
├──────────────────────────────────────────────────────────────────────────┤
│ 🟡 AMBER ZONE (CONDITIONAL / REVIEW REQUIRED)                             │
│   - requirements.txt (CẤM tự thêm thư viện nếu chưa duyệt)              │
│   - configs/* (Siêu tham số mô hình / Training hyperparameters)          │
│   - app.py (Entry point chính của Streamlit Dashboard)                   │
├──────────────────────────────────────────────────────────────────────────┤
│ 🟢 GREEN ZONE (AUTONOMOUS WORKSPACE)                                     │
│   - src/* (data/, models/, analysis/, visuals/)                          │
│   - scripts/* (train, benchmark, export artifacts)                       │
│   - notebooks/*, output/*, tests/*, audit/*, docs/dev_logs/              │
└──────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Quy tắc Mệnh lệnh cho Codex (Actionable Directives)
- `[STRICT:DATA]` **KHÔNG** sửa, đổi tên, ghi đè hoặc xóa bất kỳ file nào trong `data/raw/*`. Dữ liệu sạch bắt buộc xuất ra `data/processed/clean_ett.parquet`.
- `[STRICT:ENV]` **BẮT BUỘC** kích hoạt `.venv` trước khi thực thi. Không tự ý chạy `pip install` làm biến động `requirements.txt`.
- `[STRICT:DECOUPLE]` Dashboard **KHÔNG** chạy suy luận PyTorch thời gian thực trên giao diện. Toàn bộ đồ thị đọc tĩnh từ các Parquet/JSON artifacts đã chuẩn hóa để duy trì SLA phản hồi $< 2\text{s}$.
- `[STRICT:BRANCH]` Mọi can thiệp code phải nằm trên feature branch tương ứng; không commit trực tiếp lên `main`.

---

## 3. DATA INTERFACE CONTRACTS (ARTIFACT SCHEMAS)

Toàn bộ pipeline mô hình xuất dữ liệu trung gian vào `output/artifacts/` hoặc `data/` theo đúng schema cố định bên dưới:

### 3.1 Dự báo Đối chuẩn (`predictions_benchmark.parquet`)
| Tên Cột | Kiểu Dữ liệu | Ràng buộc / Giá trị Mẫu | Mô tả |
| :--- | :--- | :--- | :--- |
| `timestamp` | `datetime64[ns]` | Chuẩn RFC3339 | Mốc thời gian dự báo |
| `horizon_step` | `int32` | `24`, `48`, `168`, `336`, `720` | Độ dài khung thời gian dự báo |
| `model_name` | `category` | `'informer'`, `'lstm'`, `'arima'` | Tên mô hình đối chuẩn |
| `target_actual` | `float32` | Giá trị OT thực tế | Ground Truth (°C) |
| `target_pred` | `float32` | Giá trị OT dự báo | Model Prediction (°C) |
| `mae` | `float32` | $\ge 0$ | Sai số tuyệt đối trung bình |
| `mse` | `float32` | $\ge 0$ | Sai số toàn phương trung bình |

### 3.2 Dải Bất định Dự báo (`uncertainty_intervals.parquet`)
| Tên Cột | Kiểu Dữ liệu | Ràng buộc / Giá trị Mẫu | Mô tả |
| :--- | :--- | :--- | :--- |
| `timestamp` | `datetime64[ns]` | Chuẩn RFC3339 | Mốc thời gian |
| `horizon_step` | `int32` | `24`, `48`, `168`, `336`, `720` | Khung dự báo |
| `target_actual` | `float32` | Nhiệt độ thực tế | Ground Truth |
| `pred_mean` | `float32` | Điểm dự báo trung tâm | Kỳ vọng dự báo |
| `lower_80` | `float32` | Phân vị 10% | Cận dưới khoảng tin cậy 80% |
| `upper_80` | `float32` | Phân vị 90% | Cận trên khoảng tin cậy 80% |
| `lower_95` | `float32` | Phân vị 2.5% | Cận dưới khoảng tin cậy 95% |
| `upper_95` | `float32` | Phân vị 97.5% | Cận trên khoảng tin cậy 95% |
| `is_breach_95c`| `bool` | `True` / `False` | `True` khi `upper_95 >= 95.0` |

### 3.3 Phân tích Phần dư (`residuals_analysis.parquet`)
| Tên Cột | Kiểu Dữ liệu | Ràng buộc / Giá trị Mẫu | Mô tả |
| :--- | :--- | :--- | :--- |
| `timestamp` | `datetime64[ns]` | Chuẩn RFC3339 | Mốc thời gian |
| `horizon_step` | `int32` | `24`, `48`, `168`, `336`, `720` | Khung dự báo |
| `model_name` | `category` | `'informer'`, `'lstm'`, `'arima'` | Mô hình đánh giá |
| `residual` | `float32` | `target_actual - target_pred` | Sai số phần dư |
| `abs_residual` | `float32` | `\|residual\|` | Độ lớn phần dư tuyệt đối |
| `z_score` | `float32` | Chuẩn hóa theo độ lệch chuẩn | Điểm Z-score |
| `is_outlier` | `bool` | `True` khi `\|z_score\| > 3.0` | Nhãn bất thường |

### 3.4 Ma trận Chú ý (`attention_weights.json`)
```json
{
  "layer_idx": 0,
  "head_idx": 1,
  "horizon_step": 168,
  "query_timestamps": ["2026-06-01T00:00:00", "..."],
  "key_timestamps": ["2026-05-25T00:00:00", "..."],
  "top_k_indices": [12, 45, 89, 120],
  "attention_matrix": [[0.042, 0.128], [0.015, 0.087]]
}
```

---

## 4. CODE & VISUALIZATION STANDARDS

### 4.1 Quy chuẩn Lập trình (Engineering Standards)
- **Code Style:** Tuân thủ PEP 8, định danh biến và hàm dạng `snake_case`, lớp dạng `PascalCase`.
- **Type Annotations:** 100% hàm trong `src/` phải khai báo kiểu tường minh (`from typing import Optional, Tuple, Dict`).
- **Tái lập Thực nghiệm (Reproducibility):** Cố định seed toàn cục `SEED = 2026` trên Torch, NumPy và random:
  ```python
  import torch, numpy as np, random
  def set_seed(seed: int = 2026) -> None:
      random.seed(seed); np.random.seed(seed)
      torch.manual_seed(seed); torch.cuda.manual_seed_all(seed)
  ```
- **Không Magic Numbers:** Toàn bộ ngưỡng an toàn (`95.0`), tỷ lệ phân chia tập dữ liệu (`12/4/4` tháng) và chu kỳ trượt phải lấy từ file hằng số/config.

### 4.2 Chuẩn Mực Thị giác (Tufte, Gestalt & Colorblind-Safe)
- **Tỷ lệ Dữ liệu - Mực (Edward Tufte Data-Ink Ratio):**
  - Xóa 100% khung viền hộp bao quanh biểu đồ (No bounding box).
  - Làm mờ hoặc tắt hoàn toàn lưới tọa độ phụ (Gridlines chính dùng màu xám nhạt `#E2E8F0`).
  - Dán nhãn trực tiếp (Direct Labeling) vào điểm cuối đường biểu diễn; hạn chế chú giải (legends) tách rời.
- **Tiêu đề Hành động (Action Titles):**
  - CẤM dùng tiêu đề tĩnh mô tả đơn thuần (ví dụ: *"Biểu đồ nhiệt độ OT"*).
  - BẮT BUỘC dùng tiêu đề rút ra kết luận nghiệp vụ (ví dụ: *"Nhiệt độ dầu OT vượt ngưỡng an toàn 95°C trong khung 14:00 - 17:00"*).
- **Nguyên lý Gestalt:** Dùng *Enclosure* (vùng phủ) và *Continuity* (đường bao) để thể hiện dải tin cậy; nhóm các KPI đo lường liên quan theo *Proximity*.
- **Bảng màu Chuẩn Accessibility (Colorblind-Safe & WCAG 2.1 AA):**
  - Chuỗi Thực tế (Actual): Xanh Navy `#1E3A8A`.
  - Dự báo Informer: Xanh lam đậm `#2563EB`.
  - Baseline (LSTM/ARIMA): Xám trung tính `#64748B`.
  - Ngưỡng Cảnh báo Nguy hiểm (95°C): Đỏ gạch `#DC2626`.
  - Vùng Tin cậy 80% CI: Xanh lam mềm `#93C5FD` với `opacity = 0.30`.
  - Vùng Tin cậy 95% CI: Xanh lam mềm `#93C5FD` với `opacity = 0.15`.
  - `[CẤM]` Tuyệt đối không dùng cặp màu Đỏ - Xanh lá đối nghịch trên cùng một biểu đồ.

---

## 5. STANDARD COMMANDS & WORKFLOW

| Tác vụ | Lệnh Thực thi Chuẩn (Chạy từ Thư mục Gốc) |
| :--- | :--- |
| **Kích hoạt Virtualenv** | `.\.venv\Scripts\activate` (PowerShell) |
| **Kiểm tra Môi trường** | `python -V && pip list` |
| **Tiền xử lý & EDA Data** | `python scripts/preprocess_ett.py --data ETTh1 --out data/processed/clean_ett.parquet` |
| **Huấn luyện Informer** | `python scripts/train_informer.py --data ETTh1 --pred_len 24 --epochs 20 --patience 3` |
| **Xuất Đối chuẩn Benchmark** | `python scripts/evaluate_benchmark.py --models informer,lstm,arima --horizons 24,48,168,336,720` |
| **Xuất Dải Bất định & Parquet**| `python scripts/export_uncertainty_artifacts.py --checkpoint models/best_informer.pt` |
| **Khởi chạy Streamlit App** | `streamlit run app.py` |
| **Kiểm thử Toàn diện** | `pytest tests/ -v --tb=short` |

---

## 6. DEFINITION OF DONE (DOD) & TASK EXECUTION CHECKLIST

Trước khi đánh dấu hoàn thành bất kỳ task code nào hoặc báo cáo kết quả, Codex BẮT BUỘC phải tự kiểm tra 5 điều kiện sau:

- [ ] **1. Guardrails Verification:** Không chỉnh sửa hoặc làm biến đổi bất kỳ file nào trong `data/raw/*`, checkpoints baseline hoặc tài liệu gốc trong `docs/`.
- [ ] **2. Contract Schema Integrity:** Mọi file Parquet/JSON xuất ra khớp 100% danh sách cột, kiểu dữ liệu (`datetime64[ns]`, `float32`, `int32`) và định dạng tại Mục 3.
- [ ] **3. Reproducibility & Clean Code:** Đã gắn `SEED = 2026`, khai báo đầy đủ Type Hints, tuân thủ PEP 8, không để lại code thử nghiệm không dùng (dead code/prints vô nghĩa).
- [ ] **4. Visual Audit Compliance:** Biểu đồ tuân thủ Tufte (Data-ink cao, không viền hộp, Action Titles), dải tin cậy đúng độ mờ (0.3 / 0.15), màu sắc Colorblind-safe (không dùng Đỏ - Xanh lá).
- [ ] **5. Performance & Smoke Test:** Script chạy không phát sinh runtime exception; dữ liệu nạp vào Dashboard mất thời gian $\le 2\text{s}$; unit tests (nếu có) đạt trạng thái PASS.
