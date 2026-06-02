import { useLanguage } from '@/i18n/LanguageContext';
import { TRANSLATIONS } from '@/i18n/translations';
import { Label } from '@/components/ui/label';
import {
  Card, CardHeader, CardTitle, CardDescription, CardContent,
} from '@/components/ui/card';
import type { ConversionOptions } from '@/types/conversion';

interface ConversionOptionsProps {
  options: ConversionOptions;
  onChange: (partial: Partial<ConversionOptions>) => void;
  disabled?: boolean;
}

export function ConversionOptionsPanel({
  options, onChange, disabled = false,
}: ConversionOptionsProps) {
  const { tl } = useLanguage();

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">{tl(TRANSLATIONS.options.title)}</CardTitle>
        <CardDescription>{tl(TRANSLATIONS.options.description)}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* Source Separation toggle */}
        <div className="flex items-center justify-between">
          <div className="space-y-0.5">
            <Label className="text-sm">{tl(TRANSLATIONS.options.sourceSeparation.label)}</Label>
            <p className="text-xs text-muted-foreground">
              {tl(TRANSLATIONS.options.sourceSeparation.description)}
            </p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={options.sourceSeparation}
            disabled={disabled}
            onClick={() => onChange({ sourceSeparation: !options.sourceSeparation })}
            className={`
              relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center
              rounded-full border-2 border-transparent transition-colors
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring
              focus-visible:ring-offset-2 disabled:opacity-50
              ${options.sourceSeparation ? 'bg-primary' : 'bg-muted-foreground/30'}
            `}
          >
            <span className={`
              pointer-events-none block h-3.5 w-3.5 rounded-full bg-white shadow-lg
              ring-0 transition-transform
              ${options.sourceSeparation ? 'translate-x-4' : 'translate-x-0.5'}
            `} />
          </button>
        </div>

        {/* GPU Acceleration toggle — only relevant when source separation is on */}
        {options.sourceSeparation && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label className="text-sm">{tl(TRANSLATIONS.options.gpu.label)}</Label>
                <p className="text-xs text-muted-foreground">
                  {tl(TRANSLATIONS.options.gpu.description)}
                </p>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={options.useGpu}
                disabled={disabled}
                onClick={() => onChange({ useGpu: !options.useGpu })}
                className={`
                  relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center
                  rounded-full border-2 border-transparent transition-colors
                  focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring
                  focus-visible:ring-offset-2 disabled:opacity-50
                  ${options.useGpu ? 'bg-primary' : 'bg-muted-foreground/30'}
                `}
              >
                <span className={`
                  pointer-events-none block h-3.5 w-3.5 rounded-full bg-white shadow-lg
                  ring-0 transition-transform
                  ${options.useGpu ? 'translate-x-4' : 'translate-x-0.5'}
                `} />
              </button>
            </div>
            {options.useGpu && (
              <p className="text-xs text-amber-600 dark:text-amber-400 border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-950 rounded-md px-2.5 py-1.5">
                {tl(TRANSLATIONS.options.gpu.warning)}
              </p>
            )}
          </div>
        )}

      </CardContent>
    </Card>
  );
}
