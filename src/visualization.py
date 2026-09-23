from __future__ import annotations
import html
from pathlib import Path
import numpy as np
from . import __version__

COLORS = {"intro": "#67859c", "low": "#668ea7", "groove": "#35b6a4", "build": "#d4a93f", "rising": "#d4a93f",
          "high": "#df7950", "peak": "#ea526f", "drop": "#cd4edd", "breakdown": "#6477bb", "transition": "#a18ac9", "recovery": "#809c9d", "outro": "#67859c"}

def render(folder: Path, features: dict, sections: list, boundaries: dict, summary: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"figure.facecolor": "#101927", "axes.facecolor": "#101927", "text.color": "#e7edf5", "axes.labelcolor": "#bccadb", "xtick.color": "#bccadb", "ytick.color": "#bccadb", "axes.edgecolor": "#405068", "font.size": 10})
    # Limit plot vertices; statistics and exports retain their full resolution.
    stride = max(1, len(features["timestamp_seconds"]) // 16000)
    t = features["timestamp_seconds"][::stride] / 60
    fig, ax = plt.subplots(figsize=(14, 4), layout="constrained")
    for key, color, alpha in [("global_energy", "#446887", .5), ("local_energy", "#bea3ed", .55), ("smoothed_energy", "#46dfc4", 1), ("macro_energy", "#ffce72", 1)]:
        ax.plot(t, features[key][::stride], color=color, alpha=alpha, label=key.replace("_", " "), linewidth=1.3)
    ax.set(title="MUSICAL ENERGY / full mix", xlabel="Time (minutes)", ylabel="Intensity", ylim=(-.03, 1.03))
    ax.legend(loc="upper right", ncols=4, facecolor="#18273a", labelcolor="#e7edf5")
    fig.savefig(folder / "energy_curve.png", dpi=150)
    plt.close(fig)
    fig, axes = plt.subplots(4, 1, figsize=(14, 9), sharex=True, layout="constrained")
    groups = [("loudness", "A-weighted approximation (dBFS)"), ("bass_energy", "Bass RMS"), ("onset_strength", "Onset activity"), ("spectral_centroid", "Spectral centroid (Hz)")]
    for ax, (key, title) in zip(axes, groups):
        ax.plot(t, features[key][::stride], color="#46dfc4", linewidth=1)
        ax.set_ylabel(title)
        ax.grid(alpha=.12)
    axes[-1].set_xlabel("Time (minutes)")
    fig.suptitle("FEATURES / distinct contributors to intensity")
    fig.savefig(folder / "feature_curves.png", dpi=140)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(14, 3.5), layout="constrained")
    for section in sections:
        start, end = section["start"]/60, section["end"]/60
        ax.axvspan(start, end, color=COLORS[section["phase"]], alpha=.3)
        if (end-start) / (summary["duration_seconds"] / 60) > .04:
            ax.text((start+end)/2, 1.02, section["phase"], ha="center", va="bottom", fontsize=8, rotation=35)
    for boundary in boundaries["boundaries"]:
        if boundary["start"] > 0:
            ax.axvline(boundary["start"]/60, color="#ffffff", linestyle="--", alpha=.65)
    ax.plot(t, features["smoothed_energy"][::stride], color="#e7edf5", linewidth=1.5)
    ax.set(xlabel="Time (minutes)", ylabel="Energy", ylim=(0, 1.3), title="SECTIONS / heuristic labels and transition candidates")
    fig.savefig(folder / "sections_timeline.png", dpi=150)
    plt.close(fig)
    rows = "".join(f"<tr><td>{s['start']:.1f}s</td><td>{s['end']:.1f}s</td><td>{html.escape(s['phase'])}</td><td>{s['global_energy']:.2f}</td><td>{s['confidence']:.2f}</td></tr>" for s in sections)
    warnings = "".join(f"<li>{html.escape(w)}</li>" for w in summary["warnings"])
    document = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Music Video Analyzer report</title><style>body{{margin:0;background:#101927;color:#e7edf5;font:16px system-ui}}main{{max-width:1200px;margin:auto;padding:40px 24px}}h1{{font-size:40px}}p{{color:#bccadb;line-height:1.6}}img{{width:100%;border:1px solid #405068;border-radius:12px;margin:14px 0}}a{{color:#46dfc4}}table{{width:100%;border-collapse:collapse}}td,th{{padding:10px;text-align:left;border-bottom:1px solid #405068}}.tag{{color:#46dfc4;letter-spacing:.15em}}</style>
<main><div class="tag">MUSIC VIDEO ANALYZER / {__version__}</div><h1>{html.escape(summary['input_name'])}</h1>
<p>{summary['duration_seconds'] / 60:.2f} minutes &middot; {summary['beat_count']} beats &middot; {len(sections)} visual segments</p>
<p>Global energy preserves differences across the mix. Local energy measures contrast within the surrounding region. Loudness is an approximation, not LUFS. Section labels, confidence scores, downbeats and track transitions are heuristic.</p>
<ul>{warnings}</ul><img src="energy_curve.png" alt="Global, local, phrase and macro energy curves"><img src="sections_timeline.png" alt="Semantic sections aligned with energy"><img src="feature_curves.png" alt="Loudness, bass, onset activity and brightness">
<p><a href="video_timeline.json">Video controls</a> &middot; <a href="video_prompts.json">Continuous-world prompts</a> &middot; <a href="energy.csv">Energy CSV</a> &middot; <a href="analysis.json">Analysis metadata</a></p>
<table><thead><tr><th>Start</th><th>End</th><th>Phase</th><th>Energy</th><th>Confidence</th></tr></thead><tbody>{rows}</tbody></table></main></html>'''
    (folder / "report.html").write_text(document, encoding="utf-8")
