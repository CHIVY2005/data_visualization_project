"""WP04 Safety & Risk Monitor visualization modules — read-only artifact consumers.

Exported builders:
- build_ot_threshold_chart: OT continuous trajectory with 85°C/95°C hazard bands and breach pop-outs.
- build_barcode_rug: Compact temporal barcode strip locating warning and critical incidents.
- build_small_multiples: Six synchronized subplots for HUFL..LULL sharing an interactive time axis.
- build_scatter_loess: Joint scatter plot of OT vs load branch with non-linear LOESS smoothing curve.
- build_regime_boxplots: Distribution box plots partitioned by Normal, Warning, and Critical regimes.
"""

from src.visuals.story2.barcode_rug import build_barcode_rug
from src.visuals.story2.ot_threshold_chart import build_ot_threshold_chart
from src.visuals.story2.regime_boxplots import build_regime_boxplots
from src.visuals.story2.scatter_loess import build_scatter_loess
from src.visuals.story2.small_multiples import build_small_multiples

__all__ = [
    "build_barcode_rug",
    "build_ot_threshold_chart",
    "build_regime_boxplots",
    "build_scatter_loess",
    "build_small_multiples",
]
