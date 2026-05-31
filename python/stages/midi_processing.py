"""
MIDI processing stage: note quantization, chord grouping, legato tiling,
and velocity envelope extraction.

Implements the three-layer expressiveness pipeline:
  1. Legato Tiling -- fill every tick between start and end with NBS notes
  2. Velocity Envelope -- RMS-based per-tick velocity with dual filtering
  3. Vibrato Strategy B -- Basic Pitch natural segmentation (handled upstream)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import librosa
from scipy.ndimage import median_filter, gaussian_filter1d

from models.task_result import NoteEvent
from utils.note_quantizer import (
    midi_to_nbs_key,
    quantize_time_to_tick,
    quantize_time_floor,
    quantize_time_ceil,
)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class QuantizedNote:
    """A single NBS-ready note after quantization and envelope processing."""

    tick: int
    key: int  # NBS key 0-72
    velocity: int  # 1-100
    instrument: int = 0
    layer: int = 0
    pitch: int = 60  # original MIDI pitch (for debugging)


@dataclass
class ChordGroup:
    """A group of notes at the same tick (within a tolerance window)."""

    tick: int
    notes: List[QuantizedNote] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Velocity envelope extractor
# ---------------------------------------------------------------------------

class VelocityEnvelopeExtractor:
    """Extract per-tick RMS velocity envelope from audio.

    Uses dual filtering (median + gaussian) to remove transient spikes
    while preserving musical dynamic shape (crescendo / decrescendo).
    """

    def __init__(
        self,
        sr: int = 44100,
        enable_filtering: bool = True,
        median_size: int = 5,
        gaussian_sigma: float = 2.0,
    ) -> None:
        self.sr = sr
        self.enable_filtering = enable_filtering
        self.median_size = median_size
        self.gaussian_sigma = gaussian_sigma

    def extract(
        self,
        audio: np.ndarray,
        note_start: float,
        note_end: float,
        tps: float = 10.0,
    ) -> List[int]:
        """Extract velocity envelope for a single note's duration.

        Parameters
        ----------
        audio : np.ndarray
            Full track audio (mono).
        note_start : float
            Note start time in seconds.
        note_end : float
            Note end time in seconds.
        tps : float
            Ticks per second.

        Returns
        -------
        List[int]
            Per-tick velocity values (1-100).
        """
        if audio.ndim > 1:
            audio = librosa.to_mono(audio)

        hop_length = int(self.sr / tps)
        if hop_length < 1:
            hop_length = 1

        # RMS energy over the whole track
        rms = librosa.feature.rms(
            y=audio,
            frame_length=max(hop_length * 2, 512),
            hop_length=hop_length,
        )[0]

        start_idx = int(note_start * tps)
        end_idx = min(int(note_end * tps) + 1, len(rms))
        note_rms = rms[start_idx:end_idx]

        if len(note_rms) == 0:
            return [50]

        if self.enable_filtering:
            note_rms = self._apply_dual_filter(note_rms)

        # Relative amplitude mapping: preserve dynamic shape
        max_val = float(note_rms.max())
        if max_val > 1e-10:
            normalized = note_rms / max_val
            velocity = (normalized * 100).astype(int)
        else:
            velocity = np.ones_like(note_rms, dtype=int) * 50

        return np.clip(velocity, 1, 100).tolist()

    def _apply_dual_filter(self, rms: np.ndarray) -> np.ndarray:
        """Dual-stage filtering to remove non-musical spikes.

        Stage 1 (median): remove isolated transient spikes (breath, drum bleed).
        Stage 2 (gaussian): smooth envelope while keeping crescendo shape.
        """
        # Stage 1: median filter removes 1-2 tick isolated spikes
        rms = median_filter(rms, size=self.median_size)

        # Stage 2: gaussian smoothing (~0.4s window at TPS=10)
        rms = gaussian_filter1d(rms, sigma=self.gaussian_sigma)

        return rms


# ---------------------------------------------------------------------------
# Main processing functions
# ---------------------------------------------------------------------------

async def process_notes_with_expression(
    note_events: List[NoteEvent],
    track_audio: np.ndarray,
    instrument_id: int,
    layer_id: int,
    tps: float = 10.0,
    enable_envelope_filter: bool = True,
    chord_window_ms: float = 50.0,
) -> List[QuantizedNote]:
    """Full three-layer expressiveness pipeline.

    Parameters
    ----------
    note_events : List[NoteEvent]
        Detected note events (Basic Pitch output).
    track_audio : np.ndarray
        Audio for this track (used for RMS envelope extraction).
    instrument_id : int
        NBS instrument ID (0-15).
    layer_id : int
        NBS layer ID (0=Drums, 1=Bass, 2=Harmony, 3=Melody).
    tps : float
        Ticks per second.
    enable_envelope_filter : bool
        Whether to apply dual filtering to velocity envelope.
    chord_window_ms : float
        Tolerance window (ms) for grouping notes into chords.

    Returns
    -------
    List[QuantizedNote]
        All processed notes sorted by tick, then key.
    """
    if not note_events:
        return []

    extractor = VelocityEnvelopeExtractor(
        sr=44100,
        enable_filtering=enable_envelope_filter,
    )

    all_notes: List[QuantizedNote] = []

    for note in note_events:
        start_tick = quantize_time_floor(note.start_time, tps)
        end_tick = quantize_time_ceil(note.end_time, tps)
        # Ensure minimum 1-tick duration
        end_tick = max(end_tick, start_tick)

        nbs_key = midi_to_nbs_key(note.pitch)

        # Extract velocity envelope
        velocities = extractor.extract(
            audio=track_audio,
            note_start=note.start_time,
            note_end=note.end_time,
            tps=tps,
        )

        # Legato tiling + velocity assignment
        for i, tick in enumerate(range(start_tick, end_tick + 1)):
            vel = velocities[i] if i < len(velocities) else 50

            all_notes.append(
                QuantizedNote(
                    tick=tick,
                    key=nbs_key,
                    velocity=vel,
                    instrument=instrument_id,
                    layer=layer_id,
                    pitch=note.pitch,
                )
            )

    # Sort by tick, then key
    all_notes.sort(key=lambda n: (n.tick, n.key))

    return all_notes


async def group_notes_as_chords(
    notes: List[QuantizedNote],
    tolerance_ticks: int = 1,
) -> Dict[int, List[QuantizedNote]]:
    """Group notes at the same tick (within tolerance) into chords.

    Parameters
    ----------
    notes : List[QuantizedNote]
        Flat list of processed notes.
    tolerance_ticks : int
        Number of ticks tolerance for grouping.

    Returns
    -------
    Dict[int, List[QuantizedNote]]
        Mapping from tick to list of simultaneous notes.
    """
    if not notes:
        return {}

    grouped: Dict[int, List[QuantizedNote]] = {}
    sorted_notes = sorted(notes, key=lambda n: n.tick)

    current_tick = sorted_notes[0].tick
    current_group: List[QuantizedNote] = []

    for note in sorted_notes:
        if note.tick - current_tick <= tolerance_ticks:
            current_group.append(note)
        else:
            grouped[current_tick] = current_group
            current_tick = note.tick
            current_group = [note]

    if current_group:
        grouped[current_tick] = current_group

    return grouped


async def process_drums_track(
    note_events: List[NoteEvent],
    track_audio: np.ndarray,
    instrument_map_fn,
    tps: float = 10.0,
) -> List[QuantizedNote]:
    """Specialized processing for drum tracks.

    Drums use rhythm detection instead of pitch detection. Notes are mapped
    to drum-specific NBS instruments based on pitch range.
    """
    if not note_events:
        return []

    all_notes: List[QuantizedNote] = []

    for note in note_events:
        start_tick = quantize_time_to_tick(note.start_time, tps)
        tick = start_tick

        # Map pitch to drum instrument
        drum_inst = instrument_map_fn(note.pitch) if instrument_map_fn else 2
        nbs_key = midi_to_nbs_key(note.pitch)

        all_notes.append(
            QuantizedNote(
                tick=tick,
                key=nbs_key,
                velocity=int(np.clip(note.velocity, 1, 100)),
                instrument=drum_inst,
                layer=0,  # Drums always layer 0
                pitch=note.pitch,
            )
        )

    all_notes.sort(key=lambda n: n.tick)
    return all_notes
