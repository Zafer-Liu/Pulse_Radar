<template>
  <section v-if="timeline?.points?.length" class="card negative-timeline-card">
    <div class="timeline-head">
      <div>
        <h3>负面发酵时间线</h3>
        <p>{{ timeline.summary || '按评论时间轴观察负面情绪如何升温、爆发与回落。' }}</p>
      </div>
      <span class="timeline-badge">{{ timeline.bucketUnit || '时间' }}粒度</span>
    </div>

    <div class="timeline-metrics">
      <div class="timeline-metric">
        <span>观察窗口</span>
        <b>{{ timeline.windowLabel || '—' }}</b>
      </div>
      <div class="timeline-metric">
        <span>时间样本</span>
        <b>{{ timeline.totalTimedComments || 0 }} 条</b>
      </div>
      <div class="timeline-metric">
        <span>峰值时刻</span>
        <b>{{ timeline.peak?.label || '—' }}</b>
      </div>
      <div class="timeline-metric">
        <span>峰值负面占比</span>
        <b>{{ timeline.peak?.negativeRatio != null ? `${timeline.peak.negativeRatio}%` : '—' }}</b>
      </div>
    </div>

    <div class="timeline-chart-wrap">
      <div ref="chartEl" class="timeline-chart"></div>
    </div>

    <div class="timeline-bottom">
      <div class="timeline-events">
        <div v-for="(item, idx) in timeline.milestones || []" :key="`${item.type}-${idx}`" class="timeline-event" :class="stageClass(item.stage)">
          <div class="event-marker">{{ idx + 1 }}</div>
          <div class="event-main">
            <div class="event-top">
              <strong>{{ item.title }}</strong>
              <span>{{ item.label }}</span>
            </div>
            <p>{{ item.desc }}</p>
            <div v-if="item.keywords?.length" class="event-tags">
              <span v-for="kw in item.keywords" :key="kw" class="event-tag">{{ kw }}</span>
            </div>
          </div>
        </div>
      </div>

      <aside class="timeline-side">
        <div class="side-block">
          <span class="side-title">高频争议词</span>
          <div class="side-tags">
            <span v-for="kw in timeline.keywords || []" :key="kw" class="side-tag">{{ kw }}</span>
            <span v-if="!(timeline.keywords || []).length" class="side-empty">暂无明显争议词</span>
          </div>
        </div>
        <div class="side-block">
          <span class="side-title">阅读建议</span>
          <ul class="side-list">
            <li>先看峰值时刻，再回到对应高赞评论复核触发点。</li>
            <li>若最近时段仍接近峰值，优先关注是否还在持续发酵。</li>
            <li>把争议词与观点聚类结合起来看，能更快定位核心问题。</li>
          </ul>
        </div>
      </aside>
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useECharts } from '../composables/useECharts'

const props = defineProps({
  timeline: { type: Object, default: null },
})

const chartEl = ref(null)
const chartData = computed(() => props.timeline?.points || [])

useECharts(chartEl, (chart, c) => {
  const points = chartData.value
  return {
    grid: { left: 24, right: 24, top: 32, bottom: 28 },
    legend: {
      top: 0,
      right: 0,
      itemWidth: 10,
      itemHeight: 10,
      textStyle: { color: c.text2, fontSize: 12 },
      data: ['负面占比', '评论量', '风险节点'],
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: c.card,
      borderColor: c.border1,
      textStyle: { color: c.text1, fontSize: 12 },
      axisPointer: { type: 'cross', crossStyle: { color: c.border1 } },
      formatter: (params) => {
        const ratio = params.find((item) => item.seriesName === '负面占比')
        const volume = params.find((item) => item.seriesName === '评论量')
        const risk = params.find((item) => item.seriesName === '风险节点')
        const point = points[ratio?.dataIndex ?? volume?.dataIndex ?? 0] || {}
        const words = (point.keywords || []).length ? `<br/>争议词：${point.keywords.join('、')}` : ''
        return `${point.label || ''}<br/>负面占比：<b>${point.negativeRatio ?? 0}%</b><br/>评论量：<b>${point.totalCount ?? 0}</b><br/>风险评论：<b>${point.riskCount ?? 0}</b><br/>阶段：<b>${point.stage || '平稳'}</b>${words}`
      },
    },
    xAxis: {
      type: 'category',
      boundaryGap: true,
      data: points.map((item) => item.label),
      axisLine: { lineStyle: { color: c.border1 } },
      axisTick: { show: false },
      axisLabel: { color: c.text3, fontSize: 11 },
    },
    yAxis: [
      {
        type: 'value',
        name: '负面占比',
        min: 0,
        max: 100,
        axisLabel: { color: c.text3, formatter: '{value}%' },
        splitLine: { lineStyle: { color: c.border1, type: 'dashed' } },
      },
      {
        type: 'value',
        name: '评论量',
        axisLabel: { color: c.text4 },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: '评论量',
        type: 'bar',
        yAxisIndex: 1,
        barWidth: 18,
        itemStyle: {
          color: 'rgba(0,47,167,0.12)',
          borderRadius: [6, 6, 0, 0],
        },
        emphasis: { itemStyle: { color: 'rgba(0,47,167,0.2)' } },
        data: points.map((item) => item.totalCount),
      },
      {
        name: '负面占比',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 8,
        lineStyle: { width: 3, color: '#dc2626' },
        itemStyle: { color: '#dc2626', borderColor: '#fff', borderWidth: 2 },
        areaStyle: {
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(220,38,38,0.22)' },
              { offset: 1, color: 'rgba(220,38,38,0.02)' },
            ],
          },
        },
        data: points.map((item) => item.negativeRatio),
      },
      {
        name: '风险节点',
        type: 'scatter',
        yAxisIndex: 0,
        symbol: 'diamond',
        data: points.map((item) => ({
          value: item.riskCount > 0 ? item.negativeRatio : null,
          riskCount: item.riskCount,
          symbolSize: item.riskCount > 0 ? 10 + item.riskCount * 4 : 0,
        })),
        itemStyle: { color: '#722ed1' },
        tooltip: { show: false },
      },
    ],
  }
}, chartData)

function stageClass(stage) {
  return {
    'stage-spark': stage === '露头',
    'stage-warm': stage === '升温',
    'stage-burst': stage === '爆发',
  }
}
</script>

<style scoped>
.negative-timeline-card {
  margin-bottom: var(--sp-4);
  border: 1px solid rgba(220,38,38,0.12);
  background: linear-gradient(180deg, rgba(220,38,38,0.04), rgba(255,255,255,0));
}
.timeline-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--sp-3);
  margin-bottom: var(--sp-3);
}
.timeline-head h3 { margin: 0; }
.timeline-head p {
  margin: 6px 0 0;
  color: var(--text-2);
  font-size: var(--fs-sm);
  line-height: var(--lh-loose);
}
.timeline-badge {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(220,38,38,0.08);
  border: 1px solid rgba(220,38,38,0.14);
  color: #dc2626;
  font-size: var(--fs-2xs);
  font-weight: 600;
}
.timeline-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--sp-3);
  margin-bottom: var(--sp-3);
}
.timeline-metric {
  padding: var(--sp-3);
  border-radius: var(--r-lg);
  background: #fff;
  border: 1px solid var(--border-2);
}
.timeline-metric span {
  display: block;
  font-size: var(--fs-2xs);
  color: var(--text-4);
}
.timeline-metric b {
  display: block;
  margin-top: 6px;
  font-size: var(--fs-sm);
  color: var(--text-1);
  line-height: var(--lh-base);
}
.timeline-chart-wrap {
  padding: var(--sp-2);
  border-radius: var(--r-lg);
  background: #fff;
  border: 1px solid var(--border-2);
}
.timeline-chart { width: 100%; height: 320px; }
.timeline-bottom {
  display: grid;
  grid-template-columns: 1.2fr 0.8fr;
  gap: var(--sp-3);
  margin-top: var(--sp-3);
}
.timeline-events {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
.timeline-event {
  display: flex;
  gap: var(--sp-3);
  align-items: flex-start;
  padding: var(--sp-3);
  border-radius: var(--r-lg);
  background: #fff;
  border: 1px solid var(--border-2);
}
.event-marker {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
  background: #86909c;
  flex-shrink: 0;
}
.stage-spark .event-marker { background: #f59e0b; }
.stage-warm .event-marker { background: #f97316; }
.stage-burst .event-marker { background: #dc2626; }
.event-main { min-width: 0; }
.event-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
}
.event-top strong { color: var(--text-1); }
.event-top span {
  font-size: var(--fs-2xs);
  color: var(--text-4);
  white-space: nowrap;
}
.event-main p {
  margin: 8px 0 0;
  color: var(--text-2);
  font-size: var(--fs-xs);
  line-height: var(--lh-loose);
}
.event-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}
.event-tag,
.side-tag {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: var(--fs-2xs);
  background: rgba(220,38,38,0.06);
  border: 1px solid rgba(220,38,38,0.12);
  color: #b91c1c;
}
.timeline-side {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
.side-block {
  padding: var(--sp-3);
  border-radius: var(--r-lg);
  background: #fff;
  border: 1px solid var(--border-2);
}
.side-title {
  display: block;
  font-size: var(--fs-2xs);
  color: var(--text-4);
  margin-bottom: 10px;
}
.side-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.side-empty {
  font-size: var(--fs-xs);
  color: var(--text-4);
}
.side-list {
  margin: 0;
  padding-left: 18px;
  color: var(--text-2);
  font-size: var(--fs-xs);
  line-height: var(--lh-loose);
}
.side-list li + li { margin-top: 6px; }

@media (max-width: 960px) {
  .timeline-metrics,
  .timeline-bottom {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 640px) {
  .timeline-head,
  .event-top {
    flex-direction: column;
    align-items: flex-start;
  }
  .timeline-metrics {
    grid-template-columns: 1fr 1fr;
  }
  .timeline-chart { height: 280px; }
}
</style>
