import { invoke } from '@tauri-apps/api/core';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';
import { open, save } from '@tauri-apps/plugin-dialog';
import type {
  EnvCheckResult,
  ConversionOptions,
  ConversionResult,
  ProgressUpdate,
  NbtExportConfig,
  InstallResult,
} from '@/types/conversion';

// =============================================================================
// Tauri availability check
// =============================================================================

/** Returns true if the app is running inside a Tauri webview. */
export function isTauri(): boolean {
  return !!(window as any).__TAURI_INTERNALS__;
}

// =============================================================================
// Environment
// =============================================================================

/** Check whether Python and required packages are available. */
export async function checkEnvironment(): Promise<EnvCheckResult> {
  return invoke<EnvCheckResult>('check_environment');
}

/** Install missing Python packages via pip. */
export async function installMissingPackages(): Promise<InstallResult> {
  return invoke<InstallResult>('install_missing_packages');
}

// =============================================================================
// Conversion
// =============================================================================

/**
 * Run the MP3-to-NBS conversion pipeline.
 *
 * Subscribes to `conversion-progress` events via `listen()` and forwards them
 * to the optional `onProgress` callback. Automatically unsubscribes on
 * completion / error.
 */
export async function runLocalConversion(
  options: ConversionOptions,
  onProgress?: (progress: ProgressUpdate) => void
): Promise<ConversionResult> {
  let unlisten: UnlistenFn = () => {};

  if (onProgress) {
    unlisten = await listen<ProgressUpdate>('conversion-progress', (event) => {
      onProgress(event.payload);
    });
  }

  try {
    const result = await invoke<ConversionResult>('run_local_conversion', {
      inputPath: options.inputPath,
      options: {
        source_separation: options.sourceSeparation,
        quality: options.quality,
        use_gpu: options.useGpu,
      },
    });
    return result;
  } finally {
    unlisten();
  }
}

// =============================================================================
// NBT Export
// =============================================================================

/** Export an NBS file to a .nbt Minecraft structure file. */
export async function exportNbt(
  nbsPath: string,
  outputPath: string,
  config: NbtExportConfig
): Promise<void> {
  return invoke('export_nbt', {
    nbsPath,
    outputPath,
    config: {
      spacing: config.spacing,
      data_version: config.dataVersion,
    },
  });
}

// =============================================================================
// File Dialogs
// =============================================================================

/** Open a native file picker for audio files (.mp3, .wav, .flac, .m4a, .ogg). */
export async function selectAudioFile(): Promise<string | null> {
  if (!isTauri()) {
    console.warn('Not running inside Tauri — file dialog unavailable');
    return null;
  }
  const file = await open({
    multiple: false,
    directory: false,
    filters: [
      {
        name: 'Audio Files',
        extensions: ['mp3', 'wav', 'flac', 'm4a', 'ogg'],
      },
    ],
  });
  return (file as string) ?? null;
}

/** Open a native file picker for NBS files (.nbs). */
export async function selectNbsFile(): Promise<string | null> {
  if (!isTauri()) {
    console.warn('Not running inside Tauri — file dialog unavailable');
    return null;
  }
  const file = await open({
    multiple: false,
    directory: false,
    filters: [
      {
        name: 'NBS Files',
        extensions: ['nbs'],
      },
    ],
  });
  return (file as string) ?? null;
}

/** Open a native "Save As" dialog. */
export async function selectSaveLocation(defaultName: string): Promise<string | null> {
  if (!isTauri()) {
    console.warn('Not running inside Tauri — save dialog unavailable');
    return null;
  }
  const path = await save({
    defaultPath: defaultName,
    filters: [{ name: 'NBS Files', extensions: ['nbs'] }],
  });
  return (path as string) ?? null;
}

/** Open a native "Save As" dialog for .nbt files. */
export async function selectNbtSaveLocation(defaultName: string): Promise<string | null> {
  if (!isTauri()) {
    console.warn('Not running inside Tauri — save dialog unavailable');
    return null;
  }
  const path = await save({
    defaultPath: defaultName,
    filters: [{ name: 'NBT Structure Files', extensions: ['nbt'] }],
  });
  return (path as string) ?? null;
}

// =============================================================================
// Drag-and-drop support
// =============================================================================

/**
 * Listen for file drops from the OS into the Tauri window.
 * Returns an unlisten function to clean up on unmount.
 */
export async function onFileDrop(
  callback: (paths: string[]) => void
): Promise<UnlistenFn> {
  return listen<{ paths: string[] }>('tauri://drag-drop', (event) => {
    const paths = event.payload.paths;
    if (paths && paths.length > 0) {
      callback(paths);
    }
  });
}

// =============================================================================
// Filesystem helpers
// =============================================================================

/** Copy a file from source to destination (uses Rust std::fs::copy — no scope restrictions). */
export async function copyFile(src: string, dst: string): Promise<void> {
  await invoke('copy_file', { src, dst });
}

/** Reveal a file/directory in the platform's file manager. */
export async function showInFolder(filePath: string): Promise<void> {
  await invoke('show_in_folder', { path: filePath });
}
