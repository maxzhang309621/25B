"""附件读取、格式统一与审计。"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from config import ROOT, DatasetSpec


@dataclass
class Spectrum:
    wavenumber_cm1: np.ndarray
    reflectance_pct: np.ndarray
    spec: DatasetSpec
    audit: dict


def load_spectrum(data_dir: Path, spec: DatasetSpec) -> Spectrum:
    path = data_dir / spec.filename
    frame = pd.read_excel(path)
    if frame.shape[1] < 2:
        raise ValueError(f"{path} 至少需要两列")

    raw_x = pd.to_numeric(frame.iloc[:, 0], errors="coerce").to_numpy(float)
    raw_y = pd.to_numeric(frame.iloc[:, 1], errors="coerce").to_numpy(float)
    finite = np.isfinite(raw_x) & np.isfinite(raw_y)
    x, y = raw_x[finite], raw_y[finite]
    if len(x) < 20:
        raise ValueError(f"{path} 有效数据过少")

    order = np.argsort(x)
    x, y = x[order], y[order]
    unique = np.r_[True, np.diff(x) > 0]
    duplicate_count = int((~unique).sum())
    x, y = x[unique], y[unique]
    if np.any(np.diff(x) <= 0):
        raise ValueError(f"{path} 波数必须严格递增")

    first_zero = bool(y[0] == 0 and np.median(y[1:10]) > 1)
    if first_zero:
        x, y = x[1:], y[1:]

    try:
        source_path = path.relative_to(ROOT).as_posix()
    except ValueError:
        source_path = path.as_posix()

    audit = {
        "source": source_path,
        "rows_in_file": int(len(frame)),
        "valid_points": int(len(x)),
        "nonfinite_rows": int((~finite).sum()),
        "duplicate_wavenumbers": duplicate_count,
        "removed_first_zero": first_zero,
        "wavenumber_min_cm1": float(x.min()),
        "wavenumber_max_cm1": float(x.max()),
        "median_spacing_cm1": float(np.median(np.diff(x))),
        "reflectance_min_pct": float(y.min()),
        "reflectance_max_pct": float(y.max()),
    }
    return Spectrum(x, y, spec, audit)
