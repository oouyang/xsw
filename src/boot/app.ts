import { defineBoot } from '#q-app/wrappers';
import { useAppConfig } from 'src/services/useAppConfig';

const { initAppConfig, config } = useAppConfig();
export default defineBoot(async ({ app }) => {
  await initAppConfig();
  app.config.globalProperties.$cfg = config; // Running in production mode
  console.log(
    `%c[boot] [app] Running in ${config.value.env} mode backend api ${config.value.apiBaseUrl}`,
    'color: red; font-weight: bold;',
  );
});
