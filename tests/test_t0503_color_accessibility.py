"""T0503: Color Accessibility & WCAG 2.1 AA Compliance Tests.

Validates:
  - WCAG 2.1 relative luminance and contrast ratios on #FFFFFF.
  - Body text colors meet CR >= 4.5:1 (Level AA).
  - UI components and large text colors meet CR >= 3.0:1 (Level AA).
  - Colorblind safety: distinguishable under Protanopia, Deuteranopia, Tritanopia.
  - Prohibition of competing pure red/green pairs.
  - Non-color dual encoding on all critical/warning thresholds.

Dependencies: standard python libraries (math, colorsys). No GPU/Torch required.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    import pytest
except ImportError:
    class _MockMark:
        @staticmethod
        def parametrize(*args, **kwargs):
            def decorator(fn):
                return fn
            return decorator

    class _MockPytest:
        mark = _MockMark()

    pytest = _MockPytest()  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# WCAG 2.1 Mathematical Formulas
# ---------------------------------------------------------------------------

def _srgb_to_linear(c_srgb: float) -> float:
    """Convert 8-bit sRGB channel [0..255] normalized to [0..1] into linear light."""
    return c_srgb / 12.92 if c_srgb <= 0.04045 else ((c_srgb + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_code: str) -> float:
    """Calculate WCAG 2.1 relative luminance for a given hex color string."""
    h = hex_code.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"Expected 6-digit hex code, got: {hex_code}")
    r, g, b = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    r_lin = _srgb_to_linear(r)
    g_lin = _srgb_to_linear(g)
    b_lin = _srgb_to_linear(b)
    return 0.2126 * r_lin + 0.7152 * g_lin + 0.0722 * b_lin


def contrast_ratio(hex1: str, hex2: str) -> float:
    """Compute WCAG 2.1 contrast ratio between two hex colors: (L1 + 0.05) / (L2 + 0.05)."""
    l1 = relative_luminance(hex1)
    l2 = relative_luminance(hex2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


# ---------------------------------------------------------------------------
# Canonical Project Palette
# ---------------------------------------------------------------------------

PALETTE_TEXT_BODY = {
    "Slate-900 (Headings)": "#0F172A",
    "Slate-800 (Primary Text)": "#1E293B",
    "Navy (OT / Normal)": "#1E3A8A",
    "Crimson (Critical)": "#DC2626",
    "Slate-500 (Context/Muted)": "#64748B",
}

PALETTE_UI_GRAPHICAL = {
    "Teal (Useful Load)": "#0D9488",
    "Amber (Warning)": "#D97706",
}


# ---------------------------------------------------------------------------
# Test Suite: Contrast Ratio Verification
# ---------------------------------------------------------------------------

class TestWCAGContrastCompliance:
    """Verify all text and graphical colors meet WCAG 2.1 Level AA thresholds."""

    @pytest.mark.parametrize("name,hex_code", PALETTE_TEXT_BODY.items())
    def test_body_text_meets_wcag_aa(self, name: str, hex_code: str) -> None:
        """Body text must have contrast ratio >= 4.5:1 against white background."""
        cr = contrast_ratio(hex_code, "#FFFFFF")
        assert cr >= 4.5, (
            f"Color {name} ({hex_code}) failed WCAG AA normal text contrast: "
            f"got {cr:.2f}:1, expected >= 4.5:1"
        )

    @pytest.mark.parametrize("name,hex_code", PALETTE_UI_GRAPHICAL.items())
    def test_ui_graphical_meets_wcag_aa(self, name: str, hex_code: str) -> None:
        """UI graphical components / large strokes must have contrast ratio >= 3.0:1."""
        cr = contrast_ratio(hex_code, "#FFFFFF")
        assert cr >= 3.0, (
            f"Color {name} ({hex_code}) failed WCAG AA UI contrast: "
            f"got {cr:.2f}:1, expected >= 3.0:1"
        )

    def test_headings_meet_wcag_aaa(self) -> None:
        """Primary dark text must exceed AAA threshold (>= 7.0:1)."""
        cr_900 = contrast_ratio("#0F172A", "#FFFFFF")
        cr_800 = contrast_ratio("#1E293B", "#FFFFFF")
        assert cr_900 >= 7.0, f"#0F172A got {cr_900:.2f}:1, expected >= 7.0:1"
        assert cr_800 >= 7.0, f"#1E293B got {cr_800:.2f}:1, expected >= 7.0:1"


# ---------------------------------------------------------------------------
# Test Suite: Colorblind Safety & Differentiation
# ---------------------------------------------------------------------------

class TestColorblindSafety:
    """Verify differentiation under color vision deficiency (CVD)."""

    def test_no_competing_red_green_pair(self) -> None:
        """Strictly prohibit using green (#00FF00, #22C55E) for Normal vs red (#DC2626) for Hazard."""
        chart_file = ROOT / "src" / "visuals" / "charts_manager.py"
        safety_file = ROOT / "src" / "visuals" / "charts_safety.py"
        cm_text = chart_file.read_text(encoding="utf-8")
        cs_text = safety_file.read_text(encoding="utf-8")

        # Normal OT is Navy (blue-dominant #1E3A8A)
        assert '_COLOUR_OT = "#1E3A8A"' in cm_text
        # Warning is Amber #D97706
        assert '_COLOUR_WARN = "#D97706"' in cs_text
        # Critical is Crimson #DC2626
        assert '_COLOUR_CRIT = "#DC2626"' in cs_text
        # Useful load is Teal #0D9488
        assert '_COLOUR_USEFUL = "#0D9488"' in cm_text
        # Pure green is never used for normal status
        assert "#00FF00" not in cm_text and "#00FF00" not in cs_text
        assert "#22C55E" not in cm_text and "#22C55E" not in cs_text

    def test_luminance_separation_between_states(self) -> None:
        """State colors (Normal, Warning, Critical) must have distinct relative luminances."""
        l_normal = relative_luminance("#1E3A8A")   # Navy ~0.05
        l_warn = relative_luminance("#D97706")     # Amber ~0.28
        l_crit = relative_luminance("#DC2626")     # Crimson ~0.17

        # In monochromatic or grayscale mode, Navy, Amber, and Crimson must be distinguishable
        assert abs(l_normal - l_warn) > 0.15, "Normal and Warning must separate in luminance"
        assert abs(l_normal - l_crit) > 0.08, "Normal and Critical must separate in luminance"
        assert abs(l_warn - l_crit) > 0.08, "Warning and Critical must separate in luminance"


# ---------------------------------------------------------------------------
# Test Suite: Non-Color Dual Encoding Invariants
# ---------------------------------------------------------------------------

class TestNonColorDualEncoding:
    """Verify that hazard thresholds are never conveyed solely by color."""

    def test_dual_encoding_charts_safety(self) -> None:
        """OT threshold lines in charts_safety must have line styling and annotations."""
        safety_file = ROOT / "src" / "visuals" / "charts_safety.py"
        source = safety_file.read_text(encoding="utf-8")
        # Must include line dash style
        assert "dash" in source, "Threshold lines must use dash line style"
        # Must include explicit text annotations
        assert "85°C" in source or "Warning" in source
        assert "95°C" in source or "Critical" in source

    def test_dual_encoding_quantile_fan(self) -> None:
        """Quantile fan must include threshold horizontal lines with text callouts."""
        chart_file = ROOT / "src" / "visuals" / "charts_manager.py"
        source = chart_file.read_text(encoding="utf-8")
        assert "add_hline" in source, "Quantile fan must have horizontal threshold lines"
        assert "annotation_text" in source, "Threshold lines must have text annotations"


if __name__ == "__main__":
    test_contrast = TestWCAGContrastCompliance()
    for name, hex_code in PALETTE_TEXT_BODY.items():
        test_contrast.test_body_text_meets_wcag_aa(name, hex_code)
    for name, hex_code in PALETTE_UI_GRAPHICAL.items():
        test_contrast.test_ui_graphical_meets_wcag_aa(name, hex_code)
    test_contrast.test_headings_meet_wcag_aaa()

    test_cb = TestColorblindSafety()
    test_cb.test_no_competing_red_green_pair()
    test_cb.test_luminance_separation_between_states()

    test_dual = TestNonColorDualEncoding()
    test_dual.test_dual_encoding_charts_safety()
    test_dual.test_dual_encoding_quantile_fan()

    print("[PASS] All T0503 Color Accessibility & WCAG AA tests passed!")
