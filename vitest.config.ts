import { defineConfig } from 'vitest/config';
import { resolve } from 'path';

export default defineConfig({
  test: {
    environment: 'happy-dom',
    globals: true,
    include: ['src/__tests__/**/*.test.ts'],
  },
  resolve: {
    alias: {
      src: resolve(__dirname, 'src'),
      boot: resolve(__dirname, 'src/boot'),
      stores: resolve(__dirname, 'src/stores'),
      components: resolve(__dirname, 'src/components'),
      layouts: resolve(__dirname, 'src/layouts'),
      pages: resolve(__dirname, 'src/pages'),
      assets: resolve(__dirname, 'src/assets'),
      app: resolve(__dirname),
    },
  },
});
