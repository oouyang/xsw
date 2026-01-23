// src/stores/appSettings.ts
import { defineStore } from 'pinia';
import { Dark } from 'quasar';
import { useAppConfig } from 'src/services/useAppConfig';

export type SupportedLocale = 'en-US' | 'zh-TW' | 'zh-CN';

export interface AppSettingsState {
  locale: SupportedLocale;
  fontsize: number; // 1..7
  dark: boolean;
}

const defaultFontsize = 5;
const defaultDark = true;
const defaultLocale = 'zh-TW';
export const useAppSettings = defineStore('appSettings', {
  state: (): AppSettingsState => ({
    locale: defaultLocale,
    fontsize: defaultFontsize,
    dark: defaultDark,
  }),

  actions: {
    load(): void {
      // const fromLS = LocalStorage.getItem<AppSettingsState>(STORAGE_KEY);
      // if (fromLS) this.$patch(fromLS);
      // Dark.set(this.dark);
      const { config } = useAppConfig();
      this.locale = config.value.locale ?? defaultLocale;
      this.fontsize = Number(config.value.fontsize) || defaultFontsize;
      this.dark = config.value.dark === 'true';
      Dark.set(this.dark);
    },

    save(): void {
      // LocalStorage.set(STORAGE_KEY, {
      //   locale: this.locale,
      //   fontsize: this.fontsize,
      //   dark: this.dark,
      // });
      const { update } = useAppConfig();
      update({ locale: this.locale, fontsize: `${this.fontsize}`, dark: `${this.dark}` });
    },

    update(p: Partial<AppSettingsState>): void {
      this.$patch(p);
      if (typeof p.dark === 'boolean') Dark.set(this.dark);
      this.save();
    },

    setLocale(l: SupportedLocale): void {
      this.locale = l;
      this.save();
    },

    setFontsize(n: number): void {
      const clamped = Math.max(1, Math.min(7, n));
      this.fontsize = clamped;
      this.save();
    },

    setDark(v: boolean): void {
      this.dark = v;
      Dark.set(v);
      this.save();
    },

    toggleDark(): void {
      this.setDark(!this.dark);
    },
  },
});

// initAutosave() {
//   watch(
//     () => ({ ...this.$state }), // deep clone pointer to trigger on any field
//     () => this.save(),
//     { deep: true, immediate: false }
//   );
// }
