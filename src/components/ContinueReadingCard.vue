<template>
  <q-card class="continue-card" flat bordered>
    <q-card-section class="q-pa-sm">
      <div class="text-subtitle2 ellipsis">{{ convertIfNeeded(entry.bookName) }}</div>
      <div class="text-caption text-grey-7 ellipsis">
        {{ convertIfNeeded(entry.chapterTitle) || `${$t('chapter.chapter')} ${entry.chapterNumber}` }}
      </div>
      <q-linear-progress
        v-if="entry.totalChapters > 0"
        :value="entry.chapterNumber / entry.totalChapters"
        color="primary"
        size="4px"
        rounded
        class="q-mt-xs"
      />
      <div v-if="entry.totalChapters > 0" class="text-caption text-grey-6 text-right">
        {{ Math.round((entry.chapterNumber / entry.totalChapters) * 100) }}%
      </div>
    </q-card-section>
    <q-card-actions class="q-pa-xs">
      <q-btn
        dense
        flat
        color="primary"
        size="sm"
        :label="$t('action.continueReading')"
        :to="chapterRoute"
        no-caps
      />
      <q-space />
      <q-btn dense flat round size="xs" icon="close" color="grey-5" @click="$emit('remove', entry.bookId)">
        <q-tooltip>{{ $t('common.remove') }}</q-tooltip>
      </q-btn>
    </q-card-actions>
  </q-card>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { ReadingHistoryEntry } from 'src/types/book-api';
import { useTextConversion } from 'src/composables/useTextConversion';

const { convertIfNeeded } = useTextConversion();

const props = defineProps<{
  entry: ReadingHistoryEntry;
}>();

defineEmits<{ remove: [bookId: string] }>();

const chapterRoute = computed(() => ({
  name: 'Chapter',
  params: {
    bookId: props.entry.bookId,
    chapterId: props.entry.chapterId || String(props.entry.chapterNumber),
    chapterTitle: props.entry.chapterTitle,
  },
}));
</script>

<style scoped>
.continue-card {
  min-width: 160px;
  max-width: 200px;
}

.ellipsis {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
