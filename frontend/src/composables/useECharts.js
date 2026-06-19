/**
 * useECharts · ECharts 按需引入 composable
 * - 自动 init / resize / dispose
 * - 主题色从 CSS 变量读取，支持暗色模式切换
 * - ResizeObserver 响应容器尺寸
 */
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import * as echarts from 'echarts/core'
import { PieChart, LineChart, BarChart } from 'echarts/charts'
import {
  TitleComponent, TooltipComponent, LegendComponent,
  GridComponent, DatasetComponent,
} from 'echarts/components'
import { LabelLayout, UniversalTransition } from 'echarts/features'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  PieChart, LineChart, BarChart,
  TitleComponent, TooltipComponent, LegendComponent,
  GridComponent, DatasetComponent,
  LabelLayout, UniversalTransition,
  CanvasRenderer,
])

/** 从 CSS 变量读取颜色，失败回退 */
function cssVar(name, fallback) {
  try {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
    return v || fallback
  } catch {
    return fallback
  }
}

/** 获取主题色板 */
export function useThemeColors() {
  return {
    brand:   cssVar('--brand', '#002FA7'),
    brand2:  cssVar('--brand-2', '#3370FF'),
    success: cssVar('--success', '#00B42A'),
    warning: cssVar('--warning', '#FF7D00'),
    danger:  cssVar('--danger', '#F53F3F'),
    purple:  cssVar('--purple', '#722ED1'),
    text1:   cssVar('--text-1', '#1D2129'),
    text2:   cssVar('--text-2', '#4E5969'),
    text3:   cssVar('--text-3', '#86909C'),
    text4:   cssVar('--text-4', '#C9CDD4'),
    border1: cssVar('--border-1', '#E5E6EB'),
    fill1:   cssVar('--fill-1', '#F7F8FA'),
    card:    cssVar('--bg-card', '#FFFFFF'),
  }
}

/**
 * @param {import('vue').Ref<HTMLElement|null>} containerRef
 * @param {(chart, colors) => object} optionFn  返回 ECharts option
 * @param {import('vue').Ref<any>} [dep]  依赖项变化时重绘
 */
export function useECharts(containerRef, optionFn, dep) {
  const chart = ref(null)
  let ro = null

  function build() {
    if (!containerRef.value) return
    if (!chart.value) {
      chart.value = echarts.init(containerRef.value, null, { renderer: 'canvas' })
      ro = new ResizeObserver(() => chart.value && chart.value.resize())
      ro.observe(containerRef.value)
    }
    const colors = useThemeColors()
    const option = optionFn(chart.value, colors)
    chart.value.setOption(option, true)
  }

  function rebuild() {
    if (chart.value) {
      chart.value.dispose()
      chart.value = null
    }
    build()
  }

  onMounted(() => nextTick(build))
  onBeforeUnmount(() => {
    if (ro) { ro.disconnect(); ro = null }
    if (chart.value) { chart.value.dispose(); chart.value = null }
  })

  if (dep) watch(dep, () => nextTick(rebuild), { deep: true })

  // 监听主题切换
  watch(
    () => document.documentElement.getAttribute('data-theme'),
    () => nextTick(rebuild),
  )

  return { chart, rebuild }
}

export { echarts }
