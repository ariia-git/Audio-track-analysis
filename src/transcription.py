"""Whisper stays out of imports and installation unless explicitly requested."""
from __future__ import annotations
import logging
from pathlib import Path
from .utils import ROOT

def transcribe(path: Path, model: str, device: str) -> tuple[list, list, str]:
    try:
        from faster_whisper import WhisperModel
        import ctranslate2
    except ImportError as exc:
        raise RuntimeError("Whisper is not installed. Run .\\setup.ps1 -WithWhisper.") from exc
    chosen = device
    if chosen == "auto":
        try:
            chosen = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except Exception:
            chosen = "cpu"
    def run(target):
        engine = WhisperModel(model, device=target, compute_type="float16" if target == "cuda" else "int8", download_root=str(ROOT / "runtime/cache/huggingface/models"))
        segments, info = engine.transcribe(str(path), word_timestamps=True, vad_filter=True)
        transcript, words = [], []
        # Iterate inside try so delayed CUDA/model errors can also fall back.
        for s in segments:
            transcript.append({"start": s.start, "end": s.end, "text": s.text, "language": info.language})
            words.extend({"start": w.start, "end": w.end, "word": w.word, "probability": w.probability} for w in (s.words or []))
        return transcript, words, target
    try:
        return run(chosen)
    except Exception:
        if chosen == "cuda" and device == "auto":
            logging.getLogger(__name__).warning("CUDA transcription failed; retrying on CPU", exc_info=True)
            return run("cpu")
        raise
