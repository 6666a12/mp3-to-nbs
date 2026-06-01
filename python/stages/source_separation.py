"""
Source separation stage using Demucs 6-stem + Residual Recursive Refinement.

Phase 1: 6-stem coarse separation via htdemucs_6s
         (drums, bass, piano, guitar, vocals, other).
Phase 2: Purity assessment via ideal-residual correlation:
         R = Mix ⊖ sum(other stems),  purity = corr(stem, R).
Phase 3: Residual recursive refinement:
         1. Detect low-correlation leakage regions in dirty stem vs ideal R.
         2. Build refinement input: leakage segment + slight R + noise.
         3. Run 2-stems Demucs on each segment.
         4. Classify piano component via harmonic richness / timbre consistency.
         5. Reclaim pure component, merge back to stem.
         6. Iterate until leakage energy converges.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import librosa
from scipy.io import wavfile

from models.task_result import StemQuality


class CascadedSourceSeparator:
    """6-stem Demucs + residual recursive refinement.

    Phase 1: htdemucs_6s → 6 coarse stems.
    Phase 2: ideal-residual correlation purity assessment.
    Phase 3: leakage-region detection + 2-stems re-separation + reclaim.
    """

    # Path to the demucs wrapper script (patches torchaudio.save → scipy)
    _DEMUCS_WRAPPER: Path = Path(__file__).resolve().parent.parent / "run_demucs.py"

    REFINEMENT_THRESHOLD = 0.60       # ideal-residual correlation minimum
    REFINEMENT_MODEL = "htdemucs_6s"  # 6-stem for 2-stems refinement of all stems
    COARSE_MODEL = "htdemucs_6s"      # 6-stem: drums, bass, piano, guitar, vocals, other
    TARGET_SR = 44100
    MAX_REFINEMENT_PASSES = 4         # recursive refinement cap
    SPECTRAL_SUBTRACT_ALPHA = 0.5     # soft-mask strength

    # Leakage detection
    LEAKAGE_CORR_THRESHOLD = 0.35     # envelope r < this → leakage region
    LEAKAGE_CONVERGENCE_RATIO = 0.05  # < 5% leakage energy → converged
    LEAKAGE_MIN_SEGMENT_S = 0.1       # minimum leakage segment length (seconds)
    REFINE_NOISE_SCALE = 0.003        # noise relative to segment std
    REFINE_RESIDUAL_MIX = 0.25        # how much ideal R to mix into refinement input

    # Stem order for refinement (cleanest → dirtiest processing).
    STEM_REFINE_ORDER = (
        "bass",      # lowest centroid, easiest to separate cleanly
        "drums",     # high kurtosis, distinct envelope
        "vocals",    # mid complexity
        "guitar",    # mid-high complexity
        "piano",     # wide frequency range, complex harmonics
        "other",     # catch-all, hardest to define ideal residual for
    )

    # Target frequency bands (Hz) for spectral concentration scoring.
    _TARGET_BANDS: Dict[str, Tuple[float, float]] = {
        "vocals": (200, 4000),
        "drums": (30, 6000),
        "bass": (40, 300),
        "piano": (80, 5000),
        "guitar": (80, 4000),
        "other": (200, 8000),
    }

    # Multi-band envelope correlation bands.
    _ENVELOPE_BANDS: Tuple[
        Tuple[str, float, float],
        Tuple[str, float, float],
        Tuple[str, float, float],
    ] = (
        ("low",    30,   250),
        ("mid",   250,  2000),
        ("high", 2000,  8000),
    )

    def __init__(
        self,
        temp_dir: str | Path,
        refinement_threshold: float = 0.82,
        use_gpu: bool = False,
    ) -> None:
        self.temp_dir = Path(temp_dir)
        self.refinement_threshold = refinement_threshold
        self.use_gpu = use_gpu
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def separate(self, audio_path: str | Path) -> Dict[str, np.ndarray]:
        """Full cascaded separation pipeline.

        Returns a dict mapping stem name to mono audio array at 44100 Hz.
        """
        audio_path = Path(audio_path)

        # Load original mix for ideal-residual computation
        original_mix, _ = librosa.load(str(audio_path), sr=self.TARGET_SR, mono=True)

        # Phase 1: 6-stem coarse separation
        coarse_stems = await self._coarse_separation(audio_path)

        # Phase 2: purity assessment via ideal-residual correlation
        qualities: Dict[str, StemQuality] = {}
        for name, audio in coarse_stems.items():
            qualities[name] = self._assess_stem_purity(
                audio, name, coarse_stems, mix_audio=original_mix,
            )

        for name, q in qualities.items():
            flag = "OK" if not q.needs_refinement else "needs refinement"
            print(
                json.dumps({
                    "step": "source_separation",
                    "progress": 0.5,
                    "message": f"[{name}] purity={q.purity_score:.3f} {flag}",
                }),
                flush=True,
            )

        # Phase 3: refine low-quality stems
        refined = await self._refine_stems(audio_path, coarse_stems, qualities)
        return refined

    # ------------------------------------------------------------------
    # Phase 1: coarse separation
    # ------------------------------------------------------------------

    async def _coarse_separation(self, audio_path: Path) -> Dict[str, np.ndarray]:
        """Run 6-stem htdemucs_6s separation and load results."""
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
        for stem_name in ("vocals", "drums", "bass", "piano", "guitar", "other"):
            stem_path = stem_dir / f"{stem_name}.wav"
            if stem_path.exists():
                audio, _ = librosa.load(str(stem_path), sr=self.TARGET_SR, mono=True)
                stems[stem_name] = audio
            else:
                # If demucs didn't produce this stem, fill with silence
                stems[stem_name] = np.zeros(1, dtype=np.float32)

        return stems

    # ------------------------------------------------------------------
    # Helpers: signal analysis
    # ------------------------------------------------------------------

    @staticmethod
    def _bandpass_envelope(
        audio: np.ndarray, low: float, high: float, sr: int = 44100,
    ) -> np.ndarray:
        """Bandpass filter *audio* and return the Hilbert envelope."""
        from scipy.signal import butter, sosfilt
        from scipy.signal import hilbert as hilbert_fn

        nyq = sr / 2
        lo_norm = max(low / nyq, 0.01)
        hi_norm = min(high / nyq, 0.99)
        if hi_norm <= lo_norm:
            return np.abs(audio)  # fallback — rectified signal
        sos = butter(4, [lo_norm, hi_norm], btype="band", output="sos")
        band = sosfilt(sos, audio)
        return np.abs(hilbert_fn(band))

    def _ideal_residual_correlation(
        self,
        stem: np.ndarray,
        ideal_r: np.ndarray,
    ) -> float:
        """Multi-band average envelope correlation between stem and ideal R.

        High correlation (close to 1.0) → stem is clean.
        Low correlation → stem contains leakage from other instruments.
        """
        corrs: List[float] = []
        for _label, low, high in self._ENVELOPE_BANDS:
            try:
                env_stem = self._bandpass_envelope(stem, low, high)
                env_r = self._bandpass_envelope(ideal_r, low, high)
            except Exception:
                continue

            # Downsample to ~50 Hz
            ds = max(1, self.TARGET_SR // 50)
            env_s = env_stem[::ds]
            env_r = env_r[::ds]
            dlen = min(env_s.shape[0], env_r.shape[0])
            env_s = env_s[:dlen]
            env_r = env_r[:dlen]
            if dlen < 20:
                continue

            s_mean = float(np.mean(env_s))
            r_mean = float(np.mean(env_r))
            s_std = float(np.std(env_s))
            r_std = float(np.std(env_r))
            if s_std < 1e-10 or r_std < 1e-10:
                continue

            c = float(
                np.mean((env_s - s_mean) * (env_r - r_mean)) / (s_std * r_std)
            )
            corrs.append(max(0.0, c))  # clip negative → 0

        if not corrs:
            return 0.30
        return float(np.mean(corrs))

    def _detect_leakage_regions(
        self,
        stem: np.ndarray,
        ideal_r: np.ndarray,
    ) -> np.ndarray:
        """Return a boolean mask of leakage regions in *stem*.

        Uses sliding-window envelope correlation.  Regions where the local
        correlation drops below ``LEAKAGE_CORR_THRESHOLD`` are marked as
        leakage (True = leaky, False = clean).
        """
        min_len = min(stem.shape[0], ideal_r.shape[0])
        stem = stem[:min_len]
        ideal_r = ideal_r[:min_len]

        # Broad-band envelope (full spectrum)
        from scipy.signal import hilbert as hilbert_fn
        env_s = np.abs(hilbert_fn(stem))
        env_r = np.abs(hilbert_fn(ideal_r))

        # Downsample to ~50 Hz for faster sliding window
        ds = max(1, self.TARGET_SR // 50)
        env_s = env_s[::ds]
        env_r = env_r[::ds]
        dlen = min(env_s.shape[0], env_r.shape[0])
        env_s = env_s[:dlen]
        env_r = env_r[:dlen]

        window = 50  # ~1 second at 50 Hz
        if dlen < window:
            return np.zeros(min_len, dtype=bool)

        # Sliding window Pearson r
        corr = np.zeros(dlen, dtype=np.float64)
        for i in range(window, dlen):
            ws = env_s[i - window:i]
            wr = env_r[i - window:i]
            sm = np.mean(ws)
            rm = np.mean(wr)
            ss = np.std(ws)
            rs = np.std(wr)
            if ss < 1e-10 or rs < 1e-10:
                corr[i] = 0.0
            else:
                corr[i] = np.mean((ws - sm) * (wr - rm)) / (ss * rs)

        # Smooth the correlation curve
        from scipy.ndimage import uniform_filter1d
        corr = uniform_filter1d(corr, size=10)

        # Mark low-correlation regions as leakage
        leaky = corr < self.LEAKAGE_CORR_THRESHOLD

        # Remove too-short segments
        min_seg_samples = int(self.LEAKAGE_MIN_SEGMENT_S * 50)  # at 50 Hz
        if min_seg_samples > 1:
            from scipy.ndimage import binary_closing
            leaky = binary_closing(leaky, structure=np.ones(min_seg_samples))

        # Upsample back to full sample rate
        full_mask = np.repeat(leaky, ds)[:min_len]
        return full_mask

    def _harmonic_richness(
        self, audio: np.ndarray, sr: int = 44100,
    ) -> float:
        """Measure harmonic richness: how many harmonic peaks exist.

        Piano has rich harmonics (many peaks at f, 2f, 3f, …).
        Returns a score in [0, 1] where higher = more harmonic peaks.
        """
        if audio.size < 512:
            return 0.0
        D = np.abs(librosa.stft(audio, n_fft=2048, hop_length=512))
        mag = np.mean(D, axis=1)
        # Find peaks
        from scipy.signal import find_peaks
        peaks, props = find_peaks(mag, height=np.max(mag) * 0.05, distance=3)
        if len(peaks) < 2:
            return 0.0

        # Check how many peaks form a harmonic series (within tolerance)
        fundamental = peaks[0]
        if fundamental < 1:
            fundamental = peaks[1] if len(peaks) > 1 else 4
        harmonic_count = 0
        for p in peaks:
            ratio = p / max(fundamental, 1)
            # Check if ratio is close to an integer
            nearest_int = round(ratio)
            if nearest_int >= 1 and abs(ratio - nearest_int) < 0.12:
                harmonic_count += 1

        # Score: harmonic_count / log(total_peaks+1) normalized
        score = min(1.0, harmonic_count / max(1, np.log2(len(peaks) + 1)) / 4)
        return score

    def _timbre_consistency(
        self, candidate: np.ndarray, reference: np.ndarray, sr: int = 44100,
    ) -> float:
        """MFCC-based timbre similarity between candidate and reference.

        Returns a score in [0, 1] where higher = more similar timbre.
        """
        if candidate.size < 1024 or reference.size < 1024:
            return 0.5

        try:
            mfcc_c = librosa.feature.mfcc(y=candidate, sr=sr, n_mfcc=13).T
            mfcc_r = librosa.feature.mfcc(y=reference, sr=sr, n_mfcc=13).T
        except Exception:
            return 0.5

        # Mean MFCC vectors
        c_mean = np.mean(mfcc_c, axis=0)
        r_mean = np.mean(mfcc_r, axis=0)

        # Cosine similarity
        dot = np.dot(c_mean, r_mean)
        norm = np.linalg.norm(c_mean) * np.linalg.norm(r_mean)
        if norm < 1e-10:
            return 0.5
        sim = (dot / norm + 1.0) / 2.0  # scale [-1,1] → [0,1]
        return float(sim)

    def _classify_piano_component(
        self,
        target_stem: np.ndarray,
        no_target_stem: np.ndarray,
        clean_reference: np.ndarray,
        stem_name: str,
    ) -> np.ndarray:
        """Choose which of two sub-stems is the *stem_name* component.

        Uses harmonic richness, spectral centroid, and timbre consistency
        to decide.  Returns the audio array that best matches the stem
        characteristics.
        """
        if clean_reference.size < 1024:
            # No clean reference — trust Demucs: target_stem is the named stem
            return target_stem

        # Compute scores for each candidate
        def score(candidate: np.ndarray, ref: np.ndarray) -> float:
            h = self._harmonic_richness(candidate)
            t = self._timbre_consistency(candidate, ref)
            # Spectral centroid closeness to reference
            try:
                cent_c = librosa.feature.spectral_centroid(y=candidate, sr=self.TARGET_SR)
                cent_r = librosa.feature.spectral_centroid(y=ref, sr=self.TARGET_SR)
                c_mean, r_mean = float(np.mean(cent_c)), float(np.mean(cent_r))
                cent_sim = 1.0 - min(1.0, abs(c_mean - r_mean) / max(r_mean, 50.0))
            except Exception:
                cent_sim = 0.5
            return h * 0.35 + t * 0.40 + cent_sim * 0.25

        score_target = score(target_stem, clean_reference)
        score_no_target = score(no_target_stem, clean_reference)

        return target_stem if score_target >= score_no_target else no_target_stem

    # ------------------------------------------------------------------
    # Phase 2: purity assessment  (v3 — ideal residual correlation)
    # ------------------------------------------------------------------

    def _assess_stem_purity(
        self,
        stem_audio: np.ndarray,
        stem_name: str,
        all_stems: Dict[str, np.ndarray],
        mix_audio: Optional[np.ndarray] = None,
    ) -> StemQuality:
        """Evaluate stem purity using ideal-residual correlation (v3).

        R = Mix ⊖ sum(all other stems)

        purity = corr(stem, R) × 0.60 + spectral × 0.25 + temporal × 0.15

        When *mix_audio* is None, falls back to internal metrics only.
        """
        if stem_audio.ndim > 1:
            audio_mono = librosa.to_mono(stem_audio)
        else:
            audio_mono = stem_audio

        if audio_mono.size == 0 or np.max(np.abs(audio_mono)) < 1e-10:
            return StemQuality(
                name=stem_name,
                purity_score=0.0,
                spectral_leakage=1.0,
                temporal_bleed=1.0,
                needs_refinement=True,
            )

        spectral_score = self._spectral_concentration_score(audio_mono, stem_name)

        # Simplified temporal bleed (envelope kurtosis — standalone)
        from scipy.signal import hilbert
        env = np.abs(hilbert(audio_mono[: min(audio_mono.size, self.TARGET_SR * 30)]))
        env_std = float(np.std(env))
        temporal_bleed = float(
            np.mean((env - np.mean(env)) ** 4) / (max(env_std, 1e-10) ** 4)
        )
        # Normalize: 3 (Gaussian) → 0 | >12 (very spiky) → 1
        temporal_norm = max(0.0, min(1.0, (temporal_bleed - 3.0) / 9.0))

        if mix_audio is not None:
            # Build ideal residual R = mix ⊖ sum(other stems)
            others_parts: List[np.ndarray] = []
            for name, a in all_stems.items():
                if name != stem_name and a.size > 0:
                    others_parts.append(a)

            if others_parts:
                min_len = min(mix_audio.shape[0], audio_mono.shape[0],
                              *(a.shape[0] for a in others_parts))
                complement = np.zeros(min_len, dtype=np.float32)
                for a in others_parts:
                    complement += a[:min_len]

                ideal_r = self._spectral_subtract(
                    mix_audio[:min_len], complement, alpha=self.SPECTRAL_SUBTRACT_ALPHA,
                )
                ideal_corr = self._ideal_residual_correlation(
                    audio_mono[:min_len], ideal_r,
                )
            else:
                ideal_corr = 0.40
        else:
            ideal_corr = 0.40  # No mix reference — neutral

        purity = (
            ideal_corr * 0.60
            + spectral_score * 0.25
            + (1.0 - temporal_norm) * 0.15
        )
        purity = max(0.0, min(1.0, purity))

        return StemQuality(
            name=stem_name,
            purity_score=purity,
            spectral_leakage=1.0 - spectral_score,
            temporal_bleed=temporal_norm,
            needs_refinement=purity < self.refinement_threshold,
        )

    def _spectral_concentration_score(
        self, audio: np.ndarray, stem_name: str
    ) -> float:
        """Fraction of total energy within the target frequency band."""
        band = self._TARGET_BANDS.get(stem_name)
        if band is None:
            return 0.5

        D = np.abs(librosa.stft(audio, n_fft=2048, hop_length=512))
        freqs = librosa.fft_frequencies(sr=self.TARGET_SR, n_fft=2048)
        low, high = band
        total_energy = np.sum(D ** 2)
        if total_energy < 1e-10:
            return 0.0
        mask = (freqs >= low) & (freqs <= high)
        target_energy = np.sum(D[mask, :] ** 2)
        return float(target_energy / total_energy)

    # ------------------------------------------------------------------
    # Phase 3: recursive two-stems refinement
    # ------------------------------------------------------------------

    async def _refine_stems(
        self,
        audio_path: Path,
        coarse_stems: Dict[str, np.ndarray],
        qualities: Dict[str, StemQuality],
    ) -> Dict[str, np.ndarray]:
        """Residual recursive refinement (v3).

        For each dirty stem:
        1. Compute ideal R = Mix ⊖ sum(all other stems).
        2. Detect leakage regions: sliding-window correlation stem vs R → mask.
        3. Extract contiguous leakage segments.
        4. Build refinement input: segment + slight R + noise.
        5. Run 2-stems Demucs on each segment.
        6. Classify piano/stem component via harmonic richness + timbre consistency.
        7. Reclaim clean component, merge back into stem.
        8. Re-assess purity; iterate if improved and leakage not converged.
        """
        refined: Dict[str, np.ndarray] = {}
        original, _ = librosa.load(str(audio_path), sr=self.TARGET_SR, mono=True)

        # Phase A: Identify clean-enough stems (these form the complement)
        dirty_list: List[Tuple[str, float, np.ndarray]] = []
        clean_set: Dict[str, np.ndarray] = {}

        for stem_name, quality in qualities.items():
            if quality.needs_refinement:
                dirty_list.append((stem_name, quality.purity_score, coarse_stems[stem_name]))
            else:
                refined[stem_name] = coarse_stems[stem_name]
                clean_set[stem_name] = coarse_stems[stem_name]

        # Sort dirty stems: cleanest → dirtiest
        dirty_list.sort(key=lambda x: x[1], reverse=True)

        for stem_name, init_purity, stem_audio in dirty_list:
            best_stem = stem_audio
            best_purity = init_purity
            prev_leakage_ratio = 1.0

            for iteration in range(self.MAX_REFINEMENT_PASSES):
                # ── Build complement from all OTHER stems ──────────────
                others: List[np.ndarray] = []
                for name in coarse_stems:
                    if name == stem_name:
                        continue
                    if name in refined:
                        others.append(refined[name])
                    elif name in clean_set:
                        others.append(clean_set[name])
                    else:
                        others.append(coarse_stems[name])

                if not others:
                    refined[stem_name] = best_stem
                    break

                min_len = min(original.shape[0], best_stem.shape[0],
                              *(a.shape[0] for a in others))
                complement = np.zeros(min_len, dtype=np.float32)
                for a in others:
                    complement += a[:min_len]

                # ── Compute ideal residual R ──────────────────────────
                ideal_r = self._spectral_subtract(
                    original[:min_len], complement,
                    alpha=self.SPECTRAL_SUBTRACT_ALPHA,
                )

                # ── Detect leakage regions ────────────────────────────
                leakage_mask = self._detect_leakage_regions(
                    best_stem[:min_len], ideal_r,
                )
                leakage_ratio = (
                    float(np.sum(best_stem[:min_len][leakage_mask] ** 2))
                    / max(1e-10, float(np.sum(best_stem[:min_len] ** 2)))
                )

                # Convergence check
                if leakage_ratio < self.LEAKAGE_CONVERGENCE_RATIO:
                    print(json.dumps({
                        "step": "source_separation", "progress": 0.5,
                        "message": f"[{stem_name}] leakage converged ({leakage_ratio:.4f})",
                    }), flush=True)
                    break
                if leakage_ratio >= prev_leakage_ratio * 0.95:
                    # Not improving significantly
                    if iteration > 0:
                        print(json.dumps({
                            "step": "source_separation", "progress": 0.5,
                            "message": f"[{stem_name}] leakage stalled ({leakage_ratio:.4f})",
                        }), flush=True)
                        break
                prev_leakage_ratio = leakage_ratio

                # ── Extract contiguous leakage segments ───────────────
                segments = self._extract_segments(
                    leakage_mask, best_stem, min_len,
                    min_duration_s=self.LEAKAGE_MIN_SEGMENT_S,
                )

                if not segments:
                    break

                # ── Clean reference for classifier ────────────────────
                clean_mask = ~leakage_mask
                clean_ref = best_stem[:min_len][clean_mask] if clean_mask.any() else best_stem[:min_len]

                # ── Process each leakage segment ──────────────────────
                reclaimed = np.zeros(min_len, dtype=np.float32)
                for seg_start, seg_end in segments:
                    seg_len = seg_end - seg_start
                    seg_audio = best_stem[seg_start:seg_end].copy()

                    # Build refinement input: segment + slight R + noise
                    r_seg = ideal_r[seg_start:seg_end]
                    noise = (
                        np.random.randn(seg_len).astype(np.float32)
                        * self.REFINE_NOISE_SCALE * float(np.std(seg_audio) + 1e-10)
                    )
                    refine_input = (
                        seg_audio
                        + self.REFINE_RESIDUAL_MIX * r_seg
                        + noise
                    )

                    # Write temp file and run 2-stems Demucs
                    ref_path = self.temp_dir / f"leak_{stem_name}_i{iteration}_{seg_start}.wav"
                    self._write_wav(ref_path, refine_input.astype(np.float32), self.TARGET_SR)

                    try:
                        target_audio, no_target_audio = await self._two_stems_separate(
                            ref_path, stem_name, shifts=1,
                        )

                        # Classify which output is the true stem component
                        piano_like = self._classify_piano_component(
                            target_audio, no_target_audio, clean_ref, stem_name,
                        )
                        # Align length
                        reclaimed[seg_start:seg_start + len(piano_like)] = piano_like[:seg_len]
                    except Exception:
                        # Refinement failed for this segment — keep original
                        reclaimed[seg_start:seg_end] = seg_audio

                # ── Merge: keep clean regions, replace leaky with reclaimed ──
                merged = best_stem[:min_len].copy()
                merged[leakage_mask] = reclaimed[leakage_mask]

                # Validate: assess purity of merged result
                # Use best-available stems (refined + clean) for complement
                best_available = dict(coarse_stems)
                best_available.update(clean_set)
                best_available.update(refined)
                merged_quality = self._assess_stem_purity(
                    merged, stem_name, best_available, mix_audio=original,
                )
                merged_purity = merged_quality.purity_score

                if merged_purity > best_purity:
                    best_stem = merged
                    best_purity = merged_purity
                    print(json.dumps({
                        "step": "source_separation", "progress": 0.5,
                        "message": (
                            f"[{stem_name}] refine pass {iteration + 1}: "
                            f"{init_purity:.3f} → {best_purity:.3f} "
                            f"(leakage {leakage_ratio:.4f})"
                            f"{' ✓' if best_purity >= self.refinement_threshold else ''}"
                        ),
                    }), flush=True)

                    if best_purity >= self.refinement_threshold:
                        break
                else:
                    if iteration == 0:
                        print(json.dumps({
                            "step": "source_separation", "progress": 0.5,
                            "message": (
                                f"[{stem_name}] refine regressed "
                                f"({init_purity:.3f} → {merged_purity:.3f}), "
                                f"keeping coarse"
                            ),
                        }), flush=True)
                    break

            refined[stem_name] = best_stem

        # Ensure all 6 stems exist
        for stem_name in ("vocals", "drums", "bass", "piano", "guitar", "other"):
            if stem_name not in refined:
                refined[stem_name] = coarse_stems.get(
                    stem_name, np.zeros(original.shape[0], dtype=np.float32)
                )

        return refined

    def _extract_segments(
        self,
        mask: np.ndarray,
        audio: np.ndarray,
        min_len: int,
        min_duration_s: float = 0.1,
    ) -> List[Tuple[int, int]]:
        """Extract contiguous True regions from a boolean mask.

        Returns list of (start_sample, end_sample) tuples.
        Segments shorter than *min_duration_s* are skipped.
        """
        min_samples = int(min_duration_s * self.TARGET_SR)
        segments: List[Tuple[int, int]] = []
        in_seg = False
        seg_start = 0

        for i in range(min_len):
            if mask[i] and not in_seg:
                in_seg = True
                seg_start = i
            elif not mask[i] and in_seg:
                in_seg = False
                if i - seg_start >= min_samples:
                    segments.append((seg_start, i))

        if in_seg and (min_len - seg_start) >= min_samples:
            segments.append((seg_start, min_len))

        return segments

    # ── spectral-domain subtraction ──────────────────────────────────

    def _spectral_subtract(
        self, mix: np.ndarray, stem: np.ndarray, alpha: float = 0.8
    ) -> np.ndarray:
        """Subtract *stem* from *mix* in the STFT domain using a soft mask.

        Avoids the phase-cancellation errors of time-domain subtraction.
        """
        eps = 1e-8
        n_fft = 2048
        hop = 512

        D_mix = librosa.stft(mix, n_fft=n_fft, hop_length=hop)
        D_stem = librosa.stft(stem, n_fft=n_fft, hop_length=hop)

        mix_mag = np.abs(D_mix)
        stem_mag = np.abs(D_stem)

        # Soft gain: g = max(ε, 1 − α·|stem|/(|mix| + ε))
        gain = np.maximum(0.01, 1.0 - alpha * stem_mag / (mix_mag + eps))
        D_residual = D_mix * gain

        residual = librosa.istft(D_residual, hop_length=hop, length=mix.shape[0])
        return residual.astype(np.float32)

    # ── two-stems demucs worker ──────────────────────────────────────

    async def _two_stems_separate(
        self, audio_path: Path, target: str, shifts: int = 2
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Run two-stems demucs to extract one target stem from the audio.

        Returns (target_audio, residual_audio).
        """
        output_dir = self.temp_dir / f"refine_{target}"
        output_dir.mkdir(parents=True, exist_ok=True)

        cmd: List[str] = [
            sys.executable, str(self._DEMUCS_WRAPPER),
            "-n", self.REFINEMENT_MODEL,
            "--two-stems", target,
            "--shifts", str(shifts),
            "-o", str(output_dir),
            str(audio_path),
        ]

        await self._run_demucs(cmd, f"refine {target}")

        base_name = audio_path.stem
        stem_dir = output_dir / self.REFINEMENT_MODEL / base_name

        target_path = stem_dir / f"{target}.wav"
        no_target_path = stem_dir / f"no_{target}.wav"

        if target_path.exists():
            target_audio, _ = librosa.load(
                str(target_path), sr=self.TARGET_SR, mono=True
            )
        else:
            target_audio, _ = librosa.load(
                str(audio_path), sr=self.TARGET_SR, mono=True
            )

        if no_target_path.exists():
            residual_audio, _ = librosa.load(
                str(no_target_path), sr=self.TARGET_SR, mono=True
            )
        else:
            residual_audio = np.zeros_like(target_audio)

        return target_audio, residual_audio

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _run_demucs(self, cmd: List[str], description: str) -> None:
        """Run a demucs command via asyncio subprocess, with GPU fallback.

        When ``use_gpu`` is True, ``--device cuda`` is injected.  If that
        fails (e.g. insufficient VRAM or missing CUDA libraries), the
        command is retried with ``--device cpu`` and a warning is logged.
        """
        # Build kwargs — hide console window on Windows.
        kwargs: dict = {
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        # Inject --device flag.  Demucs expects: … [options] INPUT
        # We insert right before the last positional argument (the audio path).
        device = "cuda" if self.use_gpu else "cpu"
        input_arg = cmd[-1]
        device_cmd = list(cmd[:-1]) + ["--device", device, input_arg]

        proc = await asyncio.create_subprocess_exec(*device_cmd, **kwargs)
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            err_text = stderr.decode("utf-8", errors="replace")

            # If GPU was requested but failed, retry with CPU automatically
            if self.use_gpu:
                print(json.dumps({
                    "step": "source_separation",
                    "progress": 0.5,
                    "message": (
                        f"GPU acceleration failed for {description}: "
                        f"{err_text[:200]}. Retrying with CPU…"
                    ),
                }), flush=True)

                cpu_cmd = list(cmd[:-1]) + ["--device", "cpu", input_arg]
                proc2 = await asyncio.create_subprocess_exec(*cpu_cmd, **kwargs)
                stdout2, stderr2 = await proc2.communicate()

                if proc2.returncode != 0:
                    err_text2 = stderr2.decode("utf-8", errors="replace")
                    msg = (
                        f"Demucs {description} failed on both GPU and CPU "
                        f"(GPU code {proc.returncode}, CPU code {proc2.returncode}): "
                        f"{err_text2[:500]}"
                    )
                    raise RuntimeError(msg)

                # GPU failed but CPU succeeded — warn and continue
                print(json.dumps({
                    "step": "source_separation",
                    "progress": 0.5,
                    "message": (
                        f"CPU fallback succeeded for {description}. "
                        f"GPU will remain disabled for subsequent steps."
                    ),
                }), flush=True)
                # Disable GPU for remaining separations in this session
                self.use_gpu = False
                return

            msg = f"Demucs {description} failed (code {proc.returncode}): {err_text[:500]}"
            raise RuntimeError(msg)

    def _write_wav(self, path: Path, audio: np.ndarray, sr: int) -> None:
        """Write a mono/stereo float32 audio array to a WAV file."""
        # Ensure proper range for int16 WAV
        audio_16 = np.clip(audio * 32767, -32768, 32767).astype(np.int16)
        if audio_16.ndim == 1:
            wavfile.write(str(path), sr, audio_16)
        else:
            wavfile.write(str(path), sr, audio_16.T)
