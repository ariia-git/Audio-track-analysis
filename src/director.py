from __future__ import annotations
import math
from .prompts import modifier

def control(energy: float, rhythm: float, delta: float, config: dict) -> dict:
    c = config["video"]
    e = max(0.0, min(1.0, energy)) ** c["response_gamma"]
    r = max(0.0, min(1.0, rhythm))
    falling = delta < -config["energy"]["stable_delta"]
    release = 0.85 if falling else 1.0
    motion = (0.8 * e + 0.2 * r) * release
    shot = c["shot_max_seconds"] - (c["shot_max_seconds"]-c["shot_min_seconds"]) * motion
    return {"movement_level": motion, "camera_speed": c["camera_min"] + (c["camera_max"]-c["camera_min"]) * motion,
            "camera_aggression": e ** 1.5 * release, "cut_frequency": 1 / shot,
            "visual_density": 0.1 + 0.9 * e, "effect_intensity": e ** 1.3 * release,
            "lighting_intensity": 0.15 + 0.85 * e,
            "transition_strength": min(1.0, 0.6 * e + 0.4 * math.tanh(abs(delta) * 10)),
            "beat_sync_strength": c["beat_sync_min"] + (c["beat_sync_max"]-c["beat_sync_min"]) * r,
            "suggested_shot_duration": shot, "prompt_modifiers": modifier(energy, falling)}

def build(sections: list[dict], config: dict) -> list[dict]:
    return [{**{k: s[k] for k in ("start", "end", "duration", "phase", "global_energy", "local_energy", "energy_percentile")},
             **control(s["global_energy"], s["rhythmic_intensity"], s["energy_delta"], config)} for s in sections]
