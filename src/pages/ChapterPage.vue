<!-- src/pages/ChapterPage.vue -->
<template>
  <q-page class="q-pa-md">
    <div class="row items-center q-mb-sm">
      <q-breadcrumbs>
        <q-breadcrumbs-el :label="config.name" icon="home" to="/" />
        <q-breadcrumbs-el :label="'📜' + (displayBookName || 'Book')" />
        <q-breadcrumbs-el :label="$t('nav.chapters')" icon="list" :to="`/book/${info?.book_id}/chapters`" />
        <q-breadcrumbs-el :label="displayChapterTitle || displayTitle || `${$t('chapter.chapter')} ${chapterNum}`" />
      </q-breadcrumbs>
      <q-space />
      <q-btn flat icon="list" :to="{ name: 'Chapters', params: { bookId } }" :label="$t('nav.chapters')" />
    </div>

    <q-banner v-if="error" class="bg-red-2 text-red-10 q-mb-md">
      <div class="row items-center">
        <div class="col">{{ error }}</div>
        <q-btn flat color="red-10" :label="$t('common.retry')" icon="refresh" @click="reload" />
      </div>
    </q-banner>

    <q-card>
      <q-card-section>
        <div v-if="loading"><q-skeleton type="text" v-for="i in 8" :key="i" /></div>
        <div
          v-else
          class="q-pb-lg"
          :class="`text-h${fontsize}`"
          style="white-space: pre-wrap"
        >
        <p v-for="(value, index) in displayContent" :key="index" class="q-my-xl">{{ value }}</p>
      </div>
      </q-card-section>
    </q-card>

    <div class="row q-my-md q-gutter-sm">
      <q-btn outline :disable="chapterNum <= 1" :to="navPrev" icon="chevron_left" :label="$t('chapter.prev')" />
      <q-btn outline :to="navNext" icon-right="chevron_right" :label="$t('chapter.next')" />
      <q-space />
      <q-toggle v-model="nocache" :label="$t('chapter.bypassCache')" @update:model-value="reload" />
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue';
import { getChapterContent, getBookInfo, getBookChapters } from 'src/services/bookApi';
import { useAppConfig } from 'src/services/useAppConfig';
import type { BookInfo, ChapterRef } from 'src/types/book-api';
import { nextTick } from 'process';
import { chapterLink, syncLastChapter } from 'src/services/utils';
import { useTextConversion } from 'src/composables/useTextConversion';

const { config, update } = useAppConfig();
const fontsize = computed(() => Number(config.value.fontsize) || 7)
const { convertIfNeeded } = useTextConversion();

const props = defineProps<{ bookId: string; chapterNum: number; chapterTitle?: string }>();
const title = ref('');
const content = ref<Array<string>>([]);
const loading = ref(false);
const error = ref('');
const nocache = ref(false);
const lastChapter = ref<number | null>(null);
const {bookId, chapterNum, chapterTitle} = props

const chapterIndex = computed(() => {
  const index = chapters.value.findIndex(
    c => c.number === chapterNum && c.title === chapterTitle
  )
  return index === -1 ? 0 : index
})
const navPrev = computed(() => {
  const index = Math.max(0, chapterIndex.value - 1);
  return chapterLink(chapters.value[index]?.number || 1, chapters.value[index]?.title || '')
});
const navNext = computed(() => {
  const index = Math.min(chapterIndex.value + 1, chapters.value.length + 1);
  return chapterLink(chapters.value[index]?.number || 1, chapters.value[index]?.title || '')
});
const chapters = computed<ChapterRef[]>(() => 
{
  const raw = config.value?.chapters ?? '[]'
  try {
    return JSON.parse(raw) as ChapterRef[]
  } catch {
    return []
  }
})
async function loadAllChapters() {
  try {
    const storedchapters = JSON.parse(config.value.chapters||'[]')

    // Check if cache is outdated by comparing with expected last chapter
    const cachedLastChapter = storedchapters.length > 0
      ? storedchapters.reduce((max: number, ch: ChapterRef) => ch.number > max ? ch.number : max, 0)
      : 0;
    const expectedLastChapter = lastChapter.value || 0;
    const isCacheOutdated = cachedLastChapter < expectedLastChapter;

    // Re-fetch if: bookId changed, no cache, OR cache is outdated/incomplete
    if (props.bookId !== config.value.bookId || storedchapters.length === 0 || isCacheOutdated) {
      if (isCacheOutdated) {
        console.log(
          `[loadAllChapters] Cache outdated (has ${cachedLastChapter}, expected ${expectedLastChapter}), re-fetching all chapters`
        );
      }

      const requests = []
      for (let i = 0; i < pages.value; i++) {
        requests.push(
          getBookChapters(props.bookId, { page: i+1, all: false })
        )
      }
      const results = await Promise.all(requests)

      // 假設每頁回傳 resp.data 或 resp.chapters（依你的 API 命名調整）

      update({bookId: props.bookId});
      update({chapters: JSON.stringify(results.flatMap(r => r))});
      update({chapter: JSON.stringify(chapters.value[chapterIndex.value])});

      console.log(`[loadAllChapters] Fetched ${results.flatMap(r => r).length} chapters across ${pages.value} pages`);
    } else {
      console.log(`[loadAllChapters] Using cached chapters (${storedchapters.length} chapters, last: ${cachedLastChapter})`);
    }

    // Sync last chapter info with loaded chapters
    if (info.value && chapters.value.length > 0) {
      info.value = syncLastChapter(info.value, chapters.value);
    }

    console.log('chapters.value[chapterIndex])', chapters.value[chapterIndex.value], chapterNum);
  } catch (e) {
    console.error('Failed to load chapters list:', e);
    throw e; // Re-throw to let caller handle it
  }
}
const info = ref<BookInfo|undefined>(undefined)
const pages = ref(1)

// Computed properties for CN to TW conversion
const displayBookName = computed(() => convertIfNeeded(info.value?.name));
const displayTitle = computed(() => convertIfNeeded(title.value));
const displayChapterTitle = computed(() => convertIfNeeded(chapterTitle));
const displayContent = computed(() =>
  content.value.map(paragraph => convertIfNeeded(paragraph))
);

async function loadMeta() {
  try {
    info.value = await getBookInfo(props.bookId);
    lastChapter.value = info.value.last_chapter_number ?? null;
    // Calculate number of pages: divide by page size (20) and round up
    pages.value = Math.ceil((lastChapter?.value || 1) / 20);

    nextTick(() => {
      void loadAllChapters()
    });

    // Sync last chapter in background by loading last page
    void syncLastPageInBackground();
  } catch (e) {
    console.log('e', e);
  }
}

/**
 * Fetch the last page of chapters in the background to sync last chapter info
 * This ensures book info shows the actual latest chapter, not outdated cached info
 */
async function syncLastPageInBackground() {
  try {
    // Calculate last page number
    const lastPageNum = Math.ceil((lastChapter.value || 100) / 20);

    console.log(`[ChapterPage] Fetching last page (${lastPageNum}) in background to sync last chapter`);
    const lastPageChapters = await getBookChapters(props.bookId, {
      page: lastPageNum,
      all: false
    });

    const chaptersArray = Array.isArray(lastPageChapters)
      ? lastPageChapters
      : lastPageChapters.chapters;

    if (info.value && chaptersArray && chaptersArray.length > 0) {
      const oldLastChapter = info.value.last_chapter_number;
      info.value = syncLastChapter(info.value, chaptersArray);

      if (info.value.last_chapter_number !== oldLastChapter) {
        console.log(
          `[ChapterPage] ✅ Synced last chapter: ${oldLastChapter} → ${info.value.last_chapter_number}`
        );
        // Update lastChapter ref
        lastChapter.value = info.value.last_chapter_number ?? null;
      }
    }
  } catch (e) {
    console.warn('[ChapterPage] Failed to sync last page:', e);
    // Non-critical error, don't show to user
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
async function load() {
  loading.value = true;
  error.value = '';

  try {
    // Ensure metadata is loaded first
    if (!info.value) {
      console.log('Waiting for metadata to load...');
      await loadMeta();
    }

    // Ensure chapters are loaded
    if (chapters.value.length === 0) {
      console.log('Loading chapters list...');
      await loadAllChapters();
    }

    console.log(`Loading chapter ${props.chapterNum}: ${chapterTitle}`);
    const data = await getChapterContent(props.bookId, Number(props.chapterNum), nocache.value);

    if (!data || !data.text) {
      throw new Error('No content returned from API');
    }

    title.value = data.title || chapterTitle || `${props.chapterNum}`;
    content.value = data.text.split(' ');
    removeTitleWordsFromContent()
    content.value = content.value.filter(Boolean)

    // Update browser title with book name and chapter title
    if (info.value?.name && title.value) {
      document.title = `${config.value.name} - ${info.value.name} - ${title.value}`;
    } else if (title.value) {
      document.title = `${config.value.name} - ${title.value}`;
    }

    console.log(`Successfully loaded chapter ${props.chapterNum}`);
  } catch (e: unknown) {
    let errorMsg = 'Unknown error';

    // Extract detailed error information from axios error
    if (typeof e === 'object' && e !== null && 'response' in e) {
      const axiosError = e as { response?: { status?: number; statusText?: string; data?: { message?: string; error?: string } } };
      const status = axiosError.response?.status || 'Unknown';
      const statusText = axiosError.response?.statusText || '';
      const serverMsg = axiosError.response?.data?.message || axiosError.response?.data?.error || '';
      errorMsg = `${status} ${statusText}${serverMsg ? ': ' + serverMsg : ''}`;
    } else if (e instanceof Error) {
      errorMsg = e.message;
    } else {
      errorMsg = String(e);
    }

    error.value = `Load content failed: ${errorMsg}`;
    console.error('Failed to load chapter content:', {
      bookId: props.bookId,
      chapterNum: props.chapterNum,
      chapterTitle: chapterTitle,
      error: e,
      response: typeof e === 'object' && e !== null && 'response' in e ? (e as { response?: unknown }).response : undefined,
      responseData: typeof e === 'object' && e !== null && 'response' in e ? (e as { response?: { data?: unknown } }).response?.data : undefined
    });
  } finally {
    loading.value = false;
  }
}
async function reload() {
  // Force bypass cache on manual retry
  const originalNocache = nocache.value;
  nocache.value = true;
  try {
    await load();
  } finally {
    // Restore original nocache setting after retry
    nocache.value = originalNocache;
  }
}

onMounted(async () => {
  await loadMeta();
  await load();

  // Update the current chapter in config for breadcrumbs
  const currentChapter = chapters.value[chapterIndex.value];
  if (currentChapter) {
    update({ chapter: JSON.stringify(currentChapter) });
  }

  console.log('fontsize ', fontsize.value)
});

// Track the current loading request to prevent race conditions
let currentLoadRequest = 0;
let debounceTimer: NodeJS.Timeout | null = null;

// Watch both chapterNum and chapterTitle to reload when navigation happens
watch(() => [props.chapterNum, props.chapterTitle], () => {
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
          const currentChapter = chapters.value[chapterIndex.value];
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
});
</script>

<style scoped>
p {
  text-indent: 2em;
}
</style>
