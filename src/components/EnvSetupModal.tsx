import { useState } from 'react';
import { CheckCircle, XCircle, Loader2, Download } from 'lucide-react';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useLanguage } from '@/i18n/LanguageContext';
import { TRANSLATIONS } from '@/i18n/translations';
import { installMissingPackages, checkEnvironment } from '@/lib/tauri';
import type { EnvCheckResult, InstallResult } from '@/types/conversion';

interface EnvSetupModalProps {
  status: EnvCheckResult;
  onClose: () => void;
  onStatusChange?: (newStatus: EnvCheckResult) => void;
}

export function EnvSetupModal({ status, onClose, onStatusChange }: EnvSetupModalProps) {
  const { tl } = useLanguage();
  const [installing, setInstalling] = useState(false);
  const [installLog, setInstallLog] = useState<string[]>([]);
  const [installResult, setInstallResult] = useState<InstallResult | null>(null);

  const handleAutoInstall = async () => {
    setInstalling(true);
    setInstallLog(['Starting pip install...']);
    try {
      const result = await installMissingPackages();
      setInstallResult(result);
      if (result.success) {
        setInstallLog((prev) => [...prev, tl(TRANSLATIONS.envModal.installSuccess)]);
        const newStatus = await checkEnvironment();
        onStatusChange?.(newStatus);
        if (newStatus.all_ready) setTimeout(() => onClose(), 1500);
      } else {
        setInstallLog((prev) => [
          ...prev,
          `Installed: ${result.installed.join(', ') || 'none'}`,
          `Still missing: ${result.remaining.join(', ') || 'none'}`,
        ]);
      }
    } catch (e) {
      setInstallLog((prev) => [...prev, `Error: ${e instanceof Error ? e.message : String(e)}`]);
    } finally {
      setInstalling(false);
    }
  };

  const pythonOk = status.python_available;
  const allOk = status.all_ready;

  return (
    <Dialog open={!allOk} onOpenChange={() => !installing && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {tl(TRANSLATIONS.envModal.title)}
          </DialogTitle>
          <DialogDescription>
            {tl(TRANSLATIONS.envModal.description)}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 px-6 pb-2">
          {/* Python status */}
          <div className="flex items-center justify-between rounded-md border p-3">
            <div className="flex items-center gap-2">
              {pythonOk
                ? <CheckCircle className="h-5 w-5 text-green-500 shrink-0" />
                : <XCircle className="h-5 w-5 text-red-500 shrink-0" />}
              <div>
                <p className="text-sm font-medium">{tl(TRANSLATIONS.settings.env.python.label)}</p>
                <p className="text-xs text-muted-foreground">
                  {status.python_version ?? tl(TRANSLATIONS.settings.env.python.notDetected)}
                </p>
              </div>
            </div>
            {pythonOk
              ? <span className="text-xs font-medium text-green-600">{tl(TRANSLATIONS.envModal.pythonInstalled)}</span>
              : <span className="text-xs font-medium text-red-600">{tl(TRANSLATIONS.envModal.pythonMissing)}</span>}
          </div>

          {/* Package dependencies */}
          <div className="rounded-md border p-3">
            <p className="text-sm font-medium mb-2">{tl(TRANSLATIONS.settings.env.packages.label)}</p>
            {status.missing_packages.length === 0 ? (
              <div className="flex items-center gap-2 text-green-600">
                <CheckCircle className="h-4 w-4" />
                <span className="text-sm">{tl(TRANSLATIONS.envModal.packagesAllReady)}</span>
              </div>
            ) : (
              <ul className="space-y-1">
                {status.missing_packages.map((pkg) => (
                  <li key={pkg} className="flex items-center gap-2 text-sm text-amber-700">
                    <XCircle className="h-3.5 w-3.5 text-amber-500 shrink-0" />
                    {pkg}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Install progress log */}
          {installLog.length > 0 && (
            <div className="rounded-md bg-gray-50 p-3 font-mono text-xs max-h-32 overflow-y-auto">
              {installLog.map((line, i) => <div key={i} className="text-gray-700">{line}</div>)}
              {installing && (
                <div className="flex items-center gap-2 text-blue-600 mt-1">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  {tl(TRANSLATIONS.envModal.installing)}
                </div>
              )}
            </div>
          )}

          {/* Install result */}
          {installResult && !installResult.success && (
            <div className="rounded-md bg-red-50 p-3">
              <p className="text-sm text-red-800 font-medium">
                {tl(TRANSLATIONS.envModal.installPartial)}
              </p>
              <p className="text-xs text-red-600 mt-1">
                Still missing: {installResult.remaining.join(', ')}
              </p>
            </div>
          )}
        </div>

        <DialogFooter className="gap-2 sm:gap-2">
          {!pythonOk && (
            <Button variant="outline"
              onClick={() => { try { window.open('https://www.python.org/downloads/', '_blank'); } catch { /* ignore */ } }}>
              <Download className="h-4 w-4" />
              {tl(TRANSLATIONS.envModal.downloadPython)}
            </Button>
          )}
          {pythonOk && status.missing_packages.length > 0 && (
            <Button onClick={handleAutoInstall} disabled={installing}>
              {installing && <Loader2 className="h-4 w-4 animate-spin" />}
              {installing ? tl(TRANSLATIONS.envModal.installing) : tl(TRANSLATIONS.envModal.installMissingButton)}
            </Button>
          )}
          <Button variant="ghost" onClick={onClose} disabled={installing}>
            {tl(TRANSLATIONS.envModal.skip)}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
