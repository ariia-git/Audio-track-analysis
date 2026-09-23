"""Contextual semantic labels, deliberately conservative about drops."""
from __future__ import annotations
import numpy as np
from scipy.signal import find_peaks

def classify(energy: float, percentile: float, slope: float, previous: float, jump: float,
             prior_rise: float, novelty: float, position: float, config: dict) -> tuple[str, float]:
    c = config["sections"]
    if jump >= c["drop_jump"] and prior_rise >= c["build_threshold"] and energy > c["high_threshold"]:
        return "drop", min(0.9, 0.55 + jump)
    if energy < c["breakdown_threshold"]:
        if position < 0.05:
            return "intro", 0.6
        if position > 0.9:
            return "outro", 0.6
        return ("breakdown", 0.7) if previous > energy + 0.12 else ("low", 0.55)
    if slope >= c["build_threshold"]:
        return "build", min(0.85, 0.5 + slope * 5)
    if slope <= -c["build_threshold"]:
        return ("outro", 0.65) if position > 0.9 else ("recovery", 0.55)
    if percentile >= c["peak_percentile"] and energy >= c["high_threshold"]:
        return "peak", 0.75
    if novelty >= c["sensitivity"]:
        return "transition", 0.5
    if energy >= c["high_threshold"]:
        return "high", 0.65
    return "groove", 0.5

def detect(features: dict, duration: float, config: dict, track_boundaries: list[dict]) -> list[dict]:
    c = config["sections"]
    t = features["timestamp_seconds"]
    dt = config["audio"]["fine_interval"]
    e = features["smoothed_energy"]
    change = np.abs(features["energy_delta"])
    distance = max(1, round(c["minimum_seconds"] / dt))
    structural, _ = find_peaks(features["novelty"], height=c["sensitivity"], distance=distance)
    movement, _ = find_peaks(change, height=c["build_threshold"], distance=distance)
    # Sustained high/low threshold crossings also delimit energy regions.
    crossings = np.flatnonzero(np.diff((e >= c["high_threshold"]).astype(int)) != 0)
    candidates = set(structural) | set(movement) | set(crossings)
    ranked = sorted(candidates, key=lambda i: features["novelty"][i] + change[i] * 5, reverse=True)
    boundaries = [0.0, duration] + [p["start"] for p in track_boundaries if 0 < p["start"] < duration]
    for i in ranked:
        value = float(t[i])
        if all(abs(value - existing) >= c["minimum_seconds"] for existing in boundaries):
            boundaries.append(value)
    boundaries = sorted(set(boundaries))
    result = []
    for start, end in zip(boundaries[:-1], boundaries[1:]):
        mask = (t >= start) & (t < end)
        if not np.any(mask):
            mask[np.argmin(abs(t-start))] = True
        context = (t >= max(0, start-c["context_seconds"])) & (t < start)
        previous = float(np.mean(e[context])) if np.any(context) else float(e[0])
        slope = float(np.polyfit(t[mask] - start, e[mask], 1)[0]) if np.count_nonzero(mask) > 1 else 0.0
        energy = float(np.mean(e[mask]))
        before = np.interp(max(0, start-2), t, features["micro_energy"])
        after = np.interp(min(duration, start+2), t, features["micro_energy"])
        # Centered phrase smoothing sees future audio; never use it to establish
        # the preceding build, or an isolated step can manufacture its own context.
        preceding = (t >= max(0, start-c["context_seconds"])) & (t < start-config["energy"]["delta_seconds"]/2)
        context_t, context_e = t[preceding], features["micro_energy"][preceding]
        prior_rise = float(np.polyfit(context_t-context_t[0], context_e, 1)[0]) if len(context_t) > 2 else 0
        percentile = float(np.mean(features["energy_percentile"][mask]))
        phase, confidence = classify(energy, percentile, slope, previous, float(after-before), prior_rise,
                                     float(np.interp(start, t, features["novelty"])), start/duration, config)
        result.append({"start": start, "end": end, "duration": end-start, "phase": phase, "confidence": confidence,
                       "global_energy": energy, "local_energy": float(np.mean(features["local_energy"][mask])),
                       "energy_percentile": percentile, "energy_delta": slope,
                       "rhythmic_intensity": float(np.mean(features["rhythmic_intensity"][mask])),
                       "evidence": {"previous_energy": previous, "jump": float(after-before), "prior_rise": prior_rise}, "heuristic": True})
    return result
