import { useState, useCallback, useRef } from 'react';
import { runLocalConversion, selectAudioFile } from '@/lib/tauri';
import type {
  ConversionOptions,
  ConversionResult,
  ProgressUpdate,
} from '@/types/conversion';

/** The overall conversion lifecycle state */
export type ConversionState =
  | 'idle'
  | 'selecting'
  | 'ready'
  | 'running'
  | 'completed'
  | 'error';

/** A single log entry with timestamp */
export interface LogEntry {
  time: string;
  text: string;
}

interface UseConversionReturn {
  /** Current lifecycle state */
  state: ConversionState;
  /** Path of the selected input audio file (null while idle) */
  selectedFile: string | null;
  /** User-configurable options */
  options: ConversionOptions;
  /** Update a subset of options */
  setOptions: (partial: Partial<ConversionOptions>) => void;
  /** Latest progress update from the backend */
  progress: ProgressUpdate | null;
  /** Result returned when conversion completes */
  result: ConversionResult | null;
  /** Error message if the conversion or selection fails */
  error: string | null;
  /** Detailed progress log lines */
  logLines: LogEntry[];
  /** Open the file picker and populate `selectedFile` */
  selectFile: () => Promise<void>;
  /** Set the file path directly (e.g., from drag-and-drop event) */
  setFileDirectly: (path: string) => void;
  /** Clear the selected file and reset to idle */
  clearSelection: () => void;
  /** Start the conversion pipeline */
  startConversion: () => Promise<void>;
  /** Reset everything back to idle */
  reset: () => void;
}

function readDefaultGpu(): boolean {
  try { return localStorage.getItem('mp3-to-nbs-use-gpu') === 'true'; }
  catch { return false; }
}

const DEFAULT_OPTIONS: ConversionOptions = {
  inputPath: '',
  sourceSeparation: true,
  quality: 'balanced',
  useGpu: readDefaultGpu(),
};

export function useConversion(): UseConversionReturn {
  const [state, setState] = useState<ConversionState>('idle');
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [options, setOptionsState] = useState<ConversionOptions>(DEFAULT_OPTIONS);
  const [progress, setProgress] = useState<ProgressUpdate | null>(null);
  const [result, setResult] = useState<ConversionResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [logLines, setLogLines] = useState<LogEntry[]>([]);

  // Abort controller ref for potential future cancellation
  const abortRef = useRef(false);

  const setOptions = useCallback((partial: Partial<ConversionOptions>) => {
    setOptionsState((prev) => ({ ...prev, ...partial }));
    // Reset result/progress state when options change if we were previously completed
    setState((prev) => (prev === 'completed' || prev === 'error' ? 'ready' : prev));
  }, []);

  const selectFile = useCallback(async () => {
    setState('selecting');
    setError(null);
    try {
      const path = await selectAudioFile();
      if (path) {
        setSelectedFile(path);
        setOptionsState((prev) => ({ ...prev, inputPath: path }));
        setState('ready');
      } else {
        // User cancelled — revert to idle if nothing was selected before
        setState((prev) => (prev === 'selecting' ? (selectedFile ? 'ready' : 'idle') : prev));
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      setState('error');
    }
  }, [selectedFile]);

  const clearSelection = useCallback(() => {
    setSelectedFile(null);
    setOptionsState((prev) => ({ ...prev, inputPath: '' }));
    setProgress(null);
    setResult(null);
    setError(null);
    setState('idle');
  }, []);

  const setFileDirectly = useCallback((path: string) => {
    setSelectedFile(path);
    setOptionsState((prev) => ({ ...prev, inputPath: path }));
    setProgress(null);
    setResult(null);
    setError(null);
    setState('ready');
  }, []);

  const startConversion = useCallback(async () => {
    if (!options.inputPath) {
      setError('No input file selected');
      return;
    }

    abortRef.current = false;
    setState('running');
    setProgress(null);
    setResult(null);
    setError(null);
    setLogLines([]);

    const addLog = (text: string) => {
      const now = new Date();
      const time = now.toLocaleTimeString('zh-CN', { hour12: false });
      setLogLines((prev) => [...prev, { time, text }]);
    };

    try {
      const conversionResult = await runLocalConversion(options, (update) => {
        if (!abortRef.current) {
          setProgress(update);
          if (update.message) {
            addLog(update.message);
          }
        }
      });

      if (!abortRef.current) {
        setResult(conversionResult);
        setState('completed');
      }
    } catch (e) {
      if (!abortRef.current) {
        const msg = e instanceof Error ? e.message : String(e);
        setError(msg);
        setState('error');
      }
    }
  }, [options]);

  const reset = useCallback(() => {
    abortRef.current = true;
    setState('idle');
    setSelectedFile(null);
    setOptionsState(DEFAULT_OPTIONS);
    setProgress(null);
    setResult(null);
    setError(null);
  }, []);

  return {
    state,
    selectedFile,
    options,
    setOptions,
    progress,
    result,
    error,
    logLines,
    selectFile,
    setFileDirectly,
    clearSelection,
    startConversion,
    reset,
  };
}
