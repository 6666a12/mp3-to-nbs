"""
NBS file generation stage using pynbs.

Creates a standard NBS file with metadata, layers, and notes from the
processing pipeline. The file follows pynbs standard format with no
custom fields.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pynbs

from models.task_result import NoteEvent
from utils.note_quantizer import midi_to_nbs_key


# Layer names in the NBS file
LAYER_NAMES: Dict[int, str] = {
    0: "Drums",
    1: "Bass",
    2: "Harmony",
    3: "Melody",
}


async def generate_nbs(
    notes_by_layer: Dict[int, List[Dict]],
    output_path: str | Path,
    song_name: str = "Converted Song",
    song_author: str = "MP3-to-NBS Converter",
    description: str = "",
    tempo: float = 10.0,
    time_signature: int = 4,
    original_author: str = "",
) -> Tuple[str, Dict]:
    """Generate an NBS file from processed note data.

    Parameters
    ----------
    notes_by_layer : Dict[int, List[Dict]]
        Mapping from layer ID (0-3) to list of note dicts. Each note dict has:
          - tick: int
          - key: int (NBS key 0-72)
          - instrument: int (0-15)
          - velocity: int (1-100)
    output_path : str or Path
        Where to save the .nbs file.
    song_name : str
        Name embedded in the NBS file.
    song_author : str
        Author embedded in the NBS file.
    description : str
        Description embedded in the NBS file.
    tempo : float
        Ticks per second (TPS) for the NBS file.
    time_signature : int
        Time signature numerator (e.g. 4 for 4/4).

    Returns
    -------
    output_path : str
        Full path to the saved NBS file.
    stats : Dict
        Statistics: note_count, layer_count, total_ticks.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Build description string
    full_description = description or "Converted from MP3 via MP3-to-NBS Converter"
    if original_author:
        full_description += f"\nOriginal: {original_author}"
    full_description += "\nMod: 6-Octave Note Blocks (Noteblocks++)"

    # Build layers
    layers: List[pynbs.Layer] = []
    max_layer = max(notes_by_layer.keys()) if notes_by_layer else 0
    for layer_id in range(max_layer + 1):
        layer_name = LAYER_NAMES.get(layer_id, f"Layer {layer_id}")
        layers.append(
            pynbs.Layer(
                id=layer_id,
                name=layer_name,
                lock=False,
                volume=100,
                panning=0,
            )
        )

    # Build notes
    notes: List[pynbs.Note] = []
    note_count = 0
    max_tick = 0

    for layer_id, layer_notes in sorted(notes_by_layer.items()):
        for note_data in layer_notes:
            tick = int(note_data["tick"])
            key = int(note_data["key"])
            instrument = int(note_data.get("instrument", 0))
            velocity = int(note_data.get("velocity", 50))

            # Clamp values to valid ranges
            tick = max(0, tick)
            key = max(0, min(72, key))
            instrument = max(0, min(15, instrument))
            velocity = max(1, min(100, velocity))

            notes.append(
                pynbs.Note(
                    tick=tick,
                    layer=layer_id,
                    instrument=instrument,
                    key=key,
                    velocity=velocity,
                    panning=0,
                    pitch=0,
                )
            )
            note_count += 1
            if tick > max_tick:
                max_tick = tick

    # Create NBS file via new_file helper (pynbs 1.0.0-beta API)
    nbs_file = pynbs.new_file(
        song_name=song_name,
        song_author=song_author,
        original_author=original_author,
        description=full_description,
        tempo=tempo,  # pynbs 1.0.0-beta stores actual TPS, not *100
        time_signature=time_signature,
        song_length=max_tick,
        song_layers=len(layers),
        blocks_added=note_count,
        default_instruments=16,
    )

    nbs_file.layers = layers
    nbs_file.notes = notes
    nbs_file.update_header(version=5)

    # Save to file
    nbs_file.save(str(output_path))

    stats = {
        "note_count": note_count,
        "layer_count": len(layers),
        "total_ticks": max_tick,
    }

    return str(output_path), stats


async def create_empty_nbs(
    output_path: str | Path,
    song_name: str = "Empty",
    tempo: float = 10.0,
) -> str:
    """Create an empty NBS file (no notes) for testing or placeholder use."""
    output_path = Path(output_path)
    notes: Dict[int, List[Dict]] = {}
    path, _ = await generate_nbs(
        notes_by_layer=notes,
        output_path=output_path,
        song_name=song_name,
        tempo=tempo,
    )
    return path
