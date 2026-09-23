import csv
import json
import re
from pathlib import Path
import numpy as np
import pytest
import soundfile as sf
from PIL import Image
from src.main import analyze, parser, main
from src.utils import ROOT
from .synthetic import create

@pytest.fixture
def result_root():
    import tempfile
    import shutil
    base = Path(tempfile.mkdtemp(prefix="integration-", dir=ROOT / "output"))
    yield base
    shutil.rmtree(base)

@pytest.mark.integration
def test_full_pipeline(result_root):
    source = create(result_root / "mix with spaces.wav")
    output = result_root / "result"
    analyze(parser().parse_args([str(source), "--output", str(output)]))
    required = ["analysis.json", "energy.csv", "energy.json", "beats.json", "sections.json", "track_boundaries.json", "video_timeline.json", "video_prompts.json", "summary.json", "analysis.log", "energy_curve.png", "feature_curves.png", "sections_timeline.png", "report.html", "features.npz"]
    assert all((output / f).is_file() for f in required)
    for path in output.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"), parse_constant=lambda x: pytest.fail(f"Nonfinite JSON: {x}"))
        assert data is not None
    rows = list(csv.DictReader((output / "energy.csv").open(encoding="utf-8")))
    assert len(rows) == 192
    def mean_between(start, end):
        return np.mean([float(r["global_energy"]) for r in rows if start <= float(r["timestamp_seconds"]) < end])
    assert mean_between(34, 44) > mean_between(3, 12) + .25
    assert mean_between(68, 77) > mean_between(52, 61) + .3
    assert mean_between(88, 95) < mean_between(68, 77)
    beats = json.loads((output / "beats.json").read_text())
    times = np.array([b["time"] for b in beats["beats"]])
    assert len(times) > 60
    assert np.all(np.diff(times) > .15)
    assert np.median(np.diff(times)) == pytest.approx(.5, abs=.04)
    assert all(b["heuristic"] for b in beats["downbeats"])
    sections = json.loads((output / "sections.json").read_text())
    assert 3 <= len(sections) < 25
    assert sections[0]["start"] == 0
    assert sections[-1]["end"] == 96
    assert all(a["end"] == b["start"] for a, b in zip(sections, sections[1:]))
    for name in ("energy_curve.png", "feature_curves.png", "sections_timeline.png"):
        with Image.open(output / name) as image:
            assert image.width > 1000
            image.verify()
    html = (output / "report.html").read_text(encoding="utf-8")
    assert all((output / name).exists() for name in re.findall(r'(?:href|src)="([^"]+)"', html))
    metadata = json.loads((output / "analysis.json").read_text())
    assert all((output / name).exists() for name in metadata["artifacts"])
    with pytest.raises(FileExistsError):
        analyze(parser().parse_args([str(source), "--output", str(output)]))

@pytest.mark.integration
@pytest.mark.parametrize("length,silent", [(0.01, False), (2, True)])
def test_short_and_silent(result_root, length, silent):
    source = result_root / "short.wav"
    t = np.arange(round(length*22050)) / 22050
    sf.write(source, np.zeros(len(t)) if silent else .2*np.sin(2*np.pi*440*t), 22050)
    output = result_root / "result"
    analyze(parser().parse_args([str(source), "--output", str(output)]))
    summary = json.loads((output / "summary.json").read_text())
    assert summary["section_count"] >= 1
    if silent:
        assert summary["maximum_energy"] == 0
        assert summary["beat_count"] == 0

@pytest.mark.integration
def test_corrupt_input_fails_without_partial_result(result_root):
    source = result_root / "corrupt.mp3"
    source.write_bytes(b"not audio")
    output = result_root / "result"
    assert main([str(source), "--output", str(output)]) == 1
    assert not output.exists()

@pytest.mark.integration
def test_manual_tracklist_and_optional_failure(result_root, monkeypatch):
    from src import transcription
    def unavailable(*args):
        raise RuntimeError("Test: optional model unavailable")
    monkeypatch.setattr(transcription, "transcribe", unavailable)
    source = create(result_root / "short.wav", duration=12)
    tracks = result_root / "tracks.json"
    tracks.write_text('[{"name":"One","start":0},{"name":"Two","start":6}]')
    output = result_root / "result"
    args = parser().parse_args([str(source), "--output", str(output), "--tracklist", str(tracks), "--transcribe"])
    analyze(args)
    result = json.loads((output / "track_boundaries.json").read_text())
    assert [p["start"] for p in result["boundaries"]] == [0, 6]
    summary = json.loads((output / "summary.json").read_text())
    assert summary["transcription"]["status"] == "failed"
    (output / "personal-note.txt").write_text("keep")
    args.force = True
    args.transcribe = False
    analyze(args)
    assert (output / "personal-note.txt").read_text() == "keep"

@pytest.mark.integration
@pytest.mark.parametrize("extension", ["mp3", "flac", "m4a"])
def test_input_formats(result_root, extension):
    import subprocess
    from src.audio import ffmpeg_path, decode
    source = create(result_root / "format source.wav", duration=3)
    target = result_root / f"format with spaces.{extension}"
    subprocess.run([str(ffmpeg_path()), "-v", "error", "-nostdin", "-y", "-i", str(source), str(target)], check=True)
    with decode(target, 22050) as audio:
        assert audio.duration == pytest.approx(3, abs=.15)
        assert np.max(np.abs(audio.samples)) > .1

@pytest.mark.integration
def test_block_seams_are_invariant(result_root):
    from src.audio import decode
    from src.features import extract
    from src.config import load_config
    source = create(result_root / "seams.wav", duration=12)
    config = load_config()
    with decode(source, 22050) as audio:
        first, onset_a, _ = extract(audio, config)
        config["audio"]["chunk_seconds"] = 1.7
        second, onset_b, _ = extract(audio, config)
    for name in first:
        np.testing.assert_allclose(first[name], second[name], atol=1e-10, err_msg=name)
    np.testing.assert_array_equal(onset_a, onset_b)
