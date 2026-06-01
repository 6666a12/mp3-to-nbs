"""
Pydantic data models for the MP3-to-NBS conversion pipeline.

These models are used for progress reporting (stdout JSON lines),
conversion results, and input validation.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ProgressUpdate(BaseModel):
    """Progress update emitted as JSON to stdout during conversion."""

    step: str = Field(..., description="Current pipeline step identifier")
    progress: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Overall progress as a fraction (0-1)",
    )
    message: str = Field(default="", description="Human-readable status message")


class NoteEvent(BaseModel):
    """A detected note event from pitch detection."""

    start_time: float = Field(..., description="Note start time in seconds")
    end_time: float = Field(..., description="Note end time in seconds")
    pitch: int = Field(..., description="MIDI note number (0-127)")
    velocity: float = Field(default=64.0, ge=0.0, le=127.0, description="Note velocity")
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Detection confidence (0-1)"
    )


class StemQuality(BaseModel):
    """Quality assessment for a single separated stem."""

    name: str = Field(..., description="Stem name (vocals, drums, bass, other)")
    purity_score: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Overall purity score (0-1)"
    )
    spectral_leakage: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Spectral leakage amount"
    )
    temporal_bleed: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Temporal bleed amount"
    )
    needs_refinement: bool = Field(
        default=False, description="Whether this stem needs secondary refinement"
    )


class ConversionOptions(BaseModel):
    """Options passed from the Rust frontend to the Python converter."""

    source_separation: bool = Field(
        default=True,
        description="Enable Demucs source separation before pitch detection",
    )
    quality: str = Field(
        default="balanced",
        pattern="^(fast|balanced|high)$",
        description="Conversion quality: fast, balanced, or high",
    )
    tps: float = Field(
        default=0.0,
        ge=0.0,
        le=60.0,
        description="Ticks per second (0 = auto-detect from BPM)",
    )
    use_gpu: bool = Field(
        default=False,
        description="Enable GPU acceleration for Demucs source separation (requires CUDA)",
    )


class ConversionResult(BaseModel):
    """Final result returned by the converter upon success."""

    output_path: str = Field(..., description="Full path to the generated NBS file")
    nbs_file_name: str = Field(default="", description="Base name of the NBS file")
    tempo: float = Field(default=120.0, description="Detected tempo in BPM")
    total_ticks: int = Field(default=0, description="Total ticks in the NBS file")
    note_count: int = Field(default=0, description="Total number of notes placed")
    layer_count: int = Field(default=0, description="Number of layers used")
