"""Deterministic six-stage fixture; also usable from the command line."""
from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import soundfile as sf

def create(path: Path, duration: float = 96, sr: int = 22050) -> Path:
    rng = np.random.default_rng(17)
    t = np.arange(round(duration*sr)) / sr
    position = t / duration
    envelope = np.interp(position, [0, .15, .16, .32, .34, .49, .51, .65, .68, .82, 1], [.025, .025, .035, .28, .65, .65, .02, .02, .85, .85, .001])
    beat_phase = t % .5
    kick = np.sin(2*np.pi*(55*beat_phase + 5*(1-np.exp(-beat_phase*30)))) * np.exp(-beat_phase*22)
    hat = rng.normal(0, .25, len(t)) * np.exp(-(t % .25)*90)
    lead = .17*np.sin(2*np.pi*440*t) + .10*np.sin(2*np.pi*660*t)
    bass = .35*np.sin(2*np.pi*65.4*t)
    signal = envelope * (kick + hat + bass + lead)
    signal *= np.minimum(1, t/.02)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, signal, sr, subtype="PCM_16")
    return path

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a quiet/build/rhythm/breakdown/peak/fade test mix")
    parser.add_argument("output", type=Path, nargs="?", default=Path("input/synthetic mix.wav"))
    parser.add_argument("--duration", type=float, default=96)
    args = parser.parse_args()
    print(create(args.output, args.duration))
