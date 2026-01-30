<template>
  <q-dialog v-model="showDialog" persistent>
    <q-card style="min-width: 400px; max-width: 600px">
      <q-card-section class="row items-center q-pb-none">
        <div class="text-h6">{{ $t('admin.title') }}</div>
        <q-space />
        <q-btn icon="close" flat round dense @click="close" />
      </q-card-section>

      <q-card-section>
        <!-- Login Form -->
        <div v-if="!isAdminLoggedIn">
          <div class="text-subtitle2 q-mb-md">{{ $t('admin.login') }}</div>

          <!-- Google Sign-In Button -->
          <div ref="googleButtonContainer" class="q-mb-md google-signin-container"></div>

          <!-- Separator -->
          <div class="row items-center q-mb-md">
            <q-separator class="col" />
            <div class="col-auto q-px-md text-grey-6">OR</div>
            <q-separator class="col" />
          </div>

          <!-- Password Login (Collapsible) -->
          <q-expansion-item
            dense
            :label="$t('admin.passwordLogin')"
            :caption="$t('admin.passwordLoginCaption')"
            icon="vpn_key"
            class="q-mb-md password-expansion"
          >
            <q-card flat bordered class="q-mt-sm">
              <q-card-section>
                <q-input
                  v-model="passwordEmail"
                  dense
                  outlined
                  type="email"
                  :label="$t('admin.email')"
                  class="q-mb-sm"
                  @keyup.enter="passwordLogin"
                />
                <q-input
                  v-model="passwordPassword"
                  dense
                  outlined
                  type="password"
                  :label="$t('admin.password')"
                  class="q-mb-md"
                  @keyup.enter="passwordLogin"
                />
                <q-btn
                  color="primary"
                  icon="login"
                  :label="$t('admin.loginButton')"
                  class="full-width"
                  @click="passwordLogin"
                  :loading="adminLoading"
                />
              </q-card-section>
            </q-card>
          </q-expansion-item>
        </div>

        <!-- Admin Panel (after login) -->
        <div v-else>
          <!-- Admin Info Bar -->
          <div class="row items-center q-mb-md q-pa-sm rounded-borders admin-info-bar">
            <!-- User Avatar -->
            <q-avatar size="32px" class="q-mr-sm">
              <img v-if="currentUser?.picture" :src="currentUser.picture" alt="User avatar" />
              <q-icon v-else name="account_circle" size="32px" />
            </q-avatar>

            <!-- User Info -->
            <div class="col">
              <div class="text-body2 text-weight-medium">{{ currentUser?.email }}</div>
              <div class="row items-center q-gutter-xs">
                <q-chip
                  dense
                  size="sm"
                  :icon="currentUser?.auth_method === 'google' ? 'verified' : 'vpn_key'"
                  :color="currentUser?.auth_method === 'google' ? 'positive' : 'grey'"
                  text-color="white"
                  class="q-ma-none"
                >
                  {{ currentUser?.auth_method === 'google' ? 'Google' : 'Password' }}
                </q-chip>
              </div>
            </div>

            <!-- Action Buttons -->
            <q-btn
              v-if="currentUser?.auth_method === 'password'"
              flat
              dense
              size="sm"
              icon="vpn_key"
              class="admin-action-btn"
              @click="showPasswordDialog = true"
            >
              <q-tooltip>{{ $t('admin.tooltips.changePassword') }}</q-tooltip>
            </q-btn>
            <q-btn
              flat
              dense
              size="sm"
              icon="logout"
              class="admin-action-btn"
              @click="logout"
            >
              <q-tooltip>{{ $t('admin.logout') }}</q-tooltip>
            </q-btn>
          </div>

          <q-tabs
            v-model="activeTab"
            dense
            class="q-mb-md"
            active-color="primary"
            indicator-color="primary"
            align="justify"
            narrow-indicator
          >
            <q-tab name="stats" :label="$t('admin.tabs.stats')" />
            <q-tab name="jobs" :label="$t('admin.tabs.jobs')" />
            <q-tab name="cache" :label="$t('admin.tabs.cache')" />
            <q-tab name="books" :label="$t('admin.tabs.books')" />
            <q-tab name="smtp" :label="$t('admin.tabs.smtp')" />
          </q-tabs>

          <q-tab-panels v-model="activeTab" animated>
            <!-- Stats Tab -->
            <q-tab-panel name="stats">
              <div class="row q-col-gutter-sm q-mb-md">
                <div class="col-6">
                  <q-card flat bordered>
                    <q-card-section class="q-pa-sm">
                      <div class="text-caption text-weight-medium">{{ $t('admin.stats.cache') }}</div>
                      <div v-if="stats.cache" class="text-body2">
                        <div>{{ $t('admin.stats.books') }}: {{ stats.cache.books_in_db }}</div>
                        <div>{{ $t('admin.stats.chapters') }}: {{ stats.cache.chapters_in_db }}</div>
                        <div>{{ $t('admin.stats.memory') }}: {{ stats.cache.memory_cache_size }}</div>
                      </div>
                      <q-spinner v-else color="primary" size="20px" />
                    </q-card-section>
                  </q-card>
                </div>
                <div class="col-6">
                  <q-card flat bordered>
                    <q-card-section class="q-pa-sm">
                      <div class="text-caption text-weight-medium">{{ $t('admin.stats.jobs') }}</div>
                      <div v-if="stats.jobs" class="text-body2">
                        <div>{{ $t('admin.stats.pending') }}: {{ stats.jobs.pending_jobs }}</div>
                        <div>{{ $t('admin.stats.completed') }}: {{ stats.jobs.completed_jobs }}</div>
                        <div>{{ $t('admin.stats.failed') }}: {{ stats.jobs.failed_jobs }}</div>
                      </div>
                      <q-spinner v-else color="primary" size="20px" />
                    </q-card-section>
                  </q-card>
                </div>
              </div>

              <div class="row q-col-gutter-sm">
                <div class="col-6">
                  <q-card flat bordered>
                    <q-card-section class="q-pa-sm">
                      <div class="text-caption text-weight-medium">{{ $t('admin.stats.midnightSync') }}</div>
                      <div v-if="stats.midnightSync" class="text-body2">
                        <div>{{ $t('admin.stats.total') }}: {{ stats.midnightSync.total }}</div>
                        <div>{{ $t('admin.stats.pending') }}: {{ stats.midnightSync.pending }} | {{ $t('admin.stats.syncing') }}: {{ stats.midnightSync.syncing }}</div>
                        <div>{{ $t('admin.stats.completed') }}: {{ stats.midnightSync.completed }} | {{ $t('admin.stats.failed') }}: {{ stats.midnightSync.failed }}</div>
                        <div class="text-caption">{{ $t('admin.stats.nextSync') }}: {{ stats.midnightSync.next_sync_time }}</div>
                      </div>
                      <q-spinner v-else color="primary" size="20px" />
                    </q-card-section>
                  </q-card>
                </div>
                <div class="col-6">
                  <q-card flat bordered>
                    <q-card-section class="q-pa-sm">
                      <div class="text-caption text-weight-medium">{{ $t('admin.stats.periodicSync') }}</div>
                      <div v-if="stats.periodicSync" class="text-body2">
                        <div>{{ $t('admin.stats.interval') }}: {{ stats.periodicSync.interval_hours }}h</div>
                        <div>{{ $t('admin.stats.priority') }}: {{ stats.periodicSync.priority }}</div>
                        <div class="text-caption">{{ $t('admin.stats.lastSync') }}: {{ stats.periodicSync.last_sync_time || 'N/A' }}</div>
                        <div class="text-caption">{{ $t('admin.stats.nextSync') }}: {{ stats.periodicSync.next_sync_time || 'N/A' }}</div>
                      </div>
                      <q-spinner v-else color="primary" size="20px" />
                    </q-card-section>
                  </q-card>
                </div>
              </div>
            </q-tab-panel>

            <!-- Jobs Tab -->
            <q-tab-panel name="jobs">
              <div class="text-subtitle2 q-mb-sm">{{ $t('admin.actions.midnightSync') }}</div>
              <div class="row q-col-gutter-sm q-mb-md">
                <div class="col-6">
                  <q-btn
                    unelevated
                    color="primary"
                    icon="queue"
                    :label="$t('admin.actions.enqueue')"
                    class="full-width"
                    @click="enqueueUnfinished"
                    :loading="actionLoading.enqueue"
                    size="sm"
                  >
                    <q-tooltip>{{ $t('admin.tooltips.enqueue') }}</q-tooltip>
                  </q-btn>
                </div>
                <div class="col-6">
                  <q-btn
                    unelevated
                    color="secondary"
                    icon="play_arrow"
                    :label="$t('admin.actions.trigger')"
                    class="full-width"
                    @click="triggerSync"
                    :loading="actionLoading.trigger"
                    size="sm"
                  >
                    <q-tooltip>{{ $t('admin.tooltips.trigger') }}</q-tooltip>
                  </q-btn>
                </div>
                <div class="col-6">
                  <q-btn
                    unelevated
                    color="warning"
                    icon="clear"
                    :label="$t('admin.actions.clear')"
                    class="full-width"
                    @click="clearCompleted"
                    :loading="actionLoading.clear"
                    size="sm"
                  >
                    <q-tooltip>{{ $t('admin.tooltips.clear') }}</q-tooltip>
                  </q-btn>
                </div>
                <div class="col-6">
                  <q-btn
                    unelevated
                    color="info"
                    icon="refresh"
                    :label="$t('admin.actions.refresh')"
                    class="full-width"
                    @click="refreshStats"
                    :loading="statsLoading"
                    size="sm"
                  >
                    <q-tooltip>{{ $t('admin.tooltips.refresh') }}</q-tooltip>
                  </q-btn>
                </div>
              </div>

              <div class="text-subtitle2 q-mb-sm q-mt-md">Job History</div>
              <q-btn
                unelevated
                color="warning"
                icon="history"
                :label="$t('admin.actions.clearHistory')"
                class="full-width"
                @click="clearJobHistory"
                :loading="actionLoading.clearHistory"
                size="sm"
              >
                <q-tooltip>{{ $t('admin.tooltips.clearHistory') }}</q-tooltip>
              </q-btn>
            </q-tab-panel>

            <!-- Cache Tab -->
            <q-tab-panel name="cache">
              <div class="text-subtitle2 q-mb-sm">{{ $t('admin.tabs.cache') }}</div>
              <q-btn
                unelevated
                color="negative"
                icon="delete_sweep"
                :label="$t('admin.actions.clearCache')"
                class="full-width"
                @click="clearCache"
                :loading="actionLoading.clearCache"
                size="sm"
              >
                <q-tooltip>{{ $t('admin.tooltips.clearCache') }}</q-tooltip>
              </q-btn>
            </q-tab-panel>

            <!-- Books Tab -->
            <q-tab-panel name="books">
              <div class="text-subtitle2 q-mb-sm">{{ $t('admin.bookManagement.title') }}</div>
              <q-input
                v-model="resyncBookId"
                dense
                outlined
                :label="$t('admin.bookManagement.bookId')"
                :placeholder="$t('admin.bookManagement.bookIdPlaceholder')"
                class="q-mb-sm"
              >
                <template v-slot:hint>
                  {{ $t('admin.bookManagement.bookIdHint') }}
                </template>
              </q-input>
              <q-btn
                unelevated
                color="orange"
                icon="sync"
                :label="$t('admin.actions.forceResync')"
                class="full-width"
                @click="forceResyncBook"
                :loading="actionLoading.resync"
                :disable="!resyncBookId"
                size="sm"
              >
                <q-tooltip>{{ $t('admin.tooltips.forceResync') }}</q-tooltip>
              </q-btn>

              <q-separator class="q-my-md" />

              <div class="text-subtitle2 q-mb-sm">{{ $t('admin.initSync.title') }}</div>
              <div class="row q-col-gutter-sm q-mb-sm">
                <div class="col-6">
                  <q-input
                    v-model.number="initSyncParams.categories"
                    dense
                    outlined
                    type="number"
                    :label="$t('admin.initSync.categories')"
                    :min="1"
                    :max="20"
                  >
                    <template v-slot:hint>
                      {{ $t('admin.initSync.categoriesHint') }}
                    </template>
                  </q-input>
                </div>
                <div class="col-6">
                  <q-input
                    v-model.number="initSyncParams.pagesPerCategory"
                    dense
                    outlined
                    type="number"
                    :label="$t('admin.initSync.pagesPerCategory')"
                    :min="1"
                    :max="50"
                  >
                    <template v-slot:hint>
                      {{ $t('admin.initSync.pagesHint') }}
                    </template>
                  </q-input>
                </div>
              </div>
              <q-btn
                unelevated
                color="negative"
                icon="restart_alt"
                :label="$t('admin.actions.initSync')"
                class="full-width"
                @click="initializeSync"
                :loading="actionLoading.initSync"
                size="sm"
              >
                <q-tooltip>{{ $t('admin.tooltips.initSync') }}</q-tooltip>
              </q-btn>
            </q-tab-panel>

            <!-- SMTP Tab -->
            <q-tab-panel name="smtp">
              <div class="text-subtitle2 q-mb-sm">{{ $t('admin.smtp.title') }}</div>

              <q-input
                v-model="smtpSettings.smtp_host"
                dense
                outlined
                :label="$t('admin.smtp.host')"
                class="q-mb-sm"
              >
                <template v-slot:hint>{{ $t('admin.smtp.hostHint') }}</template>
              </q-input>

              <div class="row q-col-gutter-sm q-mb-sm">
                <div class="col-6">
                  <q-input
                    v-model.number="smtpSettings.smtp_port"
                    dense
                    outlined
                    type="number"
                    :label="$t('admin.smtp.port')"
                  >
                    <template v-slot:hint>{{ $t('admin.smtp.portHint') }}</template>
                  </q-input>
                </div>
                <div class="col-6">
                  <q-checkbox
                    v-model="smtpSettings.use_tls"
                    :label="$t('admin.smtp.useTLS')"
                    dense
                  />
                  <q-checkbox
                    v-model="smtpSettings.use_ssl"
                    :label="$t('admin.smtp.useSSL')"
                    dense
                    class="q-ml-sm"
                  />
                </div>
              </div>

              <q-input
                v-model="smtpSettings.smtp_user"
                dense
                outlined
                :label="$t('admin.smtp.user')"
                class="q-mb-sm"
              >
                <template v-slot:hint>{{ $t('admin.smtp.userHint') }}</template>
              </q-input>

              <q-input
                v-model="smtpSettings.smtp_password"
                dense
                outlined
                type="password"
                :label="$t('admin.smtp.password')"
                class="q-mb-sm"
              >
                <template v-slot:hint>{{ $t('admin.smtp.passwordHint') }}</template>
              </q-input>

              <q-input
                v-model="smtpSettings.from_email"
                dense
                outlined
                :label="$t('admin.smtp.fromEmail')"
                class="q-mb-sm"
              >
                <template v-slot:hint>{{ $t('admin.smtp.fromEmailHint') }}</template>
              </q-input>

              <q-input
                v-model="smtpSettings.from_name"
                dense
                outlined
                :label="$t('admin.smtp.fromName')"
                class="q-mb-md"
              />

              <div class="row q-col-gutter-sm">
                <div class="col-6">
                  <q-btn
                    unelevated
                    color="primary"
                    icon="save"
                    :label="$t('admin.actions.saveSMTP')"
                    class="full-width"
                    @click="saveSMTPSettings"
                    :loading="actionLoading.saveSMTP"
                    size="sm"
                  />
                </div>
                <div class="col-6">
                  <q-btn
                    unelevated
                    color="secondary"
                    icon="check_circle"
                    :label="$t('admin.actions.testSMTP')"
                    class="full-width"
                    @click="testSMTPConnection"
                    :loading="actionLoading.testSMTP"
                    size="sm"
                  />
                </div>
              </div>

              <div v-if="smtpSettings.last_test_status" class="q-mt-md q-pa-sm rounded-borders" :class="smtpSettings.last_test_status === 'success' ? 'bg-positive text-white' : 'bg-negative text-white'">
                <div class="text-caption">{{ $t('admin.smtp.lastTest') }}: {{ smtpSettings.last_test_at }}</div>
                <div class="text-body2">{{ smtpSettings.last_test_status === 'success' ? $t('admin.smtp.testSuccess') : $t('admin.smtp.testFailed') }}</div>
              </div>
            </q-tab-panel>
          </q-tab-panels>
        </div>
      </q-card-section>
    </q-card>
  </q-dialog>

  <!-- Change Password Dialog -->
  <q-dialog v-model="showPasswordDialog" persistent>
    <q-card style="min-width: 350px" class="password-dialog">
      <q-card-section>
        <div class="text-h6">{{ $t('admin.changePassword') }}</div>
      </q-card-section>

      <q-card-section class="q-pt-none">
        <q-input
          v-model="passwordForm.currentPassword"
          dense
          outlined
          type="password"
          :label="$t('admin.currentPassword')"
          class="q-mb-sm"
          :error="passwordForm.error !== ''"
          :error-message="passwordForm.error"
        />
        <q-input
          v-model="passwordForm.newPassword"
          dense
          outlined
          type="password"
          :label="$t('admin.newPassword')"
          class="q-mb-sm"
        />
        <q-input
          v-model="passwordForm.confirmPassword"
          dense
          outlined
          type="password"
          :label="$t('admin.confirmPassword')"
        />
      </q-card-section>

      <q-card-actions align="right">
        <q-btn flat :label="$t('common.cancel')" @click="closePasswordDialog" />
        <q-btn
          flat
          :label="$t('admin.changePassword')"
          color="primary"
          @click="changePassword"
          :loading="passwordForm.loading"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue';
import { useQuasar } from 'quasar';
import { useI18n } from 'vue-i18n';
import { api } from 'src/boot/axios';
import { authService, type AuthUser } from 'src/services/authService';

const { t } = useI18n();

// Props
interface Props {
  modelValue: boolean;
}

const props = defineProps<Props>();

// Emits
const emit = defineEmits<{
  'update:modelValue': [value: boolean];
}>();

const $q = useQuasar();
const showDialog = ref(props.modelValue);
const activeTab = ref('stats');

// Watch for external changes
watch(() => props.modelValue, (newVal) => {
  showDialog.value = newVal;
  if (newVal && isAdminLoggedIn.value) {
    void refreshStats();
  }
});

watch(showDialog, (newVal) => {
  emit('update:modelValue', newVal);
});

// Admin login state
const isAdminLoggedIn = ref(false);
const currentUser = ref<AuthUser | null>(null);
const passwordEmail = ref('admin@localhost');
const passwordPassword = ref('');
const adminLoading = ref(false);
const statsLoading = ref(false);
const resyncBookId = ref('');
const googleButtonContainer = ref<HTMLElement | null>(null);

// Init sync parameters
const initSyncParams = ref({
  categories: 7,
  pagesPerCategory: 10
});

// Action loading states
const actionLoading = ref({
  enqueue: false,
  trigger: false,
  clear: false,
  clearCache: false,
  resync: false,
  clearHistory: false,
  initSync: false,
  saveSMTP: false,
  testSMTP: false
});

// SMTP settings state
const smtpSettings = ref({
  smtp_host: '',
  smtp_port: 587,
  smtp_user: '',
  smtp_password: '',
  use_tls: true,
  use_ssl: false,
  from_email: '',
  from_name: '看小說 Admin',
  last_test_at: null as string | null,
  last_test_status: null as string | null
});

// Password change state
const showPasswordDialog = ref(false);
const passwordForm = ref({
  currentPassword: '',
  newPassword: '',
  confirmPassword: '',
  loading: false,
  error: ''
});

// Google Sign-In integration
declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: {
            client_id: string;
            callback: (response: { credential: string }) => void;
          }) => void;
          renderButton: (
            parent: HTMLElement,
            options: {
              theme?: string;
              size?: string;
              text?: string;
              width?: number;
            }
          ) => void;
        };
      };
    };
  }
}

// Stats interfaces
interface CacheStats {
  books_in_db: number;
  chapters_in_db: number;
  memory_cache_size: number;
}

interface JobStats {
  pending_jobs: number;
  completed_jobs: number;
  failed_jobs: number;
  active_jobs: number;
}

interface MidnightSyncStats {
  total: number;
  pending: number;
  syncing: number;
  completed: number;
  failed: number;
  next_sync_time: string;
}

interface PeriodicSyncStats {
  running: boolean;
  interval_hours: number;
  last_sync_time: string | null;
  next_sync_time: string | null;
  priority: number;
}

const stats = ref<{
  cache: CacheStats | null;
  jobs: JobStats | null;
  midnightSync: MidnightSyncStats | null;
  periodicSync: PeriodicSyncStats | null;
}>({
  cache: null,
  jobs: null,
  midnightSync: null,
  periodicSync: null
});

// Admin authentication functions
async function handleGoogleSignIn(response: { credential: string }) {
  adminLoading.value = true;
  try {
    const authResponse = await authService.authenticateWithGoogle(response.credential);
    currentUser.value = authResponse.user;
    isAdminLoggedIn.value = true;
    void refreshStats();
    $q.notify({
      type: 'positive',
      message: t('admin.loginSuccess'),
      position: 'top'
    });
  } catch (error) {
    console.error('Google Sign-In failed:', error);
    $q.notify({
      type: 'negative',
      message: t('admin.googleSignInFailed'),
      position: 'top'
    });
  } finally {
    adminLoading.value = false;
  }
}

async function passwordLogin() {
  if (!passwordEmail.value || !passwordPassword.value) {
    $q.notify({
      type: 'warning',
      message: t('admin.allFieldsRequired'),
      position: 'top'
    });
    return;
  }

  adminLoading.value = true;
  try {
    const authResponse = await authService.authenticateWithPassword(
      passwordEmail.value,
      passwordPassword.value
    );
    currentUser.value = authResponse.user;
    isAdminLoggedIn.value = true;
    passwordPassword.value = '';
    void refreshStats();
    $q.notify({
      type: 'positive',
      message: t('admin.loginSuccess'),
      position: 'top'
    });
  } catch (error) {
    console.error('Password login failed:', error);
    $q.notify({
      type: 'negative',
      message: t('admin.loginFailed'),
      position: 'top'
    });
  } finally {
    adminLoading.value = false;
  }
}

function logout() {
  authService.clearAuth();
  isAdminLoggedIn.value = false;
  currentUser.value = null;
  passwordEmail.value = 'admin@localhost';
  passwordPassword.value = '';
  activeTab.value = 'stats';
  $q.notify({
    type: 'info',
    message: t('admin.logoutSuccess'),
    position: 'top'
  });
}

function loadGoogleSignIn() {
  // Check if VITE_GOOGLE_CLIENT_ID is configured
  const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;
  if (!clientId) {
    console.warn('[AdminDialog] VITE_GOOGLE_CLIENT_ID not configured, Google Sign-In disabled');
    return;
  }

  // Load Google Sign-In script
  const script = document.createElement('script');
  script.src = 'https://accounts.google.com/gsi/client';
  script.async = true;
  script.defer = true;
  script.onload = () => {
    if (window.google && googleButtonContainer.value) {
      initializeGoogleSignIn();
    }
  };
  document.head.appendChild(script);
}

function initializeGoogleSignIn() {
  const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;
  if (!clientId || !window.google || !googleButtonContainer.value) {
    return;
  }

  try {
    window.google.accounts.id.initialize({
      client_id: clientId,
      callback: (response: { credential: string }) => {
        void handleGoogleSignIn(response);
      }
    });

    window.google.accounts.id.renderButton(googleButtonContainer.value, {
      theme: 'outline',
      size: 'large',
      text: 'signin_with',
      width: googleButtonContainer.value.offsetWidth || 300
    });
  } catch (error) {
    console.error('[AdminDialog] Failed to initialize Google Sign-In:', error);
  }
}

// Check if user is already authenticated
function checkExistingAuth() {
  if (authService.isAuthenticated()) {
    currentUser.value = authService.getUser();
    isAdminLoggedIn.value = true;
  }
}

onMounted(() => {
  checkExistingAuth();
  loadGoogleSignIn();
});

function close() {
  showDialog.value = false;
}

function closePasswordDialog() {
  showPasswordDialog.value = false;
  passwordForm.value = {
    currentPassword: '',
    newPassword: '',
    confirmPassword: '',
    loading: false,
    error: ''
  };
}

async function changePassword() {
  passwordForm.value.error = '';

  // Validation
  if (!passwordForm.value.currentPassword || !passwordForm.value.newPassword || !passwordForm.value.confirmPassword) {
    passwordForm.value.error = t('admin.allFieldsRequired');
    return;
  }

  if (passwordForm.value.newPassword !== passwordForm.value.confirmPassword) {
    passwordForm.value.error = t('admin.passwordMismatch');
    return;
  }

  if (passwordForm.value.newPassword.length < 4) {
    passwordForm.value.error = t('admin.passwordTooShort');
    return;
  }

  // Change password via backend
  passwordForm.value.loading = true;
  try {
    await authService.changePassword(
      passwordForm.value.currentPassword,
      passwordForm.value.newPassword
    );

    $q.notify({
      type: 'positive',
      message: t('admin.passwordChanged'),
      position: 'top'
    });

    closePasswordDialog();
  } catch (error) {
    console.error('Failed to change password:', error);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const errorMessage = (error as any).response?.status === 401
      ? t('admin.incorrectPassword')
      : t('admin.passwordChangeFailed');

    passwordForm.value.error = errorMessage;
    $q.notify({
      type: 'negative',
      message: errorMessage,
      position: 'top'
    });
  } finally {
    passwordForm.value.loading = false;
  }
}

async function refreshStats() {
  statsLoading.value = true;
  try {
    const [healthResponse, jobStatsResponse, midnightSyncResponse, periodicSyncResponse] = await Promise.all([
      api.get('/health'),
      api.get('/admin/jobs/stats'),
      api.get('/admin/midnight-sync/stats'),
      api.get('/admin/periodic-sync/stats')
    ]);

    stats.value.cache = healthResponse.data.cache_stats;
    stats.value.jobs = jobStatsResponse.data;
    stats.value.midnightSync = midnightSyncResponse.data;
    stats.value.periodicSync = periodicSyncResponse.data;
    $q.notify({
      type: 'positive',
      message: t('admin.messages.statsRefreshed'),
      position: 'top'
    });
  } catch (error) {
    console.error('Failed to fetch stats:', error);
    $q.notify({
      type: 'negative',
      message: t('admin.messages.fetchStatsFailed'),
      position: 'top'
    });
  } finally {
    statsLoading.value = false;
  }
}

async function enqueueUnfinished() {
  actionLoading.value.enqueue = true;
  try {
    const response = await api.post('/admin/midnight-sync/enqueue-unfinished');
    $q.notify({
      type: 'positive',
      message: t('admin.messages.enqueuedBooks', { count: response.data.added_count }),
      position: 'top'
    });
    void refreshStats();
  } catch (error) {
    console.error('Failed to enqueue:', error);
    $q.notify({
      type: 'negative',
      message: t('admin.messages.enqueueFailed'),
      position: 'top'
    });
  } finally {
    actionLoading.value.enqueue = false;
  }
}

async function triggerSync() {
  actionLoading.value.trigger = true;
  try {
    await api.post('/admin/midnight-sync/trigger');
    $q.notify({
      type: 'positive',
      message: t('admin.messages.syncTriggered'),
      position: 'top'
    });
    void refreshStats();
  } catch (error) {
    console.error('Failed to trigger sync:', error);
    $q.notify({
      type: 'negative',
      message: t('admin.messages.triggerFailed'),
      position: 'top'
    });
  } finally {
    actionLoading.value.trigger = false;
  }
}

async function clearCompleted() {
  actionLoading.value.clear = true;
  try {
    const response = await api.post('/admin/midnight-sync/clear-completed');
    $q.notify({
      type: 'positive',
      message: t('admin.messages.clearedEntries', { count: response.data.removed_count }),
      position: 'top'
    });
    void refreshStats();
  } catch (error) {
    console.error('Failed to clear:', error);
    $q.notify({
      type: 'negative',
      message: t('admin.messages.clearFailed'),
      position: 'top'
    });
  } finally {
    actionLoading.value.clear = false;
  }
}

function clearCache() {
  $q.dialog({
    title: t('admin.confirm.title'),
    message: t('admin.confirm.clearCache'),
    cancel: true,
    persistent: true
  }).onOk(() => {
    actionLoading.value.clearCache = true;
    void (async () => {
      try {
        await api.post('/admin/cache/clear');
        $q.notify({
          type: 'positive',
          message: t('admin.messages.cacheCleared'),
          position: 'top'
        });
        void refreshStats();
      } catch (error) {
        console.error('Failed to clear cache:', error);
        $q.notify({
          type: 'warning',
          message: t('admin.messages.cacheClearFailed'),
          position: 'top'
        });
      } finally {
        actionLoading.value.clearCache = false;
      }
    })();
  });
}

function clearJobHistory() {
  $q.dialog({
    title: t('admin.confirm.title'),
    message: t('admin.confirm.clearHistory'),
    cancel: true,
    persistent: true
  }).onOk(() => {
    actionLoading.value.clearHistory = true;
    void (async () => {
      try {
        const response = await api.post('/admin/jobs/clear_history');
        $q.notify({
          type: 'positive',
          message: t('admin.messages.historyCleared', { count: response.data.removed }),
          position: 'top'
        });
        void refreshStats();
      } catch (error) {
        console.error('Failed to clear job history:', error);
        $q.notify({
          type: 'negative',
          message: t('admin.messages.historyClearFailed'),
          position: 'top'
        });
      } finally {
        actionLoading.value.clearHistory = false;
      }
    })();
  });
}

function forceResyncBook() {
  if (!resyncBookId.value) {
    $q.notify({
      type: 'warning',
      message: t('admin.messages.enterBookId'),
      position: 'top'
    });
    return;
  }

  $q.dialog({
    title: t('admin.confirm.title'),
    message: t('admin.confirm.forceResync', { bookId: resyncBookId.value }),
    cancel: true,
    persistent: true
  }).onOk(() => {
    actionLoading.value.resync = true;
    void (async () => {
      try {
        const response = await api.post(`/admin/jobs/force-resync/${resyncBookId.value}`, null, {
          params: {
            priority: 15,
            clear_cache: true
          }
        });

        const isAlreadySyncing = response.data.status === 'already_syncing';
        $q.notify({
          type: isAlreadySyncing ? 'warning' : 'positive',
          message: isAlreadySyncing ? t('admin.messages.bookAlreadySyncing') : t('admin.messages.bookQueued'),
          position: 'top'
        });
        resyncBookId.value = '';
        void refreshStats();
      } catch (error) {
        console.error('Failed to resync book:', error);
        $q.notify({
          type: 'negative',
          message: t('admin.messages.resyncFailed'),
          position: 'top'
        });
      } finally {
        actionLoading.value.resync = false;
      }
    })();
  });
}

function initializeSync() {
  $q.dialog({
    title: t('admin.confirm.title'),
    message: t('admin.confirm.initSync'),
    cancel: true,
    persistent: true,
    html: true
  }).onOk(() => {
    actionLoading.value.initSync = true;
    void (async () => {
      try {
        const response = await api.post('/admin/init-sync', null, {
          params: {
            categories_limit: initSyncParams.value.categories,
            pages_per_category: initSyncParams.value.pagesPerCategory
          },
          timeout: 300000  // 5 minutes for long-running init-sync operation
        });

        $q.notify({
          type: 'positive',
          message: t('admin.messages.initSyncSuccess', {
            queued: response.data.queued,
            categories: response.data.scanned.categories
          }),
          position: 'top',
          timeout: 5000
        });
        void refreshStats();
      } catch (error) {
        console.error('Failed to initialize sync:', error);
        $q.notify({
          type: 'negative',
          message: t('admin.messages.initSyncFailed'),
          position: 'top'
        });
      } finally {
        actionLoading.value.initSync = false;
      }
    })();
  });
}

async function loadSMTPSettings() {
  try {
    const response = await api.get('/admin/smtp/settings');
    if (response.data.configured) {
      Object.assign(smtpSettings.value, response.data);
    }
  } catch (error) {
    console.error('Failed to load SMTP settings:', error);
  }
}

async function saveSMTPSettings() {
  actionLoading.value.saveSMTP = true;
  try {
    await api.post('/admin/smtp/settings', null, {
      params: {
        smtp_host: smtpSettings.value.smtp_host,
        smtp_port: smtpSettings.value.smtp_port,
        smtp_user: smtpSettings.value.smtp_user,
        smtp_password: smtpSettings.value.smtp_password,
        use_tls: smtpSettings.value.use_tls,
        use_ssl: smtpSettings.value.use_ssl,
        from_email: smtpSettings.value.from_email || smtpSettings.value.smtp_user,
        from_name: smtpSettings.value.from_name
      }
    });

    $q.notify({
      type: 'positive',
      message: t('admin.smtp.saveSuccess'),
      position: 'top'
    });
  } catch (error) {
    console.error('Failed to save SMTP settings:', error);
    $q.notify({
      type: 'negative',
      message: t('admin.smtp.saveFailed'),
      position: 'top'
    });
  } finally {
    actionLoading.value.saveSMTP = false;
  }
}

async function testSMTPConnection() {
  actionLoading.value.testSMTP = true;
  try {
    const response = await api.post('/admin/smtp/test');

    smtpSettings.value.last_test_status = response.data.status;
    smtpSettings.value.last_test_at = new Date().toLocaleString();

    $q.notify({
      type: response.data.status === 'success' ? 'positive' : 'negative',
      message: response.data.message,
      position: 'top'
    });
  } catch (error) {
    console.error('Failed to test SMTP connection:', error);
    smtpSettings.value.last_test_status = 'error';
    smtpSettings.value.last_test_at = new Date().toLocaleString();
    $q.notify({
      type: 'negative',
      message: t('admin.smtp.testFailed'),
      position: 'top'
    });
  } finally {
    actionLoading.value.testSMTP = false;
  }
}

// Load SMTP settings when dialog opens and user is logged in
watch(() => [showDialog.value, isAdminLoggedIn.value], ([dialog, loggedIn]) => {
  if (dialog && loggedIn) {
    void loadSMTPSettings();
  }
});
</script>

<style scoped>
.rounded-borders {
  border-radius: 4px;
}

/* Google Sign-In button container */
.google-signin-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 44px;
}

/* Password expansion item */
.password-expansion {
  border: 1px solid rgba(0, 0, 0, 0.12);
  border-radius: 4px;
}

body.body--dark .password-expansion {
  border-color: rgba(255, 255, 255, 0.18);
}

/* Admin info bar - light mode */
.admin-info-bar {
  background-color: rgba(0, 0, 0, 0.05);
  border: 1px solid rgba(0, 0, 0, 0.12);
}

/* Admin info bar - dark mode */
body.body--dark .admin-info-bar {
  background-color: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.18);
}

/* Action buttons in admin info bar - ensure visibility in dark mode */
.admin-action-btn {
  opacity: 0.7;
  transition: opacity 0.2s;
}

.admin-action-btn:hover {
  opacity: 1;
}

body.body--dark .admin-action-btn {
  opacity: 0.85;
}

body.body--dark .admin-action-btn:hover {
  opacity: 1;
}

/* Password dialog - ensure good contrast in dark mode */
.password-dialog {
  /* Quasar handles the background automatically, but we can add extra styling if needed */
}

body.body--dark .password-dialog {
  /* Additional dark mode styling for password dialog if needed */
}
</style>
