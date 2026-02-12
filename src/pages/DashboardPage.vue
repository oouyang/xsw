<!-- src/pages/DashboardPage.vue -->
<template>
  <q-page class="q-pa-md">
    <div class="row items-center q-mb-md">
      <div class="text-h4">{{ config.name }}</div>
      <q-space />
      <q-btn flat icon="refresh" @click="load" />
    </div>

    <!-- Continue Reading section -->
    <div v-if="readingHistory.length > 0" class="q-mb-lg">
      <div class="row items-center q-mb-sm">
        <div class="text-h6">{{ $t('dashboard.continueReading') }}</div>
        <q-space />
        <q-btn flat dense size="sm" :label="$t('common.clear')" @click="clearReadingHistory" />
      </div>
      <q-separator class="q-mb-sm" />
      <div class="row q-gutter-sm" style="overflow-x: auto; flex-wrap: nowrap;">
        <ContinueReadingCard
          v-for="entry in readingHistory"
          :key="entry.bookId"
          :entry="entry"
          @remove="removeHistoryEntry"
        />
      </div>
    </div>

    <q-banner v-if="error" class="bg-red-2 text-red-10 q-mb-md">{{ error }}</q-banner>

    <q-skeleton v-if="loading" type="rect" height="36px" class="q-mb-md" />
    <div class="column q-gutter-xl">
      <div v-for="cat in displayCategories" :key="cat.id" v-intersection="onCategoryVisible(cat.id)">
        <div class="row items-center q-mb-sm">
          <div class="text-h6">{{ cat.name }}</div>
          <q-space />
          <q-btn flat :to="{ name: 'Category', params: { catId: cat.id } }" :label="$t('category.viewAll')" />
        </div>
        <q-separator />

        <!-- Loading skeleton for category books -->
        <div v-if="!loadedCategories.has(cat.id)" class="row q-col-gutter-md q-mt-sm">
          <div class="col-12 col-sm-6 col-md-4 col-lg-3" v-for="i in 8" :key="i">
            <q-skeleton type="rect" height="200px" />
          </div>
        </div>

        <!-- Actual books -->
        <div v-else class="row q-col-gutter-md">
          <div
            class="col-12 col-sm-6 col-md-4 col-lg-3"
            v-for="book in topBooks[cat.id] || []"
            :key="book.bookurl"
          >
            <BookCard :book="book" />
          </div>
        </div>
      </div>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import BookCard from 'components/BookCard.vue';
import ContinueReadingCard from 'components/ContinueReadingCard.vue';
import type { Category, BookSummary } from 'src/types/book-api';
import { getCategories, listBooksInCategory } from 'src/services/bookApi';
import { useAppConfig } from 'src/services/useAppConfig';
import { useTextConversion } from 'src/composables/useTextConversion';
import { useReadingHistory } from 'src/composables/useReadingHistory';

const { convertIfNeeded } = useTextConversion();
const { history: readingHistory, clearHistory: clearReadingHistoryFn, removeEntry: removeHistoryEntry } = useReadingHistory();

function clearReadingHistory() {
  clearReadingHistoryFn();
}

const categories = ref<Category[]>([]);
const topBooks = ref<Record<string, BookSummary[]>>({});
const loading = ref(false);
const error = ref('');
const { config } = useAppConfig();
const loadedCategories = ref<Set<string>>(new Set());

// Cache configuration
const CACHE_KEY = 'dashboard_cache:v2';
const CACHE_KEY_OLD = 'dashboard_cache';
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

interface CachedData {
  categories: Category[];
  topBooks: Record<string, BookSummary[]>;
  loadedCategories: string[];
  timestamp: number;
}

// Convert category names for zh-CN users
const displayCategories = computed(() => {
  if (!Array.isArray(categories.value)) {
    return [];
  }
  return categories.value.map(cat => ({
    ...cat,
    name: convertIfNeeded(cat.name)
  }));
});

function loadFromCache(): CachedData | null {
  try {
    const cached = localStorage.getItem(CACHE_KEY);
    if (!cached) return null;

    const data: CachedData = JSON.parse(cached);
    const age = Date.now() - data.timestamp;

    if (age > CACHE_TTL) {
      console.log('[Dashboard Cache] Cache expired');
      return null;
    }

    console.log(`[Dashboard Cache] Using cached data (${Math.round(age / 1000)}s old)`);
    return data;
  } catch (e) {
    console.warn('[Dashboard Cache] Failed to load cache:', e);
    return null;
  }
}

function saveToCache(data: CachedData) {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(data));
    console.log('[Dashboard Cache] Saved to cache');
  } catch (e) {
    console.warn('[Dashboard Cache] Failed to save cache:', e);
  }
}

async function loadCategoryBooks(catId: string) {
  if (loadedCategories.value.has(catId)) return;

  try {
    loadedCategories.value.add(catId);
    const books = await listBooksInCategory(catId, 1);
    topBooks.value[catId] = books.slice(0, 8);

    // Update cache with newly loaded category
    saveToCache({
      categories: categories.value,
      topBooks: topBooks.value,
      loadedCategories: Array.from(loadedCategories.value),
      timestamp: Date.now()
    });
  } catch (e) {
    console.error(`[Dashboard] Failed to load category ${catId}:`, e);
    loadedCategories.value.delete(catId);
  }
}

function onCategoryVisible(catId: string) {
  return (entry: IntersectionObserverEntry) => {
    if (entry.isIntersecting) {
      void loadCategoryBooks(catId);
    }
  };
}

async function fetchFreshData() {
  error.value = '';
  try {
    const result = await getCategories();
    // Ensure we have an array
    categories.value = Array.isArray(result) ? result : [];

    if (categories.value.length === 0) {
      error.value = 'No categories found';
      return;
    }

    // Don't load all category books - let lazy loading handle it
    // Just save the categories to cache
    saveToCache({
      categories: categories.value,
      topBooks: topBooks.value,
      loadedCategories: Array.from(loadedCategories.value),
      timestamp: Date.now()
    });
  } catch (e) {
    error.value = 'Load failed';
    console.log('e', e);
  } finally {
    loading.value = false;
  }
}

async function load() {
  // Remove stale v1 cache (had czbooks IDs, no public_id)
  localStorage.removeItem(CACHE_KEY_OLD);

  // Try to load from cache first (stale-while-revalidate)
  const cached = loadFromCache();
  if (cached) {
    // Show cached data immediately
    categories.value = cached.categories;
    topBooks.value = cached.topBooks;
    loadedCategories.value = new Set(cached.loadedCategories || []);
    // Fetch fresh categories list in background (no loading indicator)
    void fetchFreshData();
    return;
  }

  // No cache - show loading indicator
  loading.value = true;
  await fetchFreshData();
}

onMounted(load);
</script>
