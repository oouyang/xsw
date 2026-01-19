<!-- src/pages/ChaptersPage.vue -->
<template>
  <q-page class="q-pa-md">
    <div class="row items-center q-mb-sm">
      <q-breadcrumbs>
        <q-breadcrumbs-el :label="config.name" icon="home" to="/" />
        <q-breadcrumbs-el :label="'📜' + displayBookName || 'Book'" />
        <q-breadcrumbs-el label="目錄"  :to="`/book/${info?.book_id}/chapters`" />
        <q-breadcrumbs-el :label="`${page}`" />
      </q-breadcrumbs>
      <q-space />
      <q-btn flat icon="arrow_back" :to="{ name: 'Dashboard' }" label="🏛️" />
    </div>

    <q-card class="q-mb-md">
      <q-card-section>
        <div class="text-subtitle2">👤 {{ displayAuthor }}</div>
        <div class="text-caption">
          🏷️ {{ displayType }} | 🚨 {{ displayStatus }} | 🗓️ {{ displayUpdate }}
        </div>
        <div class="text-caption">⚡ {{ displayLastChapterTitle }}</div>
      </q-card-section>
    </q-card>

    <q-banner v-if="error" class="bg-red-2 text-red-10 q-mb-md">{{ error }}</q-banner>

    <div class="row justify-center q-my-lg">
      <q-pagination
        v-model="page"
        :max="maxPages"
        @update:model-value="loadChapters"
        color="primary"
        max-pages="12"
      />
    </div>

    <q-list bordered separator>
      <q-item
        v-for="c in displayChapters"
        :key="c.number"
        clickable
        :to="chapterLink(c.number, c.title)"
      >
        <q-item-section>
          <div class="text-body2">{{ c.title }}</div>
        </q-item-section>
        <q-item-section side>
          <q-icon name="chevron_right" />
        </q-item-section>
      </q-item>
    </q-list>

    <div class="row justify-center q-my-lg">
      <q-pagination
        v-model="page"
        :max="maxPages"
        @update:model-value="loadChapters"
        color="primary"
        max-pages="12"
      />
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue';
import type { BookInfo, ChapterRef, Chapters } from 'src/types/book-api';
import { getBookInfo, getBookChapters } from 'src/services/bookApi';
import { useQuasar, useMeta } from 'quasar';
import { useRoute, useRouter } from 'vue-router';
import { useAppConfig } from 'src/services/useAppConfig';
import { chapterLink, dedupeBy, normalizeNum, toArr, syncLastChapter } from 'src/services/utils';
import { useTextConversion } from 'src/composables/useTextConversion';

const { config, update } = useAppConfig();
const { convertIfNeeded } = useTextConversion();

const $q = useQuasar();
const route = useRoute();
const router = useRouter();

const props = defineProps<{ bookId: string }>();
const info = ref<BookInfo | null>(null);
const chapters = ref<Chapters>({} as Chapters);
const page = ref(Number(config.value?.page) || 1);
const maxPages = ref(50);
const error = ref('');

// Computed properties for CN to TW conversion
const displayBookName = computed(() => convertIfNeeded(info.value?.name));
const displayAuthor = computed(() => convertIfNeeded(info.value?.author));
const displayType = computed(() => convertIfNeeded(info.value?.type));
const displayStatus = computed(() => convertIfNeeded(info.value?.status));
const displayUpdate = computed(() => convertIfNeeded(info.value?.update));
const displayLastChapterTitle = computed(() => convertIfNeeded(info.value?.last_chapter_title));
const displayChapters = computed(() =>
  chapters.value.chapters?.map(c => ({
    ...c,
    title: convertIfNeeded(c.title)
  })) || []
);

useMeta({ title: `${config.value.name} ${info.value?.name ? ' >> '+ info.value?.name : ''}` });

watch(page, (newVal, oldVal) => {
  // Validate page number
  if (!Number.isFinite(newVal) || newVal < 1) {
    console.warn(`[ChaptersPage] Invalid page value: ${newVal}, resetting to 1`);
    page.value = 1;
    return;
  }

  // $q.localStorage.setItem('chapterPage', page.value)
  update({page: `${page.value}`});
  void router.replace({
    query: {
      ...route.query,
      page: newVal
    }
  })
  console.log(`page changed from ${oldVal} to ${newVal} -`, $q.localStorage.getItem('chapterPage'));
});


watch(
  () => props.bookId,
  async (newBookId, oldBookId) => {
    if (newBookId !== oldBookId) {
      // Reset page for a new book
      page.value = 1;
      // $q.localStorage.set('bookId', newBookId);
      // $q.localStorage.set('chapterPage', 1);
        update({page: `${page.value}`, bookId: newBookId});

      // ✅ Properly handle the promise
      try {
        await loadChapters(); // reload chapters for page 1
      } catch (err) {
        console.error('Failed to reload chapters:', err);
        error.value = 'Load chapters failed';
      }
    }
  }
);


async function loadInfo() {
  try {
    info.value = await getBookInfo(props.bookId);
    // Calculate max pages: divide last chapter by page size (20) and round up
    maxPages.value = Math.ceil((info.value?.last_chapter_number || 100) / 20);

    // Update browser title with book name
    if (info.value?.name) {
      document.title = `${config.value.name} - ${info.value.name}`;
    }

    // Fetch last page to sync actual last chapter (non-blocking)
    void syncLastPageInBackground();
  } catch (e) {
    error.value = 'Load book info failed';
    console.log('e', e);
  }
}

/**
 * Fetch the last page of chapters in the background to sync last chapter info
 * This ensures book info shows the actual latest chapter, not outdated/incorrect info
 *
 * IMPORTANT: This is the ONLY place where syncing should happen to prevent cascade.
 * This function explicitly fetches the calculated last page to verify actual data.
 */
async function syncLastPageInBackground() {
  try {
    // Skip if we're already on the last page - no need for background fetch
    if (page.value === maxPages.value) {
      console.log('[syncLastPage] Already on last page, skipping background sync');
      return;
    }

    // Check if we have complete cached data
    const cachedChapters: ChapterRef[] = (() => {
      try {
        return JSON.parse(config.value.chapters || '[]') as ChapterRef[];
      } catch {
        return [];
      }
    })();

    // Only trust cache if it's substantial AND has MORE chapters than book info
    // Never reduce based on cache - only increase
    if (cachedChapters.length > 50 && info.value) {
      const cachedLastChapter = cachedChapters.reduce((max, ch) =>
        ch.number > max ? ch.number : max, 0
      );
      const bookInfoLastChapter = info.value.last_chapter_number || 0;

      // ONLY sync if cache has MORE than book info (upward sync only)
      if (cachedLastChapter > bookInfoLastChapter) {
        const oldLastChapter = info.value.last_chapter_number;
        info.value = syncLastChapter(info.value, cachedChapters);

        console.log(
          `[syncLastPage] ✅ Synced UP from cache (${cachedChapters.length} chapters, last: ${cachedLastChapter}): ${oldLastChapter} → ${info.value.last_chapter_number}`
        );
        // Update maxPages based on actual chapter count
        maxPages.value = Math.ceil(info.value.last_chapter_number! / 20);
        return;
      } else if (cachedLastChapter < bookInfoLastChapter) {
        console.log(
          `[syncLastPage] Cache outdated (has ${cachedLastChapter}, expected ${bookInfoLastChapter}), fetching from API`
        );
        // Don't return - continue to fetch from API to get complete data
      } else {
        // Cache matches book info, no sync needed
        console.log('[syncLastPage] Cache matches book info, no sync needed');
        return;
      }
    }

    // Fetch last page from API to verify
    console.log(`[syncLastPage] Fetching last page (${maxPages.value}) in background`);
    const lastPageChapters = await getBookChapters(props.bookId, {
      page: maxPages.value,
      all: false
    });

    const chaptersArray = Array.isArray(lastPageChapters)
      ? lastPageChapters
      : lastPageChapters.chapters;

    if (info.value && chaptersArray && chaptersArray.length > 0) {
      const oldLastChapter = info.value.last_chapter_number ?? 1;
      const fetchedLastChapter = chaptersArray.reduce((max, ch) =>
        ch.number > max ? ch.number : max, 0
      );

      // ONLY sync if fetched data has MORE chapters (upward sync only)
      // Never reduce based on a single page - book info might be more accurate
      if (fetchedLastChapter > oldLastChapter) {
        info.value = syncLastChapter(info.value, chaptersArray);

        console.log(
          `[syncLastPage] ✅ Synced UP from API (page ${maxPages.value}): ${oldLastChapter} → ${info.value.last_chapter_number}`
        );
        // Recalculate maxPages based on actual last chapter
        maxPages.value = Math.ceil((info.value.last_chapter_number || 100) / 20);
        console.log(`[syncLastPage] Updated maxPages: ${maxPages.value}`);
      } else if (fetchedLastChapter < oldLastChapter) {
        console.log(
          `[syncLastPage] ⚠️ Fetched page ${maxPages.value} has less chapters (${fetchedLastChapter}) than expected (${oldLastChapter}), NOT syncing down. Book info might be more accurate.`
        );
        // Don't sync down - might be incomplete data or wrong page
      } else {
        console.log('[syncLastPage] Fetched data matches book info');
      }
    } else if (chaptersArray && chaptersArray.length === 0) {
      // Empty last page - this is expected if book info's last chapter is accurate
      // Don't backtrack and sync down - just log it
      console.log(
        `[syncLastPage] Page ${maxPages.value} is empty, which is expected if book info (${info.value?.last_chapter_number}) is accurate. Not syncing.`
      );
      // The book info is the source of truth here - don't reduce it
    }
  } catch (e) {
    console.warn('[syncLastPage] Failed to sync last page:', e);
    // Non-critical error, don't show to user
  }
}

async function loadChapters() {
  const storedchapters = await loadPageChapters() // JSON.parse(config.value.chapters||'[]')
  if (storedchapters && storedchapters?.length > 0) {
    chapters.value.chapters = storedchapters
  }
  try {
    error.value = '';
    const resp = await getBookChapters(props.bookId, { page: page.value, all: false });
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
  } catch (e) {
    error.value = 'Load chapters failed';
    console.log('e', e);
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
    const currentPage = Number(page.value ?? 1)

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
          Math.ceil(cachedChapters.length / pageSize) || chapters.value.totalPages || 0
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

  if (route.query.page) {
    const queryPage = Number(route.query.page);
    page.value = Number.isFinite(queryPage) && queryPage > 0 ? queryPage : 1;
    // $q.localStorage.set('bookId', props.bookId);
    // $q.localStorage.set('chapterPage', page.value);
    update({page: `${page.value}`, bookId: props.bookId});
  } else if (storedBookId === props.bookId && Number.isFinite(storedPage) && storedPage > 0) {
    page.value = storedPage;
  } else {
    page.value = 1;
    // $q.localStorage.set('bookId', props.bookId);
    // $q.localStorage.set('chapterPage', page.value);
    update({page: `${page.value}`, bookId: props.bookId});
  }

  await loadInfo();
  await loadChapters();

  // console.log('route', route, router)
});

</script>
