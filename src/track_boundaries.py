from __future__ import annotations
from pathlib import Path
import numpy as np
from scipy.signal import find_peaks
from .utils import read_json, parse_time
from .energy import robust_normalize, smooth

def novelty(features: dict, config: dict) -> np.ndarray:
    dt = config["audio"]["fine_interval"]
    half = max(1, round(config["sections"]["novelty_window_seconds"] / dt))
    names = ["spectral_centroid", "bass_energy", "high_energy", "onset_strength", "global_energy", "tempo_bpm", *[f"chroma_{i}" for i in range(12)]]
    contrasts = []
    for name in names:
        scaled, _ = robust_normalize(features[name])
        mean = smooth(scaled, half * dt, dt)
        left = mean[np.maximum(0, np.arange(len(mean)) - half//2)]
        right = mean[np.minimum(len(mean)-1, np.arange(len(mean)) + half//2)]
        contrasts.append(np.abs(right-left))
    raw = np.mean(contrasts, axis=0)
    # Keep magnitude meaningful; don't force a boundary in an unchanging mix.
    return np.clip(raw * 2, 0, 1)

def load_tracklist(path: Path, duration: float) -> list[dict]:
    data = read_json(path)
    if not isinstance(data, list) or not data:
        raise ValueError("Tracklist must be a nonempty JSON array")
    result = []
    for item in data:
        start = parse_time(item["start"])
        if start >= duration or (result and start <= result[-1]["start"]):
            raise ValueError("Track starts must be strictly increasing and inside audio duration")
        result.append({"name": str(item.get("name", f"Track {len(result)+1}")), "start": start, "confidence": 1.0, "source": "manual"})
    if result[0]["start"] > 0:
        result.insert(0, {"name": "Unspecified opening", "start": 0.0, "confidence": 1.0, "source": "manual"})
    return result

def detect(features: dict, duration: float, config: dict, manual: list[dict] | None) -> dict:
    c = config["boundaries"]
    dt = config["audio"]["fine_interval"]
    values = features["novelty"]
    peaks, props = find_peaks(values, height=c["sensitivity"], distance=max(1, round(c["minimum_seconds"] / dt)), prominence=c["sensitivity"] / 3)
    candidates = [{"start": float(features["timestamp_seconds"][i]), "confidence": float(values[i]), "source": "automatic", "name": "Transition candidate"} for i in peaks if c["minimum_seconds"] / 2 <= features["timestamp_seconds"][i] <= duration - c["minimum_seconds"] / 2]
    if manual is not None:
        selected = list(manual)
        if c["manual_mode"] == "combine":
            selected += [p for p in candidates if all(abs(p["start"]-m["start"]) >= c["minimum_seconds"] for m in manual)]
    else:
        selected = [{"start": 0.0, "name": "Mix start", "confidence": 1.0, "source": "origin"}, *candidates]
    selected = sorted(selected, key=lambda p: p["start"])
    return {"method": "Local before/after timbre, chroma, rhythm, tempo and energy novelty; no source-track identification",
            "confidence_definition": "Heuristic normalized contrast, not calibrated probability", "manual_mode": c["manual_mode"],
            "candidates": candidates, "boundaries": selected}
