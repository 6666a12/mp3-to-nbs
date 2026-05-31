import { useState, useCallback, useEffect, DragEvent } from 'react';
import { Upload, FileAudio, X } from 'lucide-react';
import { useLanguage } from '@/i18n/LanguageContext';
import { TRANSLATIONS } from '@/i18n/translations';
import { cn } from '@/lib/utils';
import { onFileDrop, isTauri } from '@/lib/tauri';

interface FileDropZoneProps {
  selectedFile: string | null;
  onFileSelected: () => Promise<void>;
  onFileDropped?: (path: string) => void;
  onClear: () => void;
  disabled?: boolean;
}

function getFileName(path: string): string {
  const parts = path.replace(/\\/g, '/').split('/');
  return parts[parts.length - 1] || path;
}

/** Filter dropped paths to only audio file extensions. */
function filterAudioFiles(paths: string[]): string | null {
  const audioExts = ['.mp3', '.wav', '.flac', '.m4a', '.ogg', '.aac', '.wma', '.aiff'];
  const match = paths.find((p) => audioExts.some((ext) => p.toLowerCase().endsWith(ext)));
  return match ?? paths[0] ?? null;
}

export function FileDropZone({
  selectedFile,
  onFileSelected,
  onFileDropped,
  onClear,
  disabled = false,
}: FileDropZoneProps) {
  const { tl } = useLanguage();
  const [isDragOver, setIsDragOver] = useState(false);

  // ---- Tauri native file-drop listener -----------------------------------
  useEffect(() => {
    if (!isTauri() || !onFileDropped) return;
    let cleanup: (() => void) | undefined;
    onFileDrop((paths) => {
      const file = filterAudioFiles(paths);
      if (file) {
        setIsDragOver(false);
        onFileDropped(file);
      }
    }).then((unlisten) => {
      cleanup = () => { unlisten(); };
    });
    return () => { cleanup?.(); };
  }, [onFileDropped]);

  // ---- HTML drag events (visual feedback) ---------------------------------
  const handleDragOver = useCallback(
    (e: DragEvent<HTMLDivElement>) => {
      e.preventDefault(); e.stopPropagation();
      if (!disabled) setIsDragOver(true);
    }, [disabled]);

  const handleDragLeave = useCallback(
    (e: DragEvent<HTMLDivElement>) => {
      e.preventDefault(); e.stopPropagation();
      setIsDragOver(false);
    }, []);

  const handleDrop = useCallback(
    (e: DragEvent<HTMLDivElement>) => {
      e.preventDefault(); e.stopPropagation();
      setIsDragOver(false);
      if (disabled) return;
      // Browser drag-and-drop (doesn't give full paths — handled by Tauri event above).
      // Fall back to opening the file dialog.
      const files = e.dataTransfer?.files;
      if (files && files.length > 0) {
        onFileSelected();
      }
    }, [disabled, onFileSelected]);

  const handleClick = useCallback(() => {
    if (!disabled) onFileSelected();
  }, [disabled, onFileSelected]);

  return (
    <div
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      onClick={selectedFile ? undefined : handleClick}
      className={cn(
        'relative flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-12 transition-all duration-200 select-none-drag cursor-pointer',
        isDragOver && 'border-primary bg-primary/5 scale-[1.01]',
        'border-muted-foreground/25 hover:border-muted-foreground/50 hover:bg-accent/50',
        selectedFile && 'border-primary/50 bg-primary/5 cursor-default',
        disabled && 'opacity-50 cursor-not-allowed'
      )}
    >
      {!selectedFile ? (
        <>
          <Upload className="h-10 w-10 text-muted-foreground mb-3" />
          <p className="text-sm font-medium">
            {tl(TRANSLATIONS.fileDrop.prompt)}
            <span className="text-primary underline-offset-2 hover:underline">
              {tl(TRANSLATIONS.fileDrop.browse)}
            </span>
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            {tl(TRANSLATIONS.fileDrop.supported)}
          </p>
        </>
      ) : (
        <div className="flex items-center gap-3 w-full max-w-full">
          <FileAudio className="h-8 w-8 text-primary shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium truncate">{getFileName(selectedFile)}</p>
            <p className="text-xs text-muted-foreground truncate">{selectedFile}</p>
          </div>
          <button
            onClick={(e) => { e.stopPropagation(); onClear(); }}
            disabled={disabled}
            className="shrink-0 rounded-full p-1 hover:bg-destructive/10 hover:text-destructive transition-colors"
            title="Clear selection"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}
    </div>
  );
}
