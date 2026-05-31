"""
MP3-to-NBS Converter -- Main Entry Point.

Called by the Rust backend via subprocess:
  python converter.py <input_audio> --output-dir <dir> [options]

Progress is reported as JSON lines on stdout (flush=True).
On completion, a ConversionResult JSON is printed to stdout.
On error, a {"error": "..."} JSON is printed to stderr.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

from models.task_result import (
    ConversionOptions,
    ConversionResult,
    ProgressUpdate,
    NoteEvent,
)
from utils.audio_loader import load_audio, load_audio_multichannel
from utils.note_quantizer import midi_to_nbs_key
from stages.beat_tracking import detect_tempo_and_beats
from stages.pitch_detection import detect_pitches
from stages.midi_processing import (
    process_notes_with_expression,
    process_drums_track,
)
from stages.instrument_map import (
    stem_to_instrument,
    stem_to_layer,
    get_drum_instrument,
    get_instrument_name,
)
from stages.nbs_generator import generate_nbs
from stages.source_separation import CascadedSourceSeparator


# ---------------------------------------------------------------------------
# Progress helpers
# ---------------------------------------------------------------------------

def report_progress(step: str, progress: float, message: str = "") -> None:
    """Emit a progress update as a JSON line to stdout."""
    update = ProgressUpdate(step=step, progress=progress, message=message)
    print(json.dumps(update.model_dump()), flush=True)


def report_error(description: str) -> None:
    """Emit an error as JSON to stderr."""
    print(json.dumps({"error": description}), flush=True, file=sys.stderr)


# ---------------------------------------------------------------------------
# Main conversion
# ---------------------------------------------------------------------------

async def run_conversion(
    input_path: str,
    output_dir: str,
    options: ConversionOptions,
) -> ConversionResult:
    """Run the full MP3-to-NBS conversion pipeline.

    Parameters
    ----------
    input_path : str
        Path to the input audio file.
    output_dir : str
        Directory where the output NBS file will be written.
    options : ConversionOptions
        Conversion parameters.

    Returns
    -------
    ConversionResult
        Metadata about the generated NBS file.
    """
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    song_name = input_path.stem
    audio_duration = 0.0

    # ==================================================================
    # Step 1: Load audio
    # ==================================================================
    report_progress("loading", 0.0, "Loading audio file...")

    audio, sample_rate = await load_audio(input_path, target_sr=44100, mono=True)
    audio_duration = len(audio) / sample_rate

    report_progress("loading", 0.05, f"Loaded {audio_duration:.1f}s of audio")

    # ==================================================================
    # Step 2: Source separation (optional)
    # ==================================================================
    stems: Dict[str, np.ndarray] = {}

    if options.source_separation:
        report_progress(
            "source_separation", 0.05, "Running source separation (Phase 1: coarse)..."
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            separator = CascadedSourceSeparator(temp_dir=temp_dir)
            stems = await separator.separate(input_path)

        report_progress(
            "source_separation",
            0.20,
            f"Source separation complete: {len(stems)} stems",
        )
    else:
        # No source separation: treat whole audio as "other" stem
        stems = {"other": audio}
        report_progress("loading", 0.10, "Skipping source separation (disabled)")

    # ==================================================================
    # Step 3: Beat tracking (on the full mix)
    # ==================================================================
    report_progress("beat_tracking", 0.25, "Detecting tempo and beats...")

    tps = options.tps
    tempo_bpm = tps * 15.0  # default conversion

    # Use the mix or 'other' stem for beat detection
    beat_audio = stems.get("other", audio)
    if beat_audio.size == 0:
        beat_audio = audio.copy()

    tempo_bpm, detected_tps, beat_frames = await detect_tempo_and_beats(
        beat_audio, sample_rate
    )

    # Use detected TPS if user didn't override (tps=0 means auto-detect)
    if options.tps <= 0:
        tps = detected_tps
    else:
        # User-specified TPS takes precedence, but keep the detected BPM for metadata
        pass

    report_progress(
        "beat_tracking",
        0.30,
        f"Tempo: {tempo_bpm:.1f} BPM, TPS: {tps:.2f}",
    )

    # ==================================================================
    # Step 4: Process each stem
    # ==================================================================
    stem_names = ["drums", "bass", "other", "vocals"]
    # Only process stems that exist
    available_stems = [s for s in stem_names if s in stems and stems[s].size > 0]

    notes_by_layer: Dict[int, List[Dict[str, Any]]] = {0: [], 1: [], 2: [], 3: []}
    total_notes = 0
    stem_count = len(available_stems)

    for idx, stem_name in enumerate(available_stems):
        base_progress = 0.30 + (idx / stem_count) * 0.55
        stem_audio = stems[stem_name]
        layer_id = stem_to_layer(stem_name)

        report_progress(
            "pitch_detection",
            base_progress,
            f"Detecting pitches in {stem_name} stem...",
        )

        # Pitch detection
        if stem_name == "drums":
            # Drums: use pitch detection but interpret results as rhythm events
            note_events = await detect_pitches(
                stem_audio, sample_rate,
                onset_threshold=0.4,  # slightly more sensitive for drums
                frame_threshold=0.25,
            )
        else:
            note_events = await detect_pitches(stem_audio, sample_rate)

        if not note_events:
            report_progress(
                "pitch_detection",
                base_progress + 0.05,
                f"No notes detected in {stem_name}, skipping",
            )
            continue

        # Determine instrument and process notes
        if stem_name == "drums":
            # Drum-specific processing
            processed = await process_drums_track(
                note_events=note_events,
                track_audio=stem_audio,
                instrument_map_fn=get_drum_instrument,
                tps=tps,
            )
        else:
            instrument_id = stem_to_instrument(stem_name)
            processed = await process_notes_with_expression(
                note_events=note_events,
                track_audio=stem_audio,
                instrument_id=instrument_id,
                layer_id=layer_id,
                tps=tps,
            )

        # Collect notes
        for note in processed:
            notes_by_layer[layer_id].append(
                {
                    "tick": note.tick,
                    "key": note.key,
                    "instrument": note.instrument,
                    "velocity": note.velocity,
                }
            )

        total_notes += len(processed)

        report_progress(
            "pitch_detection",
            base_progress + 0.05,
            f"Processed {stem_name}: {len(processed)} notes (inst={get_instrument_name(stem_to_instrument(stem_name))})",
        )

    # ==================================================================
    # Step 5: Generate NBS file
    # ==================================================================
    report_progress("generating_nbs", 0.85, "Generating NBS file...")

    output_path = output_dir / f"{song_name}.nbs"
    output_path_str, stats = await generate_nbs(
        notes_by_layer=notes_by_layer,
        output_path=output_path,
        song_name=song_name,
        song_author="MP3-to-NBS Converter",
        description=f"Converted from {input_path.name}\n"
                    f"BPM: {tempo_bpm:.1f} (TPS: {tps:.2f})",
        tempo=tps,
    )

    report_progress("complete", 1.0, f"Conversion complete: {stats['note_count']} notes")

    # ==================================================================
    # Return result
    # ==================================================================
    return ConversionResult(
        output_path=output_path_str,
        nbs_file_name=output_path.name,
        tempo=tempo_bpm,
        total_ticks=stats["total_ticks"],
        note_count=stats["note_count"],
        layer_count=stats["layer_count"],
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert audio files (MP3/WAV/FLAC/etc.) to Minecraft NBS format.",
    )
    parser.add_argument(
        "input", type=str, help="Path to the input audio file."
    )
    parser.add_argument(
        "--output-dir", type=str, required=True,
        help="Directory for the output NBS file.",
    )
    parser.add_argument(
        "--source-separation", type=str, default="true",
        choices=["true", "false"],
        help="Enable Demucs source separation (default: true).",
    )
    parser.add_argument(
        "--quality", type=str, default="balanced",
        choices=["fast", "balanced", "high"],
        help="Conversion quality preset (default: balanced).",
    )
    parser.add_argument(
        "--tps", type=float, default=0.0,
        help="Ticks per second (0 = auto-detect from BPM, default: auto).",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Build options from CLI args
    options = ConversionOptions(
        source_separation=args.source_separation == "true",
        quality=args.quality,
        tps=args.tps,
    )

    try:
        result = asyncio.run(
            run_conversion(
                input_path=args.input,
                output_dir=args.output_dir,
                options=options,
            )
        )

        # Output final result as JSON to stdout
        print(json.dumps(result.model_dump()), flush=True)

    except FileNotFoundError as e:
        report_error(str(e))
        sys.exit(1)
    except ValueError as e:
        report_error(str(e))
        sys.exit(1)
    except RuntimeError as e:
        report_error(str(e))
        sys.exit(1)
    except Exception as e:
        report_error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
