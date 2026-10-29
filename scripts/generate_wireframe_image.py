"""Generate editable Draw.io and matching 300-DPI PNG from one layout model.

All chart marks are schematic, not observed ETT measurements. No data is read.
Only docs/wireframes/story1_story2_layout.{drawio,png} are written.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/wireframes"
WIDTH, HEIGHT, SCALE = 2440, 1720, 3
NAVY, TEAL, SLATE = "#1E3A8A", "#0D9488", "#64748B"
AMBER, CRIMSON, GRID = "#D97706", "#DC2626", "#E2E8F0"
INK, MUTED, PAPER = "#0F172A", "#475569", "#F1F5F9"
SEED = 2026  # Layout is deterministic and does not require random sampling.


class Canvas:
    """Shared vector primitives for raster rendering and editable mxCells."""

    def __init__(self) -> None:
        self.image = Image.new("RGB", (WIDTH * SCALE, HEIGHT * SCALE), PAPER)
        self.draw = ImageDraw.Draw(self.image)
        self.xml = ET.Element("mxfile", host="app.diagrams.net", version="24.7.17")
        diagram = ET.SubElement(self.xml, "diagram", id="ett-v2", name="Story 1 + Story 2")
        model = ET.SubElement(diagram, "mxGraphModel", dx=str(WIDTH), dy=str(HEIGHT),
                              grid="1", gridSize="10", page="1", pageScale="1",
                              pageWidth=str(WIDTH), pageHeight=str(HEIGHT))
        self.root = ET.SubElement(model, "root")
        ET.SubElement(self.root, "mxCell", id="0")
        ET.SubElement(self.root, "mxCell", id="1", parent="0")
        self.counter = 1
        self.parent = "1"
        self.origin = (0.0, 0.0)
        font_dir = Path("C:/Windows/Fonts")
        self.fonts = {
            (size, bold): ImageFont.truetype(
                str(font_dir / ("arialbd.ttf" if bold else "arial.ttf")), size * SCALE)
            for size in (10, 11, 12, 13, 14, 15, 16, 18, 20, 24, 26, 30)
            for bold in (False, True)
        }

    def cell(self, value: str, style: str, x: float, y: float,
             w: float, h: float) -> str:
        self.counter += 1
        identifier = str(self.counter)
        cell = ET.SubElement(self.root, "mxCell", id=identifier, value=value,
                             style=style, vertex="1", parent=self.parent)
        ox, oy = self.origin
        ET.SubElement(cell, "mxGeometry", x=str(x - ox), y=str(y - oy),
                      width=str(w), height=str(h), **{"as": "geometry"})
        return identifier

    def box(self, x: float, y: float, w: float, h: float,
            fill: str = "#FFFFFF", border: str = GRID, radius: int = 10) -> str:
        bounds = tuple(round(v * SCALE) for v in (x, y, x + w, y + h))
        self.draw.rounded_rectangle(bounds, radius=radius * SCALE,
                                    fill=fill, outline=border, width=SCALE)
        return self.cell("", f"rounded={int(radius > 0)};arcSize=6;fillColor={fill};"
                         f"strokeColor={border};shadow=0;", x, y, w, h)

    def text(self, x: float, y: float, value: str, size: int = 14,
             color: str = INK, bold: bool = False, width: float = 1000) -> None:
        font = self.fonts[size, bold]
        for index, line in enumerate(value.split("\n")):
            if self.draw.textlength(line, font=font) > width * SCALE:
                raise ValueError(f"Text overflows allocated width: {line}")
            self.draw.text((x * SCALE, (y + index * (size + 5)) * SCALE),
                           line, fill=color, font=font)
        self.cell(value, f"text;html=0;whiteSpace=wrap;align=left;verticalAlign=top;"
                  f"fontFamily=Arial;fontSize={size};fontColor={color};"
                  f"fontStyle={int(bold)};spacing=0;strokeColor=none;fillColor=none;",
                  x, y, width, len(value.split("\n")) * (size + 5))

    def line(self, points: list[tuple[float, float]], color: str = NAVY,
             weight: int = 2, dashed: bool = False) -> None:
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            if dashed:
                length = math.hypot(x2 - x1, y2 - y1)
                steps = max(1, int(length / 7))
                for step in range(0, steps, 2):
                    a, b = step / steps, min(1, (step + 1) / steps)
                    self.draw.line([(SCALE * (x1 + a * (x2 - x1)),
                                     SCALE * (y1 + a * (y2 - y1))),
                                    (SCALE * (x1 + b * (x2 - x1)),
                                     SCALE * (y1 + b * (y2 - y1)))],
                                   fill=color, width=weight * SCALE)
            else:
                self.draw.line([(x1 * SCALE, y1 * SCALE), (x2 * SCALE, y2 * SCALE)],
                               fill=color, width=weight * SCALE)
            self.counter += 1
            edge = ET.SubElement(self.root, "mxCell", id=str(self.counter), edge="1",
                                 parent=self.parent, style=f"endArrow=none;"
                                 f"strokeColor={color};strokeWidth={weight};"
                                 f"dashed={int(dashed)};")
            geometry = ET.SubElement(edge, "mxGeometry", relative="1", **{"as": "geometry"})
            ox, oy = self.origin
            ET.SubElement(geometry, "mxPoint", x=str(x1 - ox), y=str(y1 - oy),
                          **{"as": "sourcePoint"})
            ET.SubElement(geometry, "mxPoint", x=str(x2 - ox), y=str(y2 - oy),
                          **{"as": "targetPoint"})


def chart(c: Canvas, x: int, y: int, w: int, h: int,
          title: str, subtitle: str) -> tuple[int, int, int, int]:
    c.box(x, y, w, h)
    c.text(x + 16, y + 13, title, 15, bold=True, width=w - 32)
    c.text(x + 16, y + 38, subtitle, 11, MUTED, width=w - 32)
    return x + 20, y + 70, w - 40, h - 100


def wave(c: Canvas, x: float, y: float, w: float, h: float,
         color: str = NAVY, phase: float = 0, dashed: bool = False) -> None:
    points = [(x + w * i / 32, y + h * (0.5 + 0.28 * math.sin(i / 5 + phase)))
              for i in range(33)]
    c.line(points, color, dashed=dashed)


def sidebar(c: Canvas, x: int, y: int, story: int) -> None:
    c.box(x, y, 190, 1380, "#F8FAFC")
    c.text(x + 14, y + 18, "THIẾT BỊ / BỘ LỌC", 13, bold=True, width=170)
    fields = ["Dataset", "ETTh1 / ETTh2 / ETTm1", "Khu vực: Chưa xác minh",
              "Điện áp: Chưa xác minh", "Mùa quy ước: All / Dry / Wet",
              "Khoảng ngày: [Bắt đầu - Kết thúc]", "Biến: OT / HUFL ... LULL"]
    for i, label in enumerate(fields):
        c.text(x + 14, y + 58 + i * 31, label, 11, MUTED, width=168)
    c.line([(x + 14, y + 295), (x + 174, y + 295)], GRID, 1)
    c.text(x + 14, y + 316, "ĐIỀU HƯỚNG", 13, bold=True, width=170)
    labels = (["01  Chu kỳ & phân vị", "02  Phân rã STL", "03  Cơ cấu tải", "04  Tương quan trễ"]
              if story == 1 else ["01  OT & sự kiện", "02  Sáu nhánh tải", "03  LOESS tham chiếu",
                                  "04  Chế độ nhiệt", "Ngưỡng: ≥85 / ≥95°C", "Brush / Zoom / Reset"])
    for i, label in enumerate(labels):
        c.box(x + 10, y + 353 + i * 46, 170, 35,
              "#DBEAFE" if i == 0 else "#FFFFFF", border=GRID, radius=5)
        c.text(x + 19, y + 362 + i * 46, label, 11, NAVY, width=152)
    c.text(x + 14, y + 720, "QUY TẮC PHẠM VI", 12, bold=True, width=170)
    c.text(x + 14, y + 754, "Observed / STL: theo ngày\nEvents: đợt đầy đủ trong scope\nFan / Lag / LOESS:\ntham chiếu lịch sử đã lưu\nKhông fit lại trên luồng UI\n\nDry/Wet: nhóm tháng dự án\nKhông suy khí hậu địa phương\n\nThiếu dữ liệu: N/A / Unknown\nKhông biến null thành 0", 11,
           MUTED, width=168)


def panel(c: Canvas, x: int, story: int) -> None:
    y, w = 100, 1170
    group = c.box(x, y, w, 1540, border="#CBD5E1", radius=12)
    c.parent, c.origin = group, (x, y)
    c.box(x, y, w, 115, "#0F172A", "#0F172A", radius=0)
    title = ("Giám sát Vận hành & Phụ tải Lưới điện ETT" if story == 1 else
             "Giám sát An toàn & Cảnh báo Sự cố Nhiệt ETT")
    subtitle = ("Quy luật chu kỳ, hiệu suất tải hữu ích & độ trễ quán tính nhiệt" if story == 1
                else "Ngưỡng 85°C/95°C, áp lực nhiệt tích lũy & phân tích đa biến")
    c.text(x + 20, y + 18, f"STORY {story}  /  {'OPERATIONAL MANAGER' if story == 1 else 'SAFETY & RISK MONITOR'}",
           12, "#93C5FD", bold=True, width=870)
    c.text(x + 20, y + 42, title, 24, "#FFFFFF", bold=True, width=1120)
    c.text(x + 20, y + 81, subtitle, 13, "#CBD5E1", width=900)
    c.text(x + 934, y + 86, "Thời gian: [Từ] → [Đến]", 11, "#FFFFFF", width=215)
    sidebar(c, x + 14, y + 132, story)
    cx, cy, cw = x + 222, y + 132, 932
    kpis = (["OT Trung bình (°C)", "Đỉnh OT Max (°C)", "Tỷ lệ vô công TB (%)", "Lag |r| lớn nhất (h)"]
            if story == 1 else ["Số đợt ≥85°C", "Số đợt ≥95°C", "Thời lượng quá nhiệt (h)", "Degree-Hours (°C·h)"])
    for i, label in enumerate(kpis):
        kx = cx + i * 237
        c.box(kx, cy, 220, 100, border=GRID)
        c.text(kx + 12, cy + 13, label, 13, MUTED, width=198)
        c.text(kx + 12, cy + 40, "[Giá trị / N/A]", 20,
               NAVY if story == 1 else (AMBER if i == 0 else CRIMSON if i == 1 else NAVY),
               bold=True, width=198)
        note = ("Theo phạm vi / cỡ mẫu" if story == 1 else
                "Ngưỡng đang chọn; không cộng chồng" if i > 1 else "Đếm riêng theo ngưỡng")
        c.text(kx + 12, cy + 77, note, 10, MUTED, width=198)
    if story == 1:
        story1(c, cx, cy + 119, cw)
    else:
        story2(c, cx, cy + 119, cw)
    c.text(cx, y + 1474, "DỮ LIỆU LỊCH SỬ · Ngưỡng 85/95°C là quy ước dự án · Không phải hệ thống an toàn chứng nhận",
           11, MUTED, width=cw)
    c.text(cx, y + 1498, "Tất cả đường/điểm trong bản vẽ là minh họa bố cục, không phải kết quả ETT. Không suy nhân quả.",
           11, MUTED, width=cw)
    c.parent, c.origin = "1", (0, 0)


def story1(c: Canvas, x: int, y: int, w: int) -> None:
    px, py, pw, ph = chart(c, x, y, 602, 345, "Chu kỳ 24h & biến thiên lịch sử cần được đối chiếu",
                            "Hourly Profile + Quantile Fan | median / mean riêng | không phải prediction interval")
    for j, color in enumerate(("#EFF6FF", "#DBEAFE", "#BFDBFE")):
        c.box(px, py + 20 + j * 21, pw, ph - 40 - j * 42, color, color, 0)
    wave(c, px, py, pw, ph, NAVY)
    wave(c, px, py, pw, ph, SLATE, 0.15, True)
    c.text(px, py + ph + 6, "00h                         12h                         23h   |  50% / 80% / 95%",
           11, MUTED, width=pw)
    hx, hy, hw, hh = chart(c, x + 618, y, 314, 345, "Phụ tải theo Ngày × Tuần",
                            "Calendar Heatmap | cùng biến / dataset")
    for row in range(7):
        for col in range(12):
            colors = ("#EFF6FF", "#DBEAFE", "#93C5FD", NAVY)
            c.box(hx + col * 22, hy + row * 26, 18, 20,
                  colors[(row * 3 + col) % 4], "#FFFFFF", 0)
    c.text(hx, hy + 198, "T2 → CN  /  Tuần →\nOT: chỉ Amber ≥85; Crimson ≥95", 11, MUTED, width=hw)
    titles = [("STL: trend / seasonal / residual", "Chu kỳ ngày: 24 mẫu / 96 mẫu"),
              ("So sánh cơ cấu useful / unuseful", "100% Stacked Bar | H / M / L"),
              ("Tải đi trước OT bao nhiêu giờ?", "Lag Heatmap | corr(load(t), OT(t+k))")]
    for i, (title, subtitle) in enumerate(titles):
        ax, ay, aw, ah = chart(c, x + i * 316, y + 362, 300, 350, title, subtitle)
        if i == 0:
            for row, label in enumerate(("Trend", "Seasonal", "Residual")):
                c.text(ax, ay + row * 74, label, 11, SLATE, width=aw)
                wave(c, ax, ay + row * 74 + 17, aw, 40, NAVY, row)
        elif i == 1:
            for j, ratio in enumerate((0.7, 0.5, 0.8)):
                c.box(ax + j * 82 + 10, ay, 48, ah * ratio, TEAL, TEAL, 0)
                c.box(ax + j * 82 + 10, ay + ah * ratio, 48, ah * (1 - ratio), SLATE, SLATE, 0)
                c.text(ax + j * 82 + 18, ay + ah + 8, ("H", "M", "L")[j], 11, MUTED, width=40)
        else:
            for row in range(6):
                for col in range(13):
                    colors = ("#F8FAFC", "#DBEAFE", "#93C5FD", "#1E3A8A", "#EBCDAA")
                    c.box(ax + col * 19, ay + row * 30, 17, 26,
                          colors[(col + row * 2) % 5], "#FFFFFF", 0)
            c.text(ax, ay + 196, "6 tải × 13 lags  |  0h → 12h\nDiverging palette: không mã cảnh báo", 11, MUTED, width=aw)
    chart(c, x, y + 730, w, 155, "What → Why → How / Story 1",
          "Dữ liệu: tải / OT / giờ / mùa  →  tác vụ: chu kỳ, cơ cấu, lag  →  encoding: position, length, heatmap")
    c.text(x + 20, y + 802, "• Composition: tải âm / mẫu số ≤0 → null + chú thích chất lượng; không clip về 0.\n"
           "• “Lag tối ưu” chỉ là lag có |r| lớn nhất theo phạm vi/phương pháp; không phải khuyến nghị điều khiển.\n"
           "• Tỷ lệ vô công là ratio từ nhãn nguồn useful/unuseful; không mặc nhiên P/Q đã hiệu chuẩn.",
           12, MUTED, width=w - 40)
    c.box(x, y + 905, w, 215, "#F8FAFC")
    c.text(x + 20, y + 924, "NGUYÊN TẮC BỐ CỤC / TƯƠNG TÁC", 14, NAVY, True, w - 40)
    c.text(x + 20, y + 960, "Gestalt proximity: 4 KPI liên quan cùng hàng; alignment: lưới và trục thẳng hàng.\n"
           "Similarity: useful = Teal, bối cảnh = Slate; enclosure: dải phân vị, không trang trí 3D/shadow.\n"
           "Tufte: chỉ lưới chính nhẹ; direct labels khi đủ chỗ; tiêu đề insight phải sinh từ dữ liệu đang lọc.\n"
           "Accessibility: chữ tối trên nền sáng; thêm nhãn/dash, không truyền trạng thái chỉ bằng màu.\n"
           "Mỗi ô là vùng xem mục tiêu; runtime có thể dùng view selector/lazy render để bảo vệ SLA.",
           13, MUTED, width=w - 40)


def story2(c: Canvas, x: int, y: int, w: int) -> None:
    ax, ay, aw, ah = chart(c, x, y, w, 270, "Định vị OT vượt ngưỡng và thời gian quan sát được",
                            "OT Threshold Line | dashed 85°C / dotted 95°C | selected threshold / half-open event support")
    c.box(ax, ay + 12, aw, 30, "#FDE9E7", "#FDE9E7", 0)
    c.box(ax, ay + 42, aw, 30, "#FEF3C7", "#FEF3C7", 0)
    c.line([(ax, ay + 42), (ax + aw, ay + 42)], CRIMSON, dashed=True)
    c.line([(ax, ay + 72), (ax + aw, ay + 72)], AMBER, dashed=True)
    wave(c, ax, ay + 25, aw * 0.45, ah - 20)
    wave(c, ax + aw * 0.52, ay + 25, aw * 0.48, ah - 20, phase=2)
    c.text(ax + 365, ay + 110, "gap: không nối nét", 11, SLATE, width=200)
    c.text(ax + aw - 100, ay + 20, "95°C Critical", 11, CRIMSON, width=100)
    c.text(ax + aw - 100, ay + 75, "85°C Warning", 11, "#92400E", width=100)
    c.box(x, y + 278, w, 50)
    c.text(x + 14, y + 292, "BARCODE / RUG", 11, MUTED, True, 150)
    for j in (190, 196, 201, 390, 398, 610, 618, 625, 820):
        c.line([(x + j, y + 288), (x + j, y + 314)],
               CRIMSON if j in (398, 625) else AMBER, 2)
    c.text(x + 18, y + 345, "SÁU NHÁNH TẢI — cùng trục thời gian / brush / zoom", 15, bold=True, width=w - 36)
    c.box(x, y + 378, w, 388)
    for i, label in enumerate(("HUFL", "HULL", "MUFL", "MULL", "LUFL", "LULL")):
        by = y + 389 + i * 59
        c.text(x + 16, by + 10, label, 12, MUTED, True, 70)
        c.line([(x + 85, by + 43), (x + w - 20, by + 43)], GRID, 1)
        wave(c, x + 90, by, w - 120, 42, TEAL if i % 2 == 0 else SLATE, i * 0.5)
        c.box(x + 610, by, 70, 43, "#F1F5F9", "#F1F5F9", 0)
    c.text(x + 92, y + 746, "[Brush time window]  ←  shared X / selection  →  [Reset]", 11, NAVY, width=w - 110)
    sx, sy, sw, sh = chart(c, x, y + 785, 458, 260, "Đối chiếu tải–OT với LOESS đã tiền tính",
                            "Joint Scatter + offline LOESS reference | không suy nhân quả")
    for i in range(45):
        px = sx + 12 + (i * 47 % int(sw - 24))
        py = sy + 15 + (i * 31 % int(sh - 25))
        c.box(px, py, 4, 4, "#94A3B8", "#94A3B8", 2)
    wave(c, sx, sy, sw, sh, NAVY, 1)
    bx, by, bw, bh = chart(c, x + 474, y + 785, 458, 260, "So sánh phân phối theo thermal regime",
                            "Regime Boxplots | Normal / Warning / Critical; Unknown riêng")
    for i, (label, color) in enumerate((("Normal", NAVY), ("Warning", AMBER), ("Critical", CRIMSON))):
        xx = bx + 35 + i * 125
        c.line([(xx + 25, by + 5), (xx + 25, by + bh - 15)], color)
        c.box(xx, by + 32 + i * 5, 50, 60, "#FFFFFF", color, 0)
        c.line([(xx, by + 62 + i * 5), (xx + 50, by + 62 + i * 5)], color)
        c.text(xx - 7, by + bh + 2, label, 11, MUTED, width=100)
    c.text(x + 16, y + 1063, "What: OT + events + 6 tải   |   Why: phát hiện / đối chiếu giả thuyết   |   How: shared X + enclosure + pop-out",
           12, MUTED, width=w - 32)
    c.text(x + 16, y + 1090, "KPI duration / Degree-Hours dùng ngưỡng đang chọn; 85°C và 95°C báo riêng, không cộng chồng.\n"
           "Không có sự kiện thực → hiển thị “Không có sự kiện”; không tạo breach giả để lấp bố cục.",
           12, MUTED, width=w - 32)


def main() -> None:
    """Write only the two approved wireframe deliverables."""
    canvas = Canvas()
    canvas.text(35, 18, "ETT_GRID_VIS_2026 / T0301 — WIREFRAME V2.0", 26, NAVY, True, 2300)
    canvas.text(35, 57, "Overview first → zoom & filter → details-on-demand  |  Bố cục mục tiêu, không phải screenshot hay dữ liệu thực",
                15, MUTED, width=2330)
    panel(canvas, 30, 1)
    panel(canvas, 1240, 2)
    canvas.text(35, 1668, "Design contract: artifact-only UI · shared filter scope · historical reference labels · source physical units · no fake insights",
                14, MUTED, width=2330)
    OUT.mkdir(parents=True, exist_ok=True)
    ET.indent(canvas.xml, space="  ")
    ET.ElementTree(canvas.xml).write(OUT / "story1_story2_layout.drawio",
                                    encoding="utf-8", xml_declaration=True)
    canvas.image.save(OUT / "story1_story2_layout.png", dpi=(300, 300))
    print("CREATED", OUT, canvas.image.size, "300 DPI; editable mxCells:", canvas.counter)


if __name__ == "__main__":
    main()