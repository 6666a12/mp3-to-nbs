"""
Note quantization utilities for the MP3-to-NBS conversion pipeline.

Handles MIDI-to-NBS key mapping, octave shifting for out-of-range notes,
and time-to-tick conversion.
"""

from __future__ import annotations

import math
from typing import Tuple

# NBS key range for 6-octave Noteblocks++: 0-72
# Maps to MIDI notes 9-81 (F#1 to F#7)
NBS_KEY_MIN = 0
NBS_KEY_MAX = 72
MIDI_NOTE_MIN = 9
MIDI_NOTE_MAX = 81


def midi_to_nbs_key(midi_note: int) -> int:
    """Convert a MIDI note number (9-81) to an NBS key (0-72).

    Standard mapping: nbs_key = midi_note - 9

    Out-of-range handling:
    - midi_note > 81: shift down one octave (-12 semitones)
    - midi_note < 9: shift up one octave (+12 semitones)

    Parameters
    ----------
    midi_note : int
        MIDI note number, typically 0-127.

    Returns
    -------
    int
        NBS key in range [0, 72].
    """
    note = midi_note

    # Handle out-of-range: shift octaves until in range or bounded
    while note > MIDI_NOTE_MAX:
        note -= 12
    while note < MIDI_NOTE_MIN:
        note += 12

    nbs_key = note - MIDI_NOTE_MIN
    return max(NBS_KEY_MIN, min(NBS_KEY_MAX, nbs_key))


def nbs_key_to_midi(nbs_key: int) -> int:
    """Convert an NBS key (0-72) back to a MIDI note number.

    Inverse of midi_to_nbs_key: midi_note = nbs_key + 9

    Parameters
    ----------
    nbs_key : int
        NBS key in range [0, 72].

    Returns
    -------
    int
        MIDI note number.
    """
    nbs_key = max(NBS_KEY_MIN, min(NBS_KEY_MAX, nbs_key))
    return nbs_key + MIDI_NOTE_MIN


def quantize_time_to_tick(time_seconds: float, tps: float) -> int:
    """Convert a time in seconds to an NBS tick number.

    Parameters
    ----------
    time_seconds : float
        Time in seconds.
    tps : float
        Ticks per second for the NBS file.

    Returns
    -------
    int
        Nearest tick number.
    """
    if tps <= 0:
        raise ValueError(f"TPS must be positive, got {tps}")
    return int(round(time_seconds * tps))


def quantize_time_floor(time_seconds: float, tps: float) -> int:
    """Convert a time in seconds to a tick number, rounding down.

    Useful for start-of-note alignment.
    """
    if tps <= 0:
        raise ValueError(f"TPS must be positive, got {tps}")
    return int(math.floor(time_seconds * tps))


def quantize_time_ceil(time_seconds: float, tps: float) -> int:
    """Convert a time in seconds to a tick number, rounding up.

    Useful for end-of-note alignment.
    """
    if tps <= 0:
        raise ValueError(f"TPS must be positive, got {tps}")
    return int(math.ceil(time_seconds * tps))


def ticks_to_time(tick: int, tps: float) -> float:
    """Convert a tick number back to time in seconds.

    Parameters
    ----------
    tick : int
        NBS tick.
    tps : float
        Ticks per second.

    Returns
    -------
    float
        Time in seconds.
    """
    if tps <= 0:
        raise ValueError(f"TPS must be positive, got {tps}")
    return tick / tps


def clamp_midi_to_valid_range(midi_note: int) -> Tuple[int, bool]:
    """Clamp a MIDI note to the valid 6-octave range.

    Returns (adjusted_midi_note, was_adjusted).
    """
    was_adjusted = False
    note = midi_note
    while note > MIDI_NOTE_MAX:
        note -= 12
        was_adjusted = True
    while note < MIDI_NOTE_MIN:
        note += 12
        was_adjusted = True
    return note, was_adjusted


def is_midi_in_range(midi_note: int) -> bool:
    """Check whether a MIDI note is within the 6-octave range without adjustment."""
    return MIDI_NOTE_MIN <= midi_note <= MIDI_NOTE_MAX
