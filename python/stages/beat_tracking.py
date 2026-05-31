"""
Beat tracking and tempo detection stage using librosa.

Detects BPM and beat positions, and converts BPM to NBS ticks-per-second (TPS)
using the formula: tps = round((bpm / 15) * 100) / 100.

This corresponds to assuming a quarter-note beat: 15 TPS = 1 beat per second
at 60 BPM, scaling linearly.
"""

from __future__ import annotations

import json
from typing import List, Optional, Tuple

import numpy as np
import librosa


async def detect_tempo_and_beats(
    audio: np.ndarray,
    sample_rate: int = 44100,
    hop_length: int = 512,
    start_bpm: float = 120.0,
    tightness: float = 100.0,
) -> Tuple[float, float, np.ndarray]:
    """Detect tempo (BPM), derive TPS, and locate beat frames.

    Parameters
    ----------
    audio : np.ndarray
        Mono audio waveform.
    sample_rate : int
        Audio sample rate.
    hop_length : int
        STFT hop length for onset strength.
    start_bpm : float
        Initial BPM guess for the beat tracker.
    tightness : float
        Beat tracking tightness (higher = tighter to onset).

    Returns
    -------
    tempo_bpm : float
        Estimated tempo in beats per minute.
    tps : float
        NBS ticks per second, derived from BPM.
    beat_frames : np.ndarray
        Frame indices of detected beats.
    """
    if audio.ndim > 1:
        audio = librosa.to_mono(audio)

    if audio.size == 0 or np.max(np.abs(audio)) < 1e-10:
        return 120.0, 10.0, np.array([], dtype=int)

    # Compute onset strength envelope
    onset_env = librosa.onset.onset_strength(
        y=audio,
        sr=sample_rate,
        hop_length=hop_length,
    )

    # Detect tempo and beat positions
    tempo_bpm, beat_frames = librosa.beat.beat_track(
        onset_envelope=onset_env,
        sr=sample_rate,
        hop_length=hop_length,
        start_bpm=start_bpm,
        tightness=tightness,
        units="frames",
    )

    # librosa may return a scalar or single-element array for tempo
    if isinstance(tempo_bpm, np.ndarray):
        tempo_bpm = float(tempo_bpm[0])
    else:
        tempo_bpm = float(tempo_bpm)

    # Validate tempo
    if tempo_bpm < 20.0 or tempo_bpm > 300.0:
        tempo_bpm = 120.0

    # Convert BPM to TPS
    # BPM = TPS * 60 / 4 (assuming quarter-note beat)
    # => TPS = BPM * 4 / 60 = BPM / 15
    tps = round((tempo_bpm / 15.0) * 100.0) / 100.0
    tps = max(2.0, min(60.0, tps))

    return tempo_bpm, tps, beat_frames


async def detect_tempo_from_file(
    file_path: str,
    sample_rate: int = 22050,
) -> Tuple[float, float]:
    """Convenience: detect tempo directly from an audio file path.

    Returns (tempo_bpm, tps).
    """
    audio, sr = librosa.load(str(file_path), sr=sample_rate, mono=True)

    if audio.size == 0:
        return 120.0, 10.0

    tempo_bpm, tps, _ = await detect_tempo_and_beats(
        audio=audio,
        sample_rate=sr,
    )
    return tempo_bpm, tps


def tps_to_bpm(tps: float) -> float:
    """Convert ticks-per-second back to beats-per-minute."""
    return tps * 15.0


async def detect_segment_tempo(
    audio: np.ndarray,
    sample_rate: int = 44100,
    hop_length: int = 512,
) -> Tuple[float, float, np.ndarray, np.ndarray]:
    """Extended beat detection returning beat times in seconds.

    Returns
    -------
    tempo_bpm : float
    tps : float
    beat_frames : np.ndarray (frame indices)
    beat_times : np.ndarray (seconds)
    """
    if audio.ndim > 1:
        audio = librosa.to_mono(audio)

    tempo_bpm, tps, beat_frames = await detect_tempo_and_beats(
        audio=audio,
        sample_rate=sample_rate,
        hop_length=hop_length,
    )

    beat_times = librosa.frames_to_time(
        beat_frames, sr=sample_rate, hop_length=hop_length
    )

    return tempo_bpm, tps, beat_frames, beat_times
