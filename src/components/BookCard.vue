<template>
  <q-card ass="fit">
    <q-card-section v-if="!useItem">
      <q-item>
        <q-item-section>
          <q-btn flat :to="bookLink">
            <span class="text-subtitle1">{{ displayBookName }} </span></q-btn
          >
          <q-item-label caption lines="2" :title="displayIntro">{{ displayIntro }}</q-item-label>
        </q-item-section>

        <q-item-section side top>
          <q-item-label caption lines="2">👤 {{ displayAuthor }}</q-item-label>
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
          <q-btn flat :to="bookLink">{{ displayBookName }}</q-btn>
        </span>
        <span class="text-caption text-grey"> 👤 {{ displayAuthor }}</span>
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
      <div class="ellipsis-3-lines">{{ displayIntro }}</div>
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
import { useTextConversion } from 'src/composables/useTextConversion';

const { convertIfNeeded } = useTextConversion();

const props = defineProps<{ book: BookSummary }>();
const bookId = computed(() => props.book.book_id || extractBookIdFromUrl(props.book.bookurl));
const bookLink = computed(() => ({ name: 'Chapters', params: { bookId: bookId.value } }));
const useItem = true;

// Computed properties for text conversion
const displayBookName = computed(() => convertIfNeeded(props.book.bookname));
const displayAuthor = computed(() => convertIfNeeded(props.book.author));
const displayIntro = computed(() => convertIfNeeded(props.book.intro));

// Last chapter link - always go to chapters page since we use sequential indexing
// The source website's chapter numbers may not match our sequential index
const lastLink = computed(() => {
  const id = bookId.value;
  if (!id) return null;

  // Link to chapters page instead of specific chapter to avoid mismatches
  // between source website chapter numbers and our sequential indexing
  return { name: 'Chapters', params: { bookId: id } };
});

const lastLabel = computed(() => {
  const lc = props.book.lastchapter?.trim();
  const converted = lc ? convertIfNeeded(lc) : '—';
  return `⚡ ${converted}`;
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
