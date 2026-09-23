from __future__ import annotations
import argparse
from datetime import datetime, timezone
import importlib.metadata
import logging
from pathlib import Path
import shutil
import sys
import uuid
from . import __version__
from .utils import ROOT, inside_project, local_environment, read_json, timestamp, write_json

LOG = logging.getLogger("analyzer")

def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Analyze DJ-mix energy, rhythm and video direction entirely locally.")
    p.add_argument("input", type=Path, help="Audio readable by FFmpeg")
    p.add_argument("--output", type=Path, help="Exact result directory inside this project (default output/<stem>)")
    p.add_argument("--interval", type=float, help="Energy CSV/JSON interval in seconds")
    p.add_argument("--config", type=Path, help="JSON configuration overrides")
    p.add_argument("--tracklist", type=Path, help="Manual track starts; otherwise config/tracklist.json if present")
    p.add_argument("--transcribe", action="store_true", help="Enable optional local Whisper")
    p.add_argument("--whisper-model", default="large-v3")
    p.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    p.add_argument("--force", action="store_true", help="Replace a previous analyzer result; unrelated directories are protected")
    p.add_argument("--debug", action="store_true")
    p.add_argument("--version", action="version", version=__version__)
    return p

def analyze(args: argparse.Namespace) -> Path:
    local_environment()
    import numpy as np
    from . import audio, features, beats, energy, sections, track_boundaries, director, prompts, outputs, visualization
    from .config import load_config
    config = load_config(args.config, args.interval)
    source = args.input.resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Input audio not found: {source}")
    destination = inside_project(args.output or ROOT / "output" / source.stem)
    if destination == ROOT or any(destination == ROOT / name or destination.is_relative_to(ROOT / name) for name in ("src", "config", "runtime", "tests", "input", "logs", ".git")):
        raise ValueError("Output must be a dedicated result folder, not a project source/runtime directory")
    if source.is_relative_to(destination):
        raise ValueError("Output directory cannot contain the input audio")
    if destination.exists() and (not args.force or not (destination / ".analyzer-result").is_file()):
        raise FileExistsError(f"Output already exists: {destination}. Use --force only for previous analyzer results.")
    bible_path = Path(config["visual_bible"])
    bible = read_json(bible_path if bible_path.is_absolute() else ROOT / bible_path)
    if not isinstance(bible.get("base_prompt"), str):
        raise ValueError("Visual bible requires a base_prompt string")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Analyze into a sibling stage; a failed run never replaces a successful result.
    stage = destination.parent / f".{destination.name}-{uuid.uuid4().hex}"
    stage.mkdir()
    file_handler = logging.FileHandler(stage / "analysis.log", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(file_handler)
    warnings = []
    try:
        LOG.info("Music Video Analyzer v%s", __version__)
        LOG.info("Input: %s", source)
        LOG.info("Decoding audio...")
        with audio.decode(source, config["audio"]["sample_rate"]) as decoded:
            duration = decoded.duration
            LOG.info("Duration: %s", timestamp(duration))
            manual_path = args.tracklist or (ROOT / "config/tracklist.json" if (ROOT / "config/tracklist.json").exists() else None)
            manual = track_boundaries.load_tracklist(manual_path, duration) if manual_path else None
            LOG.info("Extracting features...")
            series, onset, onsets = features.extract(decoded, config)
        LOG.info("Detecting beats...")
        rhythm = beats.detect(onset, series, duration, config)
        rhythm["onsets"] = onsets.tolist()
        warnings.extend(rhythm["warnings"])
        if not rhythm["beats"]:
            warnings.append("No reliable beats detected; beat and bar arrays may be empty.")
        if np.max(series["rms"]) < 10 ** (config["audio"]["silence_db"] / 20):
            warnings.append("Audio is silent or below the configured silence threshold.")
        LOG.info("Calculating global energy...")
        normalization = energy.calculate(series, config)
        series["novelty"] = track_boundaries.novelty(series, config)
        LOG.info("Finding transition candidates...")
        boundaries = track_boundaries.detect(series, duration, config, manual)
        LOG.info("Detecting sections...")
        phases = sections.detect(series, duration, config, boundaries["boundaries"])
        LOG.info("Creating video direction...")
        timeline = director.build(phases, config)
        video_prompts = prompts.build(timeline, bible)
        transcription_status = {"requested": args.transcribe, "status": "disabled"}
        if args.transcribe:
            LOG.info("Transcribing with optional Whisper...")
            try:
                from .transcription import transcribe
                transcript, words, device = transcribe(source, args.whisper_model, args.device)
                write_json(stage / "transcript.json", transcript)
                write_json(stage / "words.json", words)
                transcription_status.update(status="complete", device=device, model=args.whisper_model)
            except Exception as exc:
                warnings.append(f"Optional transcription failed: {exc}")
                transcription_status.update(status="failed", error=str(exc))
                LOG.warning("Optional transcription failed: %s", exc, exc_info=args.debug)
        rows = outputs.save_energy(stage, series, phases, config, duration)
        for filename, value in [("beats.json", rhythm), ("sections.json", phases), ("track_boundaries.json", boundaries), ("video_timeline.json", timeline), ("video_prompts.json", video_prompts)]:
            write_json(stage / filename, value)
        # Fine-resolution controls remain available without an enormous CSV.
        np.savez_compressed(stage / "features.npz", **series)
        summary = {"software_version": __version__, "input_name": source.name, "duration_seconds": duration,
                   "beat_count": len(rhythm["beats"]), "section_count": len(phases), "energy_rows": rows,
                   "maximum_energy": float(np.max(series["global_energy"])), "mean_energy": float(np.mean(series["global_energy"])),
                   "top_moments": sorted(phases, key=lambda s: s["global_energy"], reverse=True)[:10], "warnings": warnings,
                   "transcription": transcription_status}
        for warning in warnings:
            LOG.warning(warning)
        LOG.info("Generating visualizations...")
        visualization.render(stage, series, phases, boundaries, summary)
        write_json(stage / "summary.json", summary)
        metadata = {"schema_version": 1, "software_version": __version__, "created_utc": datetime.now(timezone.utc).isoformat(),
                    "input": str(source), "input_size_bytes": source.stat().st_size, "duration_seconds": duration,
                    "analysis_sample_rate": config["audio"]["sample_rate"], "channels": "mono downmix",
                    "parameters": config, "visual_bible": bible, "feature_definitions": features.DEFINITIONS,
                    "normalization": normalization, "transcription": transcription_status,
                    "dependencies": {name: importlib.metadata.version(name) for name in ("numpy", "scipy", "librosa", "soundfile", "matplotlib")},
                    "artifacts": sorted(p.name for p in stage.iterdir()) + ["analysis.json"]}
        write_json(stage / "analysis.json", metadata)
        (stage / ".analyzer-result").write_text(__version__, encoding="ascii")
        LOG.info("Complete. Results: %s", destination)
    except Exception:
        LOG.exception("Analysis failed")
        file_handler.close()
        logging.getLogger().removeHandler(file_handler)
        failure = ROOT / "logs" / ("failed-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".log")
        failure.parent.mkdir(exist_ok=True)
        shutil.copy2(stage / "analysis.log", failure)
        shutil.rmtree(stage)
        raise
    else:
        file_handler.close()
        logging.getLogger().removeHandler(file_handler)
        if destination.exists():
            # Retain unrelated files added by the user; replace only known old artifacts.
            old = read_json(destination / "analysis.json")
            for filename in old.get("artifacts", []):
                candidate = destination / filename
                if candidate.parent == destination and candidate.is_file():
                    candidate.unlink()
            for artifact in stage.iterdir():
                artifact.replace(destination / artifact.name)
            stage.rmdir()
        else:
            stage.rename(destination)
    for moment in sorted(summary["top_moments"], key=lambda m: m["start"]):
        LOG.info("%s  %s (energy %.2f)", timestamp(moment["start"]), moment["phase"], moment["global_energy"])
    return destination

def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO, format="%(message)s")
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    logging.getLogger("numba").setLevel(logging.WARNING)
    try:
        analyze(args)
        return 0
    except KeyboardInterrupt:
        LOG.error("Interrupted.")
        return 130
    except Exception as exc:
        LOG.error("%s", exc, exc_info=args.debug)
        return 1

if __name__ == "__main__":
    sys.exit(main())
