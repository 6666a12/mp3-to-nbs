import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from 'react';
import type { Language } from './types';
import { t, type TranslationLeaf } from './translations';

// =============================================================================
// Storage
// =============================================================================

const STORAGE_KEY = 'mp3-to-nbs-language';

function loadLanguage(): Language {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'zh' || stored === 'en') return stored;
  } catch { /* localStorage not available */ }
  // Default to browser language, fallback to English
  if (typeof navigator !== 'undefined') {
    const nav = navigator.language.toLowerCase();
    if (nav.startsWith('zh')) return 'zh';
  }
  return 'en';
}

function saveLanguage(lang: Language): void {
  try {
    localStorage.setItem(STORAGE_KEY, lang);
  } catch { /* ignore */ }
}

// =============================================================================
// Context
// =============================================================================

interface LanguageContextValue {
  lang: Language;
  setLang: (lang: Language) => void;
  toggleLang: () => void;
  /** Direct translation accessor (for use with TranslationLeaf objects) */
  tl: (leaf: TranslationLeaf) => string;
}

const LanguageContext = createContext<LanguageContextValue | null>(null);

// =============================================================================
// Provider
// =============================================================================

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Language>(loadLanguage);

  const setLang = useCallback((next: Language) => {
    setLangState(next);
    saveLanguage(next);
  }, []);

  const toggleLang = useCallback(() => {
    setLangState((prev) => {
      const next = prev === 'zh' ? 'en' : 'zh';
      saveLanguage(next);
      return next;
    });
  }, []);

  /** Resolve a TranslationLeaf to a string for the current language */
  const tl = useCallback(
    (leaf: TranslationLeaf): string => leaf[lang],
    [lang],
  );

  return (
    <LanguageContext.Provider value={{ lang, setLang, toggleLang, tl }}>
      {children}
    </LanguageContext.Provider>
  );
}

// =============================================================================
// Hook
// =============================================================================

export function useLanguage(): LanguageContextValue {
  const ctx = useContext(LanguageContext);
  if (!ctx) {
    throw new Error('useLanguage must be used within a <LanguageProvider>');
  }
  return ctx;
}
