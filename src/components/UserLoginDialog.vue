<template>
  <q-dialog v-model="showDialog" persistent>
    <q-card style="min-width: 350px; max-width: 450px">
      <q-card-section class="row items-center q-pb-none">
        <div class="text-h6">{{ $t('userAuth.loginTitle') }}</div>
        <q-space />
        <q-btn icon="close" flat round dense @click="close" />
      </q-card-section>

      <q-card-section>
        <div class="text-body2 text-grey-7 q-mb-lg">
          {{ $t('userAuth.loginSubtitle') }}
        </div>

        <q-banner v-if="error" class="bg-red-1 text-red-10 q-mb-md" dense rounded>
          {{ error }}
        </q-banner>

        <!-- Google Sign-In -->
        <q-btn
          class="full-width q-mb-sm"
          outline
          color="red"
          icon="img:https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg"
          :label="$t('userAuth.signInGoogle')"
          :loading="loading === 'google'"
          :disable="!!loading"
          @click="handleGoogleLogin"
        />

        <!-- Facebook Sign-In -->
        <q-btn
          class="full-width q-mb-sm"
          outline
          color="blue-8"
          icon="facebook"
          :label="$t('userAuth.signInFacebook')"
          :loading="loading === 'facebook'"
          :disable="!!loading"
          @click="handleFacebookLogin"
        />

        <!-- Apple Sign-In -->
        <q-btn
          class="full-width q-mb-sm"
          outline
          color="dark"
          icon="apple"
          :label="$t('userAuth.signInApple')"
          :loading="loading === 'apple'"
          :disable="!!loading"
          @click="handleAppleLogin"
        />

        <!-- WeChat Sign-In -->
        <q-btn
          class="full-width q-mb-md"
          outline
          color="green"
          icon="chat"
          :label="$t('userAuth.signInWeChat')"
          :loading="loading === 'wechat'"
          :disable="!!loading"
          @click="handleWeChatLogin"
        />

        <div class="text-caption text-grey-6 text-center">
          {{ $t('userAuth.syncMessage') }}
        </div>
      </q-card-section>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useUserAuthStore } from 'src/stores/userAuth';
import { useAppConfig } from 'src/services/useAppConfig';

const userAuth = useUserAuthStore();
const { config } = useAppConfig();

const showDialog = ref(true);
const loading = ref<string | null>(null);
const error = ref('');

const emit = defineEmits<{ close: [] }>();

function close() {
  showDialog.value = false;
  emit('close');
}

async function handleGoogleLogin() {
  loading.value = 'google';
  error.value = '';

  try {
    // Dynamically load Google Identity Services
    const googleClientId = config.value.googleClientId;
    if (!googleClientId) {
      error.value = 'Google Client ID not configured';
      return;
    }

    await loadGoogleScript();

    // Use google.accounts.oauth2.initTokenClient for popup flow
    const google = (window as unknown as { google: GoogleIdentity }).google;
    const client = google.accounts.oauth2.initTokenClient({
      client_id: googleClientId,
      scope: 'openid email profile',
      callback: (response: { access_token?: string; error?: string }) => {
        if (response.error) {
          error.value = response.error;
          loading.value = null;
          return;
        }

        // We need an ID token, not an access token.
        // Use the code flow or the One Tap / Sign In With Google button instead.
        // For simplicity, let's use the id_token from google.accounts.id
        error.value = 'Please use the alternative Google flow';
        loading.value = null;
      },
    });
    client.requestAccessToken();

    // Alternative: Use google.accounts.id for ID token
    google.accounts.id.initialize({
      client_id: googleClientId,
      callback: (response: { credential: string }) => {
        void (async () => {
          try {
            await userAuth.loginWithGoogle(response.credential);
            close();
          } catch (e: unknown) {
            error.value = (e as Error).message || 'Login failed';
          } finally {
            loading.value = null;
          }
        })();
      },
    });
    google.accounts.id.prompt();
  } catch (e: unknown) {
    error.value = (e as Error).message || 'Google login failed';
  } finally {
    if (loading.value === 'google') loading.value = null;
  }
}

async function handleFacebookLogin() {
  loading.value = 'facebook';
  error.value = '';

  try {
    await loadFacebookScript();

    const FB = (window as unknown as { FB: FacebookSDK }).FB;
    FB.login(
      (response: { authResponse?: { accessToken: string } }) => {
        if (response.authResponse) {
          void (async () => {
            try {
              await userAuth.loginWithFacebook(response.authResponse!.accessToken);
              close();
            } catch (e: unknown) {
              error.value = (e as Error).message || 'Login failed';
            } finally {
              loading.value = null;
            }
          })();
        } else {
          error.value = 'Facebook login cancelled';
          loading.value = null;
        }
      },
      { scope: 'email,public_profile' },
    );
  } catch (e: unknown) {
    error.value = (e as Error).message || 'Facebook login failed';
    loading.value = null;
  }
}

async function handleAppleLogin() {
  loading.value = 'apple';
  error.value = '';

  try {
    await loadAppleScript();

    const AppleID = (window as unknown as { AppleID: AppleIDAuth }).AppleID;
    AppleID.auth.init({
      clientId: config.value.appleClientId || '',
      scope: 'name email',
      redirectURI: window.location.origin + '/auth/apple/callback',
      usePopup: true,
    });

    const response = await AppleID.auth.signIn();
    const idToken = response.authorization?.id_token;
    const code = response.authorization?.code;

    if (idToken) {
      await userAuth.loginWithApple(idToken, code);
      close();
    } else {
      error.value = 'Apple login failed: no token received';
    }
  } catch (e: unknown) {
    error.value = (e as Error).message || 'Apple login failed';
  } finally {
    loading.value = null;
  }
}

function handleWeChatLogin() {
  loading.value = 'wechat';
  error.value = '';

  // WeChat uses redirect-based flow
  const appId = config.value.wechatAppId;
  if (!appId) {
    error.value = 'WeChat App ID not configured';
    loading.value = null;
    return;
  }

  const redirectUri = encodeURIComponent(
    window.location.origin + '/auth/wechat/callback',
  );
  const state = Math.random().toString(36).slice(2);
  sessionStorage.setItem('wechat_state', state);

  window.location.href =
    `https://open.weixin.qq.com/connect/qrconnect?appid=${appId}` +
    `&redirect_uri=${redirectUri}&response_type=code&scope=snsapi_login&state=${state}#wechat_redirect`;
}

// --- SDK Loaders ---

function loadGoogleScript(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (document.getElementById('google-gsi')) {
      resolve();
      return;
    }
    const script = document.createElement('script');
    script.id = 'google-gsi';
    script.src = 'https://accounts.google.com/gsi/client';
    script.onload = () => resolve();
    script.onerror = () => reject(new Error('Failed to load Google SDK'));
    document.head.appendChild(script);
  });
}

function loadFacebookScript(): Promise<void> {
  return new Promise((resolve, reject) => {
    if ((window as unknown as { FB?: unknown }).FB) {
      resolve();
      return;
    }
    const script = document.createElement('script');
    script.src = 'https://connect.facebook.net/en_US/sdk.js';
    script.onload = () => {
      const FB = (window as unknown as { FB: FacebookSDK }).FB;
      FB.init({
        appId: config.value.facebookAppId || '',
        version: 'v18.0',
      });
      resolve();
    };
    script.onerror = () => reject(new Error('Failed to load Facebook SDK'));
    document.head.appendChild(script);
  });
}

function loadAppleScript(): Promise<void> {
  return new Promise((resolve, reject) => {
    if ((window as unknown as { AppleID?: unknown }).AppleID) {
      resolve();
      return;
    }
    const script = document.createElement('script');
    script.src =
      'https://appleid.cdn-apple.com/appleauth/static/jsapi/appleid/1/en_US/appleid.auth.js';
    script.onload = () => resolve();
    script.onerror = () => reject(new Error('Failed to load Apple SDK'));
    document.head.appendChild(script);
  });
}

// --- Type declarations for third-party SDKs ---

interface GoogleIdentity {
  accounts: {
    id: {
      initialize: (config: { client_id: string; callback: (response: { credential: string }) => void }) => void;
      prompt: () => void;
    };
    oauth2: {
      initTokenClient: (config: {
        client_id: string;
        scope: string;
        callback: (response: { access_token?: string; error?: string }) => void;
      }) => { requestAccessToken: () => void };
    };
  };
}

interface FacebookSDK {
  init: (config: { appId: string; version: string }) => void;
  login: (
    callback: (response: { authResponse?: { accessToken: string } }) => void,
    options: { scope: string },
  ) => void;
}

interface AppleIDAuth {
  auth: {
    init: (config: {
      clientId: string;
      scope: string;
      redirectURI: string;
      usePopup: boolean;
    }) => void;
    signIn: () => Promise<{
      authorization?: { id_token?: string; code?: string };
    }>;
  };
}
</script>
