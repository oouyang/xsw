<!-- src/pages/ChaptersPage.vue -->
<template>
  <q-page class="q-pa-md">
    <div class="row items-center q-mb-sm">
      <q-breadcrumbs>
        <q-breadcrumbs-el :label="config.name" icon="home" to="/" />
        <q-breadcrumbs-el :label="'📜' + info?.name || 'Book'" />
        <q-breadcrumbs-el label="目錄"  :to="`/book/${info?.book_id}/chapters`" />
        <q-breadcrumbs-el :label="`${page}`" />
      </q-breadcrumbs>
      <q-space />
      <q-btn flat icon="arrow_back" :to="{ name: 'Dashboard' }" label="🏛️" />
    </div>

    <q-card class="q-mb-md">
      <q-card-section>
        <div class="text-subtitle2">👤 {{ info?.author }}</div>
        <div class="text-caption">
          🏷️ {{ info?.type }} | 🚨 {{ info?.status }} | 🗓️ {{ info?.update }}
        </div>
        <div class="text-caption">⚡ {{ info?.last_chapter_title }}</div>
      </q-card-section>
    </q-card>

    <q-banner v-if="error" class="bg-red-2 text-red-10 q-mb-md">{{ error }}</q-banner>

    <div class="row justify-center q-my-lg">
      <q-pagination
        v-model="page"
        :max="maxPages"
        @update:model-value="loadChapters"
        color="primary"
        max-pages="12"
      />
    </div>

    <q-list bordered separator>
      <q-item
        v-for="c in chapters.chapters"
        :key="c.number"
        clickable
        :to="chapterLink(c.number, c.title)"
      >
        <q-item-section>
          <div class="text-body2">{{ c.title }}</div>
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
        max-pages="12"
      />
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue';
import type { BookInfo, Chapters } from 'src/types/book-api';
import { getBookInfo, getBookChapters } from 'src/services/bookApi';
import { useQuasar, useMeta } from 'quasar';
import { useRoute, useRouter } from 'vue-router';
import { useAppConfig } from 'src/services/useAppConfig';
import { chapterLink } from 'src/services/utils';

const { config, update } = useAppConfig();

const $q = useQuasar();
const route = useRoute();
const router = useRouter();

const props = defineProps<{ bookId: string }>();
const info = ref<BookInfo | null>(null);
const chapters = ref<Chapters>({} as Chapters);
const page = ref(Number(config.value?.page) || 1);
const maxPages = ref(50);
const error = ref('');

useMeta({ title: `${config.value.name} ${info.value?.name ? ' >> '+ info.value?.name : ''}` });

watch(page, (newVal, oldVal) => {
  // $q.localStorage.setItem('chapterPage', page.value)
  update({page: `${page.value}`});
  void router.replace({
    query: {
      ...route.query,
      page: newVal
    }
  })
  console.log(`page changed from ${oldVal} to ${newVal} -`, $q.localStorage.getItem('chapterPage'));
});


watch(
  () => props.bookId,
  async (newBookId, oldBookId) => {
    if (newBookId !== oldBookId) {
      // Reset page for a new book
      page.value = 1;
      // $q.localStorage.set('bookId', newBookId);
      // $q.localStorage.set('chapterPage', 1);
        update({page: `${page.value},`, bookId: newBookId});
        update({chapters: undefined});

      // ✅ Properly handle the promise
      try {
        await loadChapters(); // reload chapters for page 1
      } catch (err) {
        console.error('Failed to reload chapters:', err);
        error.value = 'Load chapters failed';
      }
    }
  }
);


async function loadInfo() {
  try {
    info.value = await getBookInfo(props.bookId);
    maxPages.value = 1 + Math.ceil(info.value?.last_chapter_number || 100) / 20;
  } catch (e) {
    error.value = 'Load book info failed';
    console.log('e', e);
  }
}

async function loadChapters() {
  try {
    error.value = '';
    const resp = await getBookChapters(props.bookId, { page: page.value, all: false });
    chapters.value.chapters = Array.isArray(resp) ? resp : resp.chapters;
    // maxPages.value = Array.isArray(resp) ? 50 : chapters.value.totalPages||0;
    console.log('chapters is array ', Array.isArray(resp));
  } catch (e) {
    error.value = 'Load chapters failed';
    console.log('e', e);
  }
}

onMounted(async () => {
  const storedBookId = config.value.bookId; // $q.localStorage.getItem('bookId');
  const storedPage = Number(config.value.page); // Number($q.localStorage.getItem('chapterPage')) || 1;

  if (route.query.page) {
    page.value = Number(route.query.page)
    // $q.localStorage.set('bookId', props.bookId);
    // $q.localStorage.set('chapterPage', page.value);
    update({page: `${page.value},`, bookId: props.bookId});
  } else if (storedBookId === props.bookId) {
    page.value = storedPage;
  } else {
    page.value = 1;
    // $q.localStorage.set('bookId', props.bookId);
    // $q.localStorage.set('chapterPage', page.value);
    update({page: `${page.value},`, bookId: props.bookId});
  }

  await loadInfo();
  await loadChapters();

  // console.log('route', route, router)
});

</script>
