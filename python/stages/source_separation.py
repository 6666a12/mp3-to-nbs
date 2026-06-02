"""
Source separation stage: Demucs 4-stem + MDX-Net vocal enhancement.

Pipeline (v3):
  1. Demucs htdemucs_ft on the full mix → 4 stems
     (drums, bass, other, vocals).
  2. MDX-Net ONNX vocal extraction → replace Demucs vocals.
  3. Align stem lengths.
  4. Wiener mask: reduce cross-stem bleed in vocals and other.
  5. Light compression on other / bass (reduces crest factor).
  6. LUFS loudness normalization (ITU-R BS.1770-4).
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np
import librosa


class CascadedSourceSeparator:
    """4-stem source separation with MDX-Net vocal enhancement.

    Pipeline: Demucs → MDX-Net vocals → Wiener masks (cross-stem bleed
    reduction on all 4 stems) → light compression (bass, other) → LUFS
    loudness normalisation.
    """

    # Path to the demucs wrapper script (patches torchaudio.save → scipy)
    _DEMUCS_WRAPPER: Path = (
        Path(__file__).resolve().parent.parent / "run_demucs.py"
    )

    COARSE_MODEL = "htdemucs_ft"
    TARGET_SR = 44100

    # ------------------------------------------------------------------
    def __init__(
        self,
        temp_dir: str | Path,
        use_gpu: bool = False,
        use_advanced_vocals: bool = True,
    ) -> None:
        self.temp_dir = Path(temp_dir)
        self.use_gpu = use_gpu
        self.use_advanced_vocals = use_advanced_vocals
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def separate(self, audio_path: str | Path) -> Dict[str, np.ndarray]:
        """Run the full separation pipeline, return {name: mono_audio}.

        This is the primary entry point used by the converter.
        """
        return await self._pipeline(Path(audio_path))

    async def cascade_separate(
        self, audio_path: str | Path,
    ) -> Dict[str, np.ndarray]:
        """Run the full separation pipeline (same as ``separate``).

        Always uses MDX-Net vocal enhancement (when ``use_advanced_vocals``
        is True) — there is no longer a quality tier system.
        """
        return await self._pipeline(Path(audio_path))

    # ------------------------------------------------------------------
    # Internal pipeline
    # ------------------------------------------------------------------

    async def _pipeline(
        self, audio_path: Path,
    ) -> Dict[str, np.ndarray]:
        """Run the 6-step pipeline and return stems."""
        original_mix, _ = librosa.load(
            str(audio_path), sr=self.TARGET_SR, mono=True,
        )

        # ── Step 1: Demucs 4-stem on full mix ───────────────────────
        self._log(0.12, "Demucs 4-stem separation on full mix...")
        stems = await self._coarse_separation(audio_path)
        self._log(0.20, f"Demucs produced {len(stems)} stems")

        # ── Step 2: MDX-Net vocal replacement ───────────────────────
        if self.use_advanced_vocals:
            mdx_vocals = await self._extract_mdx_vocals(audio_path)
            if mdx_vocals is not None and "vocals" in stems:
                min_len = min(mdx_vocals.shape[0], stems["vocals"].shape[0])
                stems["vocals"] = mdx_vocals[:min_len]
                self._log(0.22, "MDX-Net vocals replaced Demucs vocals")
            elif "vocals" in stems:
                self._log(0.22, "MDX-Net failed, keeping Demucs vocals")
        else:
            self._log(0.22, "Vocal enhancement skipped (disabled)")

        # ── Step 3: Align lengths ──────────────────────────────────
        min_len = min(*(a.shape[0] for a in stems.values()),
                       original_mix.shape[0])
        for name in stems:
            stems[name] = stems[name][:min_len]
        original_mix = original_mix[:min_len]

        # ── Step 4: Wiener mask — reduce cross-stem bleed ─────────
        if "vocals" in stems and all(
            s in stems for s in ("drums", "bass", "other")
        ):
            # Pass 4a: remove all instrument bleed (bass weighted slightly)
            self._log(0.24, "Wiener mask: cleaning vocal bleed (all refs)...")
            stems["vocals"] = self._wiener_clean_stem(
                stems["vocals"],
                {"drums": stems["drums"], "bass": stems["bass"], "other": stems["other"]},
                floor_db=-20.0,
                weights={"bass": 1.5},
            )
            # Pass 4b: aggressive "other" bleed removal (β=8.0 on other)
            # Piano / synth share the vocal range, so equal-weight Wiener
            # only attenuates them ~6 dB.  β=8.0 pushes that to ~19 dB
            # while vocal-dominant bins stay within 0.7 dB of unity.
            self._log(0.245, "Wiener mask: targeting other bleed in vocals (β=8)...")
            stems["vocals"] = self._wiener_clean_stem(
                stems["vocals"],
                {"other": stems["other"]},
                floor_db=-30.0,
                weights={"other": 8.0},
            )

        if "other" in stems and "bass" in stems:
            self._log(0.25, "Wiener mask: cleaning bass bleed from other...")
            stems["other"] = self._wiener_clean_stem(
                stems["other"],
                {"bass": stems["bass"]},
                floor_db=-14.0,  # gentler: legitimate harmonic overlap exists
            )

        if "drums" in stems and any(
            s in stems for s in ("bass", "other")
        ):
            # Bass weight kept low: kick drum & bass share sub-100 Hz,
            # so aggressive bass removal would kill legitimate kick content.
            self._log(0.255, "Wiener mask: cleaning bleed from drums...")
            stems["drums"] = self._wiener_clean_stem(
                stems["drums"],
                {"bass": stems["bass"], "other": stems["other"]},
                floor_db=-14.0,
                weights={"bass": 0.4},
            )

        if "bass" in stems and any(
            s in stems for s in ("drums", "other")
        ):
            self._log(0.26, "Wiener mask: cleaning bleed from bass...")
            stems["bass"] = self._wiener_clean_stem(
                stems["bass"],
                {"drums": stems["drums"], "other": stems["other"]},
                floor_db=-18.0,  # slightly gentler: kick drum has natural bass overlap
                weights={"other": 1.5},
            )

        # ── Step 5: Compress high-dynamic-range stems ──────────────
        if "other" in stems:
            self._log(0.27, "Compressing other stem...")
            stems["other"] = self._compress_stem(stems["other"], sr=self.TARGET_SR)

        if "bass" in stems:
            self._log(0.275, "Compressing bass stem...")
            stems["bass"] = self._compress_stem(stems["bass"], sr=self.TARGET_SR)

        # ── Step 6: Loudness normalize ─────────────────────────────
        for name in list(stems.keys()):
            audio = stems[name]
            if audio.size == 0 or float(np.abs(audio).max()) < 1e-10:
                continue
            stems[name] = self._normalize_loudness(audio, sr=self.TARGET_SR)

        self._log(0.30, f"Pipeline complete: {', '.join(sorted(stems.keys()))}")
        return stems

    # ------------------------------------------------------------------
    # Step 1: Demucs 4-stem separation
    # ------------------------------------------------------------------

    async def _coarse_separation(self, audio_path: Path) -> Dict[str, np.ndarray]:
        """Run htdemucs_ft on the full mix and load 4 stems."""
        output_dir = self.temp_dir / "coarse"
        output_dir.mkdir(parents=True, exist_ok=True)

        cmd: List[str] = [
            sys.executable, str(self._DEMUCS_WRAPPER),
            "-n", self.COARSE_MODEL,
            "--shifts", "1",
            "-o", str(output_dir),
            str(audio_path),
        ]

        await self._run_demucs(cmd, "coarse separation")

        base_name = audio_path.stem
        stem_dir = output_dir / self.COARSE_MODEL / base_name

        stems: Dict[str, np.ndarray] = {}
        for stem_name in ("vocals", "drums", "bass", "other"):
            stem_path = stem_dir / f"{stem_name}.wav"
            if stem_path.exists():
                audio, _ = librosa.load(
                    str(stem_path), sr=self.TARGET_SR, mono=True,
                )
                stems[stem_name] = audio.astype(np.float32)
            else:
                stems[stem_name] = np.zeros(1, dtype=np.float32)

        return stems

    # ------------------------------------------------------------------
    # Step 2: MDX-Net vocal extraction
    # ------------------------------------------------------------------

    async def _extract_mdx_vocals(
        self, audio_path: Path,
    ) -> np.ndarray | None:
        """Run MDX-Net ONNX vocal extraction, return vocal array or None."""
        try:
            from stages.roformer_vocal import RoformerVocalExtractor

            extractor = RoformerVocalExtractor(
                model_cache_dir=None,
                use_gpu=self.use_gpu,
            )
            self._log(0.14, "MDX-Net vocal extraction...")
            result = extractor.extract(audio_path)
            if result is not None:
                vocals, _ = result
                return vocals.astype(np.float32)
            return None
        except Exception as e:
            self._log(0.18, f"MDX-Net error: {e}, keeping Demucs vocals")
            return None

    # ------------------------------------------------------------------
    # Step 4: Wiener mask — cross-stem bleed reduction
    # ------------------------------------------------------------------

    @staticmethod
    def _wiener_clean_stem(
        target: np.ndarray,
        references: Dict[str, np.ndarray],
        floor_db: float = -20.0,
        weights: Dict[str, float] | None = None,
    ) -> np.ndarray:
        """Reduce bleed from *references* in *target* via soft Wiener mask.

        At each time-frequency bin:
            mask = |target|² / (|target|² + Σ(w_i · |ref_i|²))

        *weights* magnifies specific references (β > 1) to be more
        aggressive against bleed from spectrally-overlapping stems
        (e.g. piano bleeding into vocals).  Default 1.0 (no bias).

        All stems are RMS-normalised first to undo Demucs' per-stem peak
        normalisation, which would otherwise distort inter-stem energy
        ratios.
        """
        import librosa

        def _rms_norm(x: np.ndarray) -> np.ndarray:
            rms = float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))
            if rms < 1e-10:
                return x
            return x / rms

        n_fft, hop = 2048, 512

        t_norm = _rms_norm(target)
        T_mag = np.abs(librosa.stft(t_norm, n_fft=n_fft, hop_length=hop))

        # Sum of weighted squared magnitudes from all reference stems
        ref_power = np.zeros_like(T_mag)
        for ref_name, ref_audio in references.items():
            w = (weights or {}).get(ref_name, 1.0)
            r_norm = _rms_norm(ref_audio)
            R_mag = np.abs(librosa.stft(r_norm, n_fft=n_fft, hop_length=hop))
            ref_power += w * (R_mag ** 2)

        eps = 1e-8
        mask = T_mag ** 2 / (T_mag ** 2 + ref_power + eps)

        # Soft floor
        floor_linear = 10.0 ** (floor_db / 20.0)
        mask = np.maximum(mask, floor_linear)

        # Apply mask to ORIGINAL target STFT (preserves phase)
        D_target = librosa.stft(target, n_fft=n_fft, hop_length=hop)
        D_clean = D_target * mask.astype(np.complex64)

        clean = librosa.istft(D_clean, hop_length=hop, length=target.shape[0])
        return clean.astype(np.float32)

    # ------------------------------------------------------------------
    # Step 5: Light compression — reduce crest factor
    # ------------------------------------------------------------------

    @staticmethod
    def _compress_stem(
        audio: np.ndarray,
        sr: int = 44100,
        threshold_db: float = -18.0,
        ratio: float = 2.5,
        attack_ms: float = 5.0,
        release_ms: float = 80.0,
        makeup_db: float = 6.0,
    ) -> np.ndarray:
        """Feed-forward RMS compressor to reduce dynamic range.

        Reduces the crest factor so subsequent LUFS normalisation can
        apply more gain without clipping.  This brings up quiet sections
        while preventing peaks from saturating.

        Uses a Wiener-style soft-knee curve: gain smoothly approaches
        the compression ratio above threshold, avoiding hard-knee
        distortion.
        """
        threshold_linear = 10.0 ** (threshold_db / 20.0)

        # Per-sample attack/release smoothing coefficients
        atk = np.exp(-1.0 / (attack_ms / 1000.0 * sr))
        rel = np.exp(-1.0 / (release_ms / 1000.0 * sr))

        # Envelope: running RMS with 5 ms window
        win = int(sr * 0.005) | 1
        audio_sq = audio.astype(np.float64) ** 2
        envelope = np.sqrt(
            np.convolve(audio_sq, np.ones(win) / win, mode="same")
        )
        envelope = np.maximum(envelope, 1e-12)

        # Target gain: 1.0 below threshold, (thr/env)^(1-1/ratio) above
        target_gain = np.ones_like(envelope, dtype=np.float64)
        above = envelope > threshold_linear
        target_gain[above] = (threshold_linear / envelope[above]) ** (1.0 - 1.0 / ratio)

        # Attack / release envelope following (one-pass loop)
        smoothed = np.ones_like(target_gain, dtype=np.float64)
        state = 1.0
        for i in range(len(target_gain)):
            if target_gain[i] < state:
                state = state * atk + target_gain[i] * (1.0 - atk)
            else:
                state = state * rel + target_gain[i] * (1.0 - rel)
            smoothed[i] = state

        # Apply gain reduction + makeup gain
        makeup_linear = 10.0 ** (makeup_db / 20.0)
        out = audio.astype(np.float64) * smoothed * makeup_linear
        return out.astype(np.float32)

    # ------------------------------------------------------------------
    # Step 6: LUFS loudness normalization
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_loudness(
        audio: np.ndarray,
        sr: int = 44100,
        target_lufs: float = -12.0,
        ceiling_db: float = -0.5,
    ) -> np.ndarray:
        """LUFS-normalize audio via ITU-R BS.1770-4 integrated loudness.

        Unlike peak or RMS normalization, LUFS models human perceived
        loudness (K-weighting + channel summation + gating).  This
        correctly handles bass (low-frequency energy that RMS
        underestimates) and transient-rich material (drums).

        A peak ceiling prevents clipping on stems with high crest factor.
        """
        import pyloudnorm as pyln

        rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
        if rms < 1e-10:
            return audio

        # pyloudnorm requires float64
        meter = pyln.Meter(sr)
        loudness = meter.integrated_loudness(audio.astype(np.float64))

        # Normalize to target LUFS
        out = pyln.normalize.loudness(
            audio.astype(np.float64), loudness, target_lufs,
        )

        # Apply peak ceiling so transients don't clip
        ceiling = 10.0 ** (ceiling_db / 20.0)
        peak = float(np.abs(out).max())
        if peak > ceiling:
            out = out * (ceiling / peak)

        return out.astype(np.float32)

    # ------------------------------------------------------------------
    # WAV I/O
    # ------------------------------------------------------------------

    def _write_wav(self, path: Path, audio: np.ndarray, sr: int) -> None:
        """Write float32 audio to 16-bit WAV with peak normalization."""
        from scipy.io import wavfile

        max_val = float(np.iinfo(np.int16).max)
        peak = float(np.abs(audio).max())
        if peak > 0:
            scaled = (audio / peak) * 0.95 * max_val
        else:
            scaled = audio
        scaled = np.clip(scaled, -max_val, max_val - 1).astype(np.int16)
        if scaled.ndim == 1:
            wavfile.write(str(path), sr, scaled)
        else:
            wavfile.write(str(path), sr, scaled.T)

    @staticmethod
    def _cleanup_temp(path: Path) -> None:
        """Remove a temp file if it exists."""
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Demucs subprocess
    # ------------------------------------------------------------------

    async def _run_demucs(self, cmd: List[str], description: str) -> None:
        """Run Demucs via asyncio subprocess, with GPU→CPU auto-fallback."""
        kwargs: dict = {
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        device = "cuda" if self.use_gpu else "cpu"
        input_arg = cmd[-1]
        device_cmd = list(cmd[:-1]) + ["--device", device, input_arg]

        proc = await asyncio.create_subprocess_exec(*device_cmd, **kwargs)
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            err_text = stderr.decode("utf-8", errors="replace")

            if self.use_gpu:
                # GPU failed — retry with CPU
                self._log(0.5, (
                    f"GPU failed for {description}: {err_text[:200]}. "
                    f"Retrying with CPU..."
                ))
                cpu_cmd = list(cmd[:-1]) + ["--device", "cpu", input_arg]
                proc2 = await asyncio.create_subprocess_exec(*cpu_cmd, **kwargs)
                _stdout2, stderr2 = await proc2.communicate()

                if proc2.returncode != 0:
                    err2 = stderr2.decode("utf-8", errors="replace")
                    raise RuntimeError(
                        f"Demucs {description} failed on both GPU and CPU "
                        f"(GPU={proc.returncode}, CPU={proc2.returncode}): "
                        f"{err2[:500]}"
                    )

                self._log(0.5, (
                    f"CPU fallback succeeded for {description}. "
                    f"GPU disabled for remaining steps."
                ))
                self.use_gpu = False
                return

            raise RuntimeError(
                f"Demucs {description} failed (code {proc.returncode}): "
                f"{err_text[:500]}"
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _log(progress: float, message: str) -> None:
        """Emit a JSON progress line to stdout (compatible with converter)."""
        print(json.dumps({
            "step": "source_separation",
            "progress": progress,
            "message": message,
        }), flush=True)
