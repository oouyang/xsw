import { defineBoot } from '#q-app/wrappers';
import { createI18n } from 'vue-i18n';

import messages from 'src/i18n';

export type MessageLanguages = keyof typeof messages;
// Type-define 'en-US' as the master schema for the resource
export type MessageSchema = (typeof messages)['en-US'];

// See https://vue-i18n.intlify.dev/guide/advanced/typescript.html#global-resource-schema-type-definition
/* eslint-disable @typescript-eslint/no-empty-object-type */
declare module 'vue-i18n' {
  // define the locale messages schema
  export interface DefineLocaleMessage extends MessageSchema {}

  // define the datetime format schema
  export interface DefineDateTimeFormat {}

  // define the number format schema
  export interface DefineNumberFormat {}
}
/* eslint-enable @typescript-eslint/no-empty-object-type */

const LOCALE_STORAGE_KEY = 'app.locale';
const DEFAULT_LOCALE: MessageLanguages = 'zh-TW'; // Default to Traditional Chinese
const AVAILABLE_LOCALES: MessageLanguages[] = ['en-US', 'zh-TW', 'zh-CN'];

/**
 * Get the stored locale from localStorage
 */
function getStoredLocale(): MessageLanguages | null {
  if (typeof window === 'undefined' || !window.localStorage) return null;

  try {
    const stored = window.localStorage.getItem(LOCALE_STORAGE_KEY);
    if (stored && AVAILABLE_LOCALES.includes(stored as MessageLanguages)) {
      return stored as MessageLanguages;
    }
  } catch {
    // localStorage access failed
  }
  return null;
}

/**
 * Store locale preference in localStorage
 */
function storeLocale(locale: MessageLanguages): void {
  if (typeof window === 'undefined' || !window.localStorage) return;

  try {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  } catch {
    // localStorage access failed
  }
}

/**
 * Detect browser language and map to available locales
 */
function detectBrowserLocale(): MessageLanguages {
  if (typeof navigator === 'undefined') return DEFAULT_LOCALE;

  // Support legacy IE userLanguage property
  const navigatorWithLegacy = navigator as Navigator & { userLanguage?: string };
  const browserLang = navigator.language || navigatorWithLegacy.userLanguage || 'en-US';

  // Map browser locales to available locales
  if (browserLang.startsWith('zh')) {
    // Chinese variants mapping
    if (browserLang.includes('TW') || browserLang.includes('HK') || browserLang.includes('Hant')) {
      return 'zh-TW'; // Traditional Chinese (Taiwan, Hong Kong)
    }
    if (browserLang.includes('CN') || browserLang.includes('Hans')) {
      return 'zh-CN'; // Simplified Chinese (China)
    }
    // Default to Traditional Chinese for unspecified Chinese
    return 'zh-TW';
  }

  if (browserLang.startsWith('en')) {
    return 'en-US';
  }

  return DEFAULT_LOCALE;
}

/**
 * Get the initial locale to use
 * Priority: stored > browser detection > default
 */
function getInitialLocale(): MessageLanguages {
  const stored = getStoredLocale();
  if (stored) return stored;

  return detectBrowserLocale();
}

export default defineBoot(({ app }) => {
  const initialLocale = getInitialLocale();

  const i18n = createI18n<{ message: MessageSchema }, MessageLanguages>({
    locale: initialLocale,
    fallbackLocale: DEFAULT_LOCALE,
    legacy: false,
    messages,
    globalInjection: true, // Enable $t, $tc, $te, etc. in templates
    missingWarn: false, // Disable warnings for missing translations in production
    fallbackWarn: false,
  });

  // Set i18n instance on app
  app.use(i18n);

  console.log('[i18n] Initialized with locale:', initialLocale);
});

/**
 * Composable for locale switching
 */
export function useLocale() {
  return {
    availableLocales: AVAILABLE_LOCALES,
    defaultLocale: DEFAULT_LOCALE,
    storeLocale,
    getStoredLocale,
  };
}
