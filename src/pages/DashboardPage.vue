<!-- src/pages/DashboardPage.vue -->
<template>
  <q-page class="q-pa-md">
    <div class="row items-center q-mb-md">
      <div class="text-h4">{{ config.name }}</div>
      <q-space />
      <q-btn flat icon="refresh" @click="load" />
    </div>

    <q-banner v-if="error" class="bg-red-2 text-red-10 q-mb-md">{{ error }}</q-banner>

    <q-skeleton v-if="loading" type="rect" height="36px" class="q-mb-md" />
    <div class="column q-gutter-xl">
      <div v-for="cat in displayCategories" :key="cat.id">
        <div class="row items-center q-mb-sm">
          <div class="text-h6">{{ cat.name }}</div>
          <q-space />
          <q-btn flat :to="{ name: 'Category', params: { catId: cat.id } }" :label="$t('category.viewAll')" />
        </div>
        <q-separator />

        <div class="row q-col-gutter-md">
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
import type { Category, BookSummary } from 'src/types/book-api';
import { getCategories, listBooksInCategory } from 'src/services/bookApi';
import { useAppConfig } from 'src/services/useAppConfig';
import { useTextConversion } from 'src/composables/useTextConversion';

const { convertIfNeeded } = useTextConversion();

const categories = ref<Category[]>([]);
const topBooks = ref<Record<string, BookSummary[]>>({});
const loading = ref(false);
const error = ref('');
const { config } = useAppConfig();

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

async function load() {
  loading.value = true;
  error.value = '';
  try {
    const result = await getCategories();
    // Ensure we have an array
    categories.value = Array.isArray(result) ? result : [];

    if (categories.value.length === 0) {
      error.value = 'No categories found';
      return;
    }

    // For each category, fetch page 1 and keep top 10
    const promises = categories.value.map(async (cat: Category) => {
      const books = await listBooksInCategory(Number(cat.id), 1);
      topBooks.value[cat.id] = books.slice(0, 10);
    });
    await Promise.all(promises);
  } catch (e) {
    error.value = 'Load failed';
    console.log('e', e);
  } finally {
    loading.value = false;
  }
}
onMounted(load);
</script>
