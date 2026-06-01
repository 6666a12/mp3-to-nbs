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

    # Layers are built after polyphony resolution (see overflow section below).
    layers: List[pynbs.Layer] = []

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

    # ---- Save original stem family on each note before sorting ----------
    FAMILY_MAP = {0: "Drums", 1: "Bass", 2: "Harmony", 3: "Melody"}
    for n in notes:
        n._family = FAMILY_MAP.get(n.layer, f"Stem{n.layer}")

    # Sort notes by tick (then layer) — REQUIRED by NBS jump-encoding format.
    notes.sort(key=lambda n: (n.tick, n.layer))

    # ---- Resolve polyphony via stem-family overflow slots -----------------
    # NBS allows one note per layer per tick.  Overlapping legato tiles
    # produce multiple notes at the same (tick, layer).  We assign each note
    # a "slot" within its stem family (0 = base, 1+ = overflow).
    occupied: set = set()         # (tick, family, slot)
    family_max_slot: dict = {}    # family_name → highest slot used
    overflow_added = 0

    for n in notes:
        family = n._family
        slot = 0
        while (n.tick, family, slot) in occupied:
            slot += 1
        occupied.add((n.tick, family, slot))
        family_max_slot[family] = max(family_max_slot.get(family, 0), slot)
        n._slot = slot          # temporary: slot within family
        if slot > 0:
            overflow_added += 1

    # ---- Build contiguous layer ID mapping per family --------------------
    # Families are ordered: Drums, Bass, Harmony, Melody.  Within each
    # family, layers are numbered sequentially (0 = base, 1+ = overflow).
    # This keeps related layers adjacent in OpenNBS.
    FAMILY_ORDER = ["Drums", "Bass", "Harmony", "Melody"]
    family_start_lid: dict = {}   # family_name → first global layer ID
    lid = 0
    for family in FAMILY_ORDER:
        family_start_lid[family] = lid
        lid += family_max_slot.get(family, 0) + 1
    total_layers = lid

    # ---- Remap notes: (family, slot) → contiguous global layer ID -------
    for n in notes:
        start = family_start_lid[n._family]
        n.layer = start + n._slot

    # ---- Build final layers list with proper names -----------------------
    layers.clear()
    for family in FAMILY_ORDER:
        start = family_start_lid[family]
        count = family_max_slot.get(family, 0) + 1
        for s in range(count):
            lid = start + s
            name = family if s == 0 else f"{family} {s + 1}"
            layers.append(pynbs.Layer(
                id=lid,
                name=name,
                lock=False,
                volume=100,
                panning=0,
            ))

    if overflow_added > 0:
        print(json.dumps({
            "step": "generating_nbs",
            "progress": 0.87,
            "message": (
                f"Polyphony resolved: {overflow_added} overflow notes, "
                f"{total_layers} layers ({', '.join(f'{f}×{family_max_slot.get(f,0)+1}' for f in FAMILY_ORDER)})"
            ),
        }), flush=True)

    # Recalculate after overflow resolution
    max_tick = max(n.tick for n in notes) if notes else 0
    note_count = len(notes)

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

    # Safety: clamp song_length to NBS SHORT range (0-65535)
    if nbs_file.header.song_length > 65535:
        nbs_file.header.song_length = 65535

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
