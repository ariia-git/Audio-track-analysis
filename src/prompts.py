from __future__ import annotations

def modifier(energy: float, falling: bool) -> str:
    if energy < 0.25:
        text = "slow floating camera, sparse fog, restrained movement, long contemplative compositions"
    elif energy < 0.55:
        text = "steady travelling camera, layered environmental movement, moderate parallax and detail"
    elif energy < 0.8:
        text = "rapid forward movement, strong parallax, dense particles and dynamic perspective"
    else:
        text = "intense camera movement, architecture transforming, extreme scale and maximum environmental activity"
    if falling:
        text += ", gradually decelerate, reduce effects and release visual tension"
    return text

def build(timeline: list[dict], bible: dict) -> list[dict]:
    context = []
    for key in ("theme", "setting", "palette_description", "camera_style", "lens_style", "texture", "characters", "recurring_objects", "lighting_style"):
        value = bible.get(key, "")
        if value:
            context.append(f"{key.replace('_', ' ')}: {', '.join(value) if isinstance(value, list) else value}")
    base = bible["base_prompt"] + " " + "; ".join(context) + "."
    forbidden = bible.get("forbidden_elements", [])
    negative = ", ".join(filter(None, [bible.get("negative_prompt", ""), ", ".join(forbidden)]))
    return [{"start": s["start"], "end": s["end"], "phase": s["phase"], "energy": s["global_energy"],
             "base_prompt": base, "energy_modifier": s["prompt_modifiers"],
             "complete_prompt": base + " " + s["prompt_modifiers"] + f". Motion intensity {s['movement_level']:.2f}/1; preserve continuity with the preceding shot.",
             "negative_prompt": negative} for s in timeline]
