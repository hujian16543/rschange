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
 * `passWithNoTests` 在 T4.1 曾置为 `true`——当时只装依赖、不写测试文件，而
 * `npm run check` 是出口门 G4.1，必须在没有测试文件的当下也是绿的。T4.4 已
 * 补齐测试套件，本项**移除**：保留它会让「测试文件被误删/被 include 模式漏掉」
 * 退化成一次静默通过，而 `check` 号称跑了测试却一个没跑。
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
  },
})
