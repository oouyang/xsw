<!-- src/components/SearchDialog.vue -->
<template>
  <q-dialog ref="dialogRef" @hide="onDialogHide">
    <q-card style="min-width: 350px; max-width: 600px; width: 90vw;">
      <q-card-section class="row items-center q-pb-none">
        <div class="text-h6">{{ $t('search.title') }}</div>
        <q-space />
        <q-btn icon="close" flat round dense @click="onDialogOK" />
      </q-card-section>

    <q-card-section>
      <div class="text-caption text-grey-7 q-mb-md">
        {{ $t('search.keyword') }}: "{{ query }}"
      </div>

      <!-- Search Type Tabs -->
      <q-tabs
        v-model="searchType"
        dense
        class="text-grey"
        active-color="primary"
        indicator-color="primary"
        align="justify"
        narrow-indicator
        @update:model-value="performSearch"
      >
        <q-tab name="all" :label="$t('search.tabs.all')" />
        <q-tab name="books" :label="$t('search.tabs.books')" />
        <q-tab name="chapters" :label="$t('search.tabs.chapters')" />
        <q-tab name="content" :label="$t('search.tabs.content')" />
      </q-tabs>
    </q-card-section>

    <q-separator />

    <q-card-section style="max-height: 60vh; overflow-y: auto;">
      <!-- Loading State -->
      <div v-if="loading" class="text-center q-pa-md">
        <q-spinner color="primary" size="3em" />
        <div class="text-caption text-grey-7 q-mt-md">{{ $t('search.searching') }}</div>
      </div>

      <!-- Error State -->
      <div v-else-if="error" class="text-center q-pa-md">
        <q-icon name="error_outline" size="3em" color="negative" />
        <div class="text-body2 q-mt-md">{{ error }}</div>
        <q-btn flat color="primary" :label="$t('common.retry')" @click="performSearch" class="q-mt-md" />
      </div>

      <!-- No Results -->
      <div v-else-if="hasNoResults" class="text-center q-pa-md">
        <q-icon name="search_off" size="3em" color="grey-5" />
        <div class="text-body2 text-grey-7 q-mt-md">{{ $t('search.noResults') }}</div>
      </div>

      <!-- Results -->
      <div v-else-if="hasResults">
        <div class="text-caption text-grey-7 q-mb-md">
          {{ $t('search.resultsCount', { count: totalResults, books: totalBooks }) }}
        </div>

        <div v-for="book in results" :key="book.book_id" class="q-mb-lg">
          <!-- Book Header -->
          <div class="book-header q-pa-sm rounded-borders">
            <div class="text-subtitle1 text-weight-medium">
              {{ book.book_name }}
            </div>
            <div class="text-caption text-grey-7">
              {{ book.author }}
            </div>
          </div>

          <!-- Matches -->
          <div v-for="(match, idx) in book.matches" :key="idx" class="q-ml-md q-mt-sm">
            <q-item
              clickable
              class="match-item rounded-borders"
              @click="navigateToMatch(book, match)"
            >
              <q-item-section>
                <q-item-label>
                  <q-badge
                    :color="getMatchColor(match.match_type)"
                    :label="getMatchTypeLabel(match.match_type)"
                    class="q-mr-sm"
                  />
                  <span v-if="match.chapter_title">{{ match.chapter_title }}</span>
                  <span v-else class="text-grey-7">{{ book.book_name }}</span>
                </q-item-label>
                <q-item-label caption class="q-mt-xs">
                  {{ match.match_context }}
                </q-item-label>
              </q-item-section>
              <q-item-section side>
                <q-icon name="chevron_right" color="grey-5" />
              </q-item-section>
            </q-item>
          </div>
        </div>
      </div>
    </q-card-section>
  </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';
import { useDialogPluginComponent } from 'quasar';
import { api } from 'src/boot/axios';

const { t } = useI18n();

interface SearchMatch {
  match_type: 'book_name' | 'author' | 'chapter_title' | 'chapter_content';
  match_context: string;
  chapter_num: number | null;
  chapter_title: string | null;
  relevance_score: number;
}

interface SearchBookResult {
  book_id: string;
  public_id?: string | null;
  book_name: string;
  author: string;
  matches: SearchMatch[];
}

interface SearchResponse {
  query: string;
  search_type: string;
  total_results: number;
  total_books: number;
  results: SearchBookResult[];
}

const props = defineProps<{
  query: string;
}>();

defineEmits([...useDialogPluginComponent.emits]);

const { dialogRef, onDialogHide, onDialogOK } = useDialogPluginComponent();
const router = useRouter();

const searchType = ref<'all' | 'books' | 'chapters' | 'content'>('all');
const loading = ref(true); // Start as true since we load immediately in onMounted
const error = ref<string | null>(null);
const results = ref<SearchBookResult[]>([]);
const totalResults = ref(0);
const totalBooks = ref(0);
const hasResults = computed(() => results.value && results.value.length > 0);
const hasNoResults = computed(() => !loading.value && results.value && results.value.length === 0);

async function performSearch() {
  if (!props.query.trim()) return;

  console.log('[SearchDialog] Starting search:', props.query, 'type:', searchType.value);
  loading.value = true;
  error.value = null;

  try {
    console.log('[SearchDialog] Calling API with params:', {
      q: props.query,
      search_type: searchType.value,
      limit: 50,
    });

    const { data } = await api.get<SearchResponse>('/search', {
      params: {
        q: props.query,
        search_type: searchType.value,
        limit: 50,
      },
    });

    console.log('[SearchDialog] Search results:', data);
    results.value = data.results;
    totalResults.value = data.total_results;
    totalBooks.value = data.total_books;
  } catch (err) {
    console.error('[SearchDialog] Search error:', err);
    const errorMessage = err instanceof Error ? err.message : t('search.searchFailed');
    error.value = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || errorMessage;
  } finally {
    loading.value = false;
  }
}

function getMatchTypeLabel(matchType: string): string {
  const labelKey = `search.matchTypes.${matchType}`;
  return t(labelKey);
}

function getMatchColor(matchType: string): string {
  const colors: Record<string, string> = {
    book_name: 'primary',
    author: 'secondary',
    chapter_title: 'accent',
    chapter_content: 'info',
  };
  return colors[matchType] || 'grey';
}

function navigateToMatch(book: SearchBookResult, match: SearchMatch) {
  console.log('[SearchDialog] Navigating to match:', book.book_id, match);

  // Close the dialog
  onDialogOK();

  // Always navigate to chapters page instead of specific chapter
  // Use public_id if available, fall back to book_id
  const id = book.public_id || book.book_id;
  const url = `/book/${id}/chapters`;
  console.log('[SearchDialog] Navigating to book chapters:', url);
  void router.push(url);
}

onMounted(() => {
  console.log('[SearchDialog] Component mounted, query:', props.query);
  void performSearch();
});
</script>

<style scoped>
.book-header {
  background-color: rgba(var(--q-primary-rgb), 0.05);
  border-left: 3px solid var(--q-primary);
}

.match-item {
  border: 1px solid rgba(0, 0, 0, 0.05);
  transition: all 0.2s ease;
}

.match-item:hover {
  background-color: rgba(var(--q-primary-rgb), 0.05);
  border-color: var(--q-primary);
}

.body--dark .match-item {
  border-color: rgba(255, 255, 255, 0.1);
}

.body--dark .match-item:hover {
  background-color: rgba(var(--q-primary-rgb), 0.15);
}
</style>
