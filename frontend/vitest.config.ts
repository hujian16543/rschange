import { fileURLToPath } from 'node:url'

import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

/**
 * Vitest 配置。
 *
 * 单独成文件而非并入 `vite.config.ts`：`tsconfig.node.json` 只收录
 * `vite.config.ts`，把测试配置混进去会让 `defineConfig` 的类型解析在
 * `vite` 与 `vitest/config` 两个模块间摇摆。
 *
 * `passWithNoTests: true` 是必要的——T4.1 只装依赖、不写测试文件（T4.4 才写），
 * 而 `npm run check` 是 Phase 4 的出口门 G4.1，必须在没有测试文件的当下也是绿的。
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    passWithNoTests: true,
  },
})
