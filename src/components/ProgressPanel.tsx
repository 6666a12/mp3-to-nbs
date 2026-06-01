import { useEffect, useRef } from 'react';
import { Check, CheckCircle2, Loader2, Circle, Terminal } from 'lucide-react';
import { Progress } from '@/components/ui/progress';
import { Card, CardContent } from '@/components/ui/card';
import { useLanguage } from '@/i18n/LanguageContext';
import { TRANSLATIONS } from '@/i18n/translations';
import { cn } from '@/lib/utils';
import type { ProgressUpdate } from '@/types/conversion';
import type { LogEntry } from '@/hooks/useConversion';

interface ProgressPanelProps {
  progress: ProgressUpdate | null;
  logLines: LogEntry[];
}

/** Pipeline step keys in display order, matching converter.py */
const STEP_KEYS = [
  'loading',
  'source_separation',
  'beat_tracking',
  'pitch_detection',
  'generating_nbs',
  'complete',
] as const;

export function ProgressPanel({ progress, logLines }: ProgressPanelProps) {
  const { tl } = useLanguage();
  const logEndRef = useRef<HTMLDivElement>(null);
  const currentStep = progress?.step ?? '';
  const pct = progress ? Math.round(progress.progress * 100) : 0;
  const currentStepIndex = STEP_KEYS.indexOf(currentStep as typeof STEP_KEYS[number]);

  // Auto-scroll log to bottom when new lines arrive.
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logLines]);

  return (
    <Card>
      <CardContent className="pt-6">
        <div className="space-y-4">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              {currentStep === 'complete' ? (
                <CheckCircle2 className="h-4 w-4 text-green-600" />
              ) : (
                <Loader2 className="h-4 w-4 animate-spin text-primary" />
              )}
              <span className="text-sm font-medium">
                {currentStep === 'complete'
                  ? tl(TRANSLATIONS.progress.steps.complete)
                  : tl(TRANSLATIONS.progress.converting)}
              </span>
            </div>
            <span className="text-sm text-muted-foreground font-mono">{pct}%</span>
          </div>

          {/* Progress bar */}
          <Progress value={pct} className="h-2.5" />

          {/* Steps list */}
          <div className="space-y-1.5 pt-2">
            {STEP_KEYS.map((key, index) => {
              const isCompleted = index < currentStepIndex;
              const isActive = index === currentStepIndex;
              const isPending = index > currentStepIndex;
              const label = tl(TRANSLATIONS.progress.steps[key]);

              return (
                <div
                  key={key}
                  className={cn(
                    'flex items-center gap-3 px-2 py-1.5 rounded text-sm transition-colors',
                    isActive && 'bg-primary/5 text-primary font-medium',
                    isCompleted && 'text-muted-foreground',
                    isPending && 'text-muted-foreground/50'
                  )}
                >
                  {isCompleted || (isActive && key === 'complete') ? (
                    <Check className="h-4 w-4 text-green-500 shrink-0" />
                  ) : isActive ? (
                    <Loader2 className="h-4 w-4 animate-spin text-primary shrink-0" />
                  ) : (
                    <Circle className="h-4 w-4 text-muted-foreground/40 shrink-0" />
                  )}
                  <span>{label}</span>
                </div>
              );
            })}
          </div>

          {/* Scrollable log area */}
          {logLines.length > 0 && (
            <div className="pt-2">
              <div className="flex items-center gap-1.5 mb-1.5">
                <Terminal className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-xs text-muted-foreground font-medium">
                  {tl(TRANSLATIONS.progress.log)}
                </span>
              </div>
              <div className="rounded-md border bg-muted/30 p-3 max-h-48 overflow-y-auto font-mono text-xs leading-relaxed">
                {logLines.map((entry, i) => (
                  <div key={i} className="flex gap-2">
                    <span className="text-muted-foreground shrink-0 select-none">
                      [{entry.time}]
                    </span>
                    <span>{entry.text}</span>
                  </div>
                ))}
                <div ref={logEndRef} />
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
