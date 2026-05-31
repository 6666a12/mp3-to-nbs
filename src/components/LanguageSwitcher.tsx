import { useLanguage } from '@/i18n/LanguageContext';
import { LANGUAGES } from '@/i18n/translations';

export function LanguageSwitcher() {
  const { lang, setLang } = useLanguage();

  return (
    <div className="flex items-center gap-1">
      {LANGUAGES.map((l) => (
        <button
          key={l.code}
          onClick={() => setLang(l.code)}
          className={`
            rounded px-2 py-0.5 text-xs font-medium transition-colors
            ${
              lang === l.code
                ? 'bg-primary/10 text-primary'
                : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
            }
          `}
          title={l.englishName}
        >
          {l.nativeName}
        </button>
      ))}
    </div>
  );
}
