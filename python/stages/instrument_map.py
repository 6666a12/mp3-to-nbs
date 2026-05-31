"""
Timbre-driven instrument mapping for the MP3-to-NBS pipeline.

Maps source-separated tracks and MIDI program numbers to NBS instruments.
All instruments have full 6-octave range (NBS key 0-72) via Noteblocks++.

Layer assignments:
  - Layer 0: Drums
  - Layer 1: Bass
  - Layer 2: Harmony
  - Layer 3: Melody
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# MIDI Drum Map (General MIDI Level 1)
# Maps MIDI note numbers (in the drum kit channel) to NBS drum instruments.
# ---------------------------------------------------------------------------

MIDI_DRUM_MAP: Dict[int, int] = {
    # Kick / Bass drums
    35: 2,   # Acoustic Bass Drum
    36: 2,   # Bass Drum 1
    # Snares
    37: 3,   # Side Stick (use Snare)
    38: 3,   # Acoustic Snare
    40: 3,   # Electric Snare
    # Hi-hats / Clicks
    42: 4,   # Closed Hi-Hat
    44: 4,   # Pedal Hi-Hat
    46: 4,   # Open Hi-Hat
    # Toms (map to Bell / Cow Bell for pitched percussion feel)
    41: 7,   # Low Floor Tom
    43: 7,   # High Floor Tom
    45: 7,   # Low Tom
    47: 7,   # Low-Mid Tom
    48: 7,   # Hi-Mid Tom
    50: 7,   # High Tom
    # Cymbals
    49: 7,   # Crash Cymbal 1
    51: 7,   # Ride Cymbal 1
    52: 7,   # Chinese Cymbal
    53: 7,   # Ride Bell
    55: 7,   # Splash Cymbal
    57: 7,   # Crash Cymbal 2
    59: 7,   # Ride Cymbal 2
    # Cowbell / percussion
    56: 11,  # Cowbell
    39: 11,  # Hand Clap (use Cow Bell)
    54: 11,  # Tambourine
    # Rim shots, clicks
    60: 4,   # Hi Bongo (use Hat)
    61: 4,   # Low Bongo
    62: 7,   # Mute High Conga
    63: 7,   # Open High Conga
    64: 7,   # Low Conga
    # Percussive melodic
    65: 9,   # High Timbale (Xylophone)
    66: 9,   # Low Timbale
    67: 9,   # High Agogo
    68: 9,   # Low Agogo
    69: 11,  # Cabasa
    70: 11,  # Maracas
    71: 9,   # Short Whistle (Xylophone)
    72: 9,   # Long Whistle
    73: 9,   # Short Guiro
    74: 9,   # Long Guiro
    75: 11,  # Claves
    76: 9,   # Hi Wood Block
    77: 9,   # Low Wood Block
    78: 11,  # Mute Cuica
    79: 11,  # Open Cuica
    80: 7,   # Mute Triangle
    81: 7,   # Open Triangle
}


# ---------------------------------------------------------------------------
# MIDI Program Number (Instrument Family) to NBS Instrument
# General MIDI divides programs into 16 families of 8 programs each.
# ---------------------------------------------------------------------------

def midi_program_to_nbs_instrument(program: int) -> int:
    """Map a MIDI program number (0-127) to an NBS instrument (0-15).

    Parameters
    ----------
    program : int
        General MIDI program number.

    Returns
    -------
    int
        NBS instrument ID:
          0 = Harp (Piano/Organ/Strings/Ensemble)
          1 = Double Bass (Bass)
          2/3/4 = Bass Drum / Snare / Hat (Chromatic Percussion)
          5 = Guitar
          6 = Flute (Brass/Reed/Pipe/Winds/Vocals)
          7 = Bell (Synth FX, pitched percussion)
          9 = Xylophone (Percussive)
          13 = Bit (Synth Pad, Lead 8-bit)
          14 = Banjo (Ethnic)
          15 = Pling (Synth Lead)
    """
    family = program // 8

    if family == 0:          # 0-7: Piano
        return 0  # Harp
    elif family == 1:        # 8-15: Chromatic Percussion
        # Distribute among drum instruments
        sub = program % 8
        if sub < 3:
            return 2  # Bass Drum
        elif sub < 6:
            return 3  # Snare
        else:
            return 4  # Hat
    elif family == 2:        # 16-23: Organ
        return 0  # Harp
    elif family == 3:        # 24-31: Guitar
        return 5  # Guitar
    elif family == 4:        # 32-39: Bass
        return 1  # Double Bass
    elif family == 5:        # 40-47: Strings
        return 0  # Harp
    elif family == 6:        # 48-55: Ensemble
        return 0  # Harp
    elif family == 7:        # 56-63: Brass
        return 6  # Flute
    elif family == 8:        # 64-71: Reed
        return 6  # Flute
    elif family == 9:        # 72-79: Pipe
        return 6  # Flute
    elif family == 10:       # 80-87: Synth Lead
        sub = program % 8
        if sub < 4:
            return 15  # Pling
        else:
            return 13  # Bit
    elif family == 11:       # 88-95: Synth Pad
        return 13  # Bit
    elif family == 12:       # 96-103: Synth Effects
        return 7  # Bell
    elif family == 13:       # 104-111: Ethnic
        sub = program % 8
        if sub < 4:
            return 6  # Flute
        else:
            return 14  # Banjo
    elif family == 14:       # 112-119: Percussive
        sub = program % 8
        if sub < 4:
            return 9  # Xylophone
        else:
            return 7  # Bell
    elif family == 15:       # 120-127: Sound Effects
        return 7  # Bell
    else:
        return 0  # Harp (fallback)


# ---------------------------------------------------------------------------
# Stem-to-instrument mapping
# ---------------------------------------------------------------------------

def stem_to_instrument(stem_name: str, midi_program: int = 0) -> int:
    """Determine the NBS instrument for a given stem and optional MIDI program.

    The stem name (from source separation) is the primary determinant.
    For the 'other' stem, the MIDI program number is used as a fallback hint.

    Parameters
    ----------
    stem_name : str
        One of: 'vocals', 'drums', 'bass', 'other'.
    midi_program : int
        MIDI program number for finer-grained mapping (used for 'other').

    Returns
    -------
    int
        NBS instrument ID (0-15).
    """
    mapping: Dict[str, int] = {
        "vocals": 6,   # Flute (breath quality closest to voice)
        "drums": 2,    # Bass Drum (default, individual drum notes use drum map)
        "bass": 1,     # Double Bass (always)
        "other": midi_program_to_nbs_instrument(midi_program),
    }
    return mapping.get(stem_name, 0)


def stem_to_layer(stem_name: str) -> int:
    """Return the default NBS layer for a given stem.

    Layer assignments:
      0 = Drums
      1 = Bass
      2 = Harmony
      3 = Melody
    """
    layer_map: Dict[str, int] = {
        "drums": 0,
        "bass": 1,
        "other": 2,
        "vocals": 3,
    }
    return layer_map.get(stem_name, 2)


def get_drum_instrument(midi_note: int) -> int:
    """Map a drum MIDI note to the appropriate NBS drum instrument.

    Uses the General MIDI drum map; defaults to Snare (3) for unmapped notes.
    """
    return MIDI_DRUM_MAP.get(midi_note, 3)


# ---------------------------------------------------------------------------
# Instrument metadata
# ---------------------------------------------------------------------------

INSTRUMENT_NAMES: Dict[int, str] = {
    0: "Harp",
    1: "Double Bass",
    2: "Bass Drum",
    3: "Snare",
    4: "Click/Hat",
    5: "Guitar",
    6: "Flute",
    7: "Bell",
    8: "Chime",
    9: "Xylophone",
    10: "Iron Xylophone",
    11: "Cow Bell",
    12: "Didgeridoo",
    13: "Bit",
    14: "Banjo",
    15: "Pling",
}


def get_instrument_name(instrument_id: int) -> str:
    """Return the human-readable name for an NBS instrument ID."""
    return INSTRUMENT_NAMES.get(instrument_id, f"Unknown ({instrument_id})")
