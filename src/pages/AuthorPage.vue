<!-- src/pages/AuthorPage.vue -->
<template>
  <q-page class="q-pa-md">
    <div class="row items-center q-mb-md">
      <q-btn flat dense round icon="arrow_back" @click="router.back()" />
      <div class="text-h6 q-ml-sm">{{ $t('author.booksBy', { author: displayAuthorName }) }}</div>
      <q-space />
    </div>

    <!-- Sort buttons -->
    <div class="row items-center q-mb-sm q-gutter-xs">
      <q-btn
        v-for="opt in sortOptions" :key="opt.value"
        :outline="sortBy !== opt.value"
        :unelevated="sortBy === opt.value"
        :color="sortBy === opt.value ? 'primary' : 'grey'"
        :icon="opt.icon"
        :label="opt.label"
        size="sm"
        dense
        no-caps
        @click="sortBy = opt.value"
      />
    </div>

    <q-banner v-if="error" class="bg-red-2 text-red-10 q-mb-md">{{ error }}</q-banner>

    <div v-if="loading" class="row justify-center q-my-lg">
      <q-spinner-dots color="primary" size="40px" />
    </div>

    <div v-else-if="sortedBooks.length === 0 && !error" class="text-center text-grey-7 q-my-lg">
      {{ $t('author.noBooksFound') }}
    </div>

    <div v-else class="row q-col-gutter-md">
      <div class="col-12 col-sm-6 col-md-4 col-lg-3" v-for="b in sortedBooks" :key="b.bookurl || b.book_id || ''">
        <BookCard :book="b" />
      </div>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue';
import { useRouter } from 'vue-router';
import BookCard from 'components/BookCard.vue';
import type { BookSummary } from 'src/types/book-api';
import { listBooksByAuthor } from 'src/services/bookApi';
import { useTextConversion } from 'src/composables/useTextConversion';

const { convertIfNeeded } = useTextConversion();
const router = useRouter();

const props = defineProps<{ authorName: string }>();
const books = ref<BookSummary[]>([]);
const loading = ref(false);
const error = ref('');

// Sort state
type SortKey = 'default' | 'bookmark' | 'views';
const sortBy = ref<SortKey>('default');
const sortOptions: { value: SortKey; label: string; icon: string }[] = [
  { value: 'default', label: '預設', icon: 'sort' },
  { value: 'bookmark', label: '收藏', icon: 'bookmark' },
  { value: 'views', label: '觀看', icon: 'visibility' },
];

const displayAuthorName = computed(() => convertIfNeeded(props.authorName));

const sortedBooks = computed(() => {
  if (sortBy.value === 'default') return books.value;
  const sorted = [...books.value];
  if (sortBy.value === 'bookmark') {
    sorted.sort((a, b) => (b.bookmark_count ?? 0) - (a.bookmark_count ?? 0));
  } else if (sortBy.value === 'views') {
    sorted.sort((a, b) => (b.view_count ?? 0) - (a.view_count ?? 0));
  }
  return sorted;
});

async function load() {
  try {
    loading.value = true;
    error.value = '';
    books.value = await listBooksByAuthor(props.authorName);
  } catch (e) {
    error.value = 'Load failed';
    console.error('[AuthorPage] Error:', e);
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  void load();
});

watch(() => props.authorName, () => {
  void load();
});
</script>
