from __future__ import annotations
import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.stats import rankdata

def robust_normalize(values: np.ndarray, percentiles=(5, 95)) -> tuple[np.ndarray, dict]:
    values = np.nan_to_num(np.asarray(values, dtype=float))
    lo, hi = np.percentile(values, percentiles)
    if hi - lo < 1e-10:
        # A constant feature cannot supply relative intensity evidence.
        normalized = np.zeros_like(values)
    else:
        normalized = np.clip((values - lo) / (hi - lo), 0, 1)
    return normalized, {"low": float(lo), "high": float(hi), "percentiles": list(percentiles), "constant": bool(hi - lo < 1e-10)}

def smooth(values: np.ndarray, seconds: float, dt: float) -> np.ndarray:
    return uniform_filter1d(values, max(1, round(seconds / dt)), mode="nearest")

def calculate(features: dict, config: dict) -> dict:
    c = config["energy"]
    dt = config["audio"]["fine_interval"]
    normalized, metadata = {}, {}
    names = set(c["weights"]) | {"onset_strength", "transient_density", "spectral_centroid", "high_energy", "spectral_flux"}
    for name in names:
        data = features[name]
        # Dynamic compression of positive amplitude/density features before full-mix scaling.
        transform = "identity" if name in ("loudness", "spectral_centroid") else "log1p(100*x)"
        value = data if transform == "identity" else np.log1p(100 * np.maximum(data, 0))
        normalized[name], metadata[name] = robust_normalize(value, c["percentiles"])
        metadata[name]["transform"] = transform
    score = sum(normalized[name] * weight for name, weight in c["weights"].items()) / sum(c["weights"].values())
    # Silence gating also suppresses the rank of numerically tiny noise in silent files.
    db = 20 * np.log10(np.maximum(features["rms"], 1e-12))
    gate = np.clip((db - config["audio"]["silence_db"]) / 12, 0, 1)
    score = np.clip(score * gate, 0, 1)
    features["global_energy"] = score
    features["smoothed_energy"] = smooth(score, c["phrase_seconds"], dt)
    features["micro_energy"] = smooth(score, c["micro_seconds"], dt)
    features["macro_energy"] = smooth(score, c["macro_seconds"], dt)
    # Rolling percentiles at a sparse grid avoid O(frames * rolling-window) storage.
    half = max(1, round(c["local_seconds"] / dt / 2))
    anchors = np.unique(np.r_[np.arange(0, len(score), max(1, round(1 / dt))), len(score)-1])
    limits = np.array([np.percentile(score[max(0, i-half):min(len(score), i+half+1)], c["percentiles"]) for i in anchors])
    low = np.interp(np.arange(len(score)), anchors, limits[:, 0])
    high = np.interp(np.arange(len(score)), anchors, limits[:, 1])
    features["local_energy"] = np.clip((score - low) / np.maximum(high-low, 1e-8), 0, 1) * gate
    features["energy_percentile"] = (rankdata(score, method="average") - 1) / max(len(score)-1, 1) * gate
    t = features["timestamp_seconds"]
    delta_span = c["delta_seconds"]
    curve = features["smoothed_energy"]
    features["energy_delta"] = (np.interp(t+delta_span/2, t, curve) - np.interp(t-delta_span/2, t, curve)) / delta_span
    features["rhythmic_intensity"] = (0.6 * normalized["onset_strength"] + 0.4 * normalized["transient_density"]) * gate
    features["spectral_intensity"] = (0.5 * normalized["spectral_centroid"] + 0.3 * normalized["high_energy"] + 0.2 * normalized["spectral_flux"]) * gate
    return metadata
