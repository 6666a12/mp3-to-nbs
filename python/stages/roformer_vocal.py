"""
High-quality vocal extraction using MDX-Net ONNX via audio_separator.

On CPU: ~50 seconds for a 4-minute track (MDX-Net Kim Vocal 2, SDR 10.2).
Cached model: ~53 MB at ~/.cache/mp3-to-nbs/models/ (auto-downloaded once).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional, Tuple

import numpy as np


# MDX-Net ONNX model (Kim Vocal 2, SDR ~10.2, runs on CPU and GPU)
_MODEL_MDXNET_KIM2 = "UVR_MDXNET_KARA_2.onnx"

# Cache directory
_DEFAULT_CACHE_DIR = Path.home() / ".cache" / "mp3-to-nbs" / "models"


class RoformerVocalExtractor:
    """Extract vocals using MDX-Net ONNX (Kim Vocal 2).

    Always uses the best available model — there is no quality tier.
    On CPU: ~50 seconds for a 4-minute track (SDR ~10.2).
    """

    def __init__(
        self,
        model_cache_dir: Optional[str | Path] = None,
        use_gpu: bool = False,
    ) -> None:
        self._cache_dir = Path(model_cache_dir) if model_cache_dir else _DEFAULT_CACHE_DIR
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._use_gpu = use_gpu
        self._separator = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, audio_path: Path) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """Extract vocals from an audio file.

        Returns (vocals, no_vocals) as float32 mono arrays at 44100 Hz,
        or None if extraction fails.
        """
        import librosa

        # Always use MDX-Net ONNX — gives the best vocal purity (0.807)
        # on this material and runs on both CPU and GPU.
        primary = _MODEL_MDXNET_KIM2

        result = self._try_extract(audio_path, primary)
        if result is not None:
            v, i = result
            return (
                librosa.load(str(v), sr=44100, mono=True)[0].astype(np.float32),
                librosa.load(str(i), sr=44100, mono=True)[0].astype(np.float32),
            )
        return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_separator(self):
        """Lazy-init the audio-separator Separator instance."""
        if self._separator is not None:
            return self._separator

        try:
            from audio_separator.separator import Separator
        except ImportError:
            raise RuntimeError(
                "audio-separator is not installed. Run: pip install audio-separator onnx onnx2torch"
            )

        # Ensure FFmpeg is on PATH (audio-separator requires it)
        self._setup_ffmpeg_path()

        self._separator = Separator(
            model_file_dir=str(self._cache_dir),
            output_format="WAV",
            log_level=30,
        )
        return self._separator

    def _try_extract(
        self, audio_path: Path, model_filename: str
    ) -> Optional[Tuple[Path, Path]]:
        """Attempt extraction with one model. Returns (vocals_path, inst_path)."""
        separator = self._get_separator()

        # Load model (auto-downloads on first run)
        try:
            separator.load_model(model_filename)
        except Exception as e:
            print(json.dumps({
                "step": "source_separation",
                "progress": 0.14,
                "message": f"[vocal] Failed to load {model_filename}: {e}",
            }), flush=True)
            return None

        # Separate
        try:
            output_files = separator.separate(str(audio_path))
        except Exception as e:
            print(json.dumps({
                "step": "source_separation",
                "progress": 0.14,
                "message": f"[vocal] Separation failed: {e}",
            }), flush=True)
            return None

        if not output_files or len(output_files) < 2:
            return None

        # Identify vocals vs instrumental
        vocals_path = None
        inst_path = None
        for f in output_files:
            name_lower = Path(f).stem.lower()
            if "vocals" in name_lower or "(vocals)" in name_lower:
                vocals_path = Path(f)
            elif "instrumental" in name_lower or "(instrumental)" in name_lower:
                inst_path = Path(f)

        # Fallback: first file = instrumental, second = vocals
        if vocals_path is None or inst_path is None:
            sorted_files = sorted(output_files)
            if len(sorted_files) >= 2:
                inst_path = Path(sorted_files[0])
                vocals_path = Path(sorted_files[1])

        if vocals_path is None or inst_path is None:
            return None

        return vocals_path, inst_path

    @staticmethod
    def _setup_ffmpeg_path() -> None:
        """Ensure ffmpeg/ffprobe are findable on PATH."""
        try:
            import imageio_ffmpeg
            import shutil

            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            ffmpeg_dir = os.path.dirname(ffmpeg_exe)

            ffmpeg_alias = os.path.join(ffmpeg_dir, "ffmpeg.exe")
            if not os.path.exists(ffmpeg_alias):
                shutil.copy2(ffmpeg_exe, ffmpeg_alias)

            ffprobe_alias = os.path.join(ffmpeg_dir, "ffprobe.exe")
            ffprobe_orig = ffmpeg_exe.replace("ffmpeg", "ffprobe")
            if not os.path.exists(ffprobe_alias) and os.path.exists(ffprobe_orig):
                shutil.copy2(ffprobe_orig, ffprobe_alias)

            os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
        except Exception:
            pass
