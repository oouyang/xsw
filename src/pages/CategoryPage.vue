<!-- src/pages/CategoryPage.vue -->
<template>
  <q-page class="q-pa-md">
    <div class="row items-center q-mb-md">
      <div class="text-h6">Category: {{ catName }}</div>
      <q-space />
      <q-btn flat icon="arrow_back" :to="{ name: 'Dashboard' }" label="Dashboard" />
    </div>

    <q-banner v-if="error" class="bg-red-2 text-red-10 q-mb-md">{{ error }}</q-banner>

    <div class="row q-col-gutter-md">
      <div class="col-12 col-sm-6 col-md-4 col-lg-3" v-for="b in books" :key="b.bookurl">
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
  </q-page>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue';
import BookCard from 'components/BookCard.vue';
import type { BookSummary, Category } from 'src/types/book-api';
import { listBooksInCategory, getCategories } from 'src/services/bookApi';

const props = defineProps<{ catId: string }>();
const books = ref<BookSummary[]>([]);
const page = ref(1);
const maxPages = ref(50); // heuristic; tune if you know the total
const catName = ref('');
const error = ref('');

async function load() {
  try {
    error.value = '';
    books.value = await listBooksInCategory(Number(props.catId), page.value);
  } catch (e) {
    error.value = 'Load failed';
    console.log('e', e);
  }
}
onMounted(async () => {
  try {
    const cats: Category[] = await getCategories();
    catName.value = cats.find((c) => c.id === props.catId)?.name || props.catId;
  } catch (e) {
    console.log('e', e);
  }
  await load();
});
watch(() => props.catId, load);
</script>
