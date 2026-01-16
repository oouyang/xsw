<template>
  <q-card ass="fit">
    <q-card-section v-if="!useItem">
      <q-item>
        <q-item-section>
          <q-btn flat :to="bookLink">
            <span class="text-subtitle1">{{ book.bookname }} </span></q-btn
          >
          <q-item-label caption lines="2" :title="book.intro">{{ book.intro }}</q-item-label>
        </q-item-section>

        <q-item-section side top>
          <q-item-label caption lines="2">👤 {{ book.author }}</q-item-label>
          <q-btn
            flat
            style="width: 230px"
            :to="lastLink"
            size="sm"
            :disable="!lastLink"
            class="text-wrap"
          >
            <div class="ellipsis text-right">
              {{ lastLabel }}
            </div>
          </q-btn>
        </q-item-section>
      </q-item>
    </q-card-section>
    <q-card-section v-if="useItem">
      <div>
        <span class="text-subtitle1">
          <q-btn flat :to="bookLink">{{ book.bookname }}</q-btn>
        </span>
        <span class="text-caption text-grey"> 👤 {{ book.author }}</span>
      </div>
      <div v-if="false">
        <span
          ><q-btn
            flat
            style="width: 250px"
            :to="lastLink"
            size="sm"
            :disable="!lastLink"
            class="text-wrap"
          >
            <div class="ellipsis">
              {{ lastLabel }}
            </div>
          </q-btn>
        </span>
      </div>
    </q-card-section>
    <q-card-section v-if="useItem" class="q-pt-none">
      <div class="ellipsis-3-lines">{{ book.intro }}</div>
    </q-card-section>
    <q-separator v-if="useItem" />
    <q-card-actions align="between">
      <q-btn flat :label="lastLabel" :to="lastLink" :disable="!lastLink" class="text-wrap" />
      <q-btn v-if="false" color="primary" :to="bookLink" label="Open" />
    </q-card-actions>
  </q-card>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { BookSummary } from 'src/types/book-api';

const props = defineProps<{ book: BookSummary }>();
const bookId = computed(() => props.book.book_id || extractBookIdFromUrl(props.book.bookurl));
const bookLink = computed(() => ({ name: 'Chapters', params: { bookId: bookId.value } }));
const useItem = true;

const lastChapterNum = computed<number | null>(() => {
  const text = props.book.lastchapter ?? '';
  // Match "第<digits>章" optionally with spaces; supports Chinese numeral context
  const m = text.match(/第\s*(\d+)\s*章/);
  return m ? Number(m[1]) : null;
});

const lastLink = computed(() => {
  const id = bookId.value;
  const num = lastChapterNum.value;

  if (!id) return null;

  if (typeof num === 'number' && Number.isFinite(num)) {
    return { name: 'ChapterContent', params: { bookId: id, chapterNum: num } };
  }
  // Fallback to chapter list when we can't parse the chapter number
  return { name: 'Chapters', params: { bookId: id } };
});

const lastLabel = computed(() => {
  const lc = props.book.lastchapter?.trim();
  return lc ? `⚡ ${lc}` : '⚡ —';
});

function extractBookIdFromUrl(url: string): string {
  // Fallback: derive id from bookurl if API doesn’t supply book_id
  // Example: /12345/ → "12345"
  const m = url.match(/\/(\d+)\//);
  return m?.[1] ?? url;
}
</script>

<style scoped>
.ellipsis-3-lines {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
