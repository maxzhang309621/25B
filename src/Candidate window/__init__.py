"""透明波段候选窗评分与自动选取。"""

import sys
from pathlib import Path

_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from band_select import (  # noqa: E402
    BandScore,
    CANDIDATE_BANDS_SI,
    CANDIDATE_BANDS_SIC,
    build_sensitivity_rows,
    select_band,
)

try:
    from band_analysis import run_band_analysis  # noqa: E402
except ImportError:
    run_band_analysis = None  # type: ignore[misc, assignment]

__all__ = [
    "BandScore",
    "CANDIDATE_BANDS_SIC",
    "CANDIDATE_BANDS_SI",
    "build_sensitivity_rows",
    "run_band_analysis",
    "select_band",
]
