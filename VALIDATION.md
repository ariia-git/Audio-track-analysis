# v0.1.0 validation

Validated on Windows with the project-local CPython 3.12.10 runtime.

## Publication verification — 2026-09-23

- Full `test.ps1` rerun: **19 passed**, 14 third-party deprecation warnings, in 16.08 seconds.
- The initial sandboxed run encountered Windows temporary-directory permission errors; the complete rerun outside that sandbox passed.
- README installation commands, CLI flags, configuration precedence and pipeline order were checked against the source.
- Publication excludes all files under `input`, `output`, `runtime` and `logs`; a fresh clone generates its own demo audio using `tests.synthetic`.

## Original implementation validation

- `setup.ps1`: installation, FFmpeg checksum/import verification, and fast self-test completed. Repeated setup reused the installation successfully.
- `test.ps1`: **19 passed**, final full suite in 11.44 seconds after compilation caches were populated.
- Unit coverage: normalization/outlier resistance, silence, full-mix energy contrast, timestamp rollover, context-sensitive semantic labels, continuous director mappings, configuration and tracklist validation, prompt continuity, and prevention of false build context from centered smoothing.
- Integration coverage: 96-second six-stage synthetic audio; beat interval close to known 120 BPM; sensible quiet/loud/breakdown/fade energy ordering; complete timeline coverage; all required files; finite parseable JSON; valid CSV; readable PNGs; report/metadata references; short and silent audio; corrupt input; manual boundaries; optional transcription failure isolation; protected overwrites.
- MP3, FLAC and M4A encode/decode checks passed, including filenames containing spaces. The full synthetic pipeline used WAV.
- Block-boundary regression: features and onset envelopes matched when processing the same audio with 30-second versus 1.7-second blocks.
- `python -m src.main --help`, `run.ps1 --version`, and local `pip check` passed; no broken requirements were reported.
- Final CLI demonstration: `analyze.ps1 "input\synthetic mix.wav"` completed and generated `output\synthetic mix\report.html`, charts, all JSON/CSV controls, and compressed fine features.
- Charts were visually inspected. Fourteen third-party Matplotlib/Pyparsing deprecation warnings appeared during tests; they did not affect artifact generation.

No real labelled DJ-mix accuracy benchmark or hour-long stress test was performed. Actual Whisper model download/transcription and CUDA inference were not tested or installed; the core application remains independent of them. Section/downbeat/boundary confidence remains explicitly heuristic. The Codex execution sandbox required elevated tool execution to access private temporary directories created by Python; this did not install anything globally or require an administrator-level Windows installation.
