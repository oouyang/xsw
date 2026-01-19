// src/boot/appSettings.ts
// import { boot } from 'quasar/wrappers';
// import { useAppSettings } from 'src/stores/appSettings';
// import { useI18n } from 'vue-i18n';

// export default boot(() => {
//   const settings = useAppSettings();
//   settings.load();

//   const { locale } = useI18n({ useScope: 'global' });

//   if ('value' in locale) locale.value = settings.locale;

//   // Apply locale to i18n if present
//   // Note: with Quasar boot, the i18n instance is available on globalProperties.
//   // const i18n = app.config.globalProperties.$i18n;
//   // if (i18n?.locale) {
//   //   i18n.locale.value = settings.locale;
//   // }
// });
