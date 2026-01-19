import { defineBoot } from '#q-app/wrappers';
import { useAppConfig } from 'src/services/useAppConfig';
import { setDark } from 'src/services/utils';

const { initAppConfig, config } = useAppConfig();

export default defineBoot(async ({ app }) => {
  await initAppConfig();
  app.config.globalProperties.$cfg = config; // Running in production mode
  console.log(
    `%c[boot] [app] Running in ${config.value.env} mode backend api ${config.value.apiBaseUrl} dark=${config.value.dark} fontsize=${config.value.fontsize}`,
    'color: red; font-weight: bold;',
  );

  // Restore dark mode preference if it was saved
  if (config.value.dark !== undefined) {
    setDark(config.value.dark === 'true');
  }
});
