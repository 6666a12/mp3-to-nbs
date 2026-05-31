import { useLanguage } from '@/i18n/LanguageContext';
import { TRANSLATIONS } from '@/i18n/translations';
import { Label } from '@/components/ui/label';
import {
  Card, CardHeader, CardTitle, CardDescription, CardContent,
} from '@/components/ui/card';
import type { ConversionOptions } from '@/types/conversion';
import type { TranslationLeaf } from '@/i18n/translations';
import { QUALITY_OPTIONS } from '@/types/conversion';

interface ConversionOptionsProps {
  options: ConversionOptions;
  onChange: (partial: Partial<ConversionOptions>) => void;
  disabled?: boolean;
}

export function ConversionOptionsPanel({
  options, onChange, disabled = false,
}: ConversionOptionsProps) {
  const { tl } = useLanguage();

  const qualityDescriptions: Record<string, { label: TranslationLeaf; desc: TranslationLeaf }> = {
    fast: { label: TRANSLATIONS.options.quality.fast.label, desc: TRANSLATIONS.options.quality.fast.desc },
    balanced: { label: TRANSLATIONS.options.quality.balanced.label, desc: TRANSLATIONS.options.quality.balanced.desc },
    high: { label: TRANSLATIONS.options.quality.high.label, desc: TRANSLATIONS.options.quality.high.desc },
  };

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

        {/* Quality selector */}
        <div className="space-y-2">
          <Label className="text-sm">{tl(TRANSLATIONS.options.quality.label)}</Label>
          <div className="flex gap-2">
            {QUALITY_OPTIONS.map((q) => (
              <button
                key={q.value}
                type="button"
                disabled={disabled}
                onClick={() => onChange({ quality: q.value })}
                className={`
                  flex-1 rounded-md border px-3 py-1.5 text-sm font-medium
                  transition-colors focus-visible:outline-none focus-visible:ring-2
                  focus-visible:ring-ring disabled:opacity-50
                  ${options.quality === q.value
                    ? 'border-primary bg-primary text-primary-foreground'
                    : 'border-input hover:bg-accent hover:text-accent-foreground'}
                `}
              >
                {tl(qualityDescriptions[q.value].label)}
              </button>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">
            {tl(qualityDescriptions[options.quality].desc)}
          </p>
        </div>

      </CardContent>
    </Card>
  );
}
