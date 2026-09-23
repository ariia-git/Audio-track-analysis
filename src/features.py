"""Block STFT feature extraction with one shared, absolute-time frame grid."""
from __future__ import annotations
import logging
import numpy as np
from scipy import signal
from scipy.ndimage import uniform_filter1d
from .audio import Audio

LOG = logging.getLogger(__name__)
BANDS = {"sub_bass_energy": (20, 60), "bass_energy": (20, 250), "low_mid_energy": (250, 500),
         "mid_energy": (500, 2000), "high_energy": (2000, 11025)}
DEFINITIONS = {
    "rms": "Linear full-scale root mean square, mono analysis signal",
    "loudness": "20 log10 of A-weighted spectral RMS; dBFS approximation, NOT LUFS",
    "onset_strength": "Mean positive log-spectral difference per STFT frame",
    "spectral_flux": "Positive difference of normalized magnitude spectra",
    "spectral_centroid": "Magnitude-weighted mean frequency (Hz)",
    "spectral_bandwidth": "Magnitude-weighted frequency standard deviation (Hz)",
    "spectral_rolloff": "Frequency below which 85 percent of spectral power lies (Hz)",
    "zero_crossing_rate": "Fraction of consecutive samples changing sign",
    "band_energy": "RMS spectral amplitude in named frequency band; overlapping sub-bass/bass",
    "chroma": "12 pitch-class power proportions, C through B; FFT projection, not chord recognition",
    "transient_density": "Prominent onset peaks per second in the micro window",
    "beat_density": "Tracked beats per second in the micro window",
    "tempo_bpm": "Windowed dynamic-programming beat estimate; may have half/double-tempo ambiguity",
    "global_energy": "Weighted full-mix robust-normalized intensity with absolute silence gate, 0..1",
    "local_energy": "Rolling robust percentile-normalized global score, 0..1; never replaces global",
    "energy_delta": "Change in smoothed global energy per second over configured delta span",
    "energy_percentile": "Full-mix rank of global energy, 0..1, silent frames fixed at zero"
}

def extract(audio: Audio, config: dict) -> tuple[dict[str, np.ndarray], np.ndarray, np.ndarray]:
    a = config["audio"]
    sr, nfft, hop = audio.sample_rate, a["n_fft"], a["hop_length"]
    # Frame centers are 0, hop, 2*hop... including partially padded edge windows.
    frames = (len(audio.samples) + hop - 1) // hop
    fine_dt = a["fine_interval"]
    count = max(1, int(np.ceil(audio.duration / fine_dt)))
    frequencies = np.fft.rfftfreq(nfft, 1 / sr)
    window = signal.windows.hann(nfft, sym=False)
    scale = nfft * np.sum(window ** 2)
    fft_weights = np.ones(len(frequencies)) * 2
    fft_weights[[0, -1]] = 1
    f2 = np.maximum(frequencies, 1) ** 2
    ra = (12194.0 ** 2 * f2 ** 2) / ((f2 + 20.6 ** 2) * np.sqrt((f2 + 107.7 ** 2) * (f2 + 737.9 ** 2)) * (f2 + 12194.0 ** 2))
    aweight = (ra * 10 ** (2 / 20)) ** 2
    pitch = np.rint(69 + 12 * np.log2(np.maximum(frequencies, 1) / 440)).astype(int) % 12
    chroma_masks = [(pitch == p) & (frequencies >= 50) & (frequencies <= 5000) for p in range(12)]
    names = ["rms", "loudness", "onset_strength", "spectral_flux", "spectral_centroid", "spectral_bandwidth", "spectral_rolloff", "zero_crossing_rate", *BANDS, *[f"chroma_{i}" for i in range(12)]]
    sums = {name: np.zeros(count) for name in names}
    counts = np.zeros(count)
    onset = np.zeros(frames, dtype=np.float32)
    previous_log = np.zeros(len(frequencies))
    previous_norm = np.zeros(len(frequencies))
    block_frames = max(1, int(a["chunk_seconds"] * sr / hop))
    for start in range(0, frames, block_frames):
        stop = min(frames, start + block_frames)
        left, right = start * hop - nfft // 2, (stop - 1) * hop + nfft - nfft // 2
        data = np.asarray(audio.samples[max(0, left):min(len(audio.samples), right)])
        data = np.pad(data, (max(0, -left), max(0, right - len(audio.samples))))
        data = np.nan_to_num(data)
        windows = np.lib.stride_tricks.sliding_window_view(data, nfft)[::hop][:stop-start]
        spec = np.abs(np.fft.rfft(windows * window, axis=1))
        power = spec ** 2 * fft_weights / scale
        denom = np.maximum(spec.sum(axis=1), 1e-12)
        centroid = (spec * frequencies).sum(axis=1) / denom
        normalized = spec / denom[:, None]
        logs = np.log1p(spec)
        novelty = np.maximum(np.diff(logs, axis=0, prepend=previous_log[None, :]), 0).mean(axis=1)
        flux = np.maximum(np.diff(normalized, axis=0, prepend=previous_norm[None, :]), 0).sum(axis=1)
        previous_log, previous_norm = logs[-1], normalized[-1]
        if start == 0:
            novelty[0] = flux[0] = 0
        onset[start:stop] = novelty
        cum = np.cumsum(power, axis=1)
        rolloff = frequencies[np.argmax(cum >= cum[:, -1:] * 0.85, axis=1)]
        vals = {"rms": np.sqrt(np.mean(windows ** 2, axis=1)),
                "loudness": 10 * np.log10(np.maximum((power * aweight).sum(axis=1), 1e-12)),
                "onset_strength": novelty, "spectral_flux": flux, "spectral_centroid": centroid,
                "spectral_bandwidth": np.sqrt((spec * (frequencies[None, :] - centroid[:, None]) ** 2).sum(axis=1) / denom),
                "spectral_rolloff": rolloff,
                "zero_crossing_rate": np.mean(windows[:, :-1] * windows[:, 1:] < 0, axis=1)}
        for name, (lo, hi) in BANDS.items():
            vals[name] = np.sqrt(power[:, (frequencies >= lo) & (frequencies < hi)].sum(axis=1))
        chroma = np.stack([power[:, mask].sum(axis=1) for mask in chroma_masks], axis=1)
        chroma /= np.maximum(chroma.sum(axis=1, keepdims=True), 1e-12)
        vals.update({f"chroma_{i}": chroma[:, i] for i in range(12)})
        bins = np.minimum((np.arange(start, stop) * hop / sr / fine_dt).astype(int), count - 1)
        counts += np.bincount(bins, minlength=count)
        for name, value in vals.items():
            sums[name] += np.bincount(bins, weights=value, minlength=count)
        LOG.info("Features: %.0f%%", 100 * stop / frames)
    t = np.arange(count) * fine_dt
    valid = counts > 0
    result = {"timestamp_seconds": t}
    for name, values in sums.items():
        result[name] = np.interp(t, t[valid], values[valid] / counts[valid])
    # Preserve unaggregated onset envelope for beat timing accuracy.
    peaks, _ = signal.find_peaks(onset, prominence=max(float(np.percentile(onset, 99)) * config["beats"]["onset_prominence"], 1e-8), distance=max(1, int(0.08 * sr / hop)))
    peak_bins = np.minimum((peaks * hop / sr / fine_dt).astype(int), count - 1)
    density = np.bincount(peak_bins, minlength=count) / fine_dt
    result["transient_density"] = uniform_filter1d(density, max(1, round(config["energy"]["micro_seconds"] / fine_dt)), mode="nearest")
    return result, onset, peaks * hop / sr
