/**
 * Vitest 全局前置。
 *
 * 三件事：
 *
 * 1. 引入 `@testing-library/jest-dom` 的匹配器（`toBeInTheDocument` 等）。
 *    入口取 `/vitest` 而非 `/jest-globals`：前者把匹配器挂到 `vitest` 模块的
 *    `Assertion` 接口上，后者是给 `expect` 走 jest 全局时的形态。本项目
 *    `globals: true`，但 `expect` 仍由 vitest 提供，故用 `/vitest`。
 * 2. 测试后卸载上一用例挂载的组件。RTL 在检测到**全局** `afterEach` 时会自动
 *    注册清理，但显式写出更可靠：一旦将来 `globals` 关掉，自动清理会静默失效，
 *    表现为「用例间 UI 串味」这类极难定位的失败。
 * 3. 还原 mock。`vi.restoreAllMocks()` 会撤销 `vi.spyOn` 与
 *    `vi.stubGlobal`，避免某个用例替换的 `URL.createObjectURL` 泄漏到下一个
 *    用例。`vi.mock` 的模块替换不在其列，由各测试文件自己 `mockClear`。
 */

import '@testing-library/jest-dom/vitest'

import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})
