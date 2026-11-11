// Standalone QA config. Runtime packages may be installed in a temporary prefix.
// PTIT_QA_NODE_MODULES points at that prefix's node_modules; application files stay unchanged.
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import vue from '@vitejs/plugin-vue'

const root = fileURLToPath(new URL('../..', import.meta.url))
const runtime = process.env.PTIT_QA_NODE_MODULES
export default {
  root,
  cacheDir: process.env.PTIT_QA_VITE_CACHE || path.join(root, 'node_modules/.qa-vite'),
  plugins: [vue()],
  resolve: {
    alias: [
      { find: '@', replacement: path.join(root, 'src') },
      { find: /^vue$/, replacement: path.join(root, 'node_modules/vue/dist/vue.runtime.esm-bundler.js') },
      ...(runtime ? [
        { find: /^vitest$/, replacement: path.join(runtime, 'vitest/dist/index.js') },
        { find: /^@vue\/test-utils$/, replacement: path.join(runtime, '@vue/test-utils/dist/vue-test-utils.esm-bundler.mjs') },
      ] : []),
      { find: '@vue', replacement: path.join(root, 'node_modules/@vue') },
    ],
    dedupe: ['vue', '@vue/reactivity', '@vue/runtime-core', '@vue/runtime-dom', '@vue/shared'],
  },
  server: { fs: { allow: [root, ...(runtime ? [runtime] : [])] } },
  test: {
    include: ['tests/qa/*.test.ts'], environment: 'jsdom', globals: false,
    server: { deps: { inline: [/@vue[\\/]test-utils/] } },
    clearMocks: true, restoreMocks: true, maxWorkers: 1,
    reporters: ['default', 'json'], outputFile: process.env.PTIT_QA_FE_OUTPUT,
  },
}
