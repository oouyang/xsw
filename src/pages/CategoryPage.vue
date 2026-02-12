<!-- src/pages/CategoryPage.vue -->
<template>
  <q-page class="q-pa-md">
    <div class="row items-center q-mb-md">
      <div class="text-h6">{{ displayCatName }}</div>
      <q-space />
      <q-btn flat icon="arrow_back" :to="{ name: 'Dashboard' }" />
    </div>

    <q-banner v-if="error" class="bg-red-2 text-red-10 q-mb-md">{{ error }}</q-banner>

    <!-- Endless scroll mode -->
    <template v-if="isEndless">
      <q-infinite-scroll :offset="250" @load="onEndlessLoad" ref="infiniteScrollRef">
        <div class="row q-col-gutter-md">
          <div class="col-12 col-sm-6 col-md-4 col-lg-3" v-for="b in allBooks" :key="b.bookurl">
            <BookCard :book="b" />
          </div>
        </div>
        <template v-slot:loading>
          <div class="row justify-center q-my-md">
            <q-spinner-dots color="primary" size="40px" />
          </div>
        </template>
      </q-infinite-scroll>
    </template>

    <!-- Paging mode (existing) -->
    <template v-else>
      <div class="row q-col-gutter-md">
        <div class="col-12 col-sm-6 col-md-4 col-lg-3" v-for="b in displayBooks" :key="b.bookurl">
          <BookCard :book="b" />
        </div>
      </div>

      <div class="row justify-center q-my-lg">
        <q-pagination
          v-model="page"
          :max="maxPages"
          @update:model-value="load"
          color="primary"
          max-pages="8"
        />
      </div>
    </template>
  </q-page>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue';
import type { QInfiniteScroll } from 'quasar';
import BookCard from 'components/BookCard.vue';
import type { BookSummary, Category } from 'src/types/book-api';
import { listBooksInCategory, getCategories } from 'src/services/bookApi';
import { useTextConversion } from 'src/composables/useTextConversion';
import { useAppConfig } from 'src/services/useAppConfig';
import { useRoute, useRouter } from 'vue-router';

const { convertIfNeeded } = useTextConversion();
const { config } = useAppConfig();
const route = useRoute();
const router = useRouter();

const props = defineProps<{ catId: string }>();
const books = ref<BookSummary[]>([]);
const page = ref(1);
const maxPages = ref(50); // heuristic; tune if you know the total
const catName = ref('');
const error = ref('');
const BOOKS_PER_PAGE = 12; // Limit books displayed per page for less scrolling

// Endless scroll state
const isEndless = computed(() => (config.value.scrollMode || 'paging') === 'endless');
const allBooks = ref<BookSummary[]>([]);
const endlessPage = ref(1);
const endlessFinished = ref(false);
const infiniteScrollRef = ref<QInfiniteScroll | null>(null);

// Convert category name for zh-CN users
const displayCatName = computed(() => convertIfNeeded(catName.value));

// Limit displayed books to reduce scrolling
const displayBooks = computed(() => books.value.slice(0, BOOKS_PER_PAGE));

async function load() {
  try {
    error.value = '';
    books.value = await listBooksInCategory(props.catId, page.value);
    // Sync URL with current page
    void router.replace({ query: { ...route.query, page: page.value } });
    // Scroll to top when page changes
    window.scrollTo({ top: 0, behavior: 'smooth' });
  } catch (e) {
    error.value = 'Load failed';
    console.log('e', e);
  }
}

async function onEndlessLoad(_index: number, done: (stop?: boolean) => void) {
  if (endlessFinished.value) {
    done(true);
    return;
  }
  try {
    endlessPage.value++;
    const newBooks = await listBooksInCategory(props.catId, endlessPage.value);
    if (!newBooks || newBooks.length === 0) {
      endlessFinished.value = true;
      done(true);
      return;
    }
    allBooks.value = [...allBooks.value, ...newBooks];
    done(false);
  } catch (e) {
    console.log('endless load error', e);
    endlessFinished.value = true;
    done(true);
  }
}

function resetEndless() {
  endlessPage.value = 1;
  endlessFinished.value = false;
  allBooks.value = [...books.value];
}

// Reset endless state when toggling mode
watch(isEndless, (val) => {
  if (val) {
    resetEndless();
  }
});

onMounted(async () => {
  // Read page from URL query if present
  const queryPage = Number(route.query.page);
  if (Number.isFinite(queryPage) && queryPage > 0) {
    page.value = queryPage;
  }

  try {
    const cats: Category[] = await getCategories();
    catName.value = cats.find((c) => c.id === props.catId)?.name || props.catId;
  } catch (e) {
    console.log('e', e);
  }
  await load();

  // Initialize endless mode if active
  if (isEndless.value) {
    resetEndless();
  }
});
watch(() => props.catId, () => {
  page.value = 1;
  void load().then(() => {
    if (isEndless.value) resetEndless();
  });
});
</script>
