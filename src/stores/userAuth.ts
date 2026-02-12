// src/stores/userAuth.ts
import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type { UserProfile } from 'src/types/book-api';
import { userAuthService } from 'src/services/userAuthService';

export const useUserAuthStore = defineStore('userAuth', () => {
  const user = ref<UserProfile | null>(userAuthService.getUser());
  const token = ref<string | null>(userAuthService.getToken());
  const loading = ref(false);
  const error = ref('');

  const isLoggedIn = computed(() => !!token.value);
  const displayName = computed(() => user.value?.display_name ?? '');
  const avatarUrl = computed(() => user.value?.avatar_url ?? '');

  function _updateState() {
    user.value = userAuthService.getUser();
    token.value = userAuthService.getToken();
  }

  async function loginWithGoogle(idToken: string) {
    loading.value = true;
    error.value = '';
    try {
      await userAuthService.loginWithGoogle(idToken);
      _updateState();
    } catch (e: unknown) {
      error.value = (e as Error).message || 'Google login failed';
      throw e;
    } finally {
      loading.value = false;
    }
  }

  async function loginWithFacebook(accessToken: string) {
    loading.value = true;
    error.value = '';
    try {
      await userAuthService.loginWithFacebook(accessToken);
      _updateState();
    } catch (e: unknown) {
      error.value = (e as Error).message || 'Facebook login failed';
      throw e;
    } finally {
      loading.value = false;
    }
  }

  async function loginWithApple(idToken: string, authorizationCode?: string) {
    loading.value = true;
    error.value = '';
    try {
      await userAuthService.loginWithApple(idToken, authorizationCode);
      _updateState();
    } catch (e: unknown) {
      error.value = (e as Error).message || 'Apple login failed';
      throw e;
    } finally {
      loading.value = false;
    }
  }

  async function loginWithWeChat(code: string) {
    loading.value = true;
    error.value = '';
    try {
      await userAuthService.loginWithWeChat(code);
      _updateState();
    } catch (e: unknown) {
      error.value = (e as Error).message || 'WeChat login failed';
      throw e;
    } finally {
      loading.value = false;
    }
  }

  function logout() {
    userAuthService.clearAuth();
    user.value = null;
    token.value = null;
    error.value = '';
  }

  function loadFromStorage() {
    _updateState();
  }

  return {
    user,
    token,
    loading,
    error,
    isLoggedIn,
    displayName,
    avatarUrl,
    loginWithGoogle,
    loginWithFacebook,
    loginWithApple,
    loginWithWeChat,
    logout,
    loadFromStorage,
  };
});
