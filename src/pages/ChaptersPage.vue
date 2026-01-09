<!-- src/pages/ChaptersPage.vue -->
<template>
  <q-page class="q-pa-md">
    <div class="row items-center q-mb-sm">
      <div class="text-h6">{{ info?.name || 'Book' }}</div>
      <q-space />
      <q-btn flat icon="arrow_back" :to="{ name: 'Dashboard' }" label="Dashboard" />
    </div>

    <q-card class="q-mb-md">
      <q-card-section>
        <div class="text-subtitle2">by {{ info?.author }}</div>
        <div class="text-caption">
          Type: {{ info?.type }} | Status: {{ info?.status }} | Update: {{ info?.update }}
        </div>
        <div class="text-caption">Last: {{ info?.last_chapter_title }}</div>
      </q-card-section>
    </q-card>

    <q-banner v-if="error" class="bg-red-2 text-red-10 q-mb-md">{{ error }}</q-banner>

    <q-list bordered separator>
      <q-item v-for="c in chapters" :key="c.number" clickable :to="chapterLink(c.number)">
        <q-item-section>
          <div class="text-body2">#{{ c.number }} — {{ c.title }}</div>
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
        max-pages="8"
      />
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import type { BookInfo, ChapterRef } from 'src/types/book-api';
import { getBookInfo, getBookChapters } from 'src/services/bookApi';

const props = defineProps<{ bookId: string }>();
const info = ref<BookInfo | null>(null);
const chapters = ref<ChapterRef[]>([]);
const page = ref(1);
const maxPages = ref(50);
const error = ref('');

function chapterLink(num: number) {
  return { name: 'Chapter', params: { bookId: props.bookId, chapterNum: num } };
}

async function loadInfo() {
  try {
    info.value = await getBookInfo(props.bookId);
  } catch (e) {
    error.value = 'Load book info failed';
    console.log('e', e);
  }
}

async function loadChapters() {
  try {
    error.value = '';
    chapters.value = await getBookChapters(props.bookId, { page: page.value, all: false });
  } catch (e) {
    error.value = 'Load chapters failed';
    console.log('e', e);
  }
}

onMounted(async () => {
  await loadInfo();
  await loadChapters();
});
</script>
