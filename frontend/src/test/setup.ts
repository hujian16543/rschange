/**
 * Vitest 全局前置。
 *
 * 引入 `@testing-library/jest-dom` 的匹配器（`toBeInTheDocument` 等），供 T4.4
 * 的组件测试使用。T4.1 尚无测试文件，此文件是依赖的一次性落位。
 */
import '@testing-library/jest-dom/vitest'
