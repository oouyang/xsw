import { defineBoot } from '#q-app/wrappers';
import axios, { type AxiosInstance } from 'axios';
import { useAppConfig } from 'src/services/useAppConfig';

declare module 'vue' {
  interface ComponentCustomProperties {
    $axios: AxiosInstance;
    $api: AxiosInstance;
  }
}

// Create axios instance inside boot to use loaded config
let api: AxiosInstance;

export default defineBoot(({ app }) => {
  const { config, loaded } = useAppConfig();

  // Wait for config to be loaded (should be loaded by app boot, but double-check)
  console.log('[boot] [axios] Config loaded status:', loaded.value);
  console.log('[boot] [axios] Config apiBaseUrl before:', config.value.apiBaseUrl);

  // Use config.json apiBaseUrl (loaded by app boot), fallback to relative path
  const baseurl = config.value.apiBaseUrl || '/xsw/api';

  api = axios.create({
    baseURL: baseurl,
    timeout: 15000,
  });

  // for use inside Vue files (Options API) through this.$axios and this.$api
  app.config.globalProperties.$axios = axios;
  // ^ ^ ^ this will allow you to use this.$axios (for Vue Options API form)
  //       so you won't necessarily have to import axios in each vue file

  app.config.globalProperties.$api = api;
  // ^ ^ ^ this will allow you to use this.$api (for Vue Options API form)
  //       so you can easily perform requests against your app's API
  console.log('[boot] [axios] baseURL:', baseurl);
  console.log('[boot] [axios] Full config:', JSON.stringify(config.value, null, 2));

  // Check if there are localStorage overrides
  if (typeof window !== 'undefined' && window.localStorage) {
    const lsKey = 'app.config.overrides';
    const overrides = window.localStorage.getItem(lsKey);
    if (overrides) {
      console.log('[boot] [axios] localStorage overrides found:', overrides);
    }
  }
});

export { api };
