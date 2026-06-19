<template>
  <div class="sentiment-ring">
    <div ref="el" class="ring-canvas"></div>
    <div v-if="total" class="ring-center">
      <b>{{ total }}</b>
      <span>评论总数</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { useECharts } from '../../composables/useECharts'

const props = defineProps({
  sentiments: { type: Object, default: () => ({}) },
  total: { type: [Number, String], default: 0 },
})

const el = ref(null)

const labels = { pos: '正向', neu: '中性', neg: '负向', con: '争议', risk: '风险' }
const order = ['pos', 'neu', 'neg', 'con', 'risk']

const data = computed(() =>
  order
    .map(k => ({ name: labels[k], key: k, value: Number(props.sentiments?.[k] || 0) }))
    .filter(d => d.value > 0)
)

const { rebuild } = useECharts(el, (chart, c) => ({
  tooltip: {
    trigger: 'item',
    backgroundColor: c.card,
    borderColor: c.border1,
    textStyle: { color: c.text1, fontSize: 12 },
    formatter: '{b}: {c}% ({d}%)',
  },
  legend: {
    orient: 'vertical',
    right: 8,
    top: 'center',
    icon: 'circle',
    itemWidth: 8,
    itemHeight: 8,
    itemGap: 12,
    textStyle: { color: c.text2, fontSize: 12 },
    formatter: name => {
      const item = data.value.find(d => d.name === name)
      return `${name}  ${item ? item.value : 0}%`
    },
  },
  series: [{
    type: 'pie',
    radius: ['62%', '88%'],
    center: ['38%', '50%'],
    avoidLabelOverlap: false,
    label: { show: false },
    labelLine: { show: false },
    itemStyle: { borderRadius: 4, borderColor: c.card, borderWidth: 2 },
    emphasis: { scale: true, scaleSize: 4, label: { show: false } },
    data: data.value.map(d => ({
      name: d.name,
      value: d.value,
      itemStyle: { color: colorOf(d.key, c) },
    })),
  }],
}), data)

// 容器可能因 CSS 动画导致初始尺寸为 0，延迟 rebuild 确保渲染
watch(() => props.total, () => {
  setTimeout(() => { if (el.value) rebuild() }, 600)
})

function colorOf(k, c) {
  return { pos: c.success, neu: c.text4, neg: c.danger, con: c.purple, risk: '#8B0000' }[k] || c.text4
}
</script>

<style scoped>
.sentiment-ring { position: relative; width: 100%; height: 220px; }
.ring-canvas { width: 100%; height: 100%; }
.ring-center {
  position: absolute; left: 38%; top: 50%;
  transform: translate(-50%, -50%);
  text-align: center; pointer-events: none;
}
.ring-center b { display: block; font-size: 26px; font-weight: 700; color: var(--text-1); line-height: 1.1; }
.ring-center span { display: block; font-size: 12px; color: var(--text-3); margin-top: 2px; }
</style>
