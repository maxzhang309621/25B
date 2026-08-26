"""项目配置与数据集元信息。"""

from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"


@dataclass(frozen=True)
class DatasetSpec:
    key: str
    filename: str
    material: str
    angle_deg: float
    refractive_index: float
    fit_band_cm1: tuple[float, float]


DATASETS = (
    DatasetSpec("sic_10", "附件1.xlsx", "SiC", 10.0, 2.55, (1100.0, 4000.0)),
    DatasetSpec("sic_15", "附件2.xlsx", "SiC", 15.0, 2.55, (1100.0, 4000.0)),
    DatasetSpec("si_10", "附件3.xlsx", "Si", 10.0, 3.42, (1000.0, 4000.0)),
    DatasetSpec("si_15", "附件4.xlsx", "Si", 15.0, 3.42, (1000.0, 4000.0)),
)

# 以波数宽度定义窗口，程序根据采样间隔转换为奇数点数。
NOISE_WINDOW_CM1 = 10.0
BASELINE_WINDOW_CM1 = 430.0
BOOTSTRAP_BLOCK_CM1 = 80.0
RANDOM_SEED = 2025
