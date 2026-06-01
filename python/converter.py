"""
MP3-to-NBS Converter -- Main Entry Point.

Called by the Rust backend via subprocess:
  python converter.py <input_audio> --output-dir <dir> [options]

Pipeline order (optimized):
  Step 1: Load audio
  Step 2: Detect metadata (BPM, duration, key) EARLY — before expensive separation
  Step 3: Source separation (optional, demucs)
  Step 4: Beat tracking (uses BPM from step 2)
  Step 5: Pitch detection per stem
  Step 6: NBS generation

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
from stages.beat_tracking import detect_tempo_and_beats, detect_audio_metadata
from stages.pitch_detection import detect_pitches
from stages.midi_processing import (
    process_notes_with_expression,
    process_drums_track,
)
from stages.instrument_map import (
    stem_to_layer,
    get_drum_instrument,
    get_instrument_name,
)
from stages.nbs_generator import generate_nbs
from stages.source_separation import CascadedSourceSeparator
from stages.timbre_classifier import (
    NoteInstrument,
    classify_notes_batch,
    get_classification_stats,
)


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
    """Run the full MP3-to-NBS conversion pipeline."""
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    song_name = input_path.stem

    # ==================================================================
    # Step 1: Load audio
    # ==================================================================
    report_progress("loading", 0.0, f"Loading audio: {input_path.name}")

    audio, sample_rate = await load_audio(input_path, target_sr=44100, mono=True)
    audio_duration = len(audio) / sample_rate

    report_progress("loading", 0.03, f"Loaded: {audio_duration:.1f}s, {sample_rate}Hz")

    # ==================================================================
    # Step 2: Detect metadata EARLY (BPM, key, duration)
    # ==================================================================
    report_progress("loading", 0.05, "Detecting tempo and audio metadata...")

    metadata = await detect_audio_metadata(audio, sample_rate)
    tempo_bpm = metadata["bpm"]
    tps = metadata["tps"]
    # key detection removed

    if options.tps > 0:
        # User override
        tps = options.tps
        tempo_bpm = tps * 15.0

    report_progress(
        "loading", 0.08,
        f"BPM: {tempo_bpm:.1f} | Duration: {audio_duration:.1f}s | TPS: {tps:.2f}",
    )

    # ==================================================================
    # Step 3: Source separation (optional)
    # ==================================================================
    stems: Dict[str, np.ndarray] = {}

    if options.source_separation:
        report_progress(
            "source_separation", 0.10,
            f"Source separation starting ({options.quality} quality)...",
        )

        try:
            quality_thresholds = {"fast": 0.50, "balanced": 0.55, "high": 0.60}
            refine_threshold = quality_thresholds.get(options.quality, 0.82)

            with tempfile.TemporaryDirectory() as temp_dir:
                separator = CascadedSourceSeparator(
                    temp_dir=temp_dir,
                    refinement_threshold=refine_threshold,
                    use_gpu=options.use_gpu,
                )
                stems = await separator.separate(input_path)

            stem_list = ", ".join(sorted(stems.keys()))
            report_progress(
                "source_separation", 0.25,
                f"Separation complete: {len(stems)} stems ({stem_list})",
            )
        except Exception as e:
            report_progress(
                "source_separation", 0.25,
                f"Source separation failed: {e}. Falling back to no separation.",
            )
            stems = {"other": audio}
    else:
        stems = {"other": audio}
        report_progress("loading", 0.10, "Source separation skipped (disabled)")

    # ==================================================================
    # Step 4: Beat tracking
    # ==================================================================
    report_progress(
        "beat_tracking", 0.28,
        f"Beat tracking at {tempo_bpm:.1f} BPM...",
    )

    beat_audio = stems.get("other", audio)
    if beat_audio.size == 0:
        beat_audio = audio.copy()

    final_bpm, final_tps, beat_frames = await detect_tempo_and_beats(
        beat_audio, sample_rate
    )

    # Use detected BPM unless user overrode
    if options.tps <= 0:
        tps = final_tps
        tempo_bpm = final_bpm

    report_progress(
        "beat_tracking", 0.32,
        f"Tempo confirmed: {tempo_bpm:.1f} BPM, TPS={tps:.2f}, {len(beat_frames)} beats",
    )

    # ==================================================================
    # Step 5: Process each stem
    # ==================================================================
    # Process order ensures drums → bass → harmony stems → melody
    stem_names = ["drums", "bass", "piano", "guitar", "other", "vocals"]
    available_stems = [s for s in stem_names if s in stems and stems[s].size > 0]

    notes_by_layer: Dict[int, List[Dict[str, Any]]] = {0: [], 1: [], 2: [], 3: []}
    total_notes = 0
    stem_count = len(available_stems)

    for idx, stem_name in enumerate(available_stems):
        base_progress = 0.32 + (idx / stem_count) * 0.50
        stem_audio = stems[stem_name]
        layer_id = stem_to_layer(stem_name)

        layer_names = {0: "Drums", 1: "Bass", 2: "Harmony", 3: "Melody"}
        layer_name = layer_names.get(layer_id, f"Layer {layer_id}")

        report_progress(
            "pitch_detection", base_progress,
            f"Processing {stem_name} → {layer_name} (layer {layer_id})...",
        )

        # Stem-specific detection parameters:
        #   Drums: short hits need permissive thresholds + low noise gate
        #   Bass:  low register, medium sensitivity
        #   Piano/Guitar: pitched instruments, moderate thresholds
        #   Other/Vocals: pitched, tight thresholds to suppress noise
        if stem_name == "drums":
            note_events = await detect_pitches(
                stem_audio, sample_rate,
                onset_threshold=0.45,
                frame_threshold=0.30,
                min_note_length_ms=60.0,
                minimum_frequency=60.0,
                noise_gate_db=-25.0,
            )
        elif stem_name == "bass":
            note_events = await detect_pitches(
                stem_audio, sample_rate,
                onset_threshold=0.50,
                frame_threshold=0.35,
                min_note_length_ms=80.0,
                minimum_frequency=60.0,
                noise_gate_db=-25.0,
            )
        elif stem_name in ("piano", "guitar"):
            note_events = await detect_pitches(
                stem_audio, sample_rate,
                onset_threshold=0.60,
                frame_threshold=0.45,
                min_note_length_ms=120.0,
                noise_gate_db=-30.0,
            )
        else:
            note_events = await detect_pitches(
                stem_audio, sample_rate,
                onset_threshold=0.70,
                frame_threshold=0.50,
                min_note_length_ms=180.0,
            )

        if not note_events:
            report_progress(
                "pitch_detection", base_progress + 0.03,
                f"{stem_name}: no notes detected, skipping",
            )
            continue

        # Process notes
        if stem_name == "drums":
            processed = await process_drums_track(
                note_events=note_events,
                track_audio=stem_audio,
                instrument_map_fn=get_drum_instrument,
                tps=tps,
            )
            inst_name = "Drum Map"
        else:
            # Per-note timbre classification
            note_instruments = await classify_notes_batch(
                stem_audio, sample_rate, note_events, stem_name=stem_name,
            )
            processed = await process_notes_with_expression(
                note_events=note_events,
                track_audio=stem_audio,
                note_instruments=note_instruments,
                layer_id=layer_id,
                tps=tps,
            )
            # Build instrument usage summary
            stats = get_classification_stats(note_instruments)
            top3 = sorted(stats.items(), key=lambda x: -x[1])[:3]
            inst_labels = ", ".join(
                f"{get_instrument_name(inst)}×{cnt}" for inst, cnt in top3
            )
            inst_name = f"({inst_labels})"

        # Collect notes from this stem
        for note in processed:
            notes_by_layer[layer_id].append({
                "tick": note.tick,
                "key": note.key,
                "instrument": note.instrument,
                "velocity": note.velocity,
            })

        total_notes += len(processed)

        report_progress(
            "pitch_detection", base_progress + 0.05,
            f"✓ {stem_name}: {len(processed)} notes → {layer_name} [{inst_name}]",
        )

    # ==================================================================
    # Step 6: Generate NBS file
    # ==================================================================
    report_progress(
        "generating_nbs", 0.85,
        f"Generating NBS: {total_notes} notes across layers...",
    )

    output_path = output_dir / f"{song_name}.nbs"
    output_path_str, stats = await generate_nbs(
        notes_by_layer=notes_by_layer,
        output_path=output_path,
        song_name=song_name,
        song_author="MP3-to-NBS Converter",
        description=(
            f"Converted from {input_path.name}\n"
            f"BPM: {tempo_bpm:.1f} | TPS: {tps:.2f}\n"
            f"Stems: {', '.join(sorted(stems.keys()))}"
        ),
        tempo=tps,
    )

    # Final stats
    nbs_size_kb = Path(output_path_str).stat().st_size / 1024

    report_progress(
        "complete", 1.0,
        f"Done! {stats['note_count']} notes, {stats['layer_count']} layers, "
        f"BPM={tempo_bpm:.1f}, "
        f"max_tick={stats['total_ticks']}, file={nbs_size_kb:.1f}KB",
    )

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
    parser.add_argument("input", type=str, help="Path to the input audio file.")
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
        help="Ticks per second (0 = auto-detect, default: auto).",
    )
    parser.add_argument(
        "--use-gpu", action="store_true", default=False,
        help="Enable GPU acceleration for Demucs source separation (requires CUDA).",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    options = ConversionOptions(
        source_separation=args.source_separation == "true",
        quality=args.quality,
        tps=args.tps,
        use_gpu=args.use_gpu,
    )

    try:
        result = asyncio.run(
            run_conversion(
                input_path=args.input,
                output_dir=args.output_dir,
                options=options,
            )
        )
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
