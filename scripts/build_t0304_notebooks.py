"""Build and execute reproducible T0304 notebooks using the active venv kernel."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from queue import Empty
import sys
from time import monotonic
from typing import Any

import nbformat
from jupyter_client import KernelManager

ROOT = Path(__file__).resolve().parents[1]

BOOTSTRAP = r'''
from pathlib import Path
import hashlib
import json
import random
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from IPython.display import display, Markdown

ROOT = next(p for p in (Path.cwd(), *Path.cwd().parents) if (p / "AGENTS.md").is_file())
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from src.data.constants import (
    SEED, CADENCE_MINUTES, EXPECTED_DATASET_ROWS, MEASUREMENTS,
    LOAD_BRANCHES, DRY_MONTHS, DAY_NAMES, WARNING_TEMP_THRESHOLD,
    CRITICAL_TEMP_THRESHOLD,
)
assert SEED == 2026
random.seed(SEED)
np.random.seed(SEED)
%matplotlib inline
plt.rcParams.update({"figure.dpi": 95, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.grid": False,
                     "font.size": 10})
NAVY, TEAL, SLATE = "#1E3A8A", "#0D9488", "#64748B"
AMBER, CRIMSON, GRID = "#D97706", "#DC2626", "#E2E8F0"
audit = json.loads((ROOT / "audit/t0205_artifacts_sync_audit.json").read_text(encoding="utf-8"))
assert audit["status"] == "PASS"
names = ["clean_ett.parquet", "load_profiles_stl.parquet", "quantile_bands.parquet",
         "lag_correlation_matrix.json", "thermal_breach_events.parquet", "loess_curves.parquet"]
source_hashes = {}
for name in names:
    path = ROOT / ("data/processed" if name == "clean_ett.parquet" else "output/artifacts") / name
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == audit["artifacts"][name]["sha256_bytes"], f"Stale audit: {name}"
    source_hashes[name] = digest
clean = pd.read_parquet(ROOT / "data/processed/clean_ett.parquet")
profiles = pd.read_parquet(ROOT / "output/artifacts/load_profiles_stl.parquet")
bands = pd.read_parquet(ROOT / "output/artifacts/quantile_bands.parquet")
lag = json.loads((ROOT / "output/artifacts/lag_correlation_matrix.json").read_text(encoding="utf-8"))
events = pd.read_parquet(ROOT / "output/artifacts/thermal_breach_events.parquet")
curves = pd.read_parquet(ROOT / "output/artifacts/loess_curves.parquet")
assert clean.groupby("dataset").size().to_dict() == EXPECTED_DATASET_ROWS
assert not clean.duplicated(["dataset", "timestamp"]).any()
data = clean.copy()
data["hour"] = data.timestamp.dt.hour
data["weekday"] = data.timestamp.dt.dayofweek
data["month"] = data.timestamp.dt.month
data["season"] = np.where(data.month.isin(DRY_MONTHS), "Dry", "Wet")
datasets = sorted(CADENCE_MINUTES)
gap_counts = {}
for dataset, group in data.groupby("dataset"):
    delta = group.timestamp.diff().dropna()
    cadence = pd.Timedelta(minutes=CADENCE_MINUTES[dataset])
    assert (delta >= cadence).all() and (delta % cadence == pd.Timedelta(0)).all()
    gap_counts[dataset] = int(delta.gt(cadence).sum())
assert gap_counts == audit["quality_audit"]["gap_counts"]
display(pd.DataFrame({"samples": clean.groupby("dataset").size(),
                      "cadence_minutes": pd.Series(CADENCE_MINUTES),
                      "observed_gaps": pd.Series(gap_counts)}))
print("Interpreter:", sys.executable)
print("Seed:", SEED, "| timezone: unknown | read-only audited inputs: six")
'''


def md(text: str) -> Any:
    """Create a Markdown notebook cell."""
    return nbformat.v4.new_markdown_cell(text.strip())


def code(text: str) -> Any:
    """Create an executable notebook cell."""
    return nbformat.v4.new_code_cell(text.strip())


def statistical_cells() -> list[Any]:
    """TQH-04 descriptive, temporal and precomputed diagnostic exploration."""
    return [md("""
# TQH-04 — Khám phá thống kê sâu trên ba dataset ETT
**T0304 · ETT_GRID_VIS_2026 v2.0 · seed 2026 · CPU-only**

Run-all từ ROOT hoặc thư mục notebooks bằng kernel `.venv`.
Chỉ đọc sáu artifacts đã kiểm toán T0205; không sửa raw, không chạy lại engine.
Mỗi dataset được phân tích riêng theo cadence 1h/15m, không gộp số mẫu thành
thời lượng hoặc coi trạm có nhiều mẫu hơn là nóng hơn.

85/95°C là **quy ước phân tích dự án**, không phải chuẩn kỹ thuật phổ quát.
Dry (tháng 11–4)/Wet (5–10) là nhóm tháng, không tự gọi là mùa hè/đông địa phương.
Quan sát và giả thuyết được tách biệt; không dùng tương quan để khẳng định nguyên nhân.
"""), code(BOOTSTRAP), md("""
## 1. Thống kê mô tả: OT và sáu nhánh tải
Min/max/mean/median/IQR theo dataset. Skew dùng Pandas sample skew;
kurtosis là **excess kurtosis** (chuẩn tham chiếu 0), không phải Pearson kurtosis.
Số mẫu hợp lệ đi kèm; OT dùng °C, tải giữ đơn vị nguồn chưa hiệu chuẩn.
"""), code('''
rows = []
for dataset, group in data.groupby("dataset"):
    for variable in MEASUREMENTS:
        values = group[variable].dropna().astype("float64")
        q25, q75 = values.quantile([0.25, 0.75])
        rows.append({"dataset": dataset, "variable": variable, "n": len(values),
                     "min": values.min(), "max": values.max(), "mean": values.mean(),
                     "median": values.median(), "q25": q25, "q75": q75,
                     "iqr": q75 - q25, "skewness": values.skew(),
                     "excess_kurtosis": values.kurt()})
descriptive = pd.DataFrame(rows).set_index(["dataset", "variable"])
assert len(descriptive) == 21
display(descriptive.round(3))
'''), md("""
## 2. Phân phối OT và xu hướng thời gian
Histogram density theo từng dataset (không coi là kiểm định chuẩn).
Trend dùng **mean/max ngày** từ quan sát thực, không phải đường dự báo;
max ngày giữ thông tin đỉnh nhưng không thay chuỗi gốc khi xác định sự kiện.
"""), code('''
fig, axes = plt.subplots(1, 3, figsize=(13, 3.2), sharex=True, sharey=True)
for ax, dataset in zip(axes, datasets):
    values = data.loc[data.dataset.eq(dataset), "OT"].dropna()
    ax.hist(values, bins=35, density=True, color=NAVY, alpha=0.75)
    ax.axvline(WARNING_TEMP_THRESHOLD, color=AMBER, ls="--", label="85°C convention")
    ax.axvline(CRITICAL_TEMP_THRESHOLD, color=CRIMSON, ls=":", label="95°C convention")
    ax.set(title=dataset, xlabel="OT (°C)")
axes[0].set_ylabel("Density (1/°C)")
axes[-1].legend(fontsize=7)
plt.tight_layout(); plt.show()
fig, axes = plt.subplots(3, 1, figsize=(12, 7), sharey=True)
for ax, dataset in zip(axes, datasets):
    daily = data.loc[data.dataset.eq(dataset)].set_index("timestamp").OT.resample("D").agg(["mean", "max"])
    ax.plot(daily.index, daily["mean"], color=NAVY, label="Daily mean")
    ax.plot(daily.index, daily["max"], color=SLATE, ls="--", lw=0.8, label="Daily max")
    ax.set(title=dataset, ylabel="OT (°C)")
    ax.legend(loc="upper right", fontsize=8)
plt.tight_layout(); plt.show()
'''), md("""
### So sánh mô tả theo nhóm tháng và khung giờ khai báo
Khung 17:00–20:59 được khai báo **để thăm dò**, không phải giờ cao điểm đã
xác minh của lưới điện. Bảng chênh lệch không phải bằng chứng tải gây nhiệt;
tự tương quan, mùa, thời lượng bao phủ và yếu tố chưa quan sát có thể gây nhiễu.
"""), code('''
data["hour_window"] = np.where(data.hour.between(17, 20), "17–20 exploratory", "Other hours")
season_summary = data.groupby(["dataset", "season"]).OT.agg(["count", "mean", "median", "std", "min", "max"])
window_summary = data.groupby(["dataset", "hour_window"]).OT.agg(["count", "mean", "median", "max"])
display(season_summary.round(3))
display(window_summary.round(3))
contrast = season_summary["mean"].unstack()
contrast["Wet_minus_Dry_C"] = contrast["Wet"] - contrast["Dry"]
display(contrast.round(3))
'''), md("""
## 3. Chu kỳ giờ, thứ và tháng
Các dải q10–q90 là **80% empirical historical bands**, không phải confidence
interval của mean. Tổng hợp thứ/tháng không nhận định mùa địa phương.
"""), code('''
cyclical = {}
for dimension in ["hour", "weekday", "month"]:
    table = data.groupby(["dataset", dimension]).OT.agg(
        sample_count="count", mean="mean", median="median", min="min", max="max",
        q10=lambda s: s.quantile(0.10), q90=lambda s: s.quantile(0.90))
    cyclical[dimension] = table
    print(dimension, "| bins per dataset:", table.groupby(level=0).size().to_dict())
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.1), sharey=True)
    for ax, dataset in zip(axes, datasets):
        sub = table.loc[dataset]
        ax.fill_between(sub.index, sub.q10, sub.q90, color="#93C5FD", alpha=0.20, label="Historical 80%")
        ax.plot(sub.index, sub["mean"], color=NAVY, label="Mean")
        ax.set(title=dataset, xlabel=dimension)
        if dimension == "weekday":
            ax.set_xticks(range(7), DAY_NAMES, rotation=45)
    axes[0].set_ylabel("OT (°C)"); axes[-1].legend(fontsize=7)
    plt.tight_layout(); plt.show()
display(cyclical["hour"].round(3))
'''), md("""
## 4. Đỉnh quan sát và đối chiếu ngưỡng
Top-5 mẫu mỗi dataset là **mốc đáng chú ý**, không mặc định là sự cố.
Cột khoảng cách đến 85°C cho biết mức gần ngưỡng mà không tự đặt ngưỡng “cận nguy hiểm”.
Sample counts vượt ngưỡng không được nhân cadence để tạo event duration giả;
duration/Degree-Hours chỉ lấy từ artifact sự kiện có hỗ trợ đã kiểm toán.
"""), code('''
top_ot = pd.concat([g.nlargest(5, "OT") for _, g in data.groupby("dataset")])
top_ot = top_ot[["dataset", "timestamp", "OT", "thermal_regime"]].copy()
top_ot["below_85_by_C"] = WARNING_TEMP_THRESHOLD - top_ot.OT
display(top_ot.reset_index(drop=True))
threshold_rows = []
for dataset, group in data.groupby("dataset"):
    valid = group.OT.dropna()
    for threshold in [WARNING_TEMP_THRESHOLD, CRITICAL_TEMP_THRESHOLD]:
        selected = events.loc[events.dataset.eq(dataset) & events.threshold_c.eq(threshold)]
        threshold_rows.append({"dataset": dataset, "threshold_C": threshold,
                               "valid_samples": len(valid), "samples_ge": int(valid.ge(threshold).sum()),
                               "sample_pct_ge": 100 * valid.ge(threshold).mean(),
                               "events": len(selected), "duration_h": selected.duration_hours.sum(),
                               "degree_hours_C_h": selected.degree_hours.sum()})
threshold_summary = pd.DataFrame(threshold_rows)
display(threshold_summary)
for dataset, group in data.groupby("dataset"):
    peak = group.loc[group.OT.idxmax()]
    display(Markdown(f"**Quan sát {dataset}:** OT cao nhất {peak.OT:.2f}°C tại {peak.timestamp}; "
                     f"cách ngưỡng 85°C {85 - peak.OT:.2f}°C. Đây không phải kết luận nguyên nhân."))
'''), md("""
## 5. Đối chiếu diagnostics tiền tính, không chạy lại engine
STL reconstruction trên hàng fit được; quantile nesting; lag/LOESS giữ scope
lịch sử. Những kiểm tra này bổ sung chứ không thay full audit T0205.
"""), code('''
valid_stl = profiles.loc[profiles.record_type.eq("stl")].dropna(subset=["trend", "seasonal", "residual", "observed"])
np.testing.assert_allclose(valid_stl.observed, valid_stl.trend + valid_stl.seasonal + valid_stl.residual,
                           atol=1e-4, rtol=1e-5)
qcols = ["q025", "q10", "q25", "q50", "q75", "q90", "q975"]
assert not (bands[qcols].diff(axis=1).iloc[:, 1:] < 0).any().any()
assert all(np.shape(r["correlation_matrix"]) == (6, 13) for r in lag["records"])
assert np.isfinite(curves[["x_load", "y_ot_smooth"]]).all().all()
display(pd.DataFrame({"STL_fitted_rows": valid_stl.groupby("dataset").size(),
                      "quantile_rows": bands.groupby("dataset").size(),
                      "LOESS_rows": curves.groupby("dataset").size()}))
print("PASS: STL reconstruction, quantile nesting, saved lag shape, finite LOESS")
'''), md("""
## 6. Kết luận và giả thuyết cần kiểm chứng
- **Quan sát:** Bảng, đồ thị và đỉnh nêu trên xuất phát trực tiếp từ artifacts đã hash-check.
- **Giả thuyết:** Thay đổi tải, điều kiện môi trường hoặc lịch vận hành có thể liên quan
  OT; dữ liệu hiện tại không đủ cô lập tác động hay kết luận nhánh tải gây sự cố.
- Gap count 0 nghĩa không phát hiện thiếu timestamp theo cadence trong cửa sổ nguồn;
  không chứng minh cảm biến hiệu chuẩn đúng hoặc dữ liệu đầy đủ ngoài cửa sổ đó.
- OT thiếu sẽ không được gán Normal; không trộn duration/Degree-Hours hai ngưỡng.
- Tự tương quan và unequal coverage làm phép kiểm định độc lập đơn giản không phù hợp;
  notebook không đưa p-value/causal claim khi chưa có thiết kế thống kê được duyệt.
- Sản phẩm là historical analytics, không prediction hay certified real-time safety.
""")]


def storytelling_cells() -> list[Any]:
    """TQH-05 evidence-derived messages with separate chart scales and truthful gaps."""
    return [md("""
# TQH-05 — Chắt lọc insight và visual storytelling cho hai User Stories
**T0304 · ETT_GRID_VIS_2026 v2.0 · seed 2026**

Mọi Action Title được tính từ artifacts, không chép con số demo hoặc gán nguyên nhân.
Notebook độc lập với notebook 02: Run-all không phụ thuộc trạng thái kernel trước.
Historical analytics, không dự báo trực tiếp hoặc chứng nhận an toàn thiết bị.
85/95°C là quy ước dự án. Các biểu đồ tiền tính chỉ tham chiếu scope đã lưu.
"""), code(BOOTSTRAP), md("""
## 1. What–Why–How: dữ liệu → tác vụ → encoding/interaction

| User Story | What | Why | How / interaction trong dashboard |
|---|---|---|---|
| US-01: kế hoạch tải | OT theo ngày, giờ, nhóm tháng | Tìm chu kỳ, so sánh giai đoạn để hỗ trợ lập lịch | Calendar Heatmap; dataset/season/date filter; tooltip giữ °C |
| US-01: tải và nhiệt | STL và hourly quantile bands | Phân biệt trend/chu kỳ và độ phân tán lịch sử | STL panels; Fan 50/80/95%; median riêng mean; shared time context |
| US-01: tỷ trọng tải | Cặp useful/unuseful ở từng cấp áp | So sánh cơ cấu, nhận diện dữ liệu không hợp lệ | **100% Stacked Bar**, không Stacked Area; loại tỷ trọng âm/mẫu số ≤0, không clip |
| US-01: độ trễ | Lag matrix 6×13 theo mùa | Sàng lọc liên hệ tải đi trước nhiệt | Heatmap tâm 0, tooltip n/r/k; không kết luận nhân quả |
| US-02: đối chiếu ngưỡng | OT gốc, ngưỡng 85/95 và events | Tìm mốc vượt ngưỡng và áp lực nhiệt | Threshold line + Barcode/Rug; selection theo khoảng hỗ trợ |
| US-02: khoanh vùng giả thuyết | Sáu tải và tọa độ LOWESS | Đối chiếu nhánh cùng thời gian và quan hệ phi tuyến | Synchronized Small Multiples + scatter/LOESS; zoom shared X trong dashboard |

Các hình dưới là **bản tĩnh nghiên cứu**, không tự nhận có brush/linked selection
như dashboard tương tác. Không chồng bảy đường khác đơn vị vào một trục y.
"""), code('''
title_rows = []
peak_rows = []
for dataset, group in data.groupby("dataset"):
    peak = group.loc[group.OT.idxmax()]
    count85 = int(group.OT.ge(WARNING_TEMP_THRESHOLD).sum())
    peak_rows.append({"dataset": dataset, "peak_ot": float(peak.OT), "timestamp": peak.timestamp})
    title_rows.append({"dataset": dataset, "story": "US-02", "chart": "Threshold line",
                       "action_title": f"{dataset}: OT đạt {peak.OT:.2f}°C tại {peak.timestamp}; {count85} mẫu ≥85°C",
                       "evidence": "observed maximum + threshold sample count; no causal attribution"})
    sub = bands.loc[bands.dataset.eq(dataset) & bands.variable.eq("OT") & bands.season.eq("Dry")]
    widest = sub.assign(iqr=sub.q75 - sub.q25).sort_values("iqr", ascending=False).iloc[0]
    title_rows.append({"dataset": dataset, "story": "US-01", "chart": "Hourly Fan / Dry",
                       "action_title": f"{dataset}, Dry: IQR OT rộng nhất {widest.q75-widest.q25:.2f}°C lúc {int(widest.hour):02d}h",
                       "evidence": "max empirical IQR over 24 bins; ties use existing hour order"})
    daily = group.set_index("timestamp").OT.resample("D").mean()
    title_rows.append({"dataset": dataset, "story": "US-01", "chart": "Calendar",
                       "action_title": f"{dataset}: OT trung bình ngày cao nhất {daily.max():.2f}°C vào {daily.idxmax().date()}",
                       "evidence": "daily mean; not instantaneous peak"})
    for threshold in [85, 95]:
        ev = events.loc[events.dataset.eq(dataset) & events.threshold_c.eq(threshold)]
        title_rows.append({"dataset": dataset, "story": "US-02", "chart": f"Events ≥{threshold}°C",
                           "action_title": f"{dataset}: {len(ev)} đợt ≥{threshold}°C; {ev.duration_hours.sum():.2f}h và {ev.degree_hours.sum():.2f}°C·h",
                           "evidence": "saved event support; each threshold separately"})
action_titles = pd.DataFrame(title_rows)
display(action_titles[["dataset", "chart", "action_title"]])
assert not action_titles.action_title.str.contains("do quán tính", regex=False).any()
'''), md("""
## 2. US-01 — Ngày đáng chú ý và dải giờ lịch sử
Calendar nghiên cứu dạng tháng × ngày; ô không có quan sát giữ masked (không tô 0).
Màu OT dùng thang tuyệt đối chung, không gán Critical cho percentile cao của OT thấp.
Fan chọn Dry như một tham chiếu có nhãn; không xem là refit theo Date Range.
"""), code('''
fig, axes = plt.subplots(1, 3, figsize=(14, 3.2), sharey=True)
for ax, dataset in zip(axes, datasets):
    daily = data.loc[data.dataset.eq(dataset)].set_index("timestamp").OT.resample("D").mean().dropna()
    selected_year = int(daily.index.year.min())
    selected = daily.loc[daily.index.year == selected_year]
    matrix = pd.DataFrame({"month": selected.index.month, "day": selected.index.day, "OT": selected.values}).pivot(index="month", columns="day", values="OT")
    image = ax.imshow(np.ma.masked_invalid(matrix.to_numpy()), aspect="auto", cmap="Blues", vmin=0, vmax=95)
    ax.set(title=f"{dataset} · daily mean · {selected_year}", xlabel="Day of month")
    ax.set_xticks([0, 9, 19, 29], [1, 10, 20, 30])
    ax.set_yticks(range(len(matrix.index)), matrix.index)
axes[0].set_ylabel("Month")
fig.colorbar(image, ax=axes, label="OT daily mean (°C)", shrink=0.8)
plt.show()
fig, axes = plt.subplots(1, 3, figsize=(14, 3.2), sharey=True)
for ax, dataset in zip(axes, datasets):
    sub = bands.loc[bands.dataset.eq(dataset) & bands.variable.eq("OT") & bands.season.eq("Dry")].sort_values("hour")
    for low, high, label, alpha in [("q025", "q975", "95%", .14), ("q10", "q90", "80%", .20), ("q25", "q75", "50%", .28)]:
        ax.fill_between(sub.hour, sub[low], sub[high], color="#93C5FD", alpha=alpha, label=label)
    ax.plot(sub.hour, sub.q50, color=NAVY, label="Median")
    ax.plot(sub.hour, sub["mean"], color=SLATE, ls="--", label="Mean")
    ax.set(title=f"{dataset} · Dry historical bands", xlabel="Hour (source timezone unknown)")
axes[0].set_ylabel("OT (°C)"); axes[-1].legend(fontsize=7)
plt.tight_layout(); plt.show()
'''), md("""
### Cơ cấu useful/unuseful theo từng cấp áp
Tính tỷ lệ từng mẫu hợp lệ rồi lấy mean theo giờ; không lấy tỷ lệ hai tổng một
cách ngầm định. Mẫu âm/null hoặc tổng ≤0 bị loại, không `.clip(lower=0)`.
Useful/unuseful là nhãn nguồn, chưa đồng nhất với P/Q đã hiệu chuẩn.
"""), code('''
selected_dataset = datasets[0]
group = data.loc[data.dataset.eq(selected_dataset)]
fig, axes = plt.subplots(1, 3, figsize=(13, 3.3), sharey=True)
share_evidence = []
for ax, (tier, useful, unuseful) in zip(axes, [("High", "HUFL", "HULL"), ("Middle", "MUFL", "MULL"), ("Low", "LUFL", "LULL")]):
    total = group[useful] + group[unuseful]
    valid = group[useful].ge(0) & group[unuseful].ge(0) & total.gt(0)
    ratio = (group[useful] / total).where(valid)
    hourly = ratio.groupby(group.hour).mean().reindex(range(24))
    ax.bar(hourly.index, 100 * hourly, color=TEAL, label="Useful")
    ax.bar(hourly.index, 100 * (1-hourly), bottom=100 * hourly, color=SLATE, label="Unuseful")
    ax.set(title=f"{selected_dataset} · {tier}", xlabel="Hour", ylim=(0,100))
    share_evidence.append({"dataset": selected_dataset, "tier": tier, "excluded_samples": int((~valid).sum()), "valid_samples": int(valid.sum())})
axes[0].set_ylabel("Mean per-sample share (%)"); axes[-1].legend(fontsize=8)
plt.tight_layout(); plt.show()
display(pd.DataFrame(share_evidence))
'''), md("""
### Lag heatmap: chỉ sàng lọc liên hệ lịch sử
Chọn Pearson/Dry và báo cả n. Tối đa |r| trên nhiều ô là thống kê mô tả,
không phải kiểm định nguyên nhân hoặc ước lượng quán tính thiết bị đã hiệu chuẩn.
"""), code('''
fig, axes = plt.subplots(1, 3, figsize=(14, 3.2), sharey=True)
lag_insights = []
for ax, dataset in zip(axes, datasets):
    record = next(r for r in lag["records"] if r["dataset"] == dataset and r["season"] == "Dry" and r["method"] == "pearson")
    matrix = np.array(record["correlation_matrix"], dtype=float)
    image = ax.imshow(np.ma.masked_invalid(matrix), aspect="auto", cmap="PuOr", vmin=-1, vmax=1)
    ax.set(title=f"{dataset} · Pearson · Dry", xlabel="Load leads OT by k hours")
    ax.set_xticks([0, 3, 6, 9, 12]); ax.set_yticks(range(6), LOAD_BRANCHES)
    if np.isfinite(matrix).any():
        branch, hour = np.unravel_index(np.nanargmax(np.abs(matrix)), matrix.shape)
        n = record["sample_counts"][branch][hour]
        lag_insights.append({"dataset": dataset, "load": LOAD_BRANCHES[branch], "lag_h": int(hour), "r": matrix[branch,hour], "paired_n": n})
fig.colorbar(image, ax=axes, label="r (association, not causation)", shrink=0.8)
plt.show(); display(pd.DataFrame(lag_insights).round(3))
for item in lag_insights:
    display(Markdown(f"**Action Title:** {item['dataset']}, Dry: |r| lớn nhất tại {item['load']}, "
                     f"lag {item['lag_h']}h, r={item['r']:.3f}, n={item['paired_n']} — chỉ là liên hệ lịch sử."))
'''), md("""
## 3. US-02 — Ngưỡng và barcode/rug sự kiện
Vẽ OT quan sát đầy đủ, không nối chéo dataset. Bảng events rỗng hợp lệ được
thông báo trực tiếp; không nâng nhiệt demo hoặc vẽ barcode giả.
"""), code('''
fig, axes = plt.subplots(3, 1, figsize=(12, 7), sharey=True)
for ax, dataset in zip(axes, datasets):
    group = data.loc[data.dataset.eq(dataset)]
    ax.plot(group.timestamp, group.OT, color=NAVY, lw=0.5)
    ax.axhline(85, color=AMBER, ls="--", label="85°C project convention")
    ax.axhline(95, color=CRIMSON, ls=":", label="95°C project convention")
    peak = group.loc[group.OT.idxmax()]
    ax.set(title=f"{dataset}: peak OT {peak.OT:.2f}°C at {peak.timestamp}", ylabel="OT (°C)")
axes[0].legend(fontsize=7); plt.tight_layout(); plt.show()
fig, ax = plt.subplots(figsize=(12, 2.4))
for index, dataset in enumerate(datasets):
    for event in events.loc[events.dataset.eq(dataset)].itertuples():
        ax.plot([event.start_timestamp, event.end_timestamp], [index,index], lw=5,
                color=CRIMSON if event.threshold_c == 95 else AMBER)
ax.set_yticks(range(3), datasets)
if events.empty:
    ax.text(.5,.5,"No observed ≥85/95°C breach events — empty artifact is valid",
            ha="center", va="center", transform=ax.transAxes)
ax.set_title("Historical thermal event barcode · thresholds summarized separately")
plt.tight_layout(); plt.show()
'''), md("""
### Sáu nhánh tải và LOWESS đã lưu
Small multiples dùng cùng X và daily mean để đọc bối cảnh; không phải view
chẩn đoán sự cố từng mẫu. Không có breach thật nên không tự gán “thủ phạm”.
Scatter dùng mẫu thưa xác định **chỉ để hiển thị**, LOESS là tọa độ artifact fit
trên toàn bộ cặp hợp lệ, scope all/ALL; không fit bằng Statsmodels trong notebook này.
"""), code('''
group = data.loc[data.dataset.eq(selected_dataset)].copy()
daily_loads = group.set_index("timestamp")[list(LOAD_BRANCHES)].resample("D").mean()
fig, axes = plt.subplots(6, 1, figsize=(12, 9), sharex=True)
for ax, variable in zip(axes, LOAD_BRANCHES):
    ax.plot(daily_loads.index, daily_loads[variable], color=TEAL if variable in ["HUFL", "MUFL", "LUFL"] else SLATE, lw=.8)
    ax.set_ylabel(variable)
axes[0].set_title(f"{selected_dataset}: six loads, aligned time axis · daily mean, source load units")
plt.tight_layout(); plt.show()
fig, axes = plt.subplots(2, 3, figsize=(13, 6.5), sharey=True)
for ax, variable in zip(axes.flat, LOAD_BRANCHES):
    sampled = group.iloc[::max(1, int(np.ceil(len(group)/1200)))]
    ax.scatter(sampled[variable], sampled.OT, color=SLATE, s=4, alpha=.25)
    reference = curves.loc[curves.dataset.eq(selected_dataset) & curves.load_feature.eq(variable)
                           & curves.scope_type.eq("all") & curves.scope_value.eq("ALL")].sort_values("x_load")
    if reference.empty:
        ax.text(.5,.5,"Offline reference unavailable", transform=ax.transAxes, ha="center")
    else:
        ax.plot(reference.x_load, reference.y_ot_smooth, color=NAVY, label="Saved LOWESS · all/ALL")
    ax.set(xlabel=f"{variable} (source units)", ylabel="OT (°C)")
axes.flat[0].legend(fontsize=7)
fig.suptitle(f"{selected_dataset}: six load–OT relations, not a six-input causal model")
plt.tight_layout(); plt.show()
'''), md("""
## 4. Insight → hành động thận trọng, giả định và giới hạn
- **US-01:** Dùng giờ/tháng có mean/IQR khác biệt làm đầu mối xem xét lịch tải,
  kiểm tra tiếp khả năng vận hành; không ra lệnh điều độ chỉ từ thống kê mô tả.
- **US-02:** Không có breach trong cửa sổ nguồn không chứng minh thiết bị an toàn
  trong tương lai hoặc ngưỡng dự án phù hợp mọi thiết bị.
- Không chép “98,4°C do quán tính tải 3h”: vừa là số liệu chưa xác minh vừa gán nhân quả.
- Timestamps timezone unknown: giờ hiển thị là giờ nguồn, không tự gọi UTC/local.
- Gap counts=0 theo T0205 không loại trừ missing ngoài cửa sổ, sai cảm biến hay biến bị bỏ sót.
- Khác cadence/số mẫu làm so sánh pooled sai lệch; giữ dataset riêng ở mọi chart.
- Thermal event ≥95 có thể nằm trong ≥85: duration/Degree-Hours tổng hợp từng ngưỡng.
- Bands/lag/LOWESS là historical references theo scope lưu, không CI/prediction intervals.
- Static figures không chứng nhận browser interaction, accessibility hay SLA <2s.
- T0304 không sửa engine/core scripts hoặc artifact nguồn; notebooks là sản phẩm nghiên cứu.
""")]


def atomic_json(payload: dict[str, Any], path: Path) -> None:
    """Write derived notebook/evidence through a verified exclusive temp file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    encoded = json.dumps(payload, ensure_ascii=False, indent=1, allow_nan=False)
    owned = False
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            owned = True
            handle.write(encoded + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        if json.loads(temporary.read_text(encoding="utf-8")) != json.loads(encoded):
            raise ValueError("Round-trip failed")
        os.replace(temporary, path)
    finally:
        if owned and temporary.exists():
            temporary.unlink()


def execute_notebook(notebook: Any, path: Path) -> dict[str, Any]:
    """Run all cells sequentially on this exact interpreter, capture IOPub outputs."""
    nbformat.validate(notebook)
    manager = KernelManager(kernel_name="python3")
    # Installed kernel specs may point to another Python; force the active .venv.
    manager.kernel_spec.argv = [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"]
    manager.start_kernel(cwd=str(ROOT))
    client = manager.client()
    client.start_channels()
    started = monotonic()
    executed = 0
    try:
        client.wait_for_ready(timeout=60)
        for cell in notebook.cells:
            if cell.cell_type != "code":
                continue
            message_id = client.execute(cell.source, stop_on_error=True)
            deadline = monotonic() + 240
            outputs = []
            while True:
                if monotonic() > deadline:
                    raise TimeoutError(f"Cell timed out: {path.name}/{executed+1}")
                try:
                    message = client.get_iopub_msg(timeout=2)
                except Empty:
                    continue
                if message.get("parent_header", {}).get("msg_id") != message_id:
                    continue
                kind, content = message["msg_type"], message["content"]
                if kind == "execute_input":
                    cell.execution_count = content["execution_count"]
                elif kind in {"stream", "display_data", "execute_result", "error"}:
                    outputs.append(nbformat.v4.output_from_msg(message))
                elif kind == "status" and content["execution_state"] == "idle":
                    break
            cell.outputs = outputs
            if any(output.output_type == "error" for output in outputs):
                raise RuntimeError(f"Notebook failed: {path.name}: {outputs[-1]}")
            executed += 1
        evidence = {"code_cells_executed": executed, "errors": 0,
                    "elapsed_seconds": round(monotonic() - started, 3),
                    "interpreter": sys.executable}
        notebook.metadata["ett_execution"] = evidence
        nbformat.validate(notebook)
        atomic_json(dict(notebook), path)
        return evidence
    finally:
        client.stop_channels()
        manager.shutdown_kernel(now=True)


def main() -> None:
    """Build/run both independent notebooks, verify inputs unchanged, save evidence."""
    import subprocess
    from datetime import datetime, timezone

    if Path(sys.prefix).resolve() != (ROOT / ".venv").resolve():
        raise RuntimeError("Activate repository .venv before execution")
    audit = json.loads((ROOT / "audit/t0205_artifacts_sync_audit.json").read_text())
    inputs = {entry["path"]: entry["sha256_bytes"] for entry in audit["artifacts"].values()}
    protected = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                 for directory in [ROOT / "data/raw", ROOT / "docs/project_charter", ROOT / "docs/references"]
                 for path in directory.rglob("*") if path.is_file()}
    results = {}
    for name, cells in [
        ("02_tqh04_statistical_analysis.ipynb", statistical_cells()),
        ("03_tqh05_insights_visual_storytelling.ipynb", storytelling_cells()),
    ]:
        notebook = nbformat.v4.new_notebook(cells=cells, metadata={
            "kernelspec": {"name": "python3", "language": "python", "display_name": ".venv (Python 3.11+)"},
            "language_info": {"name": "python", "version": sys.version.split()[0]},
            "ett_task": {"id": "T0304", "schema_version": "2.0", "seed": 2026,
                         "input_sha256": inputs},
        })
        path = ROOT / "notebooks" / name
        results[name] = execute_notebook(notebook, path)
        print(name, results[name], flush=True)
    for value, digest in {**inputs, **protected}.items():
        if hashlib.sha256(Path(value).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Input/protected source changed: {value}")
    evidence = {"task": "T0304", "generated_at": datetime.now(timezone.utc).isoformat(),
                "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, encoding="utf-8").strip(),
                "notebooks": results, "input_sha256": inputs,
                "protected_files_checked": len(protected), "protected_unchanged": True,
                "browser_sla": "NOT_MEASURED", "status": "PASS"}
    atomic_json(evidence, ROOT / "audit/t0304_notebook_execution.json")


if __name__ == "__main__":
    main()