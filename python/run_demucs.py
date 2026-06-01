"""
Wrapper script that patches torchaudio.save to use scipy.io.wavfile,
avoiding the torchcodec / FFmpeg shared-library dependency on Windows.

Usage: python run_demucs.py [all the same args as python -m demucs.separate]
"""

import os
import sys
from pathlib import Path

import numpy as np
import torch
import torchaudio
from scipy.io import wavfile


# ── Monkey-patch torchaudio.load BEFORE any demucs import ──────────────────
# torchaudio 2.11+ requires torchcodec (often missing on Windows).
# Fall back to librosa which already handles MP3/WAV/FLAC via audioread/ffmpeg.
_original_ta_load = torchaudio.load


def _patched_ta_load(
    uri,
    frame_offset=0,
    num_frames=-1,
    normalize=True,
    channels_first=True,
    **kwargs,
):
    """Drop-in replacement using librosa (avoids torchcodec dependency)."""
    import librosa

    # librosa natively resamples to 22050; get the native sr instead
    audio_np, sr = librosa.load(
        str(uri),
        sr=None,  # keep native sample rate
        mono=False,  # preserve channels
        offset=frame_offset / 44100.0 if frame_offset else 0.0,
        duration=(num_frames / 44100.0) if num_frames > 0 else None,
    )
    # librosa returns [samples] for mono, [channels, samples] for stereo
    if audio_np.ndim == 1:
        audio_np = audio_np[np.newaxis, :]  # [1, samples]
    # Convert to torch tensor
    waveform = torch.from_numpy(audio_np.astype(np.float32))
    if not channels_first:
        waveform = waveform.T  # [samples, channels]
    return waveform, int(sr)


torchaudio.load = _patched_ta_load


# ── Monkey-patch torchaudio.save BEFORE any demucs import ──────────────────
_original_ta_save = torchaudio.save


def _patched_ta_save(
    uri,
    src,
    sample_rate,
    channels_first=True,
    format="wav",
    encoding=None,
    bits_per_sample=None,
    **kwargs,
):
    """Drop-in replacement using scipy.io.wavfile instead of torchcodec."""
    # Convert tensor to numpy
    audio_np = src.data.cpu().numpy()
    if audio_np.ndim == 2 and channels_first:
        audio_np = audio_np.T  # [channels, samples] → [samples, channels]
    elif audio_np.ndim == 1:
        pass  # already [samples]
    else:
        audio_np = audio_np.squeeze()

    # Determine dtype
    if bits_per_sample == 32 or (encoding and "F" in str(encoding)):
        dtype = np.int32
        max_val = float(np.iinfo(np.int32).max)
    else:
        dtype = np.int16
        max_val = float(np.iinfo(np.int16).max)

    # Normalize and scale
    peak = float(np.abs(audio_np).max())
    if peak > 0:
        audio_scaled = (audio_np / peak) * max_val * 0.95
    else:
        audio_scaled = audio_np
    audio_scaled = np.clip(audio_scaled, -max_val, max_val - 1).astype(dtype)

    wavfile.write(str(uri), sample_rate, audio_scaled)


torchaudio.save = _patched_ta_save


def _setup_ffmpeg_path():
    """Ensure ffmpeg/ffprobe are findable on PATH for audio loading."""
    try:
        import imageio_ffmpeg
        import shutil

        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        ffmpeg_dir = os.path.dirname(ffmpeg_exe)

        # Create plain ffmpeg.exe alias if needed
        ffmpeg_alias = os.path.join(ffmpeg_dir, "ffmpeg.exe")
        if not os.path.exists(ffmpeg_alias):
            shutil.copy2(ffmpeg_exe, ffmpeg_alias)

        # Create ffprobe.exe alias if we have the binary
        ffprobe_alias = os.path.join(ffmpeg_dir, "ffprobe.exe")
        ffprobe_orig = ffmpeg_exe.replace("ffmpeg", "ffprobe")
        if not os.path.exists(ffprobe_alias) and os.path.exists(ffprobe_orig):
            shutil.copy2(ffprobe_orig, ffprobe_alias)

        os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        pass


if __name__ == "__main__":
    # 1. Set up ffmpeg/ffprobe PATH (needed for demucs audio loading)
    _setup_ffmpeg_path()

    # 2. Now import demucs — torchaudio.save is already patched
    import demucs.separate

    # 3. Run demucs with the original CLI args
    sys.argv[0] = sys.executable + " -m demucs.separate"
    demucs.separate.main()
