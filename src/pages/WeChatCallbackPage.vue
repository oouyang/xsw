<template>
  <q-page class="flex flex-center">
    <div class="text-center">
      <q-spinner-dots color="primary" size="40px" v-if="loading" />
      <q-banner v-if="error" class="bg-red-1 text-red-10 q-mt-md" rounded>
        {{ error }}
      </q-banner>
      <div v-if="loading" class="text-grey-7 q-mt-md">{{ $t('userAuth.loggingIn') }}</div>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { useUserAuthStore } from 'src/stores/userAuth';
import { useReadingHistory } from 'src/composables/useReadingHistory';

const router = useRouter();
const route = useRoute();
const userAuth = useUserAuthStore();
const { syncOnLogin } = useReadingHistory();

const loading = ref(true);
const error = ref('');

onMounted(async () => {
  const code = route.query.code as string | undefined;
  const state = route.query.state as string | undefined;

  // Validate state to prevent CSRF
  const savedState = sessionStorage.getItem('wechat_state');
  if (state && savedState && state !== savedState) {
    error.value = 'Invalid state parameter';
    loading.value = false;
    return;
  }
  sessionStorage.removeItem('wechat_state');

  if (!code) {
    error.value = 'No authorization code received';
    loading.value = false;
    return;
  }

  try {
    await userAuth.loginWithWeChat(code);
    await syncOnLogin();
    void router.replace({ name: 'Dashboard' });
  } catch (e: unknown) {
    error.value = (e as Error).message || 'WeChat login failed';
    loading.value = false;
  }
});
</script>
