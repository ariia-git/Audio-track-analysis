"""Small shared helpers without audio-library imports."""
from __future__ import annotations
import json
import math
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

def local_environment() -> None:
    cache = ROOT / "runtime/cache"
    paths = {"TEMP": cache / "tmp", "TMP": cache / "tmp", "MPLCONFIGDIR": cache / "matplotlib",
             "NUMBA_CACHE_DIR": cache / "numba", "HF_HOME": cache / "huggingface",
             "HUGGINGFACE_HUB_CACHE": cache / "huggingface/hub", "XDG_CACHE_HOME": cache,
             "PIP_CACHE_DIR": cache / "pip"}
    for key, path in paths.items():
        path.mkdir(parents=True, exist_ok=True)
        os.environ[key] = str(path)
    os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

def timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, rem = divmod(milliseconds, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}"

def parse_time(value: str | float) -> float:
    if isinstance(value, str) and ":" in value:
        fields = value.split(":")
        if len(fields) not in (2, 3):
            raise ValueError(f"Invalid timestamp: {value}")
        parts = [float(p) for p in fields]
        if any(p < 0 for p in parts) or any(p >= 60 for p in parts[1:]):
            raise ValueError(f"Invalid timestamp: {value}")
        result = sum(p * 60 ** i for i, p in enumerate(reversed(parts)))
    else:
        result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError("Timestamps must be finite and non-negative")
    return result

def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8-sig") as f:
        return json.load(f)

def write_json(path: Path, value: Any) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write("\n")

def inside_project(path: Path) -> Path:
    path = path.resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError(f"Project outputs must stay inside {ROOT}")
    return path
