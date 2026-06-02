"""
Per-note timbre classifier for NBS instrument assignment.

Extracts short-time spectral features from each note's audio segment,
classifies it to an NBS instrument (0–15), and optionally recommends a
secondary instrument + velocity multiplier for richer timbre.

Layered on top of the existing stem-family overflow layer system:
primary and secondary notes share the same tick/key/family, and the
overflow resolver in nbs_generator assigns them distinct contiguous
layer IDs automatically.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# Dual-instrument combinations for richer NBS timbre
# ---------------------------------------------------------------------------
# Each entry: primary → (secondary, velocity_multiplier)
# secondary=None means no doubling.
DUAL_INSTRUMENT_RULES: Dict[int, Tuple[int | None, float]] = {
    0:  (8, 0.35),    # Harp    + Chime      — piano body + subtle overtone
    1:  (None, 1.0),  # Double Bass (solo)   — already thick enough
    2:  (None, 1.0),  # Bass Drum (solo)
    3:  (None, 1.0),  # Snare (solo)
    4:  (None, 1.0),  # Click/Hat (solo)
    5:  (15, 0.45),   # Guitar  + Pling      — string body + pluck transient
    6:  (0, 0.60),    # Flute   + Harp       — breath + warmth
    7:  (8, 0.35),    # Bell    + Chime      — metallic + subtle overtone
    8:  (None, 1.0),  # Chime (solo)         — bright enough alone
    9:  (7, 0.45),    # Xylophone + Bell     — woody + metallic overtone
    10: (None, 1.0),  # Iron Xylophone (solo)
    11: (None, 1.0),  # Cow Bell (solo)
    12: (None, 1.0),  # Didgeridoo (solo)
    13: (5, 0.45),    # Bit     + Guitar     — chiptune + string texture
    14: (None, 1.0),  # Banjo (solo)
    15: (None, 1.0),  # Pling (solo)
}


# ---------------------------------------------------------------------------
# Instrument metadata for classification reports
# ---------------------------------------------------------------------------

INSTRUMENT_NAMES: Dict[int, str] = {
    0: "Harp", 1: "Double Bass", 2: "Bass Drum", 3: "Snare",
    4: "Click/Hat", 5: "Guitar", 6: "Flute", 7: "Bell",
    8: "Chime", 9: "Xylophone", 10: "Iron Xylophone",
    11: "Cow Bell", 12: "Didgeridoo", 13: "Bit",
    14: "Banjo", 15: "Pling",
}


# ---------------------------------------------------------------------------
# Spectral feature extraction
# ---------------------------------------------------------------------------

def _extract_segment_features(
    audio: np.ndarray,
    sample_rate: int,
    start_time: float,
    end_time: float,
) -> Dict[str, float]:
    """Extract spectral features from a note's audio segment.

    Parameters
    ----------
    audio : np.ndarray
        Full track audio (mono, float32).
    sample_rate : int
        Sample rate in Hz.
    start_time : float
        Note start time in seconds.
    end_time : float
        Note end time in seconds.

    Returns
    -------
    dict
        Feature dictionary with keys:
        - centroid: spectral centroid (Hz), brightness indicator
        - rolloff: spectral rolloff (Hz), energy concentration
        - flatness: spectral flatness [0,1], tonal vs noisy
        - zcr: zero-crossing rate [0,1], percussive indicator
        - odd_ratio: odd/even harmonic ratio, instrument family indicator
        - rms_energy: RMS energy of segment
    """
    start_sample = int(start_time * sample_rate)
    end_sample = int(end_time * sample_rate)
    start_sample = max(0, start_sample)
    end_sample = min(len(audio), max(end_sample, start_sample + sample_rate // 100))

    segment = audio[start_sample:end_sample].astype(np.float64)
    if segment.size < 64:
        return {
            "centroid": 1000.0,
            "rolloff": 2000.0,
            "flatness": 0.5,
            "zcr": 0.1,
            "odd_ratio": 0.5,
            "rms_energy": 0.01,
        }

    # Windowed FFT (Hann, 2048-point or shorter for very short segments)
    n_fft = min(2048, segment.shape[0])
    if n_fft < 16:
        n_fft = 16

    try:
        import librosa

        # ---- Spectral centroid (brightness) ----
        centroid = librosa.feature.spectral_centroid(
            y=segment, sr=sample_rate, n_fft=n_fft, hop_length=n_fft // 4
        )[0]
        centroid_hz = float(np.mean(centroid))

        # ---- Spectral rolloff (energy concentration) ----
        rolloff = librosa.feature.spectral_rolloff(
            y=segment, sr=sample_rate, n_fft=n_fft, hop_length=n_fft // 4, roll_percent=0.85
        )[0]
        rolloff_hz = float(np.mean(rolloff))

        # ---- Spectral flatness (tonal vs noisy) ----
        flatness = librosa.feature.spectral_flatness(
            y=segment, n_fft=n_fft, hop_length=n_fft // 4
        )[0]
        flatness_val = float(np.mean(flatness))

        # ---- Zero-crossing rate (percussive indicator) ----
        zcr = librosa.feature.zero_crossing_rate(
            y=segment, frame_length=n_fft, hop_length=n_fft // 4
        )[0]
        zcr_val = float(np.mean(zcr))

        # ---- Odd/even harmonic ratio (instrument family) ----
        # Higher ratio → more odd harmonics (clarinet-like, reed/brass)
        # Lower ratio → balanced odd+even (strings, piano)
        magnitude = np.abs(
            librosa.stft(segment, n_fft=n_fft, hop_length=n_fft // 4)
        )
        mag_mean = np.mean(magnitude, axis=1)
        n_bins = mag_mean.shape[0]

        odd_energy = 0.0
        even_energy = 0.0
        # Scan harmonic bins starting from fundamental (~bin 2)
        for h in range(1, min(8, n_bins // 2)):
            bin_idx = h * 2  # approximate harmonic spacing
            if bin_idx < n_bins:
                if h % 2 == 1:  # odd harmonic
                    odd_energy += float(mag_mean[bin_idx])
                else:           # even harmonic
                    even_energy += float(mag_mean[bin_idx])
        total_harm_energy = odd_energy + even_energy
        odd_ratio = odd_energy / total_harm_energy if total_harm_energy > 1e-10 else 0.5

        # ---- RMS energy ----
        rms = librosa.feature.rms(y=segment, frame_length=n_fft, hop_length=n_fft // 4)[0]
        rms_energy = float(np.mean(rms))

        # ---- Spectral spread (bandwidth around centroid) ----
        # High → wide-band synth pad; Low → focused acoustic instrument
        spread = librosa.feature.spectral_bandwidth(
            y=segment, sr=sample_rate, n_fft=n_fft, hop_length=n_fft // 4
        )[0]
        spectral_spread = float(np.mean(spread))

        # ---- Spectral flux (frame-to-frame magnitude change rate) ----
        # High → filter sweep / FX; Low → steady sustained tone
        spec_mag = np.abs(librosa.stft(
            segment, n_fft=n_fft, hop_length=n_fft // 4
        ))
        if spec_mag.shape[1] >= 2:
            diff = np.diff(spec_mag, axis=1)
            flux = np.mean(np.abs(diff), axis=0)
            spectral_flux = float(np.mean(flux)) / (float(np.mean(spec_mag)) + 1e-10)
        else:
            spectral_flux = 0.01

        # ---- Sub-harmonic energy ratio (energy below fundamental / total) ----
        # High → synth bass with sub oscillator; Low → natural bass
        n_bins_mag = mag_mean.shape[0]
        # Estimate fundamental bin (~bin 2-3 for typical notes)
        fund_bin = 2
        if fund_bin < n_bins_mag:
            sub_energy = float(np.sum(mag_mean[:fund_bin]))
            total_energy = float(np.sum(mag_mean)) + 1e-10
            sub_harmonic_ratio = sub_energy / total_energy
        else:
            sub_harmonic_ratio = 0.1

    except Exception:
        # Fallback: heuristic features from raw waveform
        centroid_hz = 1000.0
        rolloff_hz = 2000.0
        flatness_val = 0.5
        zcr_val = float(np.mean(np.abs(np.diff(np.sign(segment)))) > 0) / 2.0
        odd_ratio = 0.5
        rms_energy = float(np.sqrt(np.mean(segment ** 2)))
        spectral_spread = 2000.0
        spectral_flux = 0.05
        sub_harmonic_ratio = 0.1

    return {
        "centroid": centroid_hz,
        "rolloff": rolloff_hz,
        "flatness": flatness_val,
        "zcr": zcr_val,
        "odd_ratio": odd_ratio,
        "rms_energy": rms_energy,
        "spread": spectral_spread,
        "flux": spectral_flux,
        "sub_harmonic": sub_harmonic_ratio,
    }


# ---------------------------------------------------------------------------
# Feature → NBS instrument classification
# ---------------------------------------------------------------------------

def _classify_single(features: Dict[str, float]) -> int:
    """Classify a single note's spectral features to an NBS instrument (0–15).

    Decision tree (order matters — most discriminative features first).

    New synth-aware branches detect:
      - Synth bass (sub-harmonic rich, low centroid)
      - Filter sweep / FX (high spectral flux)
      - Synth pad (wide bandwidth, slow evolution)
      - Synth lead (bright, odd-harmonic dominant saw wave)
    """
    centroid = features["centroid"]
    flatness = features["flatness"]
    zcr = features["zcr"]
    odd_ratio = features["odd_ratio"]
    rolloff = features["rolloff"]
    # New synth-related features (may be absent from older callers)
    spread = features.get("spread", 2000.0)
    flux = features.get("flux", 0.05)
    sub_harmonic = features.get("sub_harmonic", 0.1)

    # ── 1. Very noisy / percussive → percussion family ──
    if flatness > 0.28:
        # High noise = definitely percussive
        return 11  # Cow Bell (generic percussion)

    if zcr > 0.25 and flatness > 0.18:
        # Rapid zero-crossing + moderate noise → snare/hat
        if centroid < 3000:
            return 3  # Snare
        else:
            return 4  # Click/Hat

    # ── 1b. Filter sweep / riser FX → Didgeridoo + Bit layer ──
    if flux > 0.30 and sub_harmonic > 0.10:
        return 12  # Didgeridoo (evolving timbre, closest to filter sweep)

    # ── 2. Synth Bass: low + strong sub-harmonic + some noise ──
    if centroid < 500.0:
        if sub_harmonic > 0.15 and flatness > 0.06:
            return 1  # Double Bass (layer with Bit via DUAL_INSTRUMENT_RULES)
        else:
            return 1  # Double Bass

    # ── 3. Low-mid register — distinguish plucked vs blown vs struck ──
    if centroid < 2000.0:
        # Synth pad in low-mid: wide bandwidth, low flux (steady)
        if spread > 2000.0 and flux < 0.15:
            return 12  # Didgeridoo (sustained evolving, closest to pad)

        if odd_ratio > 0.55:
            # Strong odd harmonics → reed/brass quality
            if flatness < 0.08:
                return 12  # Didgeridoo (rich odd harmonics)
            else:
                return 6  # Flute (breathy)
        elif zcr > 0.12:
            # Some attack transient → plucked
            return 5  # Guitar
        else:
            # Smooth, balanced harmonics → piano/strings
            return 0  # Harp

    # ── 4. High register (>4000 Hz) ──
    if centroid > 5000.0:
        # Synth lead: very bright, strong odd harmonics (saw wave character)
        if odd_ratio > 0.65 and flatness > 0.04 and flatness < 0.15:
            return 13  # Bit (chiptune/square → closest to saw lead)

        # Very bright — keep Chime for the purest tones only
        if flatness < 0.04:
            return 8  # Chime (crystalline)
        elif odd_ratio > 0.55:
            return 7  # Bell (bright metallic)
        elif flatness < 0.08:
            return 15  # Pling (pure high)
        else:
            return 13  # Bit (synth)
    else:
        # ── 5. Mid-high register (2000–5000 Hz) ──
        # Synth pad: wide bandwidth, moderate centroid, slow evolution
        if spread > 2500.0 and flux < 0.15 and centroid > 2500.0:
            return 12  # Didgeridoo (sustained pad character)

        # Synth lead: bright, odd-harmonic heavy
        if odd_ratio > 0.65 and centroid > 3000.0 and flatness > 0.04:
            return 13  # Bit (synth lead character)

        # Spread across instruments — Harp/Guitar/Flute as defaults
        if odd_ratio > 0.55:
            if flatness < 0.07:
                return 6  # Flute (clear tone)
            else:
                return 7  # Bell (complex metallic)
        elif zcr > 0.15:
            if flatness < 0.08:
                return 9  # Xylophone (percussive melodic)
            else:
                return 5  # Guitar (plucked with body)
        elif flatness < 0.04:
            return 8  # Chime (very rare — extremely pure)
        elif flatness < 0.10:
            if rolloff < 2500.0:
                return 5  # Guitar (darker plucked)
            else:
                return 0  # Harp (default warm pitched)
        else:
            if rolloff > 3000.0:
                return 6  # Flute (breathy)
            else:
                return 5  # Guitar (mid-range plucked)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@dataclass
class NoteInstrument:
    """Instrument assignment for a single detected note."""

    primary: int           # NBS instrument 0–15
    secondary: int | None  # Secondary NBS instrument or None
    secondary_vel_mult: float  # Velocity multiplier for secondary note


def classify_note(
    audio: np.ndarray,
    sample_rate: int,
    start_time: float,
    end_time: float,
    stem_name: str = "other",
) -> NoteInstrument:
    """Classify a single note's timbre and return instrument assignment.

    Parameters
    ----------
    audio : np.ndarray
        Full track audio (mono float32).
    sample_rate : int
        Sample rate in Hz.
    start_time : float
        Note start in seconds.
    end_time : float
        Note end in seconds.
    stem_name : str
        Source stem name (bass/other/vocals) — used to bias classification.

    Returns
    -------
    NoteInstrument
        Primary and optional secondary instrument assignment.
    """
    # Stem-based override for bass (always Double Bass)
    if stem_name == "bass":
        return NoteInstrument(primary=1, secondary=None, secondary_vel_mult=1.0)

    # Stem-based default for vocals (Flute-forward)
    if stem_name == "vocals":
        features = _extract_segment_features(audio, sample_rate, start_time, end_time)
        # Vocals have breath quality + wide centroid range
        # Bias toward Flute but allow Bell/Xylophone for bright passages
        centroid = features["centroid"]
        if centroid > 4000.0 and features["flatness"] < 0.08:
            primary = 7  # Bell — bright vocal peak
        elif centroid > 3000.0 and features["zcr"] > 0.10:
            primary = 9  # Xylophone — rhythmic vocal
        else:
            primary = 6  # Flute — default vocal
    else:
        # Full classification for "other" stem
        features = _extract_segment_features(audio, sample_rate, start_time, end_time)
        primary = _classify_single(features)

    # Dual-instrument lookup
    sec_inst, sec_mult = DUAL_INSTRUMENT_RULES.get(primary, (None, 1.0))
    return NoteInstrument(primary=primary, secondary=sec_inst, secondary_vel_mult=sec_mult)


async def classify_notes_batch(
    audio: np.ndarray,
    sample_rate: int,
    note_events: list,
    stem_name: str = "other",
) -> List[NoteInstrument]:
    """Classify a batch of note events.

    Parameters
    ----------
    audio : np.ndarray
        Full track audio (mono float32).
    sample_rate : int
        Sample rate in Hz.
    note_events : list[NoteEvent]
        Detected note events from basic_pitch.
    stem_name : str
        Source stem name.

    Returns
    -------
    list[NoteInstrument]
        One instrument assignment per note event (same order).
    """
    results: List[NoteInstrument] = []
    n_total = len(note_events)

    for i, ne in enumerate(note_events):
        start = float(ne.start_time)
        end = float(ne.end_time)

        # For drums stem we don't use this classifier
        ni = classify_note(audio, sample_rate, start, end, stem_name=stem_name)
        results.append(ni)

        if i % 500 == 0 and n_total > 1000:
            print(json.dumps({
                "step": "timbre_classification",
                "progress": 0.0,
                "message": f"Classifying {stem_name}: {i}/{n_total} notes",
            }), flush=True)

    return results


def get_classification_stats(
    note_instruments: List[NoteInstrument],
) -> Dict[int, int]:
    """Return a histogram of primary instrument usage."""
    from collections import Counter
    return dict(Counter(ni.primary for ni in note_instruments))
