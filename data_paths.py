import os
from dataclasses import dataclass
from pathlib import Path


ENV_NAME = "LOL_DATA_ROOT"
REPOSITORY_ROOT = Path(__file__).resolve().parent
DEFAULT_DATA_ROOT = REPOSITORY_ROOT / "data"


@dataclass(frozen=True)
class DataPaths:
    root: Path
    raw: Path
    csv: Path
    excel: Path


def resolve_data_root(explicit=None, environ=None):
    if explicit is not None:
        return Path(explicit).expanduser().resolve()
    environment = os.environ if environ is None else environ
    configured = environment.get(ENV_NAME)
    if configured:
        return Path(configured).expanduser().resolve()
    return DEFAULT_DATA_ROOT


def get_data_paths(explicit=None, environ=None):
    root = resolve_data_root(explicit, environ)
    return DataPaths(root=root, raw=root / "raw", csv=root / "csv", excel=root / "excel")


DATA_ROOT = resolve_data_root()
RAW_ROOT = DATA_ROOT / "raw"
CSV_ROOT = DATA_ROOT / "csv"
EXCEL_ROOT = DATA_ROOT / "excel"
