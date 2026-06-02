/** Result of environment detection */
export interface EnvCheckResult {
  python_available: boolean;
  python_version: string | null;
  missing_packages: string[];
  all_ready: boolean;
}

/** Options passed to the conversion command */
export interface ConversionOptions {
  inputPath: string;
  sourceSeparation: boolean;
  /** Enable GPU acceleration for Demucs source separation (requires CUDA-compatible GPU). */
  useGpu: boolean;
}

/** Final result returned from a completed conversion */
export interface ConversionResult {
  output_path: string;
  nbs_file_name: string;
  tempo: number;
  total_ticks: number;
  note_count: number;
  layer_count: number;
}

/** Progress event emitted by the Rust backend during conversion */
export interface ProgressUpdate {
  step: string;
  progress: number;
  message: string;
}

/** NBT export configuration */
export interface NbtExportConfig {
  spacing: number;
  dataVersion: number;
}

/** Result of installing missing Python packages */
export interface InstallResult {
  success: boolean;
  installed: string[];
  remaining: string[];
}

/** Which page/view is currently active */
export type AppView = 'convert' | 'nbt-export' | 'settings';

/** Conversion pipeline step names (display order) — must match Python converter.py step keys */
export const PIPELINE_STEPS = [
  { key: 'loading', label: 'Loading Audio' },
  { key: 'source_separation', label: 'Source Separation' },
  { key: 'beat_tracking', label: 'Beat Tracking' },
  { key: 'pitch_detection', label: 'Pitch Detection' },
  { key: 'generating_nbs', label: 'NBS Generation' },
  { key: 'complete', label: 'Complete' },
] as const;

