"""
Pitch detection stage using Spotify's Basic Pitch (CREPE architecture).

Detects notes (onset, offset, pitch, velocity, confidence) from an audio
array. Uses multiple_pitch_bends=True so Basic Pitch internally handles
vibrato segmentation (Strategy B from the design document).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy.io import wavfile

from models.task_result import NoteEvent


def _apply_noise_gate(
    audio: np.ndarray,
    sample_rate: int,
    threshold_db: float = -30.0,
    fade_ms: float = 5.0,
) -> np.ndarray:
    """Suppress low-level background noise before pitch detection.

    Silences audio segments whose local RMS is more than *threshold_db*
    below the track's peak RMS.  A short linear crossfade avoids clicks
    at gate transitions.

    Parameters
    ----------
    audio : np.ndarray
        Mono float32 waveform.
    sample_rate : int
        Sample rate in Hz.
    threshold_db : float
        RMS threshold relative to peak (e.g. -30 dB).
    fade_ms : float
        Crossfade duration in ms (default 5).

    Returns
    -------
    np.ndarray
        Gated waveform (same shape / dtype as input).
    """
    if audio.size == 0:
        return audio

    import librosa

    # Local RMS per ~46 ms frame (2048 samples @ 44.1k), 512-sample hop
    rms = librosa.feature.rms(y=audio, frame_length=2048, hop_length=512)[0]
    rms_max: float = float(rms.max())
    if rms_max < 1e-10:
        return audio

    threshold_linear = rms_max * (10.0 ** (threshold_db / 20.0))

    # Frame-level binary gate
    gate = np.where(rms >= threshold_linear, 1.0, 0.0).astype(np.float32)

    # Expand to sample resolution
    sample_gate = np.repeat(gate, 512)[:audio.shape[0]]

    # Short linear crossfade to prevent clicks
    fade_samples = int(sample_rate * fade_ms / 1000.0)
    if fade_samples > 1:
        from scipy.ndimage import uniform_filter1d
        sample_gate = uniform_filter1d(sample_gate, size=fade_samples * 2 + 1)
        sample_gate = np.clip(sample_gate, 0.0, 1.0)

    return (audio * sample_gate).astype(audio.dtype, copy=False)


async def detect_pitches(
    audio: np.ndarray,
    sample_rate: int = 44100,
    onset_threshold: float = 0.6,
    frame_threshold: float = 0.4,
    min_note_length_ms: float = 120.0,
    minimum_frequency: float = 120.0,
    maximum_frequency: float = 4000.0,
    noise_gate_db: float | None = -30.0,
    melodia_trick: bool = True,
    multiple_pitch_bends: bool = True,
) -> List[NoteEvent]:
    """Detect note events from an audio array using Basic Pitch.

    Parameters
    ----------
    audio : np.ndarray
        Mono audio waveform (float32, [-1, 1]).
    sample_rate : int
        Sample rate of the audio (default 44100).
    onset_threshold : float
        Onset detection sensitivity (higher = fewer onsets, default 0.6).
    frame_threshold : float
        Frame-level activation threshold (higher = fewer frames, default 0.4).
    min_note_length_ms : float
        Minimum note length in milliseconds (default 120, range 80-150).
    minimum_frequency : float
        Lowest frequency in Hz that Basic Pitch will track (default 120).
    maximum_frequency : float
        Highest frequency in Hz that Basic Pitch will track (default 4000).
    noise_gate_db : float or None
        Noise-gate threshold in dB relative to peak RMS.  ``None`` disables
        the gate.  Default ``-30`` silences segments 30 dB below peak.
    melodia_trick : bool
        Apply Melodia-style harmonic filtering to reduce false positives.
    multiple_pitch_bends : bool
        Let Basic Pitch internally segment pitch bends into discrete notes
        (Strategy B vibrato handling). When True, wide vibrato and
        portamento are automatically split across semitone boundaries.

    Returns
    -------
    List[NoteEvent]
        Detected note events sorted by start time.
    """
    # Validate the audio is meaningful
    if audio.size == 0 or np.max(np.abs(audio)) < 1e-10:
        return []

    # ---- Pre-processing: noise gate ----------------------------------------
    if noise_gate_db is not None:
        audio = _apply_noise_gate(audio, sample_rate, threshold_db=noise_gate_db)

    try:
        from basic_pitch.inference import predict

        # Basic Pitch API expects either a file path or numpy array.
        # We write to a temporary WAV to pass a path, which is the most
        # reliable interface.
        temp_wav = _write_temp_wav(audio, sample_rate)

        _, midi_data, note_events = predict(
            str(temp_wav),
            onset_threshold=onset_threshold,
            frame_threshold=frame_threshold,
            minimum_note_length=min_note_length_ms / 1000.0,  # seconds
            minimum_frequency=minimum_frequency,
            maximum_frequency=maximum_frequency,
            melodia_trick=melodia_trick,
            multiple_pitch_bends=multiple_pitch_bends,
        )

        # Clean up temp file
        try:
            temp_wav.unlink(missing_ok=True)
        except Exception:
            pass

        notes: List[NoteEvent] = []
        for ne in note_events:
            # basic_pitch returns tuples: (start_time, end_time, pitch, amplitude, pitch_bends)
            if isinstance(ne, tuple):
                start_time = float(ne[0])
                end_time = float(ne[1])
                pitch = int(ne[2])
                # amplitude is roughly [0, 1]; scale to NBS velocity range [1, 100]
                amplitude = float(ne[3]) if len(ne) > 3 else 0.5
                velocity = max(1.0, min(100.0, amplitude * 100.0))
                confidence = 1.0
            else:
                # Fallback: try attribute-style access (older basic_pitch versions)
                start_time = float(getattr(ne, "start_time_s", getattr(ne, "start_time", 0.0)))
                end_time = float(getattr(ne, "end_time_s", getattr(ne, "end_time", 0.0)))
                pitch = int(getattr(ne, "pitch_midi", getattr(ne, "pitch", 60)))
                amplitude = float(getattr(ne, "velocity", getattr(ne, "amplitude", 0.5)))
                velocity = max(1.0, min(100.0, amplitude * 100.0 if amplitude <= 1.0 else amplitude))
                confidence = float(getattr(ne, "confidence", 1.0))

            notes.append(
                NoteEvent(
                    start_time=start_time,
                    end_time=end_time,
                    pitch=pitch,
                    velocity=velocity,
                    confidence=confidence,
                )
            )

        # Sort by start time
        notes.sort(key=lambda n: n.start_time)
        return notes

    except ImportError:
        return []
    except Exception:
        return []


async def detect_pitches_from_file(
    file_path: str | Path,
    onset_threshold: float = 0.6,
    frame_threshold: float = 0.4,
    min_note_length_ms: float = 120.0,
    minimum_frequency: float = 120.0,
    maximum_frequency: float = 4000.0,
    noise_gate_db: float | None = -30.0,
    melodia_trick: bool = True,
    multiple_pitch_bends: bool = True,
) -> List[NoteEvent]:
    """Detect note events directly from an audio file path.

    This is a convenience wrapper that calls detect_pitches after loading.
    """
    import librosa

    audio, sr = librosa.load(str(file_path), sr=44100, mono=True)
    if audio.size == 0:
        return []

    return await detect_pitches(
        audio=audio,
        sample_rate=sr,
        onset_threshold=onset_threshold,
        frame_threshold=frame_threshold,
        min_note_length_ms=min_note_length_ms,
        minimum_frequency=minimum_frequency,
        maximum_frequency=maximum_frequency,
        noise_gate_db=noise_gate_db,
        melodia_trick=melodia_trick,
        multiple_pitch_bends=multiple_pitch_bends,
    )


def _write_temp_wav(audio: np.ndarray, sample_rate: int) -> Path:
    """Write audio to a temporary WAV file and return its path."""
    import tempfile

    if audio.ndim > 1:
        import librosa
        audio = librosa.to_mono(audio)

    audio_16 = np.clip(audio * 32767, -32768, 32767).astype(np.int16)

    fd, path = tempfile.mkstemp(suffix=".wav", prefix="basic_pitch_")
    import os
    os.close(fd)
    wavfile.write(str(path), sample_rate, audio_16)
    return Path(path)
