/**
 * `ResultPanel` 结果渲染测试（契约 §9.3 的 13 个字段）。
 *
 * 本文件守护 T4.2 的核心回归点：`detector` / `pixel_area_m2` /
 * `changed_area_m2` 三个新增字段**必须真的被渲染出来**。旧前端只展示 10 个
 * 字段，这三个曾整块缺失；只靠类型定义无法发现「字段存在但没人用」——类型不会
 * 因为一个字段没被读取而报错。
 *
 * 每条断言都把「期望串」写成 fixture 里独立导出的常量（如
 * `EXAMPLE_AREA_DISPLAY = '72.09 公顷'`），而不是从 `result` 现算一份再比对。
 * 若写成 `expect(...).toHaveTextContent(formatArea(result.changed_area_m2))`，
 * 那就是「渲染结果与格式化函数互相印证」的循环，格式化函数改了、字段根本没
 * 被渲染，都会照样绿。这里期望值是**人工核对过的字面量**，字段缺失必红。
 *
 * 边界覆盖：`geojson === null`、三个 `image_*_url === null`、
 * `image_corners` 为空数组——都是 §9.3 允许的取值，且都不能渲染出破图或空
 * `<img>`。
 */

import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ResultPanel } from '@/features/detection/components/ResultPanel'
import type { DetectionResponse } from '@/types/detection'
import {
  EXAMPLE_AREA_DISPLAY,
  EXAMPLE_CHANGE_PIXELS,
  EXAMPLE_DETECTOR,
  EXAMPLE_PIXEL_AREA_DISPLAY,
  EXAMPLE_RATE_DISPLAY,
  EXAMPLE_RESPONSE,
  EXAMPLE_THRESHOLD_DISPLAY,
  RESPONSE_WITH_NULLS,
} from '@/test/fixtures'

/** 从 fixture 派生一份响应，只改需要变的字段。 */
function withOverrides(overrides: Partial<DetectionResponse>): DetectionResponse {
  return { ...EXAMPLE_RESPONSE, ...overrides }
}

describe('ResultPanel 渲染契约 13 字段', () => {
  it('渲染 detector（T4.2 新增，结果溯源）', () => {
    render(<ResultPanel result={EXAMPLE_RESPONSE} />)

    // `cva` 只可能来自 `result.detector`——页面其他任何文案都不含它。
    expect(screen.getByText(EXAMPLE_DETECTOR)).toBeInTheDocument()
    expect(screen.getByText('检测算法')).toBeInTheDocument()
  })

  it('detector 随响应变化，而非写死（防止渲染常量）', () => {
    const { unmount } = render(<ResultPanel result={withOverrides({ detector: 'cva' })} />)
    expect(screen.getByText('cva')).toBeInTheDocument()
    unmount()

    render(<ResultPanel result={withOverrides({ detector: 'ir-mad' })} />)
    expect(screen.getByText('ir-mad')).toBeInTheDocument()
    expect(screen.queryByText('cva')).not.toBeInTheDocument()
  })

  it('渲染 pixel_area_m2（T4.2 新增，单像元面积）', () => {
    render(<ResultPanel result={EXAMPLE_RESPONSE} />)

    expect(screen.getByText('单像元面积')).toBeInTheDocument()
    // fixture 里 pixel_area_m2 = 100.0 → 展示 "100 m²"
    expect(screen.getByText(EXAMPLE_PIXEL_AREA_DISPLAY)).toBeInTheDocument()
  })

  it('pixel_area_m2 随数值变化（证明是按字段值渲染的）', () => {
    render(<ResultPanel result={withOverrides({ pixel_area_m2: 900 })} />)

    expect(screen.getByText('900 m²')).toBeInTheDocument()
    expect(screen.queryByText(EXAMPLE_PIXEL_AREA_DISPLAY)).not.toBeInTheDocument()
  })

  it('渲染 changed_area_m2（T4.2 新增，核心指标）', () => {
    render(<ResultPanel result={EXAMPLE_RESPONSE} />)

    expect(screen.getByText('真实变化面积')).toBeInTheDocument()
    // changed_area_m2 = 720900 → 量级落在公顷档 → "72.09 公顷"
    expect(screen.getByText(EXAMPLE_AREA_DISPLAY)).toBeInTheDocument()
  })

  it('changed_area_m2 的单位换算：随量级切换 m² / 公顷 / km²', () => {
    // < 1e4 m²：直接给平方米
    const { unmount: u1 } = render(<ResultPanel result={withOverrides({ changed_area_m2: 9999 })} />)
    expect(screen.getByText('9,999 m²')).toBeInTheDocument()
    u1()

    // [1e4, 1e6)：换算为公顷 —— 合同锚点 720900 走这一档
    const { unmount: u2 } = render(<ResultPanel result={withOverrides({ changed_area_m2: 720900 })} />)
    expect(screen.getByText('72.09 公顷')).toBeInTheDocument()
    u2()

    // >= 1e6：换算为 km²
    render(<ResultPanel result={withOverrides({ changed_area_m2: 2_500_000 })} />)
    expect(screen.getByText('2.5 km²')).toBeInTheDocument()
  })

  it('变化面积保留原始平方米原值（换算后仍可取证核对）', () => {
    render(<ResultPanel result={EXAMPLE_RESPONSE} />)

    // 主展示换成了「公顷」，但 title 必须留着 720,900 m²，否则无法与
    // 契约锚点（§9.10）直接核对。
    const display = screen.getByText(EXAMPLE_AREA_DISPLAY)
    expect(display).toHaveAttribute('title', '720,900 m²')
  })

  it('渲染其余统计字段：变化像元 / 总像元 / 变化率 / 阈值', () => {
    render(<ResultPanel result={EXAMPLE_RESPONSE} />)

    expect(screen.getByText('7,209')).toBeInTheDocument()
    expect(screen.getByText('65,536')).toBeInTheDocument()
    expect(screen.getByText(EXAMPLE_RATE_DISPLAY)).toBeInTheDocument()
    expect(screen.getByText(EXAMPLE_THRESHOLD_DISPLAY)).toBeInTheDocument()
  })

  it('变化面积与「像元数 × 单像元面积」的换算关系被展示出来', () => {
    render(<ResultPanel result={EXAMPLE_RESPONSE} />)

    // 用来解释面积是怎么来的，用户才能核对。
    expect(
      screen.getByText(`= ${EXAMPLE_CHANGE_PIXELS.toLocaleString('en-US')} 像元 × ${EXAMPLE_PIXEL_AREA_DISPLAY}`),
    ).toBeInTheDocument()
  })
})

describe('ResultPanel 预览图与空值边界', () => {
  it('三个 URL 齐全时渲染三张图，且每张都有非空 alt', () => {
    render(<ResultPanel result={EXAMPLE_RESPONSE} />)

    const images = screen.getAllByRole('img')
    expect(images).toHaveLength(3)

    for (const image of images) {
      // 空 alt（alt=""）会被读屏整块跳过，用户不知道这里有几张图。
      const alt = image.getAttribute('alt')
      expect(alt).not.toBeNull()
      expect(alt).not.toBe('')
    }
  })

  it('图片的 alt 说明是哪一时相，而非无意义的 "image"', () => {
    render(<ResultPanel result={EXAMPLE_RESPONSE} />)

    expect(screen.getByAltText('前时相')).toBeInTheDocument()
    expect(screen.getByAltText('后时相')).toBeInTheDocument()
    expect(screen.getByAltText('变化检测（红色为变化区域）')).toBeInTheDocument()
  })

  it('图片 src 直接取自响应的三个 URL', () => {
    render(<ResultPanel result={EXAMPLE_RESPONSE} />)

    expect(screen.getByAltText('前时相')).toHaveAttribute('src', EXAMPLE_RESPONSE.image_before_url)
    expect(screen.getByAltText('后时相')).toHaveAttribute('src', EXAMPLE_RESPONSE.image_after_url)
    expect(screen.getByAltText('变化检测（红色为变化区域）')).toHaveAttribute(
      'src',
      EXAMPLE_RESPONSE.image_diff_url,
    )
  })

  it('三个 URL 全为 null 时不渲染任何 <img>（不出现破图）', () => {
    render(<ResultPanel result={RESPONSE_WITH_NULLS} />)

    expect(screen.queryAllByRole('img')).toHaveLength(0)
  })

  it('部分 URL 为 null 时也不渲染破图（整块不渲染）', () => {
    render(<ResultPanel result={withOverrides({ image_diff_url: null })} />)

    // diff 图缺失时，三图对比区整体不渲染，避免出现一个空图位。
    expect(screen.queryByAltText('变化检测（红色为变化区域）')).not.toBeInTheDocument()
    expect(screen.queryAllByRole('img')).toHaveLength(0)
  })

  it('src 为空字符串同样不渲染 <img>', () => {
    render(
      <ResultPanel
        result={withOverrides({
          image_before_url: '',
          image_after_url: '',
          image_diff_url: '',
        })}
      />,
    )

    expect(screen.queryAllByRole('img')).toHaveLength(0)
  })

  it('统计字段在预览图缺失时仍完整渲染（图片与统计解耦）', () => {
    render(<ResultPanel result={RESPONSE_WITH_NULLS} />)

    expect(screen.getByText(EXAMPLE_DETECTOR)).toBeInTheDocument()
    expect(screen.getByText(EXAMPLE_AREA_DISPLAY)).toBeInTheDocument()
    expect(screen.getByText(EXAMPLE_PIXEL_AREA_DISPLAY)).toBeInTheDocument()
  })
})

describe('ResultPanel geojson 与 image_corners 边界', () => {
  it('geojson 非空时提供下载按钮与「已矢量化」标记', () => {
    render(<ResultPanel result={EXAMPLE_RESPONSE} />)

    expect(screen.getByText('变化区域已矢量化')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '下载 GeoJSON' })).toBeInTheDocument()
  })

  it('geojson 为 null 时不渲染下载按钮（点了没反应比没有更糟）', () => {
    render(<ResultPanel result={withOverrides({ geojson: null })} />)

    expect(screen.queryByRole('button', { name: '下载 GeoJSON' })).not.toBeInTheDocument()
    expect(screen.queryByText('变化区域已矢量化')).not.toBeInTheDocument()
  })

  it('geojson 为 null 但 corners 存在时，角点仍渲染', () => {
    render(<ResultPanel result={withOverrides({ geojson: null })} />)

    expect(screen.getByText('左上')).toBeInTheDocument()
    expect(screen.getByText('左下')).toBeInTheDocument()
  })

  it('image_corners 为 null 时不渲染角点区块', () => {
    render(<ResultPanel result={withOverrides({ image_corners: null })} />)

    expect(screen.queryByText('左上')).not.toBeInTheDocument()
  })

  it('image_corners 为空数组时不崩溃、不渲染角点', () => {
    render(<ResultPanel result={withOverrides({ image_corners: [] })} />)

    expect(screen.queryByText('左上')).not.toBeInTheDocument()
    // 四个角点名称一个都不该出现。
    for (const label of ['左上', '右上', '右下', '左下']) {
      expect(screen.queryByText(label)).not.toBeInTheDocument()
    }
    // 统计区仍在——空角点不该把整块结果打没。
    expect(screen.getByText(EXAMPLE_DETECTOR)).toBeInTheDocument()
  })

  it('geojson 与 corners 同时为空时不渲染「矢量与范围」卡', () => {
    render(<ResultPanel result={withOverrides({ geojson: null, image_corners: null })} />)

    expect(screen.queryByText('矢量与范围')).not.toBeInTheDocument()
  })

  it('角点经纬度按契约顺序（左上、右上、右下、左下）配对显示', () => {
    render(<ResultPanel result={EXAMPLE_RESPONSE} />)

    // 四角齐全时应有四行；用 dl 内的 dt/dd 配对关系核对顺序。
    const leftTop = screen.getByText('左上')
    const row = leftTop.closest('div')
    expect(row).not.toBeNull()
    if (row !== null) {
      expect(within(row).getByText('117.00000°, 36.14472°')).toBeInTheDocument()
    }

    expect(screen.getByText('右上')).toBeInTheDocument()
    expect(screen.getByText('右下')).toBeInTheDocument()
    expect(screen.getByText('左下')).toBeInTheDocument()
  })

  it('角点数量多于四个时退化为「角点 N」而非丢失', () => {
    render(
      <ResultPanel
        result={withOverrides({
          image_corners: [
            [1, 2],
            [3, 4],
            [5, 6],
            [7, 8],
            [9, 10],
          ],
        })}
      />,
    )

    expect(screen.getByText('角点 5')).toBeInTheDocument()
  })
})

describe('ResultPanel 整体结构', () => {
  it('三块面板（核心指标 / 统计明细 / 矢量与范围）都渲染', () => {
    render(<ResultPanel result={EXAMPLE_RESPONSE} />)

    expect(screen.getByText('真实变化面积')).toBeInTheDocument()
    expect(screen.getByText('统计明细')).toBeInTheDocument()
    expect(screen.getByText('矢量与范围')).toBeInTheDocument()
  })

  it('统计明细以 <dl> 承载标签-数值配对（进入无障碍树）', () => {
    render(<ResultPanel result={EXAMPLE_RESPONSE} />)

    const list = screen.getByText('检测算法').closest('dl')
    expect(list).not.toBeNull()
  })
})
