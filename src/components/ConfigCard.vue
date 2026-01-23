<template>
  <q-dialog ref="dialogRef" @hide="onDialogHide" v-bind="$attrs" position="bottom">
    <q-card class="config-card" style="width: 100%; max-width: 500px;">
      <q-card-section class="row items-center q-pb-none">
        <div class="text-h6">{{ $t('settings.title') }}</div>
        <q-space />
        <q-btn flat dense round icon="close" @click="onDialogOK" />
      </q-card-section>

      <q-separator class="q-my-sm" />

      <q-card-section class="q-pt-none">
        <!-- Language Selector -->
        <div class="setting-group q-mb-lg">
          <div class="setting-label row items-center q-mb-sm">
            <q-icon name="language" size="20px" class="q-mr-xs" />
            <span class="text-subtitle2">Language / 語言 / 语言</span>
          </div>
          <div class="row q-col-gutter-sm">
            <div class="col-4">
              <q-btn
                unelevated
                no-caps
                :outline="locale !== 'en-US'"
                :color="locale === 'en-US' ? 'primary' : (isDarkActive() ? 'grey-7' : 'grey-5')"
                :text-color="locale === 'en-US' ? 'white' : (isDarkActive() ? 'grey-3' : 'grey-8')"
                :label="$t('language.enUS')"
                class="full-width"
                @click="changeLocale('en-US')"
              />
            </div>
            <div class="col-4">
              <q-btn
                unelevated
                no-caps
                :outline="locale !== 'zh-TW'"
                :color="locale === 'zh-TW' ? 'primary' : (isDarkActive() ? 'grey-7' : 'grey-5')"
                :text-color="locale === 'zh-TW' ? 'white' : (isDarkActive() ? 'grey-3' : 'grey-8')"
                :label="$t('language.zhTW')"
                class="full-width"
                @click="changeLocale('zh-TW')"
              />
            </div>
            <div class="col-4">
              <q-btn
                unelevated
                no-caps
                :outline="locale !== 'zh-CN'"
                :color="locale === 'zh-CN' ? 'primary' : (isDarkActive() ? 'grey-7' : 'grey-5')"
                :text-color="locale === 'zh-CN' ? 'white' : (isDarkActive() ? 'grey-3' : 'grey-8')"
                :label="$t('language.zhCN')"
                class="full-width"
                @click="changeLocale('zh-CN')"
              />
            </div>
          </div>
        </div>

        <!-- Dark Mode Toggle -->
        <div class="setting-group q-mb-lg">
          <div class="setting-label row items-center q-mb-sm">
            <q-icon :name="isDarkActive() ? 'dark_mode' : 'light_mode'" size="20px" class="q-mr-xs" />
            <span class="text-subtitle2">{{ $t('settings.darkMode') }}</span>
          </div>
          <q-btn-toggle
            :model-value="isDarkActive()"
            @update:model-value="toggleDark()"
            toggle-color="primary"
            unelevated
            spread
            :options="[
              { label: `☀️ ${$t('settings.lightMode')}`, value: false, icon: 'light_mode' },
              { label: `🌙 ${$t('settings.darkModeLabel')}`, value: true, icon: 'dark_mode' }
            ]"
          />
        </div>

        <!-- Font Size Slider -->
        <div class="setting-group q-mb-md">
          <div class="setting-label row items-center q-mb-sm">
            <q-icon name="format_size" size="20px" class="q-mr-xs" />
            <span class="text-subtitle2">{{ $t('settings.fontSize') }}</span>
            <q-space />
            <q-chip dense color="primary" text-color="white" size="sm">
              {{ fontSizeLabel }}
            </q-chip>
          </div>

          <div class="row items-center q-gutter-sm">
            <q-btn
              flat
              dense
              round
              icon="remove"
              :disable="fontsize >= 7"
              @click="updateFontSize(fontsize + 1)"
              size="sm"
            />
            <q-slider
              :model-value="fontsize"
              @update:model-value="updateFontSize"
              :min="1"
              :max="7"
              :step="1"
              label
              label-always
              :label-value="fontSizeLabel"
              color="primary"
              class="col"
              markers
              snap
            />
            <q-btn
              flat
              dense
              round
              icon="add"
              :disable="fontsize <= 1"
              @click="updateFontSize(fontsize - 1)"
              size="sm"
            />
          </div>
        </div>

        <!-- Preview -->
        <div class="setting-group q-mb-lg">
          <div class="setting-label row items-center q-mb-sm">
            <q-icon name="visibility" size="20px" class="q-mr-xs" />
            <span class="text-subtitle2">{{ $t('settings.preview') }}</span>
          </div>
          <q-card flat bordered class="preview-card q-pa-md">
            <p :class="`text-h${fontsize}`" style="margin: 0; text-indent: 2em; line-height: 1.8;">
              {{ $t('settings.previewText') }}
            </p>
          </q-card>
        </div>

        <!-- Admin Section -->
        <div class="setting-group">
          <q-separator class="q-my-md" />
          <q-btn
            unelevated
            color="primary"
            icon="admin_panel_settings"
            label="Admin Panel"
            class="full-width"
            @click="showAdminDialog = true"
          />
        </div>
      </q-card-section>

      <q-card-actions align="right" class="q-px-md q-pb-md">
        <q-btn
          flat
          color="primary"
          :label="$t('common.done')"
          icon-right="check"
          @click="onDialogOK"
          padding="sm lg"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>

  <!-- Admin Dialog -->
  <AdminDialog v-model="showAdminDialog" />
</template>

<script setup lang="ts">
import { useDialogPluginComponent } from 'quasar';
import { useAppConfig } from 'src/services/useAppConfig';
import { isDarkActive, toggleDark } from 'src/services/utils';
import AdminDialog from 'src/components/AdminDialog.vue';
import { useLocale } from 'boot/i18n';
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';

defineEmits([...useDialogPluginComponent.emits]);

const { dialogRef, onDialogHide, onDialogOK } = useDialogPluginComponent();
const { config, update } = useAppConfig();
const { locale, t } = useI18n();
const { storeLocale } = useLocale();

const fontsize = computed(() => Number(config.value.fontsize || 7));

const fontSizeLabel = computed(() => {
  const labels: Record<number, string> = {
    1: t('fontSizes.largest'),
    2: t('fontSizes.larger'),
    3: t('fontSizes.large'),
    4: t('fontSizes.mediumLarge'),
    5: t('fontSizes.medium'),
    6: t('fontSizes.small'),
    7: t('fontSizes.smallest')
  };
  return labels[fontsize.value] || t('fontSizes.medium');
});

function updateFontSize(size: number | null) {
  if (size === null) return;
  const validSize = Math.max(1, Math.min(7, size));
  update({ fontsize: `${validSize}` });
}

function changeLocale(newLocale: string) {
  locale.value = newLocale;
  // Type assertion: newLocale comes from language buttons with known values
  storeLocale(newLocale as 'en-US' | 'zh-TW' | 'zh-CN');
}

// Admin dialog
const showAdminDialog = ref(false);
</script>

<style scoped>
.config-card {
  border-radius: 16px 16px 0 0;
}

.setting-group {
  animation: fadeIn 0.3s ease-in;
}

.setting-label {
  font-weight: 500;
  opacity: 0.8;
}

.preview-card {
  background: var(--q-color-dark-page, #f5f5f5);
  border-radius: 8px;
  transition: all 0.3s ease;
}

.q-dark .preview-card {
  background: rgba(255, 255, 255, 0.05);
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.admin-panel {
  animation: fadeIn 0.4s ease-in;
  padding: 8px;
  border-radius: 8px;
  background: rgba(33, 150, 243, 0.05);
}

.q-dark .admin-panel {
  background: rgba(33, 150, 243, 0.1);
}

.admin-panel .text-body2 {
  font-size: 0.875rem;
  line-height: 1.4;
}

.admin-panel .text-body2 > div {
  padding: 2px 0;
}
</style>