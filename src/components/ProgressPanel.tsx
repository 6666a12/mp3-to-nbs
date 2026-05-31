import { Check, CheckCircle2, Loader2, Circle } from 'lucide-react';
import { Progress } from '@/components/ui/progress';
import { Card, CardContent } from '@/components/ui/card';
import { useLanguage } from '@/i18n/LanguageContext';
import { TRANSLATIONS } from '@/i18n/translations';
import { cn } from '@/lib/utils';
import type { ProgressUpdate } from '@/types/conversion';

interface ProgressPanelProps {
  progress: ProgressUpdate | null;
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

export function ProgressPanel({ progress }: ProgressPanelProps) {
  const { tl } = useLanguage();
  const currentStep = progress?.step ?? '';
  const pct = progress ? Math.round(progress.progress * 100) : 0;
  const currentStepIndex = STEP_KEYS.indexOf(currentStep as typeof STEP_KEYS[number]);

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

          {/* Current step message */}
          {progress?.message && (
            <p className="text-xs text-muted-foreground">{progress.message}</p>
          )}

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
        </div>
      </CardContent>
    </Card>
  );
}
