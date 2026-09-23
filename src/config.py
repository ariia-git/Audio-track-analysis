from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import math
from .utils import ROOT, read_json

def merge(base: dict, override: dict) -> dict:
    result = deepcopy(base)
    for key, value in override.items():
        if key not in base:
            raise ValueError(f"Unknown configuration key: {key}")
        if isinstance(base[key], dict):
            if not isinstance(value, dict):
                raise ValueError(f"{key} must be an object")
            result[key] = merge(base[key], value)
        else:
            result[key] = value
    return result

def load_config(path: Path | None = None, interval: float | None = None) -> dict:
    config = read_json(ROOT / "config/default.json")
    if path:
        config = merge(config, read_json(path))
    if interval is not None:
        config["interval"] = interval
    validate(config)
    return config

def validate(c: dict) -> None:
    def positive(value, name):
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be a finite positive number")
    positive(c["interval"], "interval")
    for group in ("audio", "energy", "beats", "sections", "boundaries", "video"):
        for key, val in c[group].items():
            if isinstance(val, (float, int)) and key != "silence_db":
                positive(val, f"{group}.{key}")
    for key in ("sample_rate", "n_fft", "hop_length"):
        if not isinstance(c["audio"][key], int):
            raise ValueError(f"audio.{key} must be an integer")
    for key in ("beats_per_bar", "bars_per_phrase"):
        if not isinstance(c["beats"][key], int):
            raise ValueError(f"beats.{key} must be an integer")
    if not 8000 <= c["audio"]["sample_rate"] <= 48000:
        raise ValueError("sample_rate must be between 8000 and 48000")
    if c["audio"]["hop_length"] > c["audio"]["n_fft"]:
        raise ValueError("hop_length cannot exceed n_fft")
    if c["audio"]["fine_interval"] > c["interval"]:
        raise ValueError("interval cannot be shorter than audio.fine_interval")
    if c["beats"]["overlap_seconds"] >= c["beats"]["window_seconds"] / 2:
        raise ValueError("Beat overlap must be less than half the window")
    lo, hi = c["energy"]["percentiles"]
    if not 0 <= lo < hi <= 100:
        raise ValueError("Invalid normalization percentiles")
    weights = c["energy"]["weights"]
    if any(not isinstance(w, (float, int)) or not math.isfinite(w) or w < 0 for w in weights.values()) or sum(weights.values()) <= 0:
        raise ValueError("Energy weights must be non-negative with positive sum")
    if c["video"]["shot_min_seconds"] > c["video"]["shot_max_seconds"]:
        raise ValueError("Minimum shot duration exceeds maximum")
    for key in ("camera", "beat_sync"):
        if not 0 <= c["video"][f"{key}_min"] <= c["video"][f"{key}_max"] <= 1:
            raise ValueError(f"Invalid {key} mapping range")
    if c["boundaries"]["manual_mode"] not in ("replace", "combine"):
        raise ValueError("manual_mode must be replace or combine")
    for group, keys in {"sections": ("sensitivity", "peak_percentile", "high_threshold", "breakdown_threshold", "drop_jump"), "boundaries": ("sensitivity",)}.items():
        if any(c[group][key] > 1 for key in keys):
            raise ValueError(f"{group} thresholds must be in (0, 1]")
