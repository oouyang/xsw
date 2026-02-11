<!-- src/pages/ChapterPage.vue -->
<template>
  <q-page class="q-px-xs q-pt-sm q-pb-md">
    <q-banner v-if="error" class="bg-red-2 text-red-10 q-mb-md">
      <div class="row items-center">
        <div class="col">{{ error }}</div>
        <q-btn flat color="red-10" :label="$t('common.retry')" icon="refresh" @click="load" />
      </div>
    </q-banner>

    <q-card>
      <q-card-section class="bg-primary text-white">
        <div class="row items-center">
          <div class="col">
            <div class="text-h6">{{ displayChapterTitle || displayTitle }}</div>
          </div>
          <div class="col-auto">
            <div class="column items-end q-gutter-xs">
              <q-chip dense size="sm" :color="loading ? 'grey-7' : 'white'" :text-color="loading ? 'white' : 'primary'">
                {{ loading ? $t('common.loading') : `${content.length} 段` }}
              </q-chip>
              <q-chip v-if="!loading && estimatedReadingTimeText" dense size="sm" color="white" text-color="primary" icon="schedule">
                {{ estimatedReadingTimeText }}
              </q-chip>
            </div>
          </div>
        </div>
      </q-card-section>

      <q-separator />

      <!-- Top Navigation -->
      <q-card-section class="q-py-sm">
        <div class="row q-gutter-sm justify-center">
          <q-btn
            outline
            color="primary"
            size="sm"
            :disable="!book.prevChapter"
            :to="book.prevChapter ? chapterLink(book.prevChapter.id ?? String(book.prevChapter.number), book.prevChapter.title) : undefined"
            icon="chevron_left"
            :label="$t('nav.prevChapter')"
          >
            <q-tooltip v-if="book.prevChapter">{{ book.prevChapter.title }}</q-tooltip>
          </q-btn>
          <q-btn
            outline
            color="secondary"
            size="sm"
            :to="`/book/${props.bookId}/chapters`"
            icon="list"
            :label="$t('nav.chapterList')"
          >
            <q-tooltip>{{ $t('nav.backToChapterList') }}</q-tooltip>
          </q-btn>
          <q-btn
            outline
            color="primary"
            size="sm"
            :disable="!book.nextChapter"
            :to="book.nextChapter ? chapterLink(book.nextChapter.id ?? String(book.nextChapter.number), book.nextChapter.title) : undefined"
            icon-right="chevron_right"
            :label="$t('nav.nextChapter')"
          >
            <q-tooltip v-if="book.nextChapter">{{ book.nextChapter.title }}</q-tooltip>
          </q-btn>
        </div>
      </q-card-section>

      <q-separator />

      <q-card-section class="q-px-sm">
        <div v-if="loading" class="q-pa-lg">
          <q-skeleton type="text" v-for="i in 8" :key="i" class="q-mb-md" />
        </div>
        <div
          v-else
          class="q-pb-lg chapter-content"
          :class="`text-h${fontsize}`"
          style="white-space: pre-wrap"
        >
          <p v-for="(value, index) in displayContent" :key="index">{{ value }}</p>
        </div>
      </q-card-section>
    </q-card>

    <!-- Keyboard Navigation Instructions -->
    <div class="q-my-md text-center text-caption text-grey-7">
      <q-icon name="keyboard" size="xs" class="q-mr-xs" />
      {{ $t('chapter.keyboardHint') }}
    </div>

    <!-- Bottom Navigation -->
    <div class="row q-my-md q-gutter-sm justify-center">
      <q-btn
        outline
        color="primary"
        :disable="!book.prevChapter"
        :to="book.prevChapter ? chapterLink(book.prevChapter.id ?? String(book.prevChapter.number), book.prevChapter.title) : undefined"
        icon="chevron_left"
        :label="$t('nav.prevChapter')"
      >
        <q-tooltip v-if="book.prevChapter">{{ book.prevChapter.title }}</q-tooltip>
      </q-btn>
      <q-btn
        outline
        color="secondary"
        :to="`/book/${props.bookId}/chapters`"
        icon="list"
        :label="$t('nav.chapterList')"
      >
        <q-tooltip>{{ $t('nav.backToChapterList') }}</q-tooltip>
      </q-btn>
      <q-btn
        outline
        color="primary"
        :disable="!book.nextChapter"
        :to="book.nextChapter ? chapterLink(book.nextChapter.id ?? String(book.nextChapter.number), book.nextChapter.title) : undefined"
        icon-right="chevron_right"
        :label="$t('nav.nextChapter')"
      >
        <q-tooltip v-if="book.nextChapter">{{ book.nextChapter.title }}</q-tooltip>
      </q-btn>
    </div>

    <!-- Progress indicator -->
    <div v-if="book.info?.last_chapter_number && currentChapterNum > 0" class="q-mt-md">
      <q-linear-progress
        :value="currentChapterNum / (book.info.last_chapter_number || 1)"
        color="primary"
        size="8px"
        rounded
      />
      <div class="text-caption text-center text-grey-7 q-mt-xs">
        {{ $t('chapter.readingProgress') }}: {{ Math.round((currentChapterNum / (book.info.last_chapter_number || 1)) * 100) }}%
      </div>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';
import { getChapterContent } from 'src/services/bookApi';
import { useAppConfig } from 'src/services/useAppConfig';
import { nextTick } from 'process';
import { chapterLink } from 'src/services/utils';
import { useTextConversion } from 'src/composables/useTextConversion';
import { useBookStore } from 'src/stores/books';

const { t } = useI18n();
const { config, update } = useAppConfig();
const fontsize = computed(() => Number(config.value.fontsize) || 7)
const { convertIfNeeded } = useTextConversion();
const router = useRouter();

const props = defineProps<{ bookId: string; chapterId: string; chapterTitle?: string }>();
const title = ref('');
const content = ref<Array<string>>([]);
const loading = ref(false);
const error = ref('');

const book = useBookStore();

// Resolve the current chapter's sequential number from the store
const currentChapterNum = computed(() => {
  const ch = book.findChapterById(props.chapterId);
  return ch?.number ?? 0;
});
// const chapterIndex = computed(() => {
//   const index = chapters.value.findIndex(
//     c => c.number === chapterNum && c.title === chapterTitle
//   )
//   return index === -1 ? 0 : index
// })
// const navPrev = computed(() => {
//   const index = Math.max(0, chapterIndex.value - 1);
//   return chapterLink(chapters.value[index]?.number || 1, chapters.value[index]?.title || '')
// });
// const navNext = computed(() => {
//   const index = Math.min(chapterIndex.value + 1, chapters.value.length + 1);
//   return chapterLink(chapters.value[index]?.number || 1, chapters.value[index]?.title || '')
// });

// const chapters = computed<ChapterRef[]>(() => 
// {
//   const raw = config.value?.chapters ?? '[]'
//   try {
//     return JSON.parse(raw) as ChapterRef[]
//   } catch {
//     return []
//   }
// })
// async function loadAllChapters() {
//   try {
//     const storedchapters = JSON.parse(config.value.chapters||'[]')

//     // Check if cache is outdated by comparing with expected last chapter
//     const cachedLastChapter = storedchapters.length > 0
//       ? storedchapters.reduce((max: number, ch: ChapterRef) => ch.number > max ? ch.number : max, 0)
//       : 0;
//     const expectedLastChapter = lastChapterNum.value || 0;
//     const isCacheOutdated = cachedLastChapter < expectedLastChapter;

//     // Re-fetch if: bookId changed, no cache, OR cache is outdated/incomplete
//     if (props.bookId !== config.value.bookId || storedchapters.length === 0 || isCacheOutdated) {
//       if (isCacheOutdated) {
//         console.log(
//           `[loadAllChapters] Cache outdated (has ${cachedLastChapter}, expected ${expectedLastChapter}), re-fetching all chapters`
//         );
//       }

//       const requests = []
//       for (let i = 0; i < pages.value; i++) {
//         requests.push(
//           getBookChapters(props.bookId, { page: i+1, all: false })
//         )
//       }
//       const results = await Promise.all(requests)

//       // 假設每頁回傳 resp.data 或 resp.chapters（依你的 API 命名調整）

//       update({bookId: props.bookId});
//       update({chapters: JSON.stringify(results.flatMap(r => r))});
//       update({chapter: JSON.stringify(chapters.value[chapterIndex.value])});
//       // update({chapter: JSON.stringify(chapters.value[chapterIndex.value])});

//       console.log(`[loadAllChapters] Fetched ${results.flatMap(r => r).length} chapters across ${pages.value} pages`);
//     } else {
//       console.log(`[loadAllChapters] Using cached chapters (${storedchapters.length} chapters, last: ${cachedLastChapter})`);
//     }

//     // Sync last chapter info with loaded chapters
//     if (info.value && chapters.value.length > 0) {
//       info.value = syncLastChapter(info.value, chapters.value);
//     }

//     console.log('chapters.value[chapterIndex])', chapters.value[chapterIndex.value], chapterNum);
//   } catch (e) {
//     console.error('Failed to load chapters list:', e);
//     throw e; // Re-throw to let caller handle it
//   }
// }
// const info = ref<BookInfo|undefined>(undefined)
// const pages = ref(1)

// Computed properties for CN to TW conversion
const displayTitle = computed(() => convertIfNeeded(title.value));
const displayChapterTitle = computed(() => convertIfNeeded(props.chapterTitle));
const displayContent = computed(() =>
  content.value.map(paragraph => convertIfNeeded(paragraph))
);

// Estimated reading time calculation
// Average reading speed: 350 Chinese characters per minute
const READING_SPEED_CPM = 350;

const estimatedReadingTimeText = computed(() => {
  if (loading.value || content.value.length === 0) {
    return '';
  }

  // Count total characters in content
  const totalChars = content.value.reduce((sum, paragraph) => sum + paragraph.length, 0);

  // Calculate reading time in minutes
  const totalMinutes = Math.ceil(totalChars / READING_SPEED_CPM);

  if (totalMinutes === 0) {
    return '';
  }

  // Format based on duration
  if (totalMinutes < 60) {
    return t('chapter.readingTimeMinutes', { minutes: totalMinutes });
  } else {
    const hours = Math.floor(totalMinutes / 60);
    const minutes = totalMinutes % 60;
    return t('chapter.readingTimeHoursMinutes', { hours, minutes });
  }
});


async function loadMeta() {
  try {
    const infoMatches = book.info && (book.info.public_id === props.bookId || book.info.book_id === props.bookId);
    if (!infoMatches) {
      await book.loadInfo(props.bookId);
    }
    // lastChapterNum.value = book.info?.last_chapter_number ?? null;
    // Calculate number of pages: divide by page size (20) and round up
    // pages.value = Math.ceil((lastChapterNum?.value || 1) / 20);

    // Load all chapters in background (don't await, just start the process)
    // This will be checked again in load() if needed
    nextTick(() => {
      if (book.allChapters.length === 0) {
        void book.loadAllChapters({
          onProgress: (msg: string) => {
            console.log('[ChapterPage] Background loading progress:', msg);
          }
        });
      }
    });

    // Note: Backend now automatically syncs last chapter when fetching all chapters
  } catch (e) {
    console.log('e', e);
  }
}

function removeTitleWordsFromContent() {
  const tokens = (title.value ?? '')
    .trim()
    .split(/\s+/)
    .slice(0, 2) // 只取前兩字
    .filter(Boolean)

  for (let i = 0; i < 4; i++) {
    const text = content.value[i]
    if (!text) continue

    let cleaned = text

    for (const t of tokens) {
      cleaned = cleaned.replace(t, '')
    }

    content.value[i] = cleaned.trim()
  }
}
// ── Priority queue-based background prefetch worker ────────────
// High priority: next 2 chapters (immediate reading need)
// Low priority:  chapters 3-5 ahead (read-ahead buffer)
// Worker always drains high queue first, so navigating to a new
// chapter immediately prioritises its next 2 over old low-priority items.
const HIGH_PRIORITY_COUNT = 2;
const LOW_PRIORITY_COUNT = 3;
const PREFETCH_DELAY_MS = 2000;

interface PrefetchItem { bookId: string; chapterId: string }
const hiQueue: PrefetchItem[] = [];
const loQueue: PrefetchItem[] = [];
const prefetchDone = new Set<string>(); // "bookId:chapterId" already fetched
let workerActive = false;
let workerBookId = '';

function prefetchKey(bookId: string, chapterId: string) { return `${bookId}:${chapterId}`; }

function isQueued(bookId: string, chapterId: string) {
  return hiQueue.some(q => q.bookId === bookId && q.chapterId === chapterId)
      || loQueue.some(q => q.bookId === bookId && q.chapterId === chapterId);
}

function enqueuePrefetch(bookId: string, currentChapterId: string) {
  // Book changed — flush everything
  if (bookId !== workerBookId) {
    hiQueue.length = 0;
    loQueue.length = 0;
    prefetchDone.clear();
    workerBookId = bookId;
  }

  // Mark current chapter as done (user already loaded it)
  prefetchDone.add(prefetchKey(bookId, currentChapterId));

  // Find current chapter index in allChapters
  const currentIndex = book.allChapters.findIndex(
    c => c.id === currentChapterId || String(c.number) === currentChapterId
  );
  if (currentIndex < 0) return;

  const total = HIGH_PRIORITY_COUNT + LOW_PRIORITY_COUNT;

  for (let i = 1; i <= total; i++) {
    const nextIndex = currentIndex + i;
    if (nextIndex >= book.allChapters.length) break;
    const nextChapter = book.allChapters[nextIndex];
    if (!nextChapter) break;
    const chId = nextChapter.id ?? String(nextChapter.number);
    const key = prefetchKey(bookId, chId);
    if (prefetchDone.has(key) || isQueued(bookId, chId)) continue;

    const item: PrefetchItem = { bookId, chapterId: chId };
    if (i <= HIGH_PRIORITY_COUNT) {
      hiQueue.push(item);
    } else {
      loQueue.push(item);
    }
  }

  if (!workerActive) void runPrefetchWorker();
}

async function runPrefetchWorker() {
  if (workerActive) return;
  workerActive = true;

  // Always prefer high-priority queue; fall back to low
  while (hiQueue.length > 0 || loQueue.length > 0) {
    const item = hiQueue.length > 0 ? hiQueue.shift()! : loQueue.shift()!;
    const key = prefetchKey(item.bookId, item.chapterId);

    if (prefetchDone.has(key)) continue;
    prefetchDone.add(key);

    await new Promise(r => setTimeout(r, PREFETCH_DELAY_MS));

    try {
      await getChapterContent(item.bookId, item.chapterId);
      const tag = hiQueue.length > 0 || loQueue.length > 0 ? '' : ' (queue empty)';
      console.log(`[Prefetch] Cached chapter ${item.chapterId}${tag}`);
    } catch {
      // Best-effort — remove from done so a future enqueue can retry
      prefetchDone.delete(key);
    }
  }

  workerActive = false;
}

async function load() {
  loading.value = true;
  error.value = '';

  try {
    // Ensure metadata is loaded first
    if (!book.info) {
      console.log('Waiting for metadata to load...');
      await loadMeta();
    }

    // Ensure chapters are loaded
    if (book.allChapters.length === 0) {
      console.log('Loading chapters list...');
      await book.loadAllChapters({
        onProgress: (msg: string) => {
          console.log('[ChapterPage] Loading progress:', msg);
        }
      });
      console.log(`[ChapterPage] All chapters loaded: ${book.allChapters.length} chapters`);
      // await loadAllChapters();
    }

    console.log(`Loading chapter ${props.chapterId}: ${props.chapterTitle}`);
    const data = await getChapterContent(props.bookId, props.chapterId);

    if (!data || !data.text) {
      throw new Error('No content returned from API');
    }

    title.value = data.title || props.chapterTitle || '';
    content.value = data.text.split(' ');
    removeTitleWordsFromContent()
    content.value = content.value.filter(Boolean)

    // Set the current chapter in the store for prev/next navigation
    // Try to find the chapter in allChapters by public_id or number
    const matchedChapter = book.findChapterById(props.chapterId);
    if (matchedChapter) {
      book.setChapter(matchedChapter);
    } else if (data.chapter_num) {
      book.setChapter({
        number: data.chapter_num,
        title: title.value,
        url: data.url || '',
        id: data.chapter_id ?? null,
      });
    }

    // Update browser title with book name and chapter title
    if (book.info?.name && title.value) {
      document.title = `${config.value.name} - ${book.info?.name} - ${title.value}`;
    } else if (title.value) {
      document.title = `${config.value.name} - ${title.value}`;
    }

    console.log(`Successfully loaded chapter ${props.chapterId}, index: ${book.currentChapterIndex}`);

    // Enqueue next chapters for background prefetch
    enqueuePrefetch(props.bookId, props.chapterId);
  } catch (e: unknown) {
    let errorMsg = 'Unknown error';
    let is404 = false;

    // Extract detailed error information from axios error
    if (typeof e === 'object' && e !== null) {
      const axiosError = e as {
        response?: { status?: number; statusText?: string; data?: { message?: string; error?: string } };
        message?: string;
        code?: string;
      };

      // Check if it's a 404 error
      if ('response' in axiosError && axiosError.response?.status === 404) {
        is404 = true;
      }

      // Check if it's a timeout error
      if (axiosError.code === 'ECONNABORTED' || axiosError.message?.includes('timeout')) {
        errorMsg = t('chapter.loadTimeout');
      } else if ('response' in axiosError && axiosError.response) {
        const status = axiosError.response?.status || 'Unknown';
        const statusText = axiosError.response?.statusText || '';
        const serverMsg = axiosError.response?.data?.message || axiosError.response?.data?.error || '';
        errorMsg = `${status} ${statusText}${serverMsg ? ': ' + serverMsg : ''}`;
      } else if (axiosError.message) {
        errorMsg = axiosError.message;
      } else {
        errorMsg = JSON.stringify(e);
      }
    } else if (e instanceof Error) {
      errorMsg = e.message;
    } else if (typeof e === 'string') {
      errorMsg = e;
    } else {
      errorMsg = JSON.stringify(e);
    }

    // Handle 404: Try to find the nearest available chapter
    if (is404 && book.allChapters.length > 0) {
      console.warn(`[ChapterPage] Chapter ${props.chapterId} not found (404), looking for nearest available chapter...`);

      // Find current chapter index
      const currentIdx = book.allChapters.findIndex(
        ch => ch.id === props.chapterId || String(ch.number) === props.chapterId
      );
      const chapters = book.allChapters;

      // Find next available chapter (by index position)
      const nextIdx = currentIdx >= 0 ? currentIdx + 1 : 0;
      if (nextIdx < chapters.length) {
        const nextChapter = chapters[nextIdx]!;
        const nextId = nextChapter.id ?? String(nextChapter.number);
        console.log(`[ChapterPage] Redirecting to next available chapter: ${nextId}`);
        error.value = `章節不存在，已跳轉至下一可用章節`;
        await new Promise(resolve => setTimeout(resolve, 1500));
        void router.replace({
          name: 'Chapter',
          params: {
            bookId: props.bookId,
            chapterId: nextId,
            chapterTitle: nextChapter.title
          }
        });
        return;
      }

      // No next chapter found, try previous
      const prevIdx = currentIdx >= 0 ? currentIdx - 1 : chapters.length - 1;
      if (prevIdx >= 0) {
        const prevChapter = chapters[prevIdx]!;
        const prevId = prevChapter.id ?? String(prevChapter.number);
        console.log(`[ChapterPage] Redirecting to previous available chapter: ${prevId}`);
        error.value = `章節不存在，已跳轉至上一可用章節`;
        await new Promise(resolve => setTimeout(resolve, 1500));
        void router.replace({
          name: 'Chapter',
          params: {
            bookId: props.bookId,
            chapterId: prevId,
            chapterTitle: prevChapter.title
          }
        });
        return;
      }

      // No chapters available at all - fall back to chapters list
      console.warn('[ChapterPage] No nearby chapters found, redirecting to chapters list');
      error.value = `章節不存在，正在返回章節列表...`;
      await new Promise(resolve => setTimeout(resolve, 1500));
      void router.replace({
        name: 'Chapters',
        params: { bookId: props.bookId }
      });
      return;
    }

    error.value = `${t('chapter.loadContentFailed')}: ${errorMsg}`;
    console.error('Failed to load chapter content:', {
      bookId: props.bookId,
      chapterId: props.chapterId,
      chapterTitle: props.chapterTitle,
      error: e,
      response: typeof e === 'object' && e !== null && 'response' in e ? (e as { response?: unknown }).response : undefined,
      responseData: typeof e === 'object' && e !== null && 'response' in e ? (e as { response?: { data?: unknown } }).response?.data : undefined
    });
  } finally {
    loading.value = false;
  }
}

/**
 * Handle keyboard shortcuts for navigation
 * - Enter: Go to chapters list
 * - P: Previous chapter
 * - N: Next chapter
 */
function handleKeyPress(event: KeyboardEvent) {
  // Ignore if user is typing in an input field
  const target = event.target as HTMLElement;
  if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') {
    return;
  }

  const key = event.key.toLowerCase();

  if (key === 'enter') {
    // Navigate to chapters list
    event.preventDefault();
    void router.push(`/book/${props.bookId}/chapters`);
    return;
  }

  if (key === 'p') {
    // Previous chapter
    event.preventDefault();
    if (book.prevChapter) {
      void router.push(chapterLink(book.prevChapter.id ?? String(book.prevChapter.number), book.prevChapter.title));
    }
    return;
  }

  if (key === 'n') {
    // Next chapter
    event.preventDefault();
    if (book.nextChapter) {
      void router.push(chapterLink(book.nextChapter.id ?? String(book.nextChapter.number), book.nextChapter.title));
    }
    return;
  }
}

onMounted(async () => {
  await loadMeta();
  await load();

  // Update the current chapter in config for breadcrumbs
  const currentChapter = book.allChapters[book.currentChapterIndex??0] //chapters.value[chapterIndex.value];
  if (currentChapter) {
    update({ chapter: JSON.stringify(currentChapter) });
  }

  console.log('fontsize ', fontsize.value)

  // Add keyboard navigation listener
  window.addEventListener('keydown', handleKeyPress);
});

// Track the current loading request to prevent race conditions
let currentLoadRequest = 0;
let debounceTimer: NodeJS.Timeout | null = null;

// Watch both chapterId and chapterTitle to reload when navigation happens
watch(() => [props.chapterId, props.chapterTitle], () => {
  // Clear existing debounce timer
  if (debounceTimer) {
    clearTimeout(debounceTimer);
  }

  // Debounce rapid chapter switches (300ms)
  debounceTimer = setTimeout(() => {
    // Increment request counter to invalidate previous requests
    currentLoadRequest++;
    const thisRequest = currentLoadRequest;

    // Use void to explicitly ignore the promise return
    void (async () => {
      try {
        await load();

        // Only update config if this is still the latest request
        if (thisRequest === currentLoadRequest) {
          // Update the current chapter in config for breadcrumbs
          const currentChapter = book.allChapters[book.currentChapterIndex??0] //chapters.value[chapterIndex.value];
          if (currentChapter) {
            update({ chapter: JSON.stringify(currentChapter) });
          }
        }
      } catch (e) {
        console.error('Error in chapter watch:', e);
      }
    })();
  }, 300);
}, { immediate: false });

// Cleanup on unmount
onBeforeUnmount(() => {
  if (debounceTimer) {
    clearTimeout(debounceTimer);
  }

  // Remove keyboard navigation listener
  window.removeEventListener('keydown', handleKeyPress);
});
</script>

<style scoped>
p {
  text-indent: 2em;
  line-height: 1.8;
  margin: 0.6em 0;
}

.chapter-content {
  max-width: 100%;
  margin: 0 auto;
  padding: 0 4px;
}

/* Smooth transitions for buttons */
.q-btn {
  transition: all 0.2s ease;
}

.q-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
}

.q-btn:active:not(:disabled) {
  transform: translateY(0);
}

/* Mobile responsive navigation - hide bottom nav on small screens */
@media (max-width: 600px) {
  /* Hide bottom navigation on mobile to reduce clutter */
  .row.q-my-md.q-gutter-sm.justify-center {
    display: none;
  }

  /* Make top navigation buttons smaller and stack better on mobile */
  .q-card-section.q-py-sm .row.q-gutter-sm {
    flex-wrap: wrap;
  }

  .q-card-section.q-py-sm .q-btn {
    font-size: 0.75rem;
    min-width: auto;
  }

  /* Adjust progress indicator for mobile */
  .q-linear-progress {
    margin-top: 8px;
  }
}

/* Tablet and larger - constrain reading width for comfort */
@media (min-width: 601px) {
  .chapter-content {
    max-width: 900px;
    padding: 0 12px;
  }
}
</style>
