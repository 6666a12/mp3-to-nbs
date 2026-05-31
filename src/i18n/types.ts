/** Supported languages */
export type Language = 'zh' | 'en';

/** Language metadata */
export interface LanguageMeta {
  code: Language;
  nativeName: string;
  englishName: string;
}
