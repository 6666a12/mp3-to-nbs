import { useState, useCallback } from 'react';
import { CheckCircle, XCircle, Loader2, RefreshCw, Download, Info } from 'lucide-react';
import {
  Card, CardHeader, CardTitle, CardDescription, CardContent,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { Badge } from '@/components/ui/badge';
import { useLanguage } from '@/i18n/LanguageContext';
import { TRANSLATIONS } from '@/i18n/translations';
import { checkEnvironment, installMissingPackages } from '@/lib/tauri';
import type { EnvCheckResult } from '@/types/conversion';

interface SettingsPageProps {
  envStatus: EnvCheckResult | null;
  onEnvUpdate: (status: EnvCheckResult) => void;
}

export function SettingsPage({ envStatus, onEnvUpdate }: SettingsPageProps) {
  const { tl } = useLanguage();
  const [rechecking, setRechecking] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [installLog, setInstallLog] = useState<string[]>([]);
  const [nbtSpacing, setNbtSpacing] = useState(2);
  const [nbtDataVersion, setNbtDataVersion] = useState(3953);
  const [gpuEnabled, setGpuEnabled] = useState(() => {
    try {
      const stored = localStorage.getItem('mp3-to-nbs-use-gpu');
      if (stored !== null) return stored === 'true';
      return true;  // GPU enabled by default
    }
    catch { return true; }
  });

  const handleRecheck = useCallback(async () => {
    setRechecking(true);
    try { const result = await checkEnvironment(); onEnvUpdate(result); }
    catch (e) { console.error('Recheck failed:', e); }
    finally { setRechecking(false); }
  }, [onEnvUpdate]);

  const handleInstall = useCallback(async () => {
    setInstalling(true);
    setInstallLog(['Starting pip install...']);
    try {
      const result = await installMissingPackages();
      setInstallLog((prev) => [
        ...prev,
        `Installed: ${result.installed.join(', ') || 'none'}`,
        result.success ? 'All packages installed!' : `Still missing: ${result.remaining.join(', ') || 'none'}`,
      ]);
      const newStatus = await checkEnvironment();
      onEnvUpdate(newStatus);
    } catch (e) {
      setInstallLog((prev) => [...prev, `Error: ${e instanceof Error ? e.message : String(e)}`]);
    } finally {
      setInstalling(false);
    }
  }, [onEnvUpdate]);

  const status = envStatus;

  return (
    <div className="flex flex-col gap-6 pb-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{tl(TRANSLATIONS.settings.title)}</h1>
        <p className="text-sm text-muted-foreground mt-1">{tl(TRANSLATIONS.settings.description)}</p>
      </div>

      {/* Local Environment */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">{tl(TRANSLATIONS.settings.env.title)}</CardTitle>
          <CardDescription>{tl(TRANSLATIONS.settings.env.description)}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {status ? (
            <>
              <div className="flex items-center justify-between rounded-md border p-3">
                <div className="flex items-center gap-2">
                  {status.python_available ? (
                    <CheckCircle className="h-5 w-5 text-green-500" />
                  ) : (
                    <XCircle className="h-5 w-5 text-red-500" />
                  )}
                  <div>
                    <p className="text-sm font-medium">{tl(TRANSLATIONS.settings.env.python.label)}</p>
                    <p className="text-xs text-muted-foreground">
                      {status.python_version ?? tl(TRANSLATIONS.settings.env.python.notDetected)}
                    </p>
                  </div>
                </div>
                <Badge variant={status.python_available ? 'success' : 'destructive'}>
                  {status.python_available
                    ? tl(TRANSLATIONS.settings.env.python.ready)
                    : tl(TRANSLATIONS.settings.env.python.missing)}
                </Badge>
              </div>

              <div className="rounded-md border p-3">
                <p className="text-sm font-medium mb-2">{tl(TRANSLATIONS.settings.env.packages.label)}</p>
                {status.missing_packages.length === 0 ? (
                  <div className="flex items-center gap-2 text-green-600">
                    <CheckCircle className="h-4 w-4" />
                    <span className="text-sm">{tl(TRANSLATIONS.settings.env.packages.allReady)}</span>
                  </div>
                ) : (
                  <div className="space-y-1">
                    {status.missing_packages.map((pkg) => (
                      <div key={pkg} className="flex items-center gap-2 text-sm text-amber-700">
                        <XCircle className="h-3.5 w-3.5 text-amber-500 shrink-0" />
                        {pkg}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="flex items-center gap-2">
                <Badge variant={status.all_ready ? 'success' : 'warning'} className="text-xs">
                  {status.all_ready
                    ? tl(TRANSLATIONS.settings.env.overall.ready)
                    : tl(TRANSLATIONS.settings.env.overall.missing)}
                </Badge>
              </div>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">{tl(TRANSLATIONS.settings.env.notChecked)}</p>
          )}

          <div className="flex gap-2">
            <Button variant="outline" onClick={handleRecheck} disabled={rechecking} size="sm">
              {rechecking ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              {tl(TRANSLATIONS.settings.env.recheck)}
            </Button>
            {status && !status.python_available && (
              <Button variant="outline" size="sm"
                onClick={() => { try { window.open('https://www.python.org/downloads/', '_blank'); } catch { /* ignore */ } }}>
                <Download className="h-4 w-4" />
                {tl(TRANSLATIONS.settings.env.downloadPython)}
              </Button>
            )}
            {status && status.python_available && status.missing_packages.length > 0 && (
              <Button variant="outline" onClick={handleInstall} disabled={installing} size="sm">
                {installing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
                {tl(TRANSLATIONS.settings.env.installDeps)}
              </Button>
            )}
          </div>

          {installLog.length > 0 && (
            <div className="rounded-md bg-gray-50 p-3 font-mono text-xs max-h-32 overflow-y-auto">
              {installLog.map((line, i) => <div key={i} className="text-gray-700">{line}</div>)}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Conversion Defaults */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">{tl(TRANSLATIONS.settings.conversion.title)}</CardTitle>
          <CardDescription>{tl(TRANSLATIONS.settings.conversion.description)}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* GPU toggle */}
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label className="text-sm">{tl(TRANSLATIONS.settings.conversion.gpuLabel)}</Label>
              <p className="text-xs text-muted-foreground">
                {tl(TRANSLATIONS.settings.conversion.gpuDesc)}
              </p>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={gpuEnabled}
              onClick={() => {
                const next = !gpuEnabled;
                setGpuEnabled(next);
                try { localStorage.setItem('mp3-to-nbs-use-gpu', String(next)); } catch { /* ignore */ }
              }}
              className={`
                relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center
                rounded-full border-2 border-transparent transition-colors
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring
                focus-visible:ring-offset-2
                ${gpuEnabled ? 'bg-primary' : 'bg-muted-foreground/30'}
              `}
            >
              <span className={`
                pointer-events-none block h-3.5 w-3.5 rounded-full bg-white shadow-lg
                ring-0 transition-transform
                ${gpuEnabled ? 'translate-x-4' : 'translate-x-0.5'}
              `} />
            </button>
          </div>
          {gpuEnabled && (
            <p className="text-xs text-amber-600 dark:text-amber-400 border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-950 rounded-md px-2.5 py-1.5">
              {tl(TRANSLATIONS.settings.conversion.gpuWarning)}
            </p>
          )}
        </CardContent>
      </Card>

      {/* Export Configuration */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">{tl(TRANSLATIONS.settings.export.title)}</CardTitle>
          <CardDescription>{tl(TRANSLATIONS.settings.export.description)}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="settings-tick-spacing">{tl(TRANSLATIONS.settings.export.spacingLabel)}</Label>
            <Input id="settings-tick-spacing" type="number" min={1} max={4} value={nbtSpacing}
              onChange={(e) => { const v = parseInt(e.target.value); if (!isNaN(v) && v >= 1 && v <= 4) setNbtSpacing(v); }}
              className="w-24" />
            <p className="text-xs text-muted-foreground">{tl(TRANSLATIONS.settings.export.spacingDesc)}</p>
          </div>
          <Separator />
          <div className="space-y-2">
            <Label htmlFor="settings-data-version">{tl(TRANSLATIONS.settings.export.dataVersionLabel)}</Label>
            <Input id="settings-data-version" type="number" value={nbtDataVersion}
              onChange={(e) => { const v = parseInt(e.target.value); if (!isNaN(v)) setNbtDataVersion(v); }}
              className="w-32" />
            <p className="text-xs text-muted-foreground">{tl(TRANSLATIONS.settings.export.dataVersionDesc)}</p>
          </div>
          <div className="flex items-start gap-2 rounded-md border bg-accent/30 p-3">
            <Info className="h-4 w-4 text-muted-foreground mt-0.5 shrink-0" />
            <p className="text-xs text-muted-foreground">{tl(TRANSLATIONS.settings.export.note)}</p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
