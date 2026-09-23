import json
import numpy as np
import pytest
from src.config import load_config
from src.energy import robust_normalize, calculate
from src.sections import classify
from src.director import control
from src.prompts import build
from src.track_boundaries import load_tracklist
from src.utils import timestamp, parse_time

def test_normalization_rejects_spike_domination():
    normal, meta = robust_normalize(np.r_[np.linspace(0, 1, 1000), 10000])
    assert normal[500] == pytest.approx(.5, abs=.02)
    assert normal[-1] == 1
    assert meta["high"] < 1

def test_constant_and_silence():
    assert np.all(robust_normalize(np.ones(30))[0] == 0)
    c = load_config()
    features = {key: np.ones(50) for key in set(c["energy"]["weights"]) | {"rms", "spectral_flux"}}
    features["rms"] = np.zeros(50)
    features["timestamp_seconds"] = np.arange(50)*.1
    calculate(features, c)
    for name in ("global_energy", "local_energy", "smoothed_energy", "energy_percentile"):
        assert np.all(features[name] == 0)

def test_energy_preserves_stronger_region():
    c = load_config()
    values = np.r_[np.linspace(.01, .1, 200), np.linspace(.3, .7, 200)]
    f = {key: values.copy() for key in set(c["energy"]["weights"]) | {"rms", "spectral_flux"}}
    f["timestamp_seconds"] = np.arange(len(values))*.1
    calculate(f, c)
    assert np.mean(f["global_energy"][200:]) > np.mean(f["global_energy"][:200]) + .3
    assert np.all(np.isfinite(f["energy_delta"]))

def test_timestamp_rollover():
    assert timestamp(3599.9999) == "01:00:00.000"
    assert timestamp(3661.25) == "01:01:01.250"
    assert parse_time("01:05:42") == 3942
    assert parse_time("05:42") == 342
    with pytest.raises(ValueError):
        parse_time("01:72:00")

def test_phase_needs_build_before_drop():
    c = load_config()
    assert classify(.8, .9, 0, .3, .4, .03, .3, .5, c)[0] == "drop"
    assert classify(.8, .9, 0, .3, .4, 0, .3, .5, c)[0] != "drop"
    assert classify(.12, .1, 0, .8, -.5, 0, 0, .5, c)[0] == "breakdown"
    assert classify(.45, .5, .03, .2, .1, 0, 0, .5, c)[0] == "build"
    assert classify(.9, .99, 0, .8, .1, 0, 0, .5, c)[0] == "peak"

def test_director_continuous_monotonic_and_release():
    c = load_config()
    controls = [control(float(e), float(e), 0, c) for e in np.linspace(0, 1, 101)]
    assert all(a["movement_level"] < b["movement_level"] for a, b in zip(controls, controls[1:]))
    assert controls[0]["suggested_shot_duration"] > controls[-1]["suggested_shot_duration"]
    for item in controls:
        assert c["video"]["shot_min_seconds"] <= item["suggested_shot_duration"] <= c["video"]["shot_max_seconds"]
    assert control(.8, .8, -.02, c)["camera_speed"] < control(.8, .8, 0, c)["camera_speed"]

def test_configuration_override_and_validation(tmp_path):
    file = tmp_path / "config.json"
    file.write_text(json.dumps({"video": {"shot_min_seconds": 2.2}}))
    c = load_config(file)
    assert c["video"]["shot_min_seconds"] == 2.2
    assert c["audio"]["sample_rate"] == 22050
    for interval in (0, -1, float("nan"), .01):
        with pytest.raises(ValueError):
            load_config(interval=interval)
    file.write_text('{"unknown": 1}')
    with pytest.raises(ValueError):
        load_config(file)

def test_tracklist(tmp_path):
    file = tmp_path / "tracks.json"
    file.write_text('[{"name":"A","start":"00:00:02"},{"name":"B","start":20}]')
    tracks = load_tracklist(file, 60)
    assert [t["start"] for t in tracks] == [0, 2, 20]
    file.write_text('[{"start":20},{"start":10}]')
    with pytest.raises(ValueError):
        load_tracklist(file, 60)

def test_prompt_continuity():
    segments = [{"start": 0, "end": 10, "phase": "low", "global_energy": .1, "movement_level": .1, "prompt_modifiers": "slow"},
                {"start": 10, "end": 20, "phase": "peak", "global_energy": .9, "movement_level": .9, "prompt_modifiers": "fast"}]
    prompts = build(segments, {"base_prompt": "Same city.", "setting": "night", "forbidden_elements": ["logos"]})
    assert prompts[0]["base_prompt"] == prompts[1]["base_prompt"]
    assert all("logos" in p["negative_prompt"] for p in prompts)

def test_step_cannot_manufacture_preceding_build():
    from src.sections import detect
    from src.energy import smooth
    c = load_config()
    t = np.arange(0, 60, .1)
    raw = np.where(t < 30, .1, .9)
    smoothed = smooth(raw, 8, .1)
    features = {"timestamp_seconds": t, "smoothed_energy": smoothed, "micro_energy": smooth(raw, 1, .1),
                "energy_delta": np.gradient(smoothed, .1), "energy_percentile": raw,
                "local_energy": raw, "rhythmic_intensity": raw, "novelty": np.zeros_like(t)}
    found = detect(features, 60, c, [{"start": 0}, {"start": 30}])
    assert all(s["phase"] != "drop" for s in found)
