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
            @click="goToLastChapter"
            size="sm"
            :disable="!bookId"
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
      <div class="row items-center q-gutter-sm q-mt-xs text-caption text-grey-7">
        <span v-if="book.bookmark_count" class="row items-center no-wrap">
          <q-icon name="bookmark_border" size="14px" class="q-mr-xs" />{{ displayBookmarkCount }}
        </span>
        <span v-if="book.view_count" class="row items-center no-wrap">
          <q-icon name="visibility" size="14px" class="q-mr-xs" />{{ displayViewCount }}
        </span>
      </div>
    </q-card-section>
    <q-card-section v-if="useItem" class="q-pt-none">
      <div class="ellipsis-3-lines">{{ displayIntro }}</div>
    </q-card-section>
    <q-separator v-if="useItem" />
    <q-card-actions align="between">
      <q-btn flat :label="lastLabel" @click="goToLastChapter" :disable="!bookId" class="text-wrap" />
      <q-btn v-if="false" color="primary" :to="bookLink" label="Open" />
    </q-card-actions>
  </q-card>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRouter } from 'vue-router';
import type { BookSummary } from 'src/types/book-api';
import { useTextConversion } from 'src/composables/useTextConversion';
import { fuzzCount, formatCount } from 'src/services/utils';

const { convertIfNeeded } = useTextConversion();
const router = useRouter();

const props = defineProps<{ book: BookSummary }>();
const bookId = computed(() => props.book.public_id || props.book.book_id || extractBookIdFromUrl(props.book.bookurl));
const bookLink = computed(() => ({ name: 'Chapters', params: { bookId: bookId.value } }));
const useItem = true;

// Computed properties for text conversion
const displayBookName = computed(() => convertIfNeeded(props.book.bookname));
const displayAuthor = computed(() => convertIfNeeded(props.book.author));
const displayIntro = computed(() => convertIfNeeded(props.book.intro));

// Fuzzed counts for display
const displayBookmarkCount = computed(() => formatCount(fuzzCount(props.book.bookmark_count)));
const displayViewCount = computed(() => formatCount(fuzzCount(props.book.view_count)));

// Navigate to chapters page at last page so user sees newest chapters
function goToLastChapter() {
  const id = bookId.value;
  if (!id) return;
  void router.push({ name: 'Chapters', params: { bookId: id }, query: { page: 'last' } });
}

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
