import { useState, useEffect } from 'react';
import { Music2, FileOutput, Settings, Circle } from 'lucide-react';
import { LanguageProvider, useLanguage } from '@/i18n/LanguageContext';
import { TRANSLATIONS } from '@/i18n/translations';
import { LanguageSwitcher } from '@/components/LanguageSwitcher';
import { useEnvironment } from '@/hooks/useEnvironment';
import { useConversion } from '@/hooks/useConversion';
import { EnvSetupModal } from '@/components/EnvSetupModal';
import { ConvertPage } from '@/pages/ConvertPage';
import { NbtExportPage } from '@/pages/NbtExportPage';
import { SettingsPage } from '@/pages/SettingsPage';
import { cn } from '@/lib/utils';
import type { AppView } from '@/types/conversion';

interface NavItem {
  view: AppView;
  labelKey: 'file' | 'nbt' | 'settings';
  icon: typeof Music2;
}

const NAV_ITEMS: NavItem[] = [
  { view: 'convert', labelKey: 'file', icon: Music2 },
  { view: 'nbt-export', labelKey: 'nbt', icon: FileOutput },
  { view: 'settings', labelKey: 'settings', icon: Settings },
];

function AppShell() {
  const [activeView, setActiveView] = useState<AppView>('convert');
  const [showEnvModal, setShowEnvModal] = useState(false);
  const { status, loading: envLoading, error: envError, everAttempted, recheck } = useEnvironment();
  const { lang, tl } = useLanguage();

  // Lift conversion state here so it persists across page navigation.
  const conversion = useConversion();

  // Show the env setup modal when a check has been attempted and the env is not ready.
  useEffect(() => {
    if (everAttempted && !status?.all_ready) {
      setShowEnvModal(true);
    }
  }, [everAttempted, status?.all_ready]);

  const handleEnvClose = () => {
    setShowEnvModal(false);
  };

  const handleEnvStatusChange = () => {
    recheck();
  };

  const handleViewChange = (view: string) => {
    if (view === 'convert' || view === 'nbt-export' || view === 'settings') {
      setActiveView(view);
    }
  };

  const envReady = status?.all_ready ?? false;

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Sidebar */}
      <aside className="flex w-56 shrink-0 flex-col border-r bg-card">
        {/* Header */}
        <div className="flex h-14 items-center gap-2 px-4 border-b">
          <Music2 className="h-5 w-5 text-primary" />
          <div>
            <h1 className="text-sm font-semibold leading-none">
              {tl(TRANSLATIONS.app.title)}
            </h1>
            <p className="text-[10px] text-muted-foreground leading-none mt-0.5">
              {tl(TRANSLATIONS.app.version)}
            </p>
          </div>
        </div>

        {/* Nav items */}
        <nav className="flex-1 space-y-1 p-2">
          {NAV_ITEMS.map((item) => {
            const isActive = activeView === item.view;
            const Icon = item.icon;

            return (
              <button
                key={item.view}
                onClick={() => setActiveView(item.view)}
                className={cn(
                  'flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-primary/10 text-primary'
                    : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                )}
              >
                <Icon className="h-4 w-4 shrink-0" />
                {tl(TRANSLATIONS.app.nav[item.labelKey])}
              </button>
            );
          })}
        </nav>

        {/* Footer — language + environment status */}
        <div className="border-t p-3 space-y-2">
          {/* Language switcher */}
          <LanguageSwitcher />

          {/* Environment status — clickable for manual re-check */}
          <button
            onClick={() => recheck()}
            disabled={envLoading}
            className="w-full flex items-center gap-2 rounded-md p-1.5 -mx-1 hover:bg-accent transition-colors text-left"
            title={tl(TRANSLATIONS.app.envStatus.recheck)}
          >
            <Circle
              className={cn(
                'h-2 w-2 shrink-0',
                envLoading
                  ? 'text-muted-foreground animate-pulse'
                  : envReady
                  ? 'text-green-500'
                  : 'text-amber-500'
              )}
              fill="currentColor"
            />
            <span className="text-xs text-muted-foreground">
              {envLoading
                ? tl(TRANSLATIONS.app.envStatus.checking)
                : envReady
                ? tl(TRANSLATIONS.app.envStatus.ready)
                : tl(TRANSLATIONS.app.envStatus.incomplete)}
            </span>
          </button>

          {/* Connection / IPC error */}
          {envError && !envLoading && (
            <p className="text-[10px] text-red-500 leading-tight">
              {envError}
            </p>
          )}

          {status && !status.python_available && (
            <p className="text-[10px] text-red-500">
              {tl(TRANSLATIONS.app.envStatus.pythonMissing)}
            </p>
          )}

          {status &&
            status.python_available &&
            status.missing_packages.length > 0 && (
              <p className="text-[10px] text-amber-600">
                {status.missing_packages.length}{' '}
                {tl(TRANSLATIONS.app.envStatus.packagesMissing)}
              </p>
            )}
        </div>
      </aside>

      {/* Main content — all pages stay mounted so background tasks keep running */}
      <main className="flex-1 overflow-y-auto px-8 py-6">
        <div className={activeView === 'convert' ? '' : 'hidden'}>
          <ConvertPage
            envStatus={status}
            onViewChange={handleViewChange}
            conversion={conversion}
          />
        </div>
        <div className={activeView === 'nbt-export' ? '' : 'hidden'}>
          <NbtExportPage />
        </div>
        <div className={activeView === 'settings' ? '' : 'hidden'}>
          <SettingsPage
            envStatus={status}
            onEnvUpdate={() => recheck()}
          />
        </div>
      </main>

      {/* Environment setup modal */}
      {showEnvModal && status && !status.all_ready && (
        <EnvSetupModal
          status={status}
          onClose={handleEnvClose}
          onStatusChange={handleEnvStatusChange}
        />
      )}
    </div>
  );
}

export default function App() {
  return (
    <LanguageProvider>
      <AppShell />
    </LanguageProvider>
  );
}
