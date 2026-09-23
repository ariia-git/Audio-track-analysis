"""Decode to temporary disk-backed PCM; never load a whole mix into RAM."""
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import subprocess
import tempfile
import numpy as np
from .utils import ROOT

@dataclass
class Audio:
    samples: np.memmap
    sample_rate: int
    duration: float

def ffmpeg_path() -> Path:
    path = ROOT / "runtime/ffmpeg/bin/ffmpeg.exe"
    if not path.is_file():
        raise FileNotFoundError("Local FFmpeg is missing. Run .\\setup.ps1.")
    return path

@contextmanager
def decode(path: Path, sample_rate: int):
    if not path.is_file():
        raise FileNotFoundError(f"Input audio not found: {path}")
    with tempfile.TemporaryDirectory(prefix="decode-", dir=ROOT / "runtime/cache/tmp") as folder:
        pcm = Path(folder) / "audio.f32"
        command = [str(ffmpeg_path()), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(path),
                   "-map", "0:a:0", "-vn", "-ac", "1", "-ar", str(sample_rate), "-f", "f32le", str(pcm)]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode or not pcm.exists() or pcm.stat().st_size < 4:
            raise ValueError(f"FFmpeg could not decode audio: {result.stderr[-2000:] or 'No audio samples'}")
        samples = np.memmap(pcm, dtype="<f4", mode="r")
        try:
            yield Audio(samples, sample_rate, len(samples) / sample_rate)
        finally:
            samples._mmap.close()
