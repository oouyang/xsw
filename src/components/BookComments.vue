<!-- src/components/BookComments.vue -->
<template>
  <div class="q-mt-lg">
    <div class="text-subtitle1 text-weight-medium q-mb-sm">{{ $t('comment.comments') }}</div>

    <!-- Comment form (logged in) -->
    <div v-if="isLoggedIn" class="q-mb-md">
      <q-input
        v-model="newText"
        outlined
        dense
        type="textarea"
        :placeholder="$t('comment.placeholder')"
        rows="2"
        maxlength="1000"
        counter
      />
      <div class="row justify-end q-mt-xs">
        <q-btn
          :label="$t('comment.addComment')"
          color="primary"
          dense
          no-caps
          :loading="posting"
          :disable="!newText.trim()"
          @click="postComment"
        />
      </div>
    </div>

    <!-- Login prompt -->
    <q-banner v-else class="bg-grey-2 q-mb-md" dense rounded>
      <div class="text-caption text-grey-7">{{ $t('comment.loginToComment') }}</div>
    </q-banner>

    <!-- Comment list -->
    <div v-if="comments.length === 0 && !loading" class="text-caption text-grey-6 q-my-sm">
      {{ $t('comment.noComments') }}
    </div>

    <q-list v-else separator>
      <q-item v-for="c in comments" :key="c.id" class="q-py-sm">
        <q-item-section avatar top>
          <q-avatar size="32px" color="grey-4" text-color="white">
            <img v-if="c.avatar_url" :src="c.avatar_url" />
            <q-icon v-else name="person" />
          </q-avatar>
        </q-item-section>
        <q-item-section>
          <q-item-label class="text-caption text-weight-medium">
            {{ c.display_name }}
            <span class="text-grey-6 q-ml-sm">{{ formatTime(c.created_at) }}</span>
          </q-item-label>
          <q-item-label class="text-body2 q-mt-xs" style="white-space: pre-wrap">{{ c.text }}</q-item-label>
        </q-item-section>
        <q-item-section v-if="isOwn(c)" side top>
          <q-btn flat dense round icon="delete" size="sm" color="grey-6" @click="removeComment(c.id)">
            <q-tooltip>{{ $t('common.remove') }}</q-tooltip>
          </q-btn>
        </q-item-section>
      </q-item>
    </q-list>

    <!-- Load more -->
    <div v-if="hasMore" class="row justify-center q-mt-sm">
      <q-btn flat dense no-caps color="primary" :loading="loading" @click="loadMore">
        {{ $t('category.viewAll') }}
      </q-btn>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { Dialog } from 'quasar';
import type { CommentEntry } from 'src/types/book-api';
import { getBookComments } from 'src/services/bookApi';
import { userAuthService } from 'src/services/userAuthService';
import { useUserAuthStore } from 'src/stores/userAuth';

const { t } = useI18n();
const userAuth = useUserAuthStore();

const props = defineProps<{ bookId: string }>();

const comments = ref<CommentEntry[]>([]);
const loading = ref(false);
const posting = ref(false);
const newText = ref('');
const page = ref(1);
const hasMore = ref(true);

const isLoggedIn = ref(userAuth.isLoggedIn);

function isOwn(c: CommentEntry): boolean {
  const user = userAuthService.getUser();
  return !!user && user.id === c.user_id;
}

function formatTime(iso: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString();
}

async function loadComments(p = 1) {
  try {
    loading.value = true;
    const data = await getBookComments(props.bookId, p);
    if (p === 1) {
      comments.value = data;
    } else {
      comments.value = [...comments.value, ...data];
    }
    hasMore.value = data.length >= 20;
    page.value = p;
  } catch (e) {
    console.error('[BookComments] Load error:', e);
  } finally {
    loading.value = false;
  }
}

function loadMore() {
  void loadComments(page.value + 1);
}

async function postComment() {
  const text = newText.value.trim();
  if (!text) return;
  if (text.length > 1000) return;

  try {
    posting.value = true;
    const entry = await userAuthService.createComment(props.bookId, text);
    comments.value = [entry, ...comments.value];
    newText.value = '';
  } catch (e) {
    console.error('[BookComments] Post error:', e);
  } finally {
    posting.value = false;
  }
}

function removeComment(id: number) {
  Dialog.create({
    title: t('comment.deleteConfirm'),
    cancel: true,
    persistent: false,
  }).onOk(() => {
    void (async () => {
      try {
        await userAuthService.deleteComment(id);
        comments.value = comments.value.filter(c => c.id !== id);
      } catch (e) {
        console.error('[BookComments] Delete error:', e);
      }
    })();
  });
}

onMounted(() => {
  void loadComments();
});
</script>
