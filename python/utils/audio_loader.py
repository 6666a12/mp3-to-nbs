"""
Audio file loading utility.

Loads MP3, WAV, FLAC, M4A, and OGG files via librosa,
converts to mono if needed, and returns the audio array
along with its sample rate.
"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

import numpy as np
import librosa


SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac", ".wma"}


async def load_audio(
    file_path: str | Path,
    target_sr: int = 44100,
    mono: bool = True,
) -> Tuple[np.ndarray, int]:
    """Load an audio file and return (audio_array, sample_rate).

    Parameters
    ----------
    file_path : str or Path
        Full path to the audio file.
    target_sr : int
        Desired sample rate (default 44100).
    mono : bool
        If True, convert multichannel audio to mono.

    Returns
    -------
    audio : np.ndarray
        Audio waveform as a 1D (mono) or 2D (stereo) float32 numpy array
        with values in [-1, 1].
    sr : int
        Actual sample rate of the loaded audio (equals target_sr).

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    ValueError
        If the file format is unsupported or the file is corrupt.
    """
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    suffix = file_path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported audio format '{suffix}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    try:
        audio, sr = librosa.load(
            str(file_path),
            sr=target_sr,
            mono=mono,
        )
    except Exception as exc:
        raise ValueError(
            f"Failed to load audio file '{file_path}': {exc}"
        ) from exc

    if audio.size == 0:
        raise ValueError(f"Audio file is empty or silent: {file_path}")

    return audio, sr


async def load_audio_multichannel(
    file_path: str | Path,
    target_sr: int = 44100,
) -> Tuple[np.ndarray, int]:
    """Load audio preserving original channel count.

    Returns (audio, sr) where audio may be 1D (mono) or 2D (multichannel).
    """
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    suffix = file_path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported audio format '{suffix}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    try:
        audio, sr = librosa.load(
            str(file_path),
            sr=target_sr,
            mono=False,
        )
    except Exception as exc:
        raise ValueError(
            f"Failed to load audio file '{file_path}': {exc}"
        ) from exc

    if audio.size == 0:
        raise ValueError(f"Audio file is empty or silent: {file_path}")

    return audio, sr


async def get_audio_duration(file_path: str | Path) -> float:
    """Return the duration in seconds of an audio file without fully loading it."""
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    try:
        duration = librosa.get_duration(path=str(file_path))
        return float(duration)
    except Exception as exc:
        raise ValueError(
            f"Failed to get duration for '{file_path}': {exc}"
        ) from exc
