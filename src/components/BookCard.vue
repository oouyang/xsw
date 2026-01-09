<template>
  <q-card class="fit">
    <q-card-section>
      <div class="text-subtitle1">{{ book.bookname }}</div>
      <div class="text-caption text-grey">by {{ book.author }}</div>
    </q-card-section>
    <q-card-section class="q-pt-none">
      <div class="ellipsis-3-lines">{{ book.intro }}</div>
    </q-card-section>
    <q-separator />
    <q-card-actions align="between">
      <q-btn flat label="Last: {{ book.lastchapter }}" class="text-wrap" />
      <q-btn color="primary" :to="bookLink" label="Open" />
    </q-card-actions>
  </q-card>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { BookSummary } from 'src/types/book-api';

const props = defineProps<{ book: BookSummary }>();
const bookId = computed(() => props.book.book_id || extractBookIdFromUrl(props.book.bookurl));
const bookLink = computed(() => ({ name: 'Chapters', params: { bookId: bookId.value } }));

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
