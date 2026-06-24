<template>
  <section v-if="trace && trace.length" class="agent-trace card">
    <div class="trace-head">
      <div class="trace-title">
        <span class="trace-icon">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16"><path d="M8 1v4M8 11v4M1 8h4M11 8h4" stroke-linecap="round"/><circle cx="8" cy="8" r="3"/><circle cx="8" cy="8" r="6" stroke-dasharray="2 2"/></svg>
        </span>
        <div>
          <h3>Agent 推理轨迹</h3>
          <p class="trace-sub">自主多轮推理 · 思考 → 查证 → 修正 → 结论</p>
        </div>
      </div>
      <div class="trace-tools">
        <span class="badge badge-brand">{{ rounds }} 轮 · {{ trace.length }} 步</span>
        <button class="btn btn-sm btn-ghost" @click="replay" :disabled="playing" title="逐步演示推理过程">
          <svg viewBox="0 0 16 16" fill="currentColor" width="12" height="12"><path d="M4 3l9 5-9 5z"/></svg>
          {{ playing ? '演示中' : '逐步演示' }}
        </button>
        <button class="btn btn-sm btn-ghost" @click="expanded = !expanded">
          {{ expanded ? '收起' : '展开' }}
          <svg :class="{ up: expanded }" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" width="12" height="12"><path d="M4 6l4 4 4-4" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </button>
      </div>
    </div>

    <div v-if="expanded" class="trace-timeline">
      <div
        v-for="(step, i) in trace"
        :key="i"
        class="trace-step"
        :class="{ active: playing && i === activeStep, dimmed: playing && i > activeStep, conclusion: step.isConclusion }"
        :style="{ '--i': i }"
      >
        <div class="step-marker">
          <span class="step-num" :class="{ done: step.isConclusion }">
            <svg v-if="step.isConclusion" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><path d="M3 8l3.5 3.5L13 5" stroke-linecap="round" stroke-linejoin="round"/></svg>
            <template v-else>{{ i + 1 }}</template>
          </span>
          <div v-if="i < trace.length - 1" class="step-line"></div>
        </div>
        <div class="step-content">
          <div class="step-rowhead">
            <span class="round-tag">第 {{ step.round || (i + 1) }} 轮</span>
            <span v-if="step.tool && !step.isConclusion" class="tool-chip">
              <svg viewBox="0 0 16 16" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M6.5 2.5a3.5 3.5 0 0 0 4.6 4.6l3 3-1.4 1.4-3-3A3.5 3.5 0 0 1 4.9 4l2 2 1.4-1.4-2-2z" stroke-linejoin="round"/></svg>
              {{ toolName(step.tool) }}
            </span>
          </div>
          <div v-if="step.thought" class="step-thought">
            <span class="step-label thought">思考</span>
            <p>{{ step.thought }}</p>
          </div>
          <div v-if="step.action && !step.isConclusion" class="step-action">
            <span class="step-label action">动作</span>
            <code>{{ step.action }}</code>
          </div>
          <div v-if="step.observation" class="step-observation" :class="{ 'is-conclusion': step.isConclusion }">
            <span class="step-label" :class="step.isConclusion ? 'conclusion-label' : 'observation'">{{ step.isConclusion ? '结论' : '观察' }}</span>
            <p>{{ step.observation }}</p>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="trace-summary">
      <div v-for="(step, i) in trace" :key="i" class="trace-brief" :class="{ conclusion: step.isConclusion }">
        <span class="brief-num">{{ step.isConclusion ? '✓' : i + 1 }}</span>
        <span class="brief-text">{{ step.isConclusion ? '得出结论' : (toolName(step.tool) || step.action || step.thought || '推理') }}</span>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  trace: { type: Array, default: () => [] },
})

// 默认展开 —— 这是项目的核心差异化能力，应一眼可见
const expanded = ref(true)
const playing = ref(false)
const activeStep = ref(-1)

const rounds = computed(() => {
  const rs = props.trace.map(s => s.round || 0).filter(Boolean)
  return rs.length ? Math.max(...rs) : props.trace.length
})

const TOOL_NAMES = {
  search_comments: '检索评论',
  reclassify: '修正判定',
  get_trend: '查趋势',
  get_cluster_detail: '看聚类',
  conclusion: '得出结论',
}
function toolName(tool) {
  if (!tool) return ''
  return TOOL_NAMES[tool] || tool
}

let timer = null
function replay() {
  if (playing.value) return
  expanded.value = true
  playing.value = true
  activeStep.value = -1
  const total = props.trace.length
  let i = 0
  clearInterval(timer)
  timer = setInterval(() => {
    activeStep.value = i
    // 滚动到当前步
    const el = document.querySelectorAll('.agent-trace .trace-step')[i]
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    i++
    if (i >= total) {
      clearInterval(timer)
      setTimeout(() => { playing.value = false; activeStep.value = -1 }, 900)
    }
  }, 900)
}
</script>

<style scoped>
.agent-trace {
  margin-top: var(--sp-4);
  border: 1px solid var(--brand);
  border-left-width: 3px;
  background: linear-gradient(180deg, var(--brand-soft) 0%, var(--bg-card) 60px);
}
.trace-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--sp-2);
  margin-bottom: var(--sp-3);
  flex-wrap: wrap;
}
.trace-title { display: flex; align-items: center; gap: var(--sp-2); }
.trace-icon {
  width: 32px; height: 32px; border-radius: var(--r-md);
  background: var(--brand); color: #fff;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.trace-title h3 { font-size: var(--fs-md); font-weight: 600; color: var(--text-1); }
.trace-sub { font-size: var(--fs-xs); color: var(--brand); margin-top: 1px; }
.trace-tools { display: flex; align-items: center; gap: var(--sp-2); flex-wrap: wrap; }
.badge-brand { background: var(--brand); color: #fff; font-weight: 600; }

/* 时间线 */
.trace-timeline { padding-left: var(--sp-1); }
.trace-step {
  display: flex;
  gap: var(--sp-3);
  animation: fadeUp 0.4s ease both;
  animation-delay: calc(var(--i) * 0.06s);
  transition: opacity .3s, transform .3s;
}
.trace-step.active { transform: scale(1.01); }
.trace-step.active .step-content {
  background: var(--brand-soft);
  border-radius: var(--r-md);
  box-shadow: 0 0 0 2px var(--brand);
}
.trace-step.dimmed { opacity: 0.4; }
@keyframes fadeUp {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.step-marker {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
}
.step-num {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: var(--brand-soft);
  color: var(--brand);
  font-size: var(--fs-xs);
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}
.step-num.done { background: var(--brand); color: #fff; }
.step-line {
  width: 2px;
  flex: 1;
  min-height: 16px;
  background: var(--border-2);
  margin: 4px 0;
}

.step-content {
  flex: 1;
  padding: var(--sp-1) var(--sp-2) var(--sp-3);
  min-width: 0;
  transition: background .3s, box-shadow .3s;
}
.step-rowhead { display: flex; align-items: center; gap: var(--sp-2); margin-bottom: var(--sp-2); }
.round-tag {
  font-size: 11px; font-weight: 600; color: var(--text-3);
  background: var(--fill-1); padding: 1px 8px; border-radius: var(--r-full);
}
.tool-chip {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 11px; font-weight: 500; color: var(--brand);
  background: var(--brand-soft); padding: 1px 8px; border-radius: var(--r-full);
}
.step-thought, .step-action, .step-observation {
  margin-bottom: var(--sp-2);
}
.step-label {
  display: inline-block;
  font-size: var(--fs-xs);
  font-weight: 500;
  padding: 1px 8px;
  border-radius: var(--r-full);
  margin-bottom: 4px;
}
.step-label.thought { background: rgba(99, 102, 241, 0.1); color: #6366f1; }
.step-label.action { background: rgba(34, 197, 94, 0.1); color: #16a34a; }
.step-label.observation { background: rgba(234, 179, 8, 0.1); color: #ca8a04; }
.conclusion-label { background: var(--brand); color: #fff; }
.step-observation.is-conclusion p { color: var(--text-1); font-weight: 500; }

.step-content p {
  font-size: var(--fs-sm);
  color: var(--text-2);
  line-height: var(--lh-loose);
  margin: 0;
  word-break: break-word;
}
.step-content code {
  display: inline-block;
  font-size: var(--fs-xs);
  background: var(--fill-1);
  padding: 2px 8px;
  border-radius: var(--r-sm);
  color: var(--text-2);
  word-break: break-all;
}

/* 收起状态 */
.trace-summary {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-2);
  align-items: center;
}
.trace-brief {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: var(--fs-xs);
  color: var(--text-3);
  background: var(--fill-1);
  padding: 3px 10px;
  border-radius: var(--r-full);
}
.trace-brief.conclusion { background: var(--brand-soft); color: var(--brand); font-weight: 500; }
.brief-num {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--brand-soft);
  color: var(--brand);
  font-size: 10px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
}
.trace-brief.conclusion .brief-num { background: var(--brand); color: #fff; }
.brief-text {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.btn-ghost .up { transform: rotate(180deg); }
.btn-ghost svg { transition: transform var(--t-fast); }
</style>
