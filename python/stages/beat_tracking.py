"""
High-precision BPM detection via multi-method consensus + beat-position regression.

Strategy (in priority order):
  1. Zero-padded FFT of onset envelope with parabolic peak interpolation
     → coarse BPM (±0.5 BPM), naturally resistant to sub-harmonic bias
  2. Improved autocorrelation — time-domain cross-validation
  3. IOI (Inter-Onset Interval) histogram — onset-level validation
  4. Weighted multi-method consensus with harmonic ambiguity resolution
  5. DP beat tracking at consensus BPM with high tightness
  6. LINEAR REGRESSION on beat positions → precise BPM (±0.01 BPM)

The linear regression in step 6 is the key to sub-0.1 BPM accuracy:
  - Fit: beat_time = intercept + slope * beat_index
  - slope = 60 / BPM  →  BPM = 60 / slope
  - With 700+ beats the standard error drops below 0.01 BPM.
"""

from __future__ import annotations

import json
from typing import List, Optional, Tuple

import numpy as np
import librosa


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def detect_tempo_and_beats(
    audio: np.ndarray,
    sample_rate: int = 44100,
    hop_length: int = 512,
) -> Tuple[float, float, np.ndarray]:
    """Detect BPM via multi-method consensus + beat-position regression.

    Parameters
    ----------
    audio : np.ndarray
        Mono audio waveform (float32).
    sample_rate : int
        Sample rate (default 44100).
    hop_length : int
        STFT hop length for onset computation.

    Returns
    -------
    tempo_bpm : float
        Estimated beats per minute (high precision).
    tps : float
        NBS ticks per second (BPM / 15).
    beat_frames : np.ndarray
        Frame indices of detected beats.
    """
    if audio.ndim > 1:
        audio = librosa.to_mono(audio)

    if audio.size == 0 or np.max(np.abs(audio)) < 1e-10:
        return 120.0, _bpm_to_tps(120.0), np.array([], dtype=int)

    # ---- Step 1: Onset envelopes --------------------------------------------
    # RAW onset (no zero-meaning) → for DP beat tracking
    onset_raw = _raw_onset_envelope(audio, sample_rate, hop_length)
    if onset_raw is None or len(onset_raw) < 16:
        return 120.0, _bpm_to_tps(120.0), np.array([], dtype=int)

    # ZERO-MEANED onsets → for FFT / autocorrelation (remove DC offset)
    onset_full = onset_raw - np.mean(onset_raw)
    onset_low = _onset_envelope_band(audio, sample_rate, hop_length, "low", 250)
    onset_high = _onset_envelope_band(audio, sample_rate, hop_length, "high", 2000)

    # ---- Step 2: Multi-method coarse BPM estimation -------------------------
    all_candidates: List[Tuple[float, float, str]] = []  # (bpm, weight, label)

    # Method A: High-resolution FFT (primary — sub-harmonic resistant)
    for env, label in [
        (onset_full, "fft_full"),
        (onset_low, "fft_low"),
        (onset_high, "fft_high"),
    ]:
        if env is not None and len(env) >= 16:
            for bpm, score in _tempo_fft_highres(env, sample_rate, hop_length)[:3]:
                all_candidates.append((bpm, score * 1.0, label))

    # Method B: Improved autocorrelation (secondary)
    for env, label, w in [
        (onset_full, "ac_full", 0.9),
        (onset_low, "ac_low", 0.7),
        (onset_high, "ac_high", 0.5),
    ]:
        if env is not None and len(env) >= 16:
            for bpm, score in _tempo_autocorr(env, sample_rate, hop_length)[:3]:
                all_candidates.append((bpm, score * w, label))

    # Method C: IOI histogram
    for bpm, score in _tempo_ioi(audio, sample_rate, hop_length)[:3]:
        all_candidates.append((bpm, score * 0.8, "ioi"))

    if not all_candidates:
        return 120.0, _bpm_to_tps(120.0), np.array([], dtype=int)

    # ---- Step 3: Weighted consensus + harmonic resolution -------------------
    coarse_bpm = _consensus_bpm(all_candidates)

    # Extract best FFT candidate (most reliable individual method)
    fft_best = max(
        [(bpm, score) for bpm, score, label in all_candidates if label.startswith("fft")],
        key=lambda x: x[1],
        default=(coarse_bpm, 0.0),
    )[0]

    # ---- Step 4: DP beat tracking (uses RAW onset — REQUIRED) ----------------
    # beat_track needs non-negative onset values; zero-meaned envelopes
    # produce garbage results (e.g. 1033 BPM for a 200 BPM song).
    _, beat_frames = librosa.beat.beat_track(
        onset_envelope=onset_raw,
        sr=sample_rate,
        hop_length=hop_length,
        start_bpm=coarse_bpm,
        tightness=100.0,
        units="frames",
    )

    # ---- Step 5: Refinement with beat-quality gating -------------------------
    # If beats are clean (low IBI variance, Theil-Sen ≈ median IBI),
    #   use Theil-Sen regression for sub-0.1 BPM precision.
    # If beats are noisy (bimodal IBI, Theil-Sen ≠ median IBI),
    #   trust FFT — the most accurate individual method.
    #
    # Rationale: noisy beats cause Theil-Sen to drift AWAY from truth
    # (e.g. ARForest 192 BPM: FFT=191.97, TS=192.71, error 0.03→0.71).

    refined_bpm = fft_best  # default: trust FFT

    if len(beat_frames) >= 8:
        beat_times = librosa.frames_to_time(
            beat_frames, sr=sample_rate, hop_length=hop_length
        )
        ibis = np.diff(beat_times)

        # Quality check: filter outliers (±30% from median), compute stats
        med_ibi = np.median(ibis)
        clean_mask = (ibis >= med_ibi * 0.7) & (ibis <= med_ibi * 1.3)
        clean_ibis = ibis[clean_mask]

        if len(clean_ibis) >= 8:
            cv = float(np.std(clean_ibis) / np.mean(clean_ibis))  # coeff of variation
            median_bpm = 60.0 / np.median(clean_ibis)

            # Only run Theil-Sen if beats appear clean
            if cv < 0.03:  # < 3% IBI variation → clean beats
                slope = _theil_sen_slope(beat_times)
                if slope is not None and slope > 1e-10:
                    ts_bpm = 60.0 / slope

                    # Gate: Theil-Sen must agree with FFT within 0.5%
                    # If it drifts away, the beats are unreliable → stick with FFT
                    if abs(ts_bpm - fft_best) / max(fft_best, 1.0) <= 0.005:
                        refined_bpm = ts_bpm
                    elif abs(coarse_bpm - fft_best) / max(fft_best, 1.0) <= 0.005:
                        refined_bpm = fft_best
                    else:
                        refined_bpm = coarse_bpm
            else:
                # Beats too noisy — trust FFT over consensus
                if abs(fft_best - coarse_bpm) / max(fft_best, 1.0) <= 0.01:
                    refined_bpm = fft_best
                else:
                    refined_bpm = coarse_bpm

        refined_bpm = max(40.0, min(300.0, refined_bpm))

    # ---- Step 6: Re-track with refined BPM if improved ----------------------
    if abs(refined_bpm - coarse_bpm) / max(coarse_bpm, 1.0) > 0.003:
        _, beat_frames = librosa.beat.beat_track(
            onset_envelope=onset_raw,
            sr=sample_rate,
            hop_length=hop_length,
            start_bpm=refined_bpm,
            tightness=100.0,
            units="frames",
        )

    tps = _bpm_to_tps(refined_bpm)
    return round(refined_bpm, 2), tps, beat_frames


async def detect_audio_metadata(
    audio: np.ndarray,
    sample_rate: int = 44100,
) -> dict:
    """Detect BPM and audio duration early in the pipeline.

    Returns
    -------
    dict with keys: bpm, tps, duration_seconds
    """
    if audio.ndim > 1:
        audio_mono = librosa.to_mono(audio)
    else:
        audio_mono = audio

    duration = len(audio_mono) / sample_rate

    tempo_bpm, tps, _ = await detect_tempo_and_beats(audio_mono, sample_rate)

    return {
        "bpm": round(tempo_bpm, 1),
        "tps": tps,
        "duration_seconds": round(duration, 1),
    }


# ---------------------------------------------------------------------------
# Helpers: onset envelopes
# ---------------------------------------------------------------------------

def _raw_onset_envelope(
    audio: np.ndarray, sr: int, hop_length: int
) -> Optional[np.ndarray]:
    """Compute RAW onset strength envelope — for DP beat tracking.

    IMPORTANT: Do NOT zero-mean this.  librosa.beat.beat_track requires
    non-negative onset values; a zero-meaned envelope produces garbage
    results (e.g. reporting 1033 BPM for a 200 BPM song).
    """
    try:
        return librosa.onset.onset_strength(y=audio, sr=sr, hop_length=hop_length)
    except Exception:
        return None


def _onset_envelope_band(
    audio: np.ndarray, sr: int, hop_length: int, band: str, cutoff: float
) -> Optional[np.ndarray]:
    """Compute zero-mean onset envelope for a specific frequency band.

    Returns zero-meaned envelope for FFT / autocorrelation usage.
    """
    try:
        from scipy.signal import butter, filtfilt
        nyq = sr / 2.0
        if band == "low":
            b, a = butter(2, cutoff / nyq, "low")
        else:
            b, a = butter(2, cutoff / nyq, "high")
        filtered = filtfilt(b, a, audio)
        env = librosa.onset.onset_strength(y=filtered, sr=sr, hop_length=hop_length)
        env = env - np.mean(env)
        return env
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Helpers: tempo estimation methods
# ---------------------------------------------------------------------------

def _tempo_fft_highres(
    onset_env: np.ndarray, sr: int, hop_length: int
) -> List[Tuple[float, float]]:
    """Estimate BPM via zero-padded FFT with parabolic peak interpolation.

    Zero-padding by 4× increases the nominal BPM resolution to ~0.12 BPM.
    Parabolic interpolation on the magnitude spectrum recovers sub-bin precision.
    """
    from scipy.signal import find_peaks

    n_original = len(onset_env)
    # Zero-pad to 8× original length for fine frequency resolution
    n_padded = n_original * 8

    fft = np.abs(np.fft.rfft(onset_env, n=n_padded))
    freqs = np.fft.rfftfreq(n_padded, d=hop_length / sr)
    bpm_axis = freqs * 60.0

    lo, hi = 45.0, 300.0
    mask = (bpm_axis >= lo) & (bpm_axis <= hi)
    if not np.any(mask):
        return []

    fft_range = fft[mask]
    bpm_range = bpm_axis[mask]

    # Distance: at least 4 BPM apart
    min_dist = max(1, len(fft_range) // 80)
    peaks_idx, _ = find_peaks(fft_range, distance=min_dist)

    if len(peaks_idx) == 0:
        return []

    # Parabolic interpolation for each peak to get sub-bin BPM
    refined_bpms = []
    refined_scores = []
    for idx in peaks_idx:
        if 0 < idx < len(fft_range) - 1:
            bpm_interp, mag_interp = _parabolic_interp(
                bpm_range[idx - 1:idx + 2],
                fft_range[idx - 1:idx + 2],
            )
            refined_bpms.append(bpm_interp)
            refined_scores.append(mag_interp)
        else:
            refined_bpms.append(float(bpm_range[idx]))
            refined_scores.append(float(fft_range[idx]))

    refined_bpms = np.array(refined_bpms)
    refined_scores = np.array(refined_scores)

    # Normalize scores
    max_val = refined_scores.max() if len(refined_scores) > 0 else 1.0
    if max_val > 0:
        refined_scores = refined_scores / max_val

    # Sort by score descending
    result = sorted(
        [(float(b), float(s)) for b, s in zip(refined_bpms, refined_scores)],
        key=lambda x: -x[1],
    )
    return result


def _parabolic_interp(
    x: np.ndarray, y: np.ndarray
) -> Tuple[float, float]:
    """Parabolic interpolation to find the true peak position and value.

    Given three points (x0,y0), (x1,y1), (x2,y2) with x1 being the
    discrete peak, fit a parabola y = a(x-x1)² + b(x-x1) + c and
    return the interpolated peak (x_peak, y_peak).
    """
    if len(x) < 3 or len(y) < 3:
        return float(x[1]), float(y[1])

    # Using the three-point formula:
    # x_peak = x1 + (y0 - y2) / (2*(y0 - 2*y1 + y2)) * (x1 - x0)
    denom = 2.0 * (y[0] - 2.0 * y[1] + y[2])
    if abs(denom) < 1e-15:
        return float(x[1]), float(y[1])

    dx = x[1] - x[0]
    offset = (y[0] - y[2]) / denom * dx
    x_peak = x[1] + offset
    y_peak = y[1] - (y[0] - y[2]) * offset / (4.0 * dx) if abs(dx) > 1e-15 else y[1]

    return float(x_peak), float(max(y_peak, y[1]))


def _tempo_autocorr(
    onset_env: np.ndarray, sr: int, hop_length: int
) -> List[Tuple[float, float]]:
    """Estimate BPM via autocorrelation of the onset envelope.

    Returns top-N candidates with confidence scores.
    """
    from scipy.signal import find_peaks

    ac = np.correlate(onset_env, onset_env, mode="full")
    ac = ac[len(ac) // 2:]
    if ac[0] < 1e-10:
        return []
    ac = ac / ac[0]

    lo, hi = 50.0, 260.0
    min_lag = int(60.0 * sr / (hi * hop_length))
    max_lag = int(60.0 * sr / (lo * hop_length))
    max_lag = min(max_lag, len(ac) - 1)
    min_lag = max(min_lag, 1)

    if min_lag >= max_lag:
        return []

    peaks_idx, _ = find_peaks(
        ac[min_lag:max_lag + 1],
        height=0.05,
        distance=max(1, min_lag // 3),
    )
    peak_lags = peaks_idx + min_lag
    peak_vals = ac[peak_lags]

    if len(peak_lags) == 0:
        return []

    peak_bpms = 60.0 * sr / (peak_lags * hop_length)

    # Score: autocorrelation + tiny BPM bonus (counters sub-harmonic bias)
    scores = []
    for bpm, val in zip(peak_bpms, peak_vals):
        bonus = 0.05 * (bpm - lo) / (hi - lo)
        scores.append(float(val + bonus))

    result = sorted(
        [(float(b), float(s)) for b, s in zip(peak_bpms, scores)],
        key=lambda x: -x[1],
    )
    return result


def _tempo_ioi(
    audio: np.ndarray, sr: int, hop_length: int
) -> List[Tuple[float, float]]:
    """Estimate BPM via Inter-Onset Interval (IOI) histogram."""
    from scipy.signal import find_peaks
    from scipy.ndimage import gaussian_filter1d

    onset_env = librosa.onset.onset_strength(y=audio, sr=sr, hop_length=hop_length)
    onset_frames = librosa.onset.onset_detect(
        onset_envelope=onset_env, sr=sr, hop_length=hop_length, backtrack=True
    )

    if len(onset_frames) < 4:
        return []

    onset_times = librosa.frames_to_time(onset_frames, sr=sr, hop_length=hop_length)
    iois = np.diff(onset_times)
    iois = iois[(iois >= 0.20) & (iois <= 1.5)]

    if len(iois) < 5:
        return []

    n_bins = 400
    hist_bins = np.linspace(0.20, 1.5, n_bins + 1)
    hist, _ = np.histogram(iois, bins=hist_bins)
    hist_smooth = gaussian_filter1d(hist.astype(float), sigma=2.5)

    h_peaks, properties = find_peaks(hist_smooth, height=np.max(hist_smooth) * 0.08)
    if len(h_peaks) == 0:
        return []

    max_h = float(properties["peak_heights"].max() if len(properties["peak_heights"]) else 1.0)
    result = []
    for idx in h_peaks:
        bpm = 60.0 / hist_bins[idx]
        if 50.0 <= bpm <= 260.0:
            result.append((bpm, float(hist_smooth[idx] / max_h)))

    result.sort(key=lambda x: -x[1])
    return result


# ---------------------------------------------------------------------------
# Helpers: consensus & harmonic resolution
# ---------------------------------------------------------------------------

def _consensus_bpm(
    candidates: List[Tuple[float, float, str]]
) -> float:
    """Weighted multi-method consensus with harmonic ambiguity resolution.

    1. Cluster candidates by BPM proximity (±4%)
    2. Sum weights within each cluster; bonus for multi-method agreement
    3. Check harmonic ratios (1:2, 2:3, 4:3) between top clusters
    4. When ambiguous: prefer higher BPM, prefer multi-method consensus
    """
    if not candidates:
        return 120.0

    # Cluster by BPM proximity
    sorted_cands = sorted(candidates, key=lambda x: x[0])
    clusters: List[List[Tuple[float, float, str]]] = []

    for bpm, weight, method in sorted_cands:
        placed = False
        for cluster in clusters:
            center = np.mean([c[0] for c in cluster])
            if abs(bpm - center) / max(center, 1.0) < 0.04:
                cluster.append((bpm, weight, method))
                placed = True
                break
        if not placed:
            clusters.append([(bpm, weight, method)])

    # Score each cluster
    cluster_scores = []
    for cluster in clusters:
        total_weight = sum(c[1] for c in cluster)
        methods_used = set(c[2].split("_")[0] for c in cluster)
        method_bonus = min(0.25, len(methods_used) * 0.08)
        center = float(np.average(
            [c[0] for c in cluster], weights=[c[1] for c in cluster]
        ))
        cluster_scores.append((center, total_weight + method_bonus, methods_used))

    cluster_scores.sort(key=lambda x: -x[1])

    if len(cluster_scores) == 1:
        return round(cluster_scores[0][0], 2)

    # Harmonic resolution between top clusters
    best = cluster_scores[0]
    best_bpm = best[0]
    best_weight = best[1]

    for i in range(1, min(len(cluster_scores), 5)):
        other_bpm = cluster_scores[i][0]
        other_weight = cluster_scores[i][1]

        ratio = best_bpm / other_bpm if best_bpm > other_bpm else other_bpm / best_bpm
        is_harmonic = (
            abs(ratio - 2.0) < 0.08 or
            abs(ratio - 1.5) < 0.06 or
            abs(ratio - 4.0 / 3.0) < 0.05
        )

        if is_harmonic:
            methods_best = best[2]
            methods_other = cluster_scores[i][2]
            # Prefer more methods agreeing; if tied, prefer higher BPM
            if len(methods_other) > len(methods_best) and other_weight > best_weight * 0.7:
                best_bpm = other_bpm
                break
            if other_weight > best_weight * 0.6 and other_bpm > best_bpm:
                best_bpm = other_bpm
                break

    return round(best_bpm, 2)


# ---------------------------------------------------------------------------
# Helpers: robust linear regression (Theil-Sen estimator)
# ---------------------------------------------------------------------------

def _theil_sen_slope(beat_times: np.ndarray) -> Optional[float]:
    """Estimate the slope of beat_time vs beat_index using Theil-Sen.

    Theil-Sen = median of all pairwise slopes. It is robust to
    outliers (mis-tracked beats) and has ~95% efficiency vs OLS.

    With N beats, we compute O(N²) slopes. For N=720 this is ~260k
    slopes — fast enough in numpy.

    Returns
    -------
    slope : float or None
        Seconds per beat (60 / BPM).
    """
    n = len(beat_times)
    if n < 8:
        return None

    indices = np.arange(n, dtype=np.float64)

    # ---- Strategy: sample pairs to avoid O(N²) for very long songs ----
    max_pairs = 100_000
    if n * (n - 1) // 2 > max_pairs:
        # Random sampling of pairs
        rng = np.random.RandomState(42)
        # We need pairs where i < j
        n_sample = int(np.sqrt(2 * max_pairs))  # ~447
        sampled_idx = np.sort(rng.choice(n, size=min(n_sample, n), replace=False))
        x_sampled = indices[sampled_idx]
        y_sampled = beat_times[sampled_idx]
        # All pairs within the sampled subset
        i_idx, j_idx = np.triu_indices(len(sampled_idx), k=1)
        x_i, x_j = x_sampled[i_idx], x_sampled[j_idx]
        y_i, y_j = y_sampled[i_idx], y_sampled[j_idx]
    else:
        i_idx, j_idx = np.triu_indices(n, k=1)
        x_i, x_j = indices[i_idx], indices[j_idx]
        y_i, y_j = beat_times[i_idx], beat_times[j_idx]

    # Pairwise slopes
    dx = x_j - x_i
    # Filter pairs that are too close (unreliable slope)
    valid = dx >= 3  # at least 3 beats apart
    if valid.sum() < 10:
        return None

    slopes = (y_j[valid] - y_i[valid]) / dx[valid]

    # Theil-Sen: median of all pairwise slopes
    slope = float(np.median(slopes))

    if slope <= 0 or not np.isfinite(slope):
        return None

    return slope


# ---------------------------------------------------------------------------
# TPS conversion
# ---------------------------------------------------------------------------

def _bpm_to_tps(bpm: float) -> float:
    """Convert BPM to NBS ticks-per-second."""
    tps = round((bpm / 15.0) * 100.0) / 100.0
    return max(2.0, min(60.0, tps))


def tps_to_bpm(tps: float) -> float:
    """Convert ticks-per-second back to beats-per-minute."""
    return tps * 15.0


# ---------------------------------------------------------------------------
# Convenience functions (preserved for compatibility)
# ---------------------------------------------------------------------------

async def detect_tempo_from_file(
    file_path: str,
    sample_rate: int = 22050,
) -> Tuple[float, float]:
    """Convenience: detect tempo directly from an audio file path."""
    audio, sr = librosa.load(str(file_path), sr=sample_rate, mono=True)

    if audio.size == 0:
        return 120.0, _bpm_to_tps(120.0)

    tempo_bpm, tps, _ = await detect_tempo_and_beats(audio=audio, sample_rate=sr)
    return tempo_bpm, tps


async def detect_segment_tempo(
    audio: np.ndarray,
    sample_rate: int = 44100,
    hop_length: int = 512,
) -> Tuple[float, float, np.ndarray, np.ndarray]:
    """Extended beat detection returning beat times in seconds."""
    if audio.ndim > 1:
        audio = librosa.to_mono(audio)

    tempo_bpm, tps, beat_frames = await detect_tempo_and_beats(
        audio=audio, sample_rate=sample_rate, hop_length=hop_length,
    )

    beat_times = librosa.frames_to_time(
        beat_frames, sr=sample_rate, hop_length=hop_length
    )

    return tempo_bpm, tps, beat_frames, beat_times
