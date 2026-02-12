<template>
  <q-btn flat round dense icon="share" :size="size" @click="onShareClick">
    <q-tooltip>{{ $t('action.share') }}</q-tooltip>
    <q-menu v-if="!share.canNativeShare" anchor="bottom right" self="top right">
      <q-list dense style="min-width: 180px">
        <q-item clickable v-close-popup @click="share.shareFacebook(shareUrl)">
          <q-item-section avatar><q-icon name="facebook" color="blue-8" /></q-item-section>
          <q-item-section>Facebook</q-item-section>
        </q-item>
        <q-item clickable v-close-popup @click="share.shareLine(shareUrl, shareText)">
          <q-item-section avatar><q-icon name="chat" color="green" /></q-item-section>
          <q-item-section>LINE</q-item-section>
        </q-item>
        <q-item clickable v-close-popup @click="share.shareTwitter(shareUrl, shareText)">
          <q-item-section avatar><q-icon name="tag" color="blue" /></q-item-section>
          <q-item-section>Twitter / X</q-item-section>
        </q-item>
        <q-item clickable v-close-popup @click="share.shareWeChatQR(shareUrl)">
          <q-item-section avatar><q-icon name="qr_code_2" color="green-8" /></q-item-section>
          <q-item-section>WeChat</q-item-section>
        </q-item>
        <q-separator />
        <q-item clickable v-close-popup @click="share.copyLink(shareUrl)">
          <q-item-section avatar><q-icon name="content_copy" /></q-item-section>
          <q-item-section>{{ $t('action.copyLink') }}</q-item-section>
        </q-item>
      </q-list>
    </q-menu>
  </q-btn>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useShare } from 'src/composables/useShare';

const share = useShare();

const props = withDefaults(
  defineProps<{
    title: string;
    text?: string;
    url?: string;
    size?: string;
  }>(),
  {
    text: '',
    url: '',
    size: 'sm',
  },
);

const shareUrl = computed(() => props.url || window.location.href);
const shareText = computed(() => props.text || props.title);

async function onShareClick() {
  if (share.canNativeShare) {
    await share.shareNative({
      title: props.title,
      text: shareText.value,
      url: shareUrl.value,
    });
  }
  // If not native, the q-menu will show automatically via click
}
</script>
