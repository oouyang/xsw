// src/composables/useTextConversion.ts
/**
 * Composable for automatic TW to CN text conversion based on current locale
 *
 * IMPORTANT: Source data from web API is in Traditional Chinese (TW)
 * - zh-TW users: Show original TW text (no conversion)
 * - zh-CN users: Convert TW → CN (Simplified)
 * - en-US users: Show original TW text (no conversion)
 */
import { computed, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { convertTWtoCNSync } from 'src/services/utils';

export function useTextConversion() {
  const { locale } = useI18n();

  /**
   * Convert text to Simplified Chinese if current locale is zh-CN
   * Otherwise return original Traditional Chinese text
   *
   * @param text - Text to potentially convert (Traditional Chinese from API)
   * @returns Converted text if locale is zh-CN, otherwise original TW text
   */
  function convertIfNeeded(text: string | null | undefined): string {
    if (!text) return '';

    // Only convert to Simplified Chinese when viewing in zh-CN
    if (locale.value === 'zh-CN') {
      return convertTWtoCNSync(text);
    }

    // For zh-TW and en-US, return original Traditional Chinese text
    return text;
  }

  /**
   * Create a reactive computed property that auto-converts text based on locale
   * Updates automatically when locale changes
   *
   * @param textRef - Ref containing the text to convert
   * @returns Computed property with converted text
   *
   * @example
   * const bookName = ref('繁體中文書名'); // Original TW from API
   * const displayName = useAutoConvert(bookName);
   * // When locale = 'zh-TW': displayName.value = '繁體中文書名' (original)
   * // When locale = 'zh-CN': displayName.value = '繁体中文书名' (converted)
   * // When locale = 'en-US': displayName.value = '繁體中文書名' (original)
   */
  function useAutoConvert(textRef: { value: string | null | undefined }) {
    return computed(() => convertIfNeeded(textRef.value));
  }

  /**
   * Create a reactive ref that converts text and updates when locale changes
   *
   * @param initialText - Initial text value (Traditional Chinese)
   * @returns Ref that automatically updates when locale or text changes
   */
  function createConvertedRef(initialText: string) {
    const converted = ref(convertIfNeeded(initialText));

    // Watch locale changes and reconvert
    watch(locale, () => {
      converted.value = convertIfNeeded(initialText);
    });

    return converted;
  }

  return {
    convertIfNeeded,
    useAutoConvert,
    createConvertedRef,
  };
}
