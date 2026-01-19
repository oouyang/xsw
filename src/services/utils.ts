import { useAppConfig } from 'src/services/useAppConfig';
import { Dialog, Dark, type QDialogOptions } from 'quasar';

export function is_production() {
  return process.env.NODE_ENV === 'production';
}

const { update, config } = useAppConfig();
export function toggleAppFeatures(key: string) {
  update({ featureFlags: { [key]: !config.value.featureFlags[key] } });
}

export function getCurrentUser() {
  const me = JSON.parse(config.value?.me || '{"name":"unknown"}');
  return me && typeof me.name === 'string' ? me.name : 'unknown';
}
export function alog(...args: unknown[]): void {
  const timestamp = `[${new Date().toLocaleString()}] :`;
  console.log(timestamp, ...args);
}

type ScrollPos =
  | 'top'
  | 'bottom'
  | 'left'
  | 'right'
  | 'topleft'
  | 'topright'
  | 'bottomleft'
  | 'bottomright'
  | 'center';

interface ScrollToOptionsEx {
  behavior?: ScrollBehavior; // 'auto' | 'smooth'
  offsetX?: number; // 目標 X 方向額外位移（正=向右）
  offsetY?: number; // 目標 Y 方向額外位移（正=向下）
}
export function showDialog(opts: QDialogOptions) {
  return Dialog.create(opts);
}

export function toggleDark() {
  Dark.toggle();
  update({ dark: `${Dark.isActive}` });
}

export function setDark(val: boolean | 'auto') {
  Dark.set(val);
  update({ dark: `${Dark.isActive}` });
}

export function isDarkActive() {
  return Dark.isActive;
}

export function chapterLink(num: number, title: string) {
  return {
    name: 'Chapter',
    params: { bookId: config.value.bookId, chapterNum: Number(num), chapterTitle: title },
  };
}

export function scrollToWindow(pos: string, opts: ScrollToOptionsEx = {}) {
  const p = (pos || '').replace(/\s+/g, '').toLowerCase() as ScrollPos;
  const { behavior = 'smooth', offsetX = 0, offsetY = 0 } = opts;

  // 取得頁面可視大小與可滾動範圍
  const docEl = document.documentElement;
  const body = document.body;

  // 內容總寬高（包含可滾動區域）
  const fullWidth = Math.max(
    body.scrollWidth,
    docEl.scrollWidth,
    body.offsetWidth,
    docEl.offsetWidth,
    body.clientWidth,
    docEl.clientWidth,
  );
  const fullHeight = Math.max(
    body.scrollHeight,
    docEl.scrollHeight,
    body.offsetHeight,
    docEl.offsetHeight,
    body.clientHeight,
    docEl.clientHeight,
  );

  // 畫面可視區域
  const viewW = window.innerWidth || docEl.clientWidth;
  const viewH = window.innerHeight || docEl.clientHeight;

  // 目標座標預設為目前位置
  let x = window.scrollX || window.pageXOffset || 0;
  let y = window.scrollY || window.pageYOffset || 0;

  // 計算各方位的目標座標
  const edge = {
    left: 0,
    right: Math.max(0, fullWidth - viewW),
    top: 0,
    bottom: Math.max(0, fullHeight - viewH),
    centerX: Math.max(0, Math.round((fullWidth - viewW) / 2)),
    centerY: Math.max(0, Math.round((fullHeight - viewH) / 2)),
  };

  switch (p) {
    case 'top':
      y = edge.top;
      break;

    case 'bottom':
      y = edge.bottom;
      break;

    case 'left':
      x = edge.left;
      break;

    case 'right':
      x = edge.right;
      break;

    case 'topleft':
      x = edge.left;
      y = edge.top;
      break;

    case 'topright':
      x = edge.right;
      y = edge.top;
      break;

    case 'bottomleft':
      x = edge.left;
      y = edge.bottom;
      break;

    case 'bottomright':
      x = edge.right;
      y = edge.bottom;
      break;
  }

  // 套用額外位移（可用於微調）
  x = Math.max(0, x + offsetX);
  y = Math.max(0, y + offsetY);

  window.scrollTo({ left: x, top: y, behavior });
  // 可選：除錯訊息
  // console.log(`scroll to ${p}: (${x}, ${y})`)
}

export function toArr<T>(x: T | T[] | null | undefined): T[] {
  if (!x) return [];
  return Array.isArray(x) ? x : [x];
}
export function dedupeBy<T, K extends PropertyKey>(arr: T[], keyFn: (x: T) => K): T[] {
  const seen = new Set<K>();
  const out: T[] = [];
  for (const item of arr) {
    const k = keyFn(item);
    if (!seen.has(k)) {
      seen.add(k);
      out.push(item);
    }
  }
  return out;
}
export function normalizeNum(x: string | number) {
  return String(x);
}

// ===== Chinese Character Conversion =====

/**
 * Lazy-loaded OpenCC converter instance
 * Only initialized when needed to avoid loading the library unnecessarily
 */
let converterInstance: ((text: string) => string) | null = null;

/**
 * Initialize the OpenCC converter (Traditional to Simplified Chinese)
 * Uses lazy loading to improve initial load performance
 */
async function initConverter() {
  if (converterInstance) return converterInstance;

  try {
    // Dynamic import to avoid loading opencc-js unless needed
    const OpenCC = await import('opencc-js');
    // tw2cn = Traditional Chinese (Taiwan) to Simplified Chinese (China)
    converterInstance = OpenCC.Converter({ from: 'tw', to: 'cn' });
    return converterInstance;
  } catch (error) {
    console.error('[Utils] Failed to initialize OpenCC converter:', error);
    // Fallback: return identity function if conversion fails
    converterInstance = (text: string) => text;
    return converterInstance;
  }
}

/**
 * Convert Traditional Chinese (TW) text to Simplified Chinese (CN)
 * Uses OpenCC (Open Chinese Convert) for accurate conversion
 *
 * NOTE: Source data from web is already in Traditional Chinese (TW)
 * This function converts to Simplified Chinese for zh-CN users
 *
 * @param text - Text to convert (Traditional Chinese from API)
 * @returns Converted text (Simplified Chinese, or original if conversion failed)
 *
 * @example
 * convertTWtoCN('繁體中文') // Returns: '繁体中文'
 * convertTWtoCN('Hello 世界') // Returns: 'Hello 世界' (preserves non-Chinese)
 * convertTWtoCN('簡體中文') // Returns: '简体中文'
 */
export async function convertTWtoCN(text: string | null | undefined): Promise<string> {
  // Handle null/undefined
  if (!text) return '';

  try {
    const converter = await initConverter();
    if (!converter) {
      console.warn('[Utils] Converter not initialized');
      return text;
    }
    return converter(text);
  } catch (error) {
    console.error('[Utils] Error during TW to CN conversion:', error);
    return text; // Return original text if conversion fails
  }
}

/**
 * Synchronous version of convertTWtoCN for use in computed properties
 * NOTE: May return original text on first call if converter not yet loaded
 * For guaranteed conversion, use the async version
 */
export function convertTWtoCNSync(text: string | null | undefined): string {
  if (!text) return '';

  // Check if converter is already initialized
  if (!converterInstance) {
    // Trigger initialization for next time (non-blocking)
    void initConverter();
    // Return original text for now
    return text;
  }

  try {
    return converterInstance(text);
  } catch (error) {
    console.error('[Utils] Error during sync TW to CN conversion:', error);
    return text;
  }
}

// ===== Book Info Sync =====

/**
 * Sync book info's last chapter with actual last chapter from chapter list
 * Always trusts the chapter list as the source of truth
 * Updates book info if it differs from the actual last chapter
 *
 * ⚠️ IMPORTANT: Only call this with chapters from the LAST PAGE or with ALL chapters
 * Do NOT call with arbitrary page chapters (e.g., page 1 of 100) or it will incorrectly
 * set the last chapter to the last chapter of that page!
 *
 * @param bookInfo - Current book info (may be outdated or incorrect)
 * @param chapters - Array of chapters from LAST PAGE or ALL chapters (source of truth)
 * @returns Updated book info with synced last chapter
 *
 * @example
 * // ✅ CORRECT: Syncing with last page
 * const lastPageChapters = await getBookChapters(bookId, { page: maxPages });
 * info.value = syncLastChapter(info.value, lastPageChapters);
 *
 * @example
 * // ✅ CORRECT: Syncing with all chapters
 * const allChapters = getAllChaptersFromCache();
 * info.value = syncLastChapter(info.value, allChapters);
 *
 * @example
 * // ❌ WRONG: Syncing with page 1 (will set last chapter to chapter 20!)
 * const page1Chapters = await getBookChapters(bookId, { page: 1 });
 * info.value = syncLastChapter(info.value, page1Chapters); // DON'T DO THIS!
 */
export function syncLastChapter<T extends { last_chapter_number?: number | null; last_chapter_title?: string; last_chapter_url?: string }>(
  bookInfo: T,
  chapters: Array<{ number: number; title: string; url: string }>
): T {
  if (!chapters || chapters.length === 0) {
    return bookInfo;
  }

  // Find the actual last chapter (highest number) - this is the source of truth
  const actualLastChapter = chapters.reduce<{ number: number; title: string; url: string }>((max, chapter) => {
    return chapter.number > max.number ? chapter : max;
  }, chapters[0]!);

  // Check if book info differs from actual chapter list
  const currentLastChapterNum = bookInfo.last_chapter_number ?? 0;
  if (actualLastChapter && actualLastChapter.number !== currentLastChapterNum) {
    const direction = actualLastChapter.number > currentLastChapterNum ? '↑' : '↓';
    console.log(
      `[syncLastChapter] ${direction} Syncing last chapter: ${currentLastChapterNum} → ${actualLastChapter.number}`
    );

    return {
      ...bookInfo,
      last_chapter_number: actualLastChapter.number,
      last_chapter_title: actualLastChapter.title,
      last_chapter_url: actualLastChapter.url,
    };
  }

  return bookInfo;
}
