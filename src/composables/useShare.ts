// src/composables/useShare.ts
import { useQuasar } from 'quasar';

export interface ShareData {
  title: string;
  text: string;
  url: string;
}

export function useShare() {
  const $q = useQuasar();

  const canNativeShare = typeof navigator !== 'undefined' && !!navigator.share;

  async function shareNative(data: ShareData): Promise<boolean> {
    if (!canNativeShare) return false;
    try {
      await navigator.share(data);
      return true;
    } catch {
      return false;
    }
  }

  function shareFacebook(url: string) {
    window.open(
      `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(url)}`,
      '_blank',
      'width=600,height=400',
    );
  }

  function shareLine(url: string, text: string) {
    window.open(
      `https://social-plugins.line.me/lineit/share?url=${encodeURIComponent(url)}&text=${encodeURIComponent(text)}`,
      '_blank',
      'width=600,height=400',
    );
  }

  function shareTwitter(url: string, text: string) {
    window.open(
      `https://twitter.com/intent/tweet?url=${encodeURIComponent(url)}&text=${encodeURIComponent(text)}`,
      '_blank',
      'width=600,height=400',
    );
  }

  async function shareWeChatQR(url: string) {
    // Dynamically import qrcode to generate QR
    try {
      const QRCode = (await import('qrcode')).default;
      const dataUrl = await QRCode.toDataURL(url, { width: 256 });

      $q.dialog({
        title: 'WeChat',
        message: '<img src="' + dataUrl + '" style="width:100%;max-width:256px;display:block;margin:0 auto" />',
        html: true,
        ok: { label: 'Close', flat: true },
      });
    } catch {
      // Fallback: just show the URL
      await copyLink(url);
    }
  }

  async function copyLink(url: string): Promise<boolean> {
    try {
      await navigator.clipboard.writeText(url);
      $q.notify({ message: 'Link copied!', type: 'positive', position: 'bottom', timeout: 1500 });
      return true;
    } catch {
      return false;
    }
  }

  return {
    canNativeShare,
    shareNative,
    shareFacebook,
    shareLine,
    shareTwitter,
    shareWeChatQR,
    copyLink,
  };
}
