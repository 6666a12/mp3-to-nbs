import { AlertCircle, Play } from 'lucide-react';
import { useLanguage } from '@/i18n/LanguageContext';
import { TRANSLATIONS } from '@/i18n/translations';
import { FileDropZone } from '@/components/FileDropZone';
import { ConversionOptionsPanel } from '@/components/ConversionOptions';
import { ProgressPanel } from '@/components/ProgressPanel';
import { ResultPanel } from '@/components/ResultPanel';
import { Button } from '@/components/ui/button';
import type { EnvCheckResult, ConversionOptions, ProgressUpdate, ConversionResult } from '@/types/conversion';
import type { ConversionState } from '@/hooks/useConversion';

interface ConvertPageProps {
  envStatus: EnvCheckResult | null;
  onViewChange?: (view: string) => void;
  conversion: {
    state: ConversionState;
    selectedFile: string | null;
    options: ConversionOptions;
    setOptions: (partial: Partial<ConversionOptions>) => void;
    progress: ProgressUpdate | null;
    result: ConversionResult | null;
    error: string | null;
    selectFile: () => Promise<void>;
    setFileDirectly: (path: string) => void;
    clearSelection: () => void;
    startConversion: () => Promise<void>;
    reset: () => void;
  };
}

export function ConvertPage({ envStatus, onViewChange, conversion }: ConvertPageProps) {
  const { tl } = useLanguage();
  const {
    state,
    selectedFile,
    options,
    setOptions,
    progress,
    result,
    error,
    selectFile,
    setFileDirectly,
    clearSelection,
    startConversion,
    reset,
  } = conversion;

  const envReady = envStatus?.all_ready ?? false;
  const canStart = selectedFile !== null && envReady && state !== 'running';

  const handleExportNbt = () => {
    onViewChange?.('nbt-export');
  };

  return (
    <div className="flex flex-col gap-6 pb-8">
      {/* Page title */}
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          {tl(TRANSLATIONS.convert.title)}
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          {tl(TRANSLATIONS.convert.description)}
        </p>
      </div>

      {/* Environment warning */}
      {!envReady && (
        <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm">
          <AlertCircle className="h-4 w-4 text-amber-600 mt-0.5 shrink-0" />
          <div>
            <p className="font-medium text-amber-800">
              {tl(TRANSLATIONS.convert.envWarning.title)}
            </p>
            <p className="text-amber-700 mt-0.5">
              {tl(TRANSLATIONS.convert.envWarning.message)}
            </p>
          </div>
        </div>
      )}

      {/* File drop zone */}
      <FileDropZone
        selectedFile={selectedFile}
        onFileSelected={selectFile}
        onFileDropped={setFileDirectly}
        onClear={clearSelection}
        disabled={state === 'running'}
      />

      {/* Conversion options */}
      <ConversionOptionsPanel
        options={options}
        onChange={setOptions}
        disabled={state === 'running'}
      />

      {/* Error display */}
      {error && (
        <div className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 p-3 text-sm">
          <AlertCircle className="h-4 w-4 text-red-600 mt-0.5 shrink-0" />
          <div>
            <p className="font-medium text-red-800">
              {tl(TRANSLATIONS.convert.conversionError.title)}
            </p>
            <p className="text-red-700 mt-0.5">{error}</p>
          </div>
        </div>
      )}

      {/* Start button */}
      <Button
        size="lg"
        disabled={!canStart}
        onClick={startConversion}
        className="w-full sm:w-auto"
      >
        <Play className="h-4 w-4" />
        {state === 'running'
          ? tl(TRANSLATIONS.convert.converting)
          : tl(TRANSLATIONS.convert.startButton)}
      </Button>

      {/* Progress panel — only shown while running, hidden after completion */}
      {state === 'running' && (
        <ProgressPanel progress={progress} />
      )}

      {/* Result panel */}
      {state === 'completed' && result && (
        <ResultPanel
          result={result}
          onExportNbt={handleExportNbt}
          onReset={reset}
        />
      )}
    </div>
  );
}
