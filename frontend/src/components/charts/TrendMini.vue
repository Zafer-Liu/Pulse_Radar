<template>
  <div ref="el" class="trend-mini"></div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useECharts } from '../../composables/useECharts'

const props = defineProps({
  data: { type: Array, default: () => [] },      // [{ label, value }]
  color: { type: String, default: 'brand' },     // brand | success | danger | warning
  height: { type: [Number, String], default: 60 },
})

const el = ref(null)

const colorMap = {
  brand: '--brand-2',
  success: '--success',
  danger: '--danger',
  warning: '--warning',
}

useECharts(el, (chart, c) => {
  const colorKey = colorMap[props.color] || colorMap.brand
  const main = cssVar(colorKey, '#3370FF')
  return {
    grid: { left: 0, right: 0, top: 4, bottom: 0 },
    xAxis: { type: 'category', show: false, data: props.data.map(d => d.label) },
    yAxis: { type: 'value', show: false },
    tooltip: {
      trigger: 'axis',
      backgroundColor: c.card,
      borderColor: c.border1,
      textStyle: { color: c.text1, fontSize: 12 },
      formatter: p => `${p[0].name}<br/><b>${p[0].value}</b>`,
      axisPointer: { type: 'line', lineStyle: { color: c.border1, type: 'dashed' } },
    },
    series: [{
      type: 'line',
      data: props.data.map(d => d.value),
      smooth: true,
      symbol: 'circle',
      symbolSize: 5,
      showSymbol: false,
      lineStyle: { width: 2, color: main },
      itemStyle: { color: main },
      areaStyle: {
        color: {
          type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: hexA(main, .22) },
            { offset: 1, color: hexA(main, 0) },
          ],
        },
      },
    }],
  }
}, computed(() => props.data))

function cssVar(name, fb) {
  try { return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fb } catch { return fb }
}
function hexA(hex, a) {
  const h = hex.replace('#', '')
  const r = parseInt(h.substring(0, 2), 16)
  const g = parseInt(h.substring(2, 4), 16)
  const b = parseInt(h.substring(4, 6), 16)
  return `rgba(${r},${g},${b},${a})`
}
</script>

<style scoped>
.trend-mini { width: 100%; height: v-bind(height + 'px'); }
</style>
