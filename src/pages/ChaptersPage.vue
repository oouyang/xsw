<!-- src/pages/ChaptersPage.vue -->
<template>
  <q-page class="q-pa-md">
    <!-- Compact header -->
    <div class="row items-center q-mb-md">
      <q-btn flat dense round icon="arrow_back" @click="router.back()" />
      <div class="q-ml-sm">
        <div class="text-h6 text-weight-medium">{{ displayBookName }}</div>
        <div class="text-caption text-grey-7">
          <router-link
            :to="{ name: 'Author', params: { authorName: book.info?.author } }"
            class="text-grey-7"
            style="text-decoration: none"
          >{{ displayAuthor }}</router-link>
          • {{ displayType }} • {{ displayStatus }}
          <span v-if="book.info?.update"> • {{ book.info.update }}</span>
        </div>
        <div class="row items-center q-gutter-sm text-caption text-grey-6 q-mt-xs">
          <span v-if="book.info?.bookmark_count" class="row items-center no-wrap">
            <q-icon name="bookmark_border" size="14px" class="q-mr-xs" />{{ displayBookmarkCount }}
          </span>
          <span v-if="book.info?.view_count" class="row items-center no-wrap">
            <q-icon name="visibility" size="14px" class="q-mr-xs" />{{ displayViewCount }}
          </span>
        </div>
        <div v-if="displayDescription" class="text-caption text-grey-7 q-mt-xs ellipsis-3-lines">
          {{ displayDescription }}
        </div>
      </div>
      <q-space />
      <ShareMenu
        :title="displayBookName"
        :text="`${displayBookName} - ${displayAuthor}`"
        size="sm"
      />
      <q-chip outline color="primary" size="sm">
        {{ book.info?.last_chapter_number || 0 }} 章
      </q-chip>
    </div>

    <!-- Recommended books -->
    <div v-if="similarBooks.length > 0" class="q-mb-md">
      <div class="text-caption text-grey-7 q-mb-xs">{{ $t('book.recommended') }}</div>
      <div class="row q-gutter-sm" style="overflow-x: auto; flex-wrap: nowrap">
        <q-card
          v-for="sb in similarBooks"
          :key="sb.book_id || sb.bookurl"
          flat
          bordered
          class="cursor-pointer"
          style="min-width: 140px; max-width: 160px"
          @click="router.push({ name: 'Chapters', params: { bookId: sb.public_id || sb.book_id || '' } })"
        >
          <q-card-section class="q-pa-sm">
            <div class="text-caption text-weight-medium ellipsis">{{ convertIfNeeded(sb.bookname) }}</div>
            <div class="text-caption text-grey-6 ellipsis">{{ convertIfNeeded(sb.author) }}</div>
          </q-card-section>
        </q-card>
      </div>
    </div>

    <!-- Compact toolbar -->
    <div class="row items-center q-mb-sm q-gutter-sm">
      <q-input
        v-model.number="jumpToChapterNum"
        dense
        outlined
        type="number"
        :min="1"
        :max="book.info?.last_chapter_number || 9999"
        placeholder="跳至章節..."
        style="max-width: 150px"
        @keyup.enter="jumpToChapter"
      >
        <template v-slot:prepend>
          <q-icon name="search" size="xs" />
        </template>
        <template v-slot:append>
          <q-btn
            flat
            dense
            round
            icon="arrow_forward"
            size="sm"
            @click="jumpToChapter"
            :disable="!jumpToChapterNum || jumpToChapterNum < 1"
          />
        </template>
      </q-input>
      <q-btn dense outline icon="refresh" @click="reload" :loading="loading">
        <q-tooltip>{{ $t('chapter.reloadChapters') }}</q-tooltip>
      </q-btn>
      <q-space />
      <template v-if="isEndless">
        <div class="text-caption text-grey-7">
          {{ endlessChapters.length }} / {{ book.allChapters.length }}
        </div>
      </template>
      <template v-else>
        <div class="text-caption text-grey-7">
          第 {{ book.page }} / {{ book.maxPages }} 頁
        </div>
        <q-pagination
          v-model="book.page"
          :max="book.maxPages"
          @update:model-value="p => switchPage(p)"
          color="primary"
          max-pages="7"
          size="sm"
          :disable="loading || book.maxPages <= 1"
          boundary-numbers
        />
      </template>
    </div>

    <!-- Context-aware error banner -->
    <q-banner
      v-if="loadError"
      :class="loadError.phase === 'phase2' ? 'bg-orange-2 text-orange-10' : 'bg-red-2 text-red-10'"
      class="q-mb-sm"
      dense
    >
      <template v-slot:avatar>
        <q-icon :name="loadError.phase === 'phase2' ? 'warning' : 'error'" size="sm" />
      </template>
      <div class="text-body2">{{ loadError.message }}</div>
      <template v-slot:action>
        <q-btn
          v-if="loadError.retryable"
          flat
          dense
          :color="loadError.phase === 'phase2' ? 'orange-10' : 'red-10'"
          icon="refresh"
          @click="retryPhase(loadError.phase)"
        >
          <q-tooltip>{{ $t('common.retry') }}</q-tooltip>
        </q-btn>
        <q-btn
          flat
          dense
          round
          icon="close"
          size="sm"
          :color="loadError.phase === 'phase2' ? 'orange-10' : 'red-10'"
          @click="loadError = null"
        />
      </template>
    </q-banner>

    <!-- Legacy error banner (fallback) -->
    <q-banner v-if="error && !loadError" class="bg-red-2 text-red-10 q-mb-sm" dense>
      <div class="row items-center">
        <div class="col text-body2">{{ error }}</div>
        <q-btn flat dense color="red-10" icon="refresh" @click="reload">
          <q-tooltip>{{ $t('common.retry') }}</q-tooltip>
        </q-btn>
      </div>
    </q-banner>


    <!-- Phase 2 background loading banner -->
    <transition name="slide-down">
      <div
        v-if="isPhase2Loading"
        class="row items-center q-px-md q-py-sm bg-blue-1 text-blue-9 q-mb-sm rounded-borders"
      >
        <q-spinner-dots color="blue-9" size="sm" />
        <div class="q-ml-sm text-caption">
          {{ phase2Message || $t('chapter.loadingRemainingInBackground') }}
          <span v-if="book.info?.last_chapter_number && book.allChapters.length > 0" class="text-grey-7">
            ({{ book.allChapters.length }} / {{ book.info.last_chapter_number }})
          </span>
        </div>
        <q-space />
        <q-btn flat dense round size="sm" icon="close" @click="isPhase2Loading = false" />
      </div>
    </transition>

    <!-- Skeleton loading during Phase 1 -->
    <div v-if="loading && displayChapters.length === 0">
      <q-list bordered separator dense>
        <q-item v-for="n in 15" :key="n" class="skeleton-item">
          <q-item-section avatar style="min-width: 50px">
            <q-skeleton type="text" width="30px" />
          </q-item-section>
          <q-item-section>
            <q-skeleton type="text" :width="`${60 + Math.random() * 20}%`" />
          </q-item-section>
          <q-item-section side>
            <q-skeleton type="circle" size="16px" />
          </q-item-section>
        </q-item>
      </q-list>
      <div class="text-center q-py-sm">
        <div class="text-caption text-grey-7">
          {{ loadingMessage }}
        </div>
      </div>
    </div>

    <!-- Endless scroll mode -->
    <template v-if="isEndless">
      <q-infinite-scroll
        v-if="endlessChapters.length > 0 || book.allChapters.length > 0"
        :offset="250"
        @load="onEndlessLoad"
        ref="infiniteScrollRef"
      >
        <q-list bordered separator dense>
          <q-item
            v-for="c in endlessChapters"
            :key="c.id || c.number"
            clickable
            :to="chapterLink(c.id ?? String(c.number), c.title)"
            class="chapter-item"
          >
            <q-item-section>
              <q-item-label class="text-body2">{{ c.title }}</q-item-label>
            </q-item-section>
            <q-item-section side>
              <q-icon name="chevron_right" color="grey-5" size="xs" />
            </q-item-section>
          </q-item>
        </q-list>
        <template v-slot:loading>
          <div class="row justify-center q-my-md">
            <q-spinner-dots color="primary" size="40px" />
          </div>
        </template>
      </q-infinite-scroll>
    </template>

    <!-- Paging mode (existing) -->
    <template v-else>
      <transition name="fade" mode="out-in">
        <q-list
          v-if="displayChapters.length > 0"
          :key="`page-${book.page}`"
          bordered
          separator
          dense
        >
          <template v-for="c in displayChaptersWithVolumes" :key="c.type === 'volume' ? `vol-${c.name}` : (c.id || c.number)">
            <q-item-label v-if="c.type === 'volume'" header class="text-weight-bold text-grey-8 bg-grey-2">
              {{ convertIfNeeded(c.name) }}
            </q-item-label>
            <q-item
              v-else
              clickable
              :to="chapterLink(c.id ?? String(c.number), c.title)"
              class="chapter-item"
            >
              <q-item-section>
                <q-item-label class="text-body2">{{ c.title }}</q-item-label>
              </q-item-section>
              <q-item-section side>
                <q-icon name="chevron_right" color="grey-5" size="xs" />
              </q-item-section>
            </q-item>
          </template>
        </q-list>
      </transition>
    </template>

    <q-banner v-if="!loading && !isEndless && displayChapters.length === 0" class="bg-grey-2 q-my-md">
      <div class="text-center text-grey-7">
        <q-icon name="info" size="md" class="q-mb-sm" />
        <div>{{ $t('chapter.noChaptersOnPage') }}</div>
      </div>
    </q-banner>

    <!-- Bottom pagination (paging mode only) -->
    <div v-if="!isEndless && displayChapters.length > 0" class="row justify-center q-mt-md">
      <q-pagination
        v-model="book.page"
        :max="book.maxPages"
        @update:model-value="p => switchPage(p)"
        color="primary"
        max-pages="7"
        size="sm"
        :disable="loading"
        boundary-numbers
      />
    </div>

    <!-- Comments section -->
    <BookComments v-if="props.bookId" :book-id="props.bookId" />
  </q-page>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, watch, nextTick } from 'vue';
import { useI18n } from 'vue-i18n';
import type { QInfiniteScroll } from 'quasar';
import type { ChapterRef, Chapters, BookSummary } from 'src/types/book-api';
import { getBookChapters, getSimilarBooks } from 'src/services/bookApi';
import { useMeta } from 'quasar';
import { useRoute, useRouter } from 'vue-router';
import { useAppConfig } from 'src/services/useAppConfig';
import { chapterLink, dedupeBy, normalizeNum, toArr, fuzzCount, formatCount } from 'src/services/utils';
import ShareMenu from 'src/components/ShareMenu.vue';
import BookComments from 'src/components/BookComments.vue';
import { useTextConversion } from 'src/composables/useTextConversion';
import { useBookStore } from 'src/stores/books';

const { t } = useI18n();
const { config, update } = useAppConfig();
const { convertIfNeeded } = useTextConversion();
const book = useBookStore();


// const $q = useQuasar();
const route = useRoute();
const router = useRouter();

const props = defineProps<{ bookId: string }>();
// const info = ref<BookInfo | null>(null);
const chapters = ref<Chapters>({} as Chapters);
// const page = ref(Number(config.value?.page) || 1);
// const maxPages = ref(50);
const error = ref('');
const loading = ref(false);
const loadingMessage = ref(t('common.loading'));

// Loading state machine
type LoadingPhase = 'idle' | 'phase1' | 'phase2' | 'complete' | 'error';
const loadingPhase = ref<LoadingPhase>('idle');

// Phase 2 loading tracking (kept for compatibility)
const isPhase2Loading = ref(false);
const phase2Message = ref('');

// Quick chapter navigation
const jumpToChapterNum = ref<number | null>(null);

// Recommended books
const similarBooks = ref<BookSummary[]>([]);

// Smart error tracking with context
interface LoadError {
  phase: 'phase1' | 'phase2' | 'info';
  message: string;
  retryable: boolean;
  technicalDetails?: string;
}

const loadError = ref<LoadError | null>(null);

// Endless scroll state
const isEndless = computed(() => (config.value.scrollMode || 'paging') === 'endless');
const endlessPage = ref(1);
const infiniteScrollRef = ref<QInfiniteScroll | null>(null);

// Endless chapters: number-based filtering from page 1 up to endlessPage
const endlessChapters = computed(() => {
  if (!isEndless.value) return [];
  const maxNum = endlessPage.value * book.pageSize;
  return book.allChapters.filter(ch => ch.number >= 1 && ch.number <= maxNum);
});

function onEndlessLoad(_index: number, done: (stop?: boolean) => void) {
  if (endlessPage.value >= book.maxPages) {
    done(true);
    return;
  }
  endlessPage.value++;
  // Defer done() until after Vue renders the new items,
  // so QInfiniteScroll can measure the new scroll height correctly
  void nextTick(() => {
    done(endlessPage.value >= book.maxPages);
  });
}

// Reset endless page when switching modes or books
watch(isEndless, (val) => {
  if (val) {
    endlessPage.value = 1;
  }
});

// Computed properties for CN to TW conversion
const displayBookName = computed(() => convertIfNeeded(book.info?.name));
const displayAuthor = computed(() => convertIfNeeded(book.info?.author));
const displayType = computed(() => convertIfNeeded(book.info?.type));
const displayStatus = computed(() => convertIfNeeded(book.info?.status));
const displayDescription = computed(() => convertIfNeeded(book.info?.description));
const displayBookmarkCount = computed(() => formatCount(fuzzCount(book.info?.bookmark_count)));
const displayViewCount = computed(() => formatCount(fuzzCount(book.info?.view_count)));
const displayChapters = computed(() => {
  const chapters = book.pageChapters;
  console.log('[displayChapters] page:', book.page, 'pageChapters:', chapters.length, 'allChapters:', book.allChapters.length);
  return chapters;
});

// Interleave volume headers into the chapter list for the current page
const displayChaptersWithVolumes = computed(() => {
  const chapters = displayChapters.value;
  if (!chapters.length) return [];
  const volumes = book.volumes;
  if (!volumes.length) {
    // No volumes: return chapters as-is with a type marker
    return chapters.map(c => ({ ...c, type: 'chapter' as const }));
  }

  // Build a mixed list: volume headers + chapters
  const result: Array<{ type: 'volume'; name: string } | (ChapterRef & { type: 'chapter' })> = [];
  let volIdx = 0;
  for (const c of chapters) {
    // Insert any volume headers that start at or before this chapter
    while (volIdx < volumes.length && (volumes[volIdx]?.start_chapter ?? Infinity) <= c.number) {
      result.push({ type: 'volume', name: volumes[volIdx]?.name ?? '' });
      volIdx++;
    }
    result.push({ ...c, type: 'chapter' });
  }
  return result;
});

useMeta({ title: `${config.value.name} ${book.info?.name ? ' >> '+ book.info?.name : ''}` });

async function switchPage(page: number) {
  book.setPage(page);
  console.log(`page changed to ${page} -`, book.page);

  // If allChapters is empty, we need to load them first
  if (book.allChapters.length === 0) {
    console.log('[switchPage] allChapters is empty, loading...');
    loading.value = true;
    loadingMessage.value = t('chapter.loadingChapters');
    loadingPhase.value = 'phase1';

    try {
      await book.loadAllChapters({
        onProgress: (msg: string) => {
          loadingMessage.value = msg;

          // Track Phase 2 loading
          if (msg.includes('背景')) {
            loadingPhase.value = 'phase2';
            isPhase2Loading.value = true;
            phase2Message.value = msg;
          } else if (msg === '') {
            loadingPhase.value = 'complete';
            isPhase2Loading.value = false;
            phase2Message.value = '';
          }
        }
      });

      // Ensure we're in complete state
      loadingPhase.value = 'complete';
    } catch (e) {
      console.error('[switchPage] Error loading chapters:', e);
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      const errorMsg = err?.response?.data?.detail || err?.message || 'Unknown error';

      // Set state machine to error
      loadingPhase.value = 'error';

      // Determine which phase failed
      const hasLoadedChapters = book.pageChapters.length > 0;

      if (hasLoadedChapters) {
        loadError.value = {
          phase: 'phase2',
          message: t('chapter.phase2LoadingWarning'),
          retryable: true,
          technicalDetails: errorMsg
        };
      } else {
        loadError.value = {
          phase: 'phase1',
          message: t('chapter.loadChaptersFailed'),
          retryable: true,
          technicalDetails: errorMsg
        };
      }
    } finally {
      loading.value = false;
    }
  }

  void router.replace({
    query: {
      ...route.query,
      page
    }
  })
}

/**
 * Jump to a specific chapter number
 */
function jumpToChapter() {
  if (!jumpToChapterNum.value || jumpToChapterNum.value < 1) return;

  const chapterNum = jumpToChapterNum.value;
  const totalChapters = book.info?.last_chapter_number || book.allChapters.length;

  if (chapterNum > totalChapters) {
    // Show warning if chapter number exceeds total
    console.warn(`[jumpToChapter] Chapter ${chapterNum} exceeds total ${totalChapters}`);
    return;
  }

  // Calculate which page this chapter is on
  const targetPage = Math.ceil(chapterNum / book.pageSize);
  console.log(`[jumpToChapter] Jumping to chapter ${chapterNum}, page ${targetPage}`);

  // If the chapter is already loaded, find it and navigate directly
  const targetChapter = book.allChapters.find(c => c.number === chapterNum);
  if (targetChapter) {
    // Navigate to chapter content directly
    void router.push(chapterLink(targetChapter.id ?? String(targetChapter.number), targetChapter.title));
  } else {
    // Switch to the page containing the chapter
    void switchPage(targetPage);
  }

  // Clear input
  jumpToChapterNum.value = null;
}

// watch(page, (newVal, oldVal) => {
//   // Validate page number
//   if (!Number.isFinite(newVal) || newVal < 1) {
//     console.warn(`[ChaptersPage] Invalid page value: ${newVal}, resetting to 1`);
//     page.value = 1;
//     return;
//   }

//   // $q.localStorage.setItem('chapterPage', page.value)
  // update({page: `${page.value}`});
//   book.setPage(newVal);
//   void router.replace({
//     query: {
//       ...route.query,
//       page: newVal
//     }
//   })
//   console.log(`page changed from ${oldVal} to ${newVal} -`, $q.localStorage.getItem('chapterPage'));
// });


// watch(
//   () => props.bookId,
//   async (newBookId, oldBookId) => {
//     if (newBookId !== oldBookId) {
//       // Reset page for a new book
//       page.value = 1;
//       // $q.localStorage.set('bookId', newBookId);
//       // $q.localStorage.set('chapterPage', 1);
//         // update({page: `${page.value}`, bookId: newBookId});
//         book.setBookId(newBookId);
//         book.setPage(1);
        

//       // ✅ Properly handle the promise
//       try {
//         await loadChapters(); // reload chapters for page 1
//       } catch (err) {
//         console.error('Failed to reload chapters:', err);
//         error.value = 'Load chapters failed';
//       }
//     }
//   }
// );


async function loadInfo() {
  try {
    loading.value = true;
    error.value = '';
    loadError.value = null;
    await book.loadInfo(props.bookId);

    // Sync config store bookId with pinia store (may have switched to public_id)
    if (book.bookId && book.bookId !== config.value.bookId) {
      update({ bookId: book.bookId });
    }

    // Update browser title with book name
    if (book.info?.name) {
      document.title = `${config.value.name} - ${book.info.name}`;
    }

    // if (info.value?.name) {
    //   document.title = `${config.value.name} - ${info.value.name}`;
    // }

    // Note: Backend now automatically syncs last chapter when fetching all chapters
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    const errorMsg = err?.response?.data?.detail || err?.message || 'Unknown error';

    // Set context-aware error for book info loading
    loadError.value = {
      phase: 'info',
      message: t('book.loadInfoFailed'),
      retryable: true,
      technicalDetails: errorMsg
    };

    console.error('[loadInfo] Error:', e);
  } finally {
    loading.value = false;
  }
}

async function reload() {
  error.value = '';
  loadError.value = null;
  loading.value = true;
  loadingMessage.value = t('common.loading');
  try {
    await book.loadAllChapters({
      force: true,
      onProgress: (msg: string) => {
        loadingMessage.value = msg;
      }
    });
    await loadInfo();
    await loadChapters();
  } catch (e) {
    error.value = 'Reload failed';
    console.error('Reload error:', e);
  } finally {
    loading.value = false;
    loadingMessage.value = t('common.loading');
  }
}

/**
 * Retry a specific phase that failed
 */
async function retryPhase(phase: 'phase1' | 'phase2' | 'info') {
  loadError.value = null;
  error.value = '';
  loadingPhase.value = 'phase1'; // Reset to initial state

  try {
    if (phase === 'info') {
      // Retry loading book info
      await loadInfo();
      loadingPhase.value = 'complete';
    } else if (phase === 'phase1') {
      // Retry Phase 1: Load pages around current position
      loading.value = true;
      loadingMessage.value = t('chapter.loadingFirstPages');
      await book.loadAllChapters({
        force: true,
        onProgress: (msg: string) => {
          loadingMessage.value = msg;

          // Track Phase 2 loading
          if (msg.includes('背景')) {
            loadingPhase.value = 'phase2';
            isPhase2Loading.value = true;
            phase2Message.value = msg;
          } else if (msg === '') {
            loadingPhase.value = 'complete';
            isPhase2Loading.value = false;
            phase2Message.value = '';
          }
        }
      });

      // Ensure we're in complete state
      loadingPhase.value = 'complete';
    } else if (phase === 'phase2') {
      // Retry Phase 2: Load remaining chapters
      // This is handled automatically by book.loadAllChapters
      // We just trigger a full reload
      loading.value = true;
      loadingMessage.value = t('chapter.loadingRemainingInBackground');
      loadingPhase.value = 'phase2';
      await book.loadAllChapters({
        force: true,
        onProgress: (msg: string) => {
          loadingMessage.value = msg;

          if (msg.includes('背景')) {
            loadingPhase.value = 'phase2';
            isPhase2Loading.value = true;
            phase2Message.value = msg;
          } else if (msg === '') {
            loadingPhase.value = 'complete';
            isPhase2Loading.value = false;
            phase2Message.value = '';
          }
        }
      });

      // Ensure we're in complete state
      loadingPhase.value = 'complete';
    }
  } catch (e) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    const errorMsg = err?.response?.data?.detail || err?.message || 'Unknown error';

    // Set state machine to error
    loadingPhase.value = 'error';

    // Set context-aware error
    if (phase === 'info') {
      loadError.value = {
        phase: 'info',
        message: t('book.loadInfoFailed'),
        retryable: true,
        technicalDetails: errorMsg
      };
    } else if (phase === 'phase1') {
      loadError.value = {
        phase: 'phase1',
        message: t('chapter.loadChaptersFailed'),
        retryable: true,
        technicalDetails: errorMsg
      };
    } else if (phase === 'phase2') {
      loadError.value = {
        phase: 'phase2',
        message: '背景載入未完成（前3頁已可用）',
        retryable: true,
        technicalDetails: errorMsg
      };
    }

    console.error(`[retryPhase] Failed to retry ${phase}:`, e);
  } finally {
    loading.value = false;
    loadingMessage.value = t('common.loading');
  }
}


async function loadChapters() {
  const storedchapters = await loadPageChapters() // JSON.parse(config.value.chapters||'[]')
  if (storedchapters && storedchapters?.length > 0) {
    chapters.value.chapters = storedchapters
  }
  try {
    error.value = '';
    const resp = await getBookChapters(props.bookId, { page: book.page, all: false });
    chapters.value.chapters = Array.isArray(resp) ? resp : resp.chapters;
    // maxPages.value = Array.isArray(resp) ? 50 : chapters.value.totalPages||0;
    console.log('chapters is array ', Array.isArray(resp));

    // ⚠️ DO NOT sync here! It creates a downward cascade.
    // Syncing is handled ONLY by syncLastPageInBackground() which explicitly
    // fetches the calculated last page, not just "current page that equals maxPages"
    //
    // The issue: if maxPages is wrong (e.g., 356 but actual is 355), and we visit
    // page 355, we sync with page 355's data, reduce last chapter to 7092,
    // maxPages becomes 355, then next visit we sync again, creating infinite reduction.
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    const errorMsg = err?.response?.data?.detail || err?.message || 'Unknown error';
    error.value = `${t('chapter.loadChaptersFailed')}: ${errorMsg}`;
    console.error('[loadChapters] Error:', e);
  }
  console.log('stored chapters ', storedchapters?.length)
}

/**
 * Cache-first page-loader:
 * 1) If cached chapters for the same bookId exist and we know page size, slice from cache.
 * 2) Otherwise fetch that page, update the view, and merge+persist the cache.
 */
async function loadPageChapters() {
  try {
    error.value = ''

    const currentBookId = String(props.bookId ?? '')
    const currentPage = Number(book.page ?? 1)

    if (!currentBookId) {
      error.value = 'Missing bookId'
      return []
    }
    if (!Number.isFinite(currentPage) || currentPage <= 0) {
      error.value = 'Invalid page'
      return []
    }

    // Resolve pageSize (prefer persisted value; fall back to a default)
    const pageSize = 20
      // Number(config.value.pageSize ?? chapters.value?.pageSize ?? 50) || 50

    // Parse cached chapters safely
    const cachedBookId = String(config.value.bookId ?? '')
    const cachedChapters: ChapterRef[] = (() => {
      try {
        return JSON.parse(config.value.chapters || '[]') as ChapterRef[]
      } catch {
        return []
      }
    })()

    const canReuseCache =
      cachedBookId === currentBookId &&
      cachedChapters.length > 0 &&
      Number.isFinite(pageSize) &&
      pageSize > 0

    if (canReuseCache) {
      const start = (currentPage - 1) * pageSize
      const end = start + pageSize
      const slice = cachedChapters.slice(start, end)

      if (slice.length > 0) {
        // Reuse cache → update reactive view and exit
        // chapters.value.chapters = slice
        // Optional: compute totalPages if you want pagination UI to be stable from cache
        const totalPages =
          Math.ceil(cachedChapters.length / pageSize) ||  0
        // chapters.value.totalPages = totalPages

        // ⚠️ DO NOT sync with cached data here!
        // Same cascade issue as loadChapters() - if cache is incomplete/outdated,
        // syncing will reduce the last chapter incorrectly.
        // Only syncLastPageInBackground() should handle syncing.

        console.log('[loadPageChapters] used cache slice', {
          page: currentPage,
          pageSize,
          sliceLen: slice.length,
          totalCached: cachedChapters.length,
          totalPages,
        })
        return slice
      }
      // If the cache doesn't have enough to fill this page, we'll fetch below
    }

    // Fetch fallback: get this page from the API
    const resp = await getBookChapters(currentBookId, {
      page: currentPage,
      all: false
    })

    // Normalize response: some APIs return [] (array) or { chapters, totalPages, pageSize }
    const receivedChapters = Array.isArray(resp) ? resp : toArr(resp?.chapters)
    // const receivedTotalPages =
    //   (Array.isArray(resp) ? undefined : Number(resp?.totalPages)) ??
    //   chapters.value.totalPages
    // Prefer persisted pageSize; if backend provides it, we can store it for future cache slicing
    const receivedPageSize = pageSize
      // (Array.isArray(resp) ? undefined : Number(resp?.pageSize)) ?? pageSize

    // Update the reactive view for current page
    // chapters.value.chapters = receivedChapters
    // if (receivedTotalPages && Number.isFinite(receivedTotalPages)) {
    //   chapters.value.totalPages = receivedTotalPages
    // }

    // Merge fetched page into cache and persist (only if this is the same book or replacing cache)
    // Strategy: dedupe by `number`, keeping first occurrence.
    const nextCache = dedupeBy<ChapterRef, string>(
      (canReuseCache ? cachedChapters : []).concat(receivedChapters),
      c => normalizeNum(c.number)
    )

    // Optionally, if you prefer precise “paged” placement in the cache (instead of concat+dedupe),
    // you can place the page slice at `[start, end)` positions in an array and then trim trailing gaps.

    // update({
    //   bookId: currentBookId,
    //   chapters: JSON.stringify(nextCache)
    // })
            book.setBookId(currentBookId);
      // book.replaceChapters(nextCache);


    console.log('[loadPageChapters] fetched page', {
      page: currentPage,
      pageSize: receivedPageSize,
      received: receivedChapters.length,
      cachedTotal: nextCache.length,
      totalPages: chapters.value.totalPages ?? 'n/a'
    })

    return receivedChapters
  } catch (e) {
    console.log('[loadPageChapters] error', e)
    error.value = 'Load chapters failed'
  }
}

onMounted(async () => {
  const storedBookId = config.value.bookId; // $q.localStorage.getItem('bookId');
  const storedPage = Number(config.value.page) || 1; // Default to 1 if NaN

  // IMPORTANT: Always set bookId FIRST to clear old book's data if switching books
  book.setBookId(props.bookId);

  const wantsLastPage = route.query.page === 'last';
  if (route.query.page && !wantsLastPage) {
    const queryPage = Number(route.query.page);
    const currentPage = Number.isFinite(queryPage) && queryPage > 0 ? queryPage : 1;
    book.setPage(currentPage);
  } else if (!wantsLastPage && storedBookId === props.bookId && Number.isFinite(storedPage) && storedPage > 0) {
    book.setPage(storedPage);
  } else {
    book.setPage(1);
  }

  // Load book info first
  await loadInfo();

  // Fire-and-forget: load recommended books
  void getSimilarBooks(props.bookId).then(data => { similarBooks.value = data; }).catch(() => {});

  // Then load all chapters in the background with progress tracking
  loading.value = true;
  loadingMessage.value = t('common.loading');
  loadingPhase.value = 'phase1';

  try {
    await book.loadAllChapters({
      onProgress: (msg: string) => {
        loadingMessage.value = msg;

        // Track Phase 2 loading
        if (msg.includes('背景')) {
          loadingPhase.value = 'phase2';
          isPhase2Loading.value = true;
          phase2Message.value = msg;
        } else if (msg === '') {
          // Phase 2 complete
          loadingPhase.value = 'complete';
          isPhase2Loading.value = false;
          phase2Message.value = '';

          // Jump to last page after all chapters are loaded
          if (wantsLastPage && book.maxPages > 0) {
            book.setPage(book.maxPages);
          }
        }
      }
    });

    // After loading all chapters, always re-derive pageChapters for current page
    // This handles stale cache, Phase 2 overwrites, and timing edge cases
    if (book.allChapters.length > 0) {
      console.log('[onMounted] Re-slicing pageChapters after loadAllChapters...');
      book.setPage(book.page); // Force re-slice
    }

    console.log(`[onMounted] Loaded ${book.allChapters.length} chapters, showing page ${book.page} with ${book.pageChapters.length} chapters`);

    // Mark loading as complete
    loadingPhase.value = 'complete';
  } catch (e) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    const errorMsg = err?.response?.data?.detail || err?.message || 'Unknown error';

    // Set state machine to error
    loadingPhase.value = 'error';

    // Determine which phase failed based on whether we have any chapters loaded
    // If pageChapters has content, Phase 1 succeeded but Phase 2 failed
    const hasLoadedChapters = book.pageChapters.length > 0;

    if (hasLoadedChapters) {
      // Phase 2 failed - less critical since first 3 pages are available
      loadError.value = {
        phase: 'phase2',
        message: '背景載入未完成（前3頁已可用）',
        retryable: true,
        technicalDetails: errorMsg
      };
    } else {
      // Phase 1 failed - critical error
      loadError.value = {
        phase: 'phase1',
        message: t('chapter.loadChaptersFailed'),
        retryable: true,
        technicalDetails: errorMsg
      };
    }

    console.error('[onMounted] Error loading chapters:', e);
  } finally {
    loading.value = false;
    loadingMessage.value = t('common.loading');
  }

  // console.log('route', route, router)
});

</script>

<style scoped>
.ellipsis-3-lines {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.chapter-item {
  transition: all 0.2s ease;
  padding-top: 8px;
  padding-bottom: 8px;
}

.chapter-item:hover {
  background-color: rgba(25, 118, 210, 0.08);
  transform: translateX(4px);
}

.chapter-item:active {
  background-color: rgba(25, 118, 210, 0.15);
}

/* Compact spacing */
.q-page {
  max-width: 1200px;
  margin: 0 auto;
}

/* Fade transition for chapter list */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* Slide down transition for Phase 2 banner */
.slide-down-enter-active,
.slide-down-leave-active {
  transition: all 0.3s ease;
}

.slide-down-enter-from,
.slide-down-leave-to {
  transform: translateY(-20px);
  opacity: 0;
}

/* Skeleton card styling */
.skeleton-card {
  animation: fadeIn 0.3s ease-in;
}

.skeleton-item {
  animation: pulse 1.5s ease-in-out infinite;
}

/* Phase 2 banner subtle animation */
.phase2-banner {
  animation: slideInDown 0.3s ease-out;
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.7;
  }
}

@keyframes slideInDown {
  from {
    transform: translateY(-10px);
    opacity: 0;
  }
  to {
    transform: translateY(0);
    opacity: 1;
  }
}
</style>
