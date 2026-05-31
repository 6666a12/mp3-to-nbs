import { useState, useCallback } from 'react';
import { FileOutput, FolderOpen, Info, FileAudio, X } from 'lucide-react';
import {
  Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { Badge } from '@/components/ui/badge';
import { useLanguage } from '@/i18n/LanguageContext';
import { TRANSLATIONS } from '@/i18n/translations';
import {
  selectNbsFile, selectNbtSaveLocation, exportNbt, showInFolder,
} from '@/lib/tauri';
import type { NbtExportConfig } from '@/types/conversion';

export function NbtExportPage() {
  const { tl } = useLanguage();
  const [nbsPath, setNbsPath] = useState<string | null>(null);
  const [spacing, setSpacing] = useState(2);
  const [dataVersion, setDataVersion] = useState(3953);
  const [exporting, setExporting] = useState(false);
  const [resultPath, setResultPath] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSelectNbs = useCallback(async () => {
    setError(null);
    try {
      const path = await selectNbsFile();
      if (path) { setNbsPath(path); setResultPath(null); }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  const handleExport = useCallback(async () => {
    if (!nbsPath) return;
    setExporting(true);
    setError(null);
    try {
      const defaultName = nbsPath
        .replace(/\\/g, '/').split('/').pop()
        ?.replace(/\.nbs$/i, '.nbt') ?? 'output.nbt';
      const savePath = await selectNbtSaveLocation(defaultName);
      if (!savePath) { setExporting(false); return; }
      const config: NbtExportConfig = { spacing, dataVersion };
      await exportNbt(nbsPath, savePath, config);
      setResultPath(savePath);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setExporting(false);
    }
  }, [nbsPath, spacing, dataVersion]);

  const handleShowInFolder = useCallback(async () => {
    if (resultPath) {
      try { await showInFolder(resultPath); } catch { /* ignore */ }
    }
  }, [resultPath]);

  const getFileName = (path: string) => {
    const parts = path.replace(/\\/g, '/').split('/');
    return parts[parts.length - 1] || path;
  };

  return (
    <div className="flex flex-col gap-6 pb-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          {tl(TRANSLATIONS.nbtExport.title)}
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          {tl(TRANSLATIONS.nbtExport.description)}
        </p>
      </div>

      {/* Info box */}
      <div className="flex items-start gap-2 rounded-md border border-blue-200 bg-blue-50 p-4 text-sm">
        <Info className="h-4 w-4 text-blue-600 mt-0.5 shrink-0" />
        <div>
          <p className="font-medium text-blue-800">
            {tl(TRANSLATIONS.nbtExport.infoTitle)}
          </p>
          <ol className="list-decimal list-inside text-blue-700 mt-1 space-y-0.5">
            {TRANSLATIONS.nbtExport.infoSteps.map((step, i) => (
              <li key={i}>{tl(step)}</li>
            ))}
          </ol>
        </div>
      </div>

      {/* NBS file selection */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">{tl(TRANSLATIONS.nbtExport.nbsFile.title)}</CardTitle>
          <CardDescription>{tl(TRANSLATIONS.nbtExport.nbsFile.description)}</CardDescription>
        </CardHeader>
        <CardContent>
          {!nbsPath ? (
            <Button variant="outline" onClick={handleSelectNbs} className="w-full py-8">
              <FileAudio className="h-5 w-5 mr-2" />
              {tl(TRANSLATIONS.nbtExport.nbsFile.select)}
            </Button>
          ) : (
            <div className="flex items-center gap-3 rounded-md border bg-accent/30 p-3">
              <FileAudio className="h-8 w-8 text-primary shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{getFileName(nbsPath)}</p>
                <p className="text-xs text-muted-foreground truncate">{nbsPath}</p>
              </div>
              <button
                onClick={() => { setNbsPath(null); setResultPath(null); setError(null); }}
                className="shrink-0 rounded-full p-1 hover:bg-destructive/10 hover:text-destructive transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Export configuration */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">{tl(TRANSLATIONS.nbtExport.config.title)}</CardTitle>
          <CardDescription>{tl(TRANSLATIONS.nbtExport.config.description)}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="nbt-spacing">{tl(TRANSLATIONS.nbtExport.spacing.label)}</Label>
            <Input id="nbt-spacing" type="number" min={1} max={4} value={spacing}
              onChange={(e) => { const v = parseInt(e.target.value); if (!isNaN(v) && v >= 1 && v <= 4) setSpacing(v); }}
              className="w-24" />
            <p className="text-xs text-muted-foreground">{tl(TRANSLATIONS.nbtExport.spacing.description)}</p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="nbt-data-version">{tl(TRANSLATIONS.nbtExport.dataVersion.label)}</Label>
            <Input id="nbt-data-version" type="number" value={dataVersion}
              onChange={(e) => { const v = parseInt(e.target.value); if (!isNaN(v)) setDataVersion(v); }}
              className="w-32" />
            <p className="text-xs text-muted-foreground">{tl(TRANSLATIONS.nbtExport.dataVersion.description)}</p>
          </div>
        </CardContent>
      </Card>

      {/* Error */}
      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          <p className="font-medium">{tl(TRANSLATIONS.nbtExport.exportError.title)}</p>
          <p className="mt-0.5">{error}</p>
        </div>
      )}

      {/* Export button */}
      <Button size="lg" disabled={!nbsPath || exporting} onClick={handleExport}
        className="w-full sm:w-auto">
        <FileOutput className="h-4 w-4" />
        {exporting ? tl(TRANSLATIONS.nbtExport.exporting) : tl(TRANSLATIONS.nbtExport.exportButton)}
      </Button>

      {/* Result */}
      {resultPath && (
        <Card className="border-green-200 bg-green-50/30">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Badge variant="success">{tl(TRANSLATIONS.nbtExport.exported)}</Badge>
                <span className="text-sm font-mono text-muted-foreground truncate max-w-md">
                  {resultPath}
                </span>
              </div>
              <Button variant="secondary" size="sm" onClick={handleShowInFolder}>
                <FolderOpen className="h-4 w-4" />
                {tl(TRANSLATIONS.result.showInFolder)}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      <Separator />
      <div className="text-xs text-muted-foreground">
        <p>{tl(TRANSLATIONS.nbtExport.compatibilityNote)}</p>
      </div>
    </div>
  );
}
