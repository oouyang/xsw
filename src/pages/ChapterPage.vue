<!-- src/pages/ChapterPage.vue -->
<template>
  <q-page class="q-pa-md">
    <div class="row items-center q-mb-sm">
      <q-breadcrumbs>
        <q-breadcrumbs-el :label="config.name" icon="home" to="/" />
        <q-breadcrumbs-el :label="'📜' + info?.name || 'Book'" />
        <q-breadcrumbs-el label="目錄" icon="list" :to="`/book/${info?.book_id}/chapters`" />
        <q-breadcrumbs-el :label="`${title}`" />
      </q-breadcrumbs>
      <q-space />
      <q-btn flat icon="list" :to="{ name: 'Chapters', params: { bookId } }" label="Chapters" />
    </div>

    <q-banner v-if="error" class="bg-red-2 text-red-10 q-mb-md">{{ error }}</q-banner>

    <q-card>
      <q-card-section>
        <div v-if="loading"><q-skeleton type="text" v-for="i in 8" :key="i" /></div>
        <div
          v-else
          class="q-pb-lg"
          :class="`text-h${config.fontsize}`"
          style="white-space: pre-wrap"
        >
        <p v-for="value in content" :key="value" class="q-my-xl">{{ value }}</p>
      </div>
      </q-card-section>
    </q-card>

    <div class="row q-my-md q-gutter-sm">
      <q-btn outline :disable="chapterNum <= 1" :to="navPrev" icon="chevron_left" label="Prev" />
      <q-btn outline :to="navNext" icon-right="chevron_right" label="Next" />
      <q-space />
      <q-toggle v-model="nocache" label="Bypass cache" @update:model-value="reload" />
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { getChapterContent, getBookInfo, getBookChapters } from 'src/services/bookApi';
import { useAppConfig } from 'src/services/useAppConfig';
import type { BookInfo, ChapterRef } from 'src/types/book-api';
import { nextTick } from 'process';
import { chapterLink } from 'src/services/utils';

const { config, update } = useAppConfig();


const props = defineProps<{ bookId: string; chapterNum: number; chapterTitle?: string }>();
const title = ref('');
const content = ref<Array<string>>([]);
const loading = ref(false);
const error = ref('');
const nocache = ref(false);
const lastChapter = ref<number | null>(null);
const {bookId, chapterNum, chapterTitle} = props

const chapterIndex = computed(() => chapters.value.findIndex(
      c => c.number === chapterNum && c.title === chapterTitle
    ) || 0)
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
    const requests = []
    for (let i = 0; i < pages.value; i++) {
      requests.push(
        getBookChapters(props.bookId, { page: i+1, all: false })
      )
    }
    const results = await Promise.all(requests)

    // 假設每頁回傳 resp.data 或 resp.chapters（依你的 API 命名調整）
    const chapterIndex = chapters.value.findIndex(
      c => c.number === chapterNum
    )

    update({chapters: JSON.stringify(results.flatMap(r => r))});
    update({chapter: JSON.stringify(chapters.value[chapterIndex])});
    console.log('chapters.value[chapterIndex])', chapters.value[chapterIndex], chapterNum);
}
const info = ref<BookInfo|undefined>(undefined)
const pages = ref(1)
async function loadMeta() {
  try {
    info.value = await getBookInfo(props.bookId);
    lastChapter.value = info.value.last_chapter_number ?? null;
    pages.value = ((lastChapter?.value || 1) / 20);

    nextTick(() => {
      void loadAllChapters()
    });
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
async function load() {
  loading.value = true;
  error.value = '';
  try {
    const data = await getChapterContent(props.bookId, Number(props.chapterNum), nocache.value);
    title.value = data.title || chapterTitle || `${props.chapterNum}`;
    content.value = data.text.split(' ');
    removeTitleWordsFromContent()
    content.value = content.value.filter(Boolean)
  } catch (e) {
    error.value = 'Load content failed';
    console.log('e', e);
  } finally {
    loading.value = false;
  }
}
async function reload() {
  await load();
}

onMounted(async () => {
  await loadMeta();
  await load();
});
watch(() => props.chapterNum, load);
</script>

<style scoped>
p {
  text-indent: 2em;
}
</style>
