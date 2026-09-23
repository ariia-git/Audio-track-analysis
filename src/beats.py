"""Windowed beat tracking; bar phase is explicitly a 4/4-style heuristic."""
from __future__ import annotations
import logging
import numpy as np
from scipy.ndimage import uniform_filter1d

LOG = logging.getLogger(__name__)

def detect(onset: np.ndarray, features: dict, duration: float, config: dict) -> dict:
    import librosa
    a, b = config["audio"], config["beats"]
    fps = a["sample_rate"] / a["hop_length"]
    width = max(4, round(b["window_seconds"] * fps))
    overlap = round(b["overlap_seconds"] * fps)
    stride = width - 2 * overlap
    points, windows = [], []
    warnings = []
    for core_start in range(0, len(onset), stride):
        core_end = min(len(onset), core_start + stride)
        start, end = max(0, core_start - overlap), min(len(onset), core_end + overlap)
        envelope = onset[start:end]
        if len(envelope) < 8 or np.max(envelope) < 1e-7:
            continue
        try:
            tempo, frames = librosa.beat.beat_track(onset_envelope=envelope, sr=a["sample_rate"], hop_length=a["hop_length"], start_bpm=b["start_bpm"], trim=True)
            bpm = float(np.asarray(tempo).reshape(-1)[0])
            absolute = np.asarray(frames, dtype=int) + start
            absolute = absolute[(absolute >= core_start) & (absolute < core_end)]
            if len(absolute) < 2 or bpm <= 0:
                continue
            intervals = np.diff(absolute) / fps
            regularity = np.exp(-np.std(intervals) / max(np.mean(intervals), 1e-6))
            support = np.mean(onset[absolute]) / max(float(np.percentile(envelope, 95)), 1e-8)
            confidence = float(np.clip(regularity * support, 0, 1))
            windows.append({"start": core_start / fps, "end": min(duration, core_end / fps), "bpm": bpm, "confidence": confidence})
            for index in absolute:
                time = float(index / fps)
                # Windows can choose different phases. Suppress implausibly close seam beats.
                if points and time - points[-1]["time"] < 0.4 * 60 / bpm:
                    continue
                if np.interp(time, features["timestamp_seconds"], features["rms"]) < 10 ** (a["silence_db"] / 20):
                    continue
                points.append({"time": time, "confidence": confidence, "bpm": bpm})
        except Exception as exc:
            LOG.warning("Beat window failed at %.1fs: %s", core_start / fps, exc)
            warnings.append(str(exc))
    # Choose bar phase from bass accents. There is no meter or true downbeat model.
    meter = b["beats_per_bar"]
    scores = [np.mean([np.interp(p["time"], features["timestamp_seconds"], features["bass_energy"]) for p in points[offset::meter]]) if points[offset::meter] else 0 for offset in range(meter)]
    offset = int(np.argmax(scores))
    bars = [{"time": p["time"], "confidence": min(0.45, p["confidence"] * 0.5), "heuristic": True} for i, p in enumerate(points) if i % meter == offset]
    t = features["timestamp_seconds"]
    dt = a["fine_interval"]
    bins = np.minimum((np.array([p["time"] for p in points]) / dt).astype(int), len(t) - 1)
    features["beat_density"] = uniform_filter1d(np.bincount(bins, minlength=len(t)).astype(float) / dt, max(1, round(config["energy"]["micro_seconds"] / dt)), mode="nearest")
    features["tempo_bpm"] = np.zeros(len(t))
    for w in windows:
        features["tempo_bpm"][(t >= w["start"]) & (t < w["end"])] = w["bpm"]
    return {"method": "librosa dynamic programming in overlapping windows", "confidence_definition": "Heuristic onset support times interval regularity; not calibrated probability",
            "beats": points, "tempo_windows": windows, "downbeats": bars, "bars": bars,
            "phrases": bars[::b["bars_per_phrase"]], "onsets": [], "warnings": warnings,
            "bar_method": f"Heuristic bass-accent phase, assumes {meter} beats per bar; not reliable meter/downbeat detection"}
