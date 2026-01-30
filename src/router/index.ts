import { defineRouter } from '#q-app/wrappers';
import {
  createMemoryHistory,
  createRouter,
  createWebHashHistory,
  createWebHistory,
} from 'vue-router';
import routes from './routes';
import { detectBasePath } from 'src/utils/basePath';

/*
 * If not building with SSR mode, you can
 * directly export the Router instantiation;
 *
 * The function below can be async too; either use
 * async/await or return a Promise which resolves
 * with the Router instance.
 */

export default defineRouter(function (/* { store, ssrContext } */) {
  const createHistory = process.env.SERVER
    ? createMemoryHistory
    : process.env.VUE_ROUTER_MODE === 'history'
      ? createWebHistory
      : createWebHashHistory;

  // Detect base path at runtime
  // Supports:
  // - / (root) - Standalone deployment
  // - /spa/ - FastAPI backend deployment
  // - Custom - Any other base path from config
  let basePath = process.env.VUE_ROUTER_BASE || '/';

  if (!process.env.SERVER) {
    // Client-side: detect base path from URL or config
    basePath = detectBasePath('auto');

    if (process.env.DEV) {
      console.log('[Router] Detected base path:', basePath);
      console.log('[Router] Current location:', window.location.pathname);
    }
  }

  const Router = createRouter({
    scrollBehavior: () => ({ left: 0, top: 0 }),
    routes,

    // Use runtime-detected base path
    // Falls back to build-time configuration for SSR
    history: createHistory(basePath),
  });

  return Router;
});
