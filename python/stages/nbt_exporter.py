"""
NBS to .nbt structure exporter (auxiliary feature).

Exports an NBS file as a gzip-compressed Minecraft .nbt structure file
compatible with the Noteblocks++ mod (6-octave support).

Layout:
  X-axis = time (repeater chain spacing)
  Y-axis = layer (stacked vertically)
  Z-axis = chord expansion (simultaneous notes spread horizontally)
"""

from __future__ import annotations

import gzip
import json
import struct
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pynbs


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# NBS instrument ID -> Noteblocks++ block state instrument string
INSTRUMENT_TO_BLOCKSTATE: Dict[int, str] = {
    0: "harp",
    1: "bass",
    2: "basedrum",
    3: "snare",
    4: "hat",
    5: "guitar",
    6: "flute",
    7: "bell",
    8: "chime",
    9: "xylophone",
    10: "iron_xylophone",
    11: "cow_bell",
    12: "didgeridoo",
    13: "bit",
    14: "banjo",
    15: "pling",
}

# NBS instrument ID -> block placed below the note block to set instrument
INSTRUMENT_BASE_BLOCK: Dict[int, str] = {
    0: "minecraft:stone",
    1: "minecraft:oak_planks",
    2: "minecraft:stone",
    3: "minecraft:sand",
    4: "minecraft:glass",
    5: "minecraft:white_wool",
    6: "minecraft:clay",
    7: "minecraft:gold_block",
    8: "minecraft:nether_bricks",
    9: "minecraft:bone_block",
    10: "minecraft:iron_block",
    11: "minecraft:soul_sand",
    12: "minecraft:pumpkin",
    13: "minecraft:emerald_block",
    14: "minecraft:hay_block",
    15: "minecraft:glowstone",
}

DEFAULT_DATA_VERSION = 3953  # Minecraft 1.21


# ---------------------------------------------------------------------------
# Key conversion
# ---------------------------------------------------------------------------

def key_to_octave_note(nbs_key: int) -> Tuple[str, int]:
    """Convert NBS key (0-72) to (octave_str, note_0_24) for Noteblocks++.

    Noteblocks++ divides the 6-octave range into three 2-octave bands:
      - low:    keys 0-24  (F#1 to F#3), note = key
      - mid:    keys 25-49 (F#3 to F#5), note = key - 25
      - high:   keys 50-72 (F#5 to F#7), note = key - 50
    """
    k = max(0, min(72, nbs_key))
    if k <= 24:
        return "low", k
    elif k <= 49:
        return "mid", k - 25
    else:
        return "high", k - 50


# ---------------------------------------------------------------------------
# NBT binary writer helpers
# ---------------------------------------------------------------------------

class _NBTWriter:
    """Minimal NBT binary format writer."""

    TAG_END = 0
    TAG_BYTE = 1
    TAG_SHORT = 2
    TAG_INT = 3
    TAG_LONG = 4
    TAG_FLOAT = 5
    TAG_DOUBLE = 6
    TAG_BYTE_ARRAY = 7
    TAG_STRING = 8
    TAG_LIST = 9
    TAG_COMPOUND = 10
    TAG_INT_ARRAY = 11
    TAG_LONG_ARRAY = 12

    def __init__(self) -> None:
        self._buf = BytesIO()

    def getvalue(self) -> bytes:
        return self._buf.getvalue()

    def _write_tag_header(self, tag_id: int, name: str | None) -> None:
        self._buf.write(struct.pack(">b", tag_id))
        if name is not None:
            name_bytes = name.encode("utf-8")
            self._buf.write(struct.pack(">H", len(name_bytes)))
            self._buf.write(name_bytes)

    def write_compound_start(self, name: str | None = None) -> None:
        self._write_tag_header(self.TAG_COMPOUND, name)

    def write_int(self, name: str, value: int) -> None:
        self._write_tag_header(self.TAG_INT, name)
        self._buf.write(struct.pack(">i", value))

    def write_short(self, name: str, value: int) -> None:
        self._write_tag_header(self.TAG_SHORT, name)
        self._buf.write(struct.pack(">h", value))

    def write_string(self, name: str, value: str) -> None:
        self._write_tag_header(self.TAG_STRING, name)
        value_bytes = value.encode("utf-8")
        self._buf.write(struct.pack(">H", len(value_bytes)))
        self._buf.write(value_bytes)

    def write_byte_array(self, name: str, data: bytes) -> None:
        self._write_tag_header(self.TAG_BYTE_ARRAY, name)
        self._buf.write(struct.pack(">i", len(data)))
        self._buf.write(data)

    def write_int_array(self, name: str, values: List[int]) -> None:
        self._write_tag_header(self.TAG_INT_ARRAY, name)
        self._buf.write(struct.pack(">i", len(values)))
        for v in values:
            self._buf.write(struct.pack(">i", v))

    def write_list_start(self, name: str, element_tag_id: int, count: int) -> None:
        self._write_tag_header(self.TAG_LIST, name)
        self._buf.write(struct.pack(">b", element_tag_id))
        self._buf.write(struct.pack(">i", count))

    def write_tag_end(self) -> None:
        self._buf.write(struct.pack(">b", self.TAG_END))


# ---------------------------------------------------------------------------
# Exporter
# ---------------------------------------------------------------------------

class NBTStructureExporter:
    """Export an NBS file to a Minecraft .nbt structure file.

    The exported structure uses a linear layout:
      - X = time (repeater chain), spacing blocks per tick
      - Y = layer offset
      - Z = chord expansion for simultaneous notes
    """

    def __init__(
        self,
        data_version: int = DEFAULT_DATA_VERSION,
        spacing: int = 2,
    ) -> None:
        self.data_version = data_version
        self.spacing = spacing

    def export(self, nbs_path: str | Path, output_path: str | Path) -> str:
        """Export an NBS file to a .nbt structure.

        Parameters
        ----------
        nbs_path : str or Path
            Path to the source .nbs file.
        output_path : str or Path
            Destination path for the .nbt file.

        Returns
        -------
        str
            The output path on success.

        Raises
        ------
        FileNotFoundError
            If the NBS file does not exist.
        ValueError
            If the NBS file has no notes.
        """
        nbs_path = Path(nbs_path)
        output_path = Path(output_path)

        if not nbs_path.exists():
            raise FileNotFoundError(f"NBS file not found: {nbs_path}")

        nbs_song = pynbs.read(str(nbs_path))
        notes = list(nbs_song.notes)

        if not notes:
            raise ValueError("NBS file contains no notes")

        # Re-tag notes with their layer info
        max_tick = max(n.tick for n in notes)
        max_layer = max(n.layer for n in notes)

        # Build palette and block list
        palette: List[Tuple[str, str, Dict[str, str]]] = []
        palette_index: Dict[str, int] = {}
        blocks: List[Tuple[int, int, int, int]] = []

        def _get_or_add_palette(key: str, block_state: str) -> int:
            if key not in palette_index:
                palette_index[key] = len(palette)
                # Parse block state for NBT writing
                palette.append((key, block_state, {}))
            return palette_index[key]

        # Group notes by (tick, layer)
        groups: Dict[Tuple[int, int], List[pynbs.Note]] = {}
        for note in notes:
            key = (note.tick, note.layer)
            groups.setdefault(key, []).append(note)

        for (tick, layer), chord in groups.items():
            base_x = tick * self.spacing + 1
            base_y = layer * 3 + 1
            base_z = 1

            for i, note in enumerate(chord):
                z = base_z + i

                inst_str = INSTRUMENT_TO_BLOCKSTATE.get(
                    note.instrument, "harp"
                )
                octave, nt = key_to_octave_note(note.key)

                # Note block
                note_key = f"note_{note.instrument}_{nt}_{octave}"
                note_state = (
                    f'{{"Name":"minecraft:note_block",'
                    f'"Properties":{{"instrument":"{inst_str}",'
                    f'"note":"{nt}","octave":"{octave}","powered":"false"}}}}'
                )
                note_idx = _get_or_add_palette(note_key, note_state)
                blocks.append((base_x, base_y, z, note_idx))

                # Instrument base block (below note block)
                base_id = INSTRUMENT_BASE_BLOCK.get(
                    note.instrument, "minecraft:stone"
                )
                base_key = f"base_{base_id}"
                base_state = f'{{"Name":"{base_id}"}}'
                base_idx = _get_or_add_palette(base_key, base_state)
                blocks.append((base_x, base_y - 1, z, base_idx))

            # Redstone repeater for timing
            rep_key = "repeater"
            rep_state = (
                '{"Name":"minecraft:repeater",'
                '"Properties":{"delay":"1","facing":"east","locked":"false","powered":"false"}}'
            )
            rep_idx = _get_or_add_palette(rep_key, rep_state)
            blocks.append((base_x - 1, base_y - 1, base_z, rep_idx))

        # Redstone wire connecting all ticks
        wire_key = "wire"
        wire_state = (
            '{"Name":"minecraft:redstone_wire",'
            '"Properties":{"east":"side","north":"none","south":"none","west":"side","power":"0"}}'
        )
        wire_idx = _get_or_add_palette(wire_key, wire_state)

        for tick in range(max_tick + 1):
            x = tick * self.spacing + 1
            for layer in range(max_layer + 1):
                y = layer * 3
                blocks.append((x, y, 0, wire_idx))

        # Structure dimensions
        size_x = (max_tick + 1) * self.spacing + 2
        size_y = (max_layer + 1) * 3 + 1
        size_z = 5

        # Build NBT
        nbt_bytes = self._build_nbt(size_x, size_y, size_z, palette, blocks)

        # Write gzip-compressed output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(nbt_bytes)

        return str(output_path)

    # ------------------------------------------------------------------
    # NBT construction
    # ------------------------------------------------------------------

    def _build_nbt(
        self,
        sx: int,
        sy: int,
        sz: int,
        palette: List[Tuple[str, str, Dict[str, str]]],
        blocks: List[Tuple[int, int, int, int]],
    ) -> bytes:
        """Build gzip-compressed NBT structure binary."""
        raw = BytesIO()
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
            w = _NBTWriter()
            w.write_compound_start("")

            # DataVersion
            w.write_int("DataVersion", self.data_version)

            # Size: [sx, sy, sz]
            w.write_int_array("size", [sx, sy, sz])

            # Palette
            w.write_list_start("palette", _NBTWriter.TAG_COMPOUND, len(palette))
            for entry_key, entry_state, _ in palette:
                self._write_palette_entry(w, entry_state)
            # List does not need explicit TAG_End

            # Blocks
            w.write_list_start("blocks", _NBTWriter.TAG_COMPOUND, len(blocks))
            for x, y, z, state in blocks:
                self._write_block_entry(w, x, y, z, state)

            # Entities (empty list)
            w.write_list_start("entities", _NBTWriter.TAG_COMPOUND, 0)

            w.write_tag_end()

            gz.write(w.getvalue())

        return raw.getvalue()

    def _write_palette_entry(self, w: _NBTWriter, state_json: str) -> None:
        """Write a single palette compound entry from a JSON block state string."""
        entry = json.loads(state_json)

        w.write_compound_start()

        w.write_string("Name", entry["Name"])

        if "Properties" in entry and entry["Properties"]:
            w.write_compound_start("Properties")
            for k, v in entry["Properties"].items():
                w.write_string(k, v)
            w.write_tag_end()  # End Properties compound

        w.write_tag_end()  # End palette entry compound

    def _write_block_entry(
        self, w: _NBTWriter, x: int, y: int, z: int, state: int
    ) -> None:
        """Write a single block compound entry."""
        w.write_compound_start()

        # pos: [x, y, z] as TAG_Int_Array style, but standard NBT uses a List of TAG_Int
        # Minecraft structure format uses TAG_List of TAG_Int for pos
        w._write_tag_header(_NBTWriter.TAG_LIST, "pos")
        w._buf.write(struct.pack(">b", _NBTWriter.TAG_INT))
        w._buf.write(struct.pack(">i", 3))
        w._buf.write(struct.pack(">iii", x, y, z))

        # state
        w.write_int("state", state)

        w.write_tag_end()  # End block compound


# ---------------------------------------------------------------------------
# CLI entry point (called by Rust backend)
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entry point for NBS-to-.nbt export.

    Usage:
      python nbt_exporter.py <nbs_path> --output <output_path> \\
          [--spacing <int>] [--data-version <int>]
    """
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Export an NBS file to a Minecraft .nbt structure file.",
    )
    parser.add_argument(
        "nbs_path", type=str, help="Path to the source .nbs file."
    )
    parser.add_argument(
        "--output", type=str, required=True,
        help="Destination path for the .nbt file.",
    )
    parser.add_argument(
        "--spacing", type=int, default=2,
        help="Number of blocks between successive ticks (default: 2).",
    )
    parser.add_argument(
        "--data-version", type=int, default=3953,
        help="Minecraft data version (default: 3953 = MC 1.21).",
    )

    args = parser.parse_args()

    try:
        exporter = NBTStructureExporter(
            data_version=args.data_version,
            spacing=args.spacing,
        )
        output_path = exporter.export(
            nbs_path=args.nbs_path,
            output_path=args.output,
        )
        print(json.dumps({"status": "ok", "output_path": output_path}), flush=True)

    except FileNotFoundError as e:
        print(json.dumps({"error": str(e)}), flush=True, file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(json.dumps({"error": str(e)}), flush=True, file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"error": f"Unexpected error: {e}"}), flush=True, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
