<!-- src/pages/ChapterPage.vue -->
<template>
  <q-page class="q-pa-md">
    <div class="row items-center q-mb-sm">
      <div class="text-subtitle1">{{ title }}</div>
      <q-space />
      <q-btn flat icon="list" :to="{ name: 'Chapters', params: { bookId } }" label="Chapters" />
    </div>

    <q-banner v-if="error" class="bg-red-2 text-red-10 q-mb-md">{{ error }}</q-banner>

    <q-card>
      <q-card-section>
        <div v-if="loading"><q-skeleton type="text" v-for="i in 8" :key="i" /></div>
        <div v-else class="q-pb-lg" style="white-space: pre-wrap">{{ content }}</div>
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
import { getChapterContent, getBookInfo } from 'src/services/bookApi';

const props = defineProps<{ bookId: string; chapterNum: number }>();
const title = ref('');
const content = ref('');
const loading = ref(false);
const error = ref('');
const nocache = ref(false);
const lastChapter = ref<number | null>(null);

const navPrev = computed(() => ({
  name: 'Chapter',
  params: { bookId: props.bookId, chapterNum: props.chapterNum - 1 },
}));
const navNext = computed(() => {
  const nextNum = (props.chapterNum || 1) + 1;
  return { name: 'Chapter', params: { bookId: props.bookId, chapterNum: nextNum } };
});

async function loadMeta() {
  try {
    const info = await getBookInfo(props.bookId);
    lastChapter.value = info.last_chapter_number ?? null;
  } catch (e) {
    console.log('e', e);
  }
}
async function load() {
  loading.value = true;
  error.value = '';
  try {
    const data = await getChapterContent(props.bookId, Number(props.chapterNum), nocache.value);
    title.value = data.title || `Chapter ${props.chapterNum}`;
    content.value = data.text;
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
