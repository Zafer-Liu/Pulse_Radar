<template>
  <section v-if="trace && trace.length" class="agent-trace card">
    <div class="trace-head">
      <h3>
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16"><path d="M8 1v4M8 11v4M1 8h4M11 8h4" stroke-linecap="round"/><circle cx="8" cy="8" r="3"/><circle cx="8" cy="8" r="6" stroke-dasharray="2 2"/></svg>
        Agent 推理轨迹
      </h3>
      <button class="btn btn-sm btn-ghost" @click="expanded = !expanded">
        {{ expanded ? '收起' : '展开' }}
        <svg :class="{ up: expanded }" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" width="12" height="12"><path d="M4 6l4 4 4-4" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </button>
    </div>

    <div v-if="expanded" class="trace-timeline">
      <div v-for="(step, i) in trace" :key="i" class="trace-step" :style="{ '--i': i }">
        <div class="step-marker">
          <span class="step-num">{{ i + 1 }}</span>
          <div v-if="i < trace.length - 1" class="step-line"></div>
        </div>
        <div class="step-content">
          <div v-if="step.thought" class="step-thought">
            <span class="step-label thought">思考</span>
            <p>{{ step.thought }}</p>
          </div>
          <div v-if="step.action" class="step-action">
            <span class="step-label action">动作</span>
            <code>{{ step.action }}</code>
          </div>
          <div v-if="step.observation" class="step-observation">
            <span class="step-label observation">观察</span>
            <p>{{ step.observation }}</p>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="trace-summary">
      <span class="badge badge-neutral">{{ trace.length }} 轮推理</span>
      <div v-for="(step, i) in trace" :key="i" class="trace-brief">
        <span class="brief-num">{{ i + 1 }}</span>
        <span class="brief-text">{{ step.action || step.thought || '完成' }}</span>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
  trace: { type: Array, default: () => [] },
})

const expanded = ref(false)
</script>

<style scoped>
.agent-trace { margin-top: var(--sp-4); }
.trace-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--sp-3);
}
.trace-head h3 {
  font-size: var(--fs-md);
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  color: var(--text-1);
}
.trace-head h3 svg { color: var(--brand); }

/* 时间线 */
.trace-timeline { padding-left: var(--sp-1); }
.trace-step {
  display: flex;
  gap: var(--sp-3);
  animation: fadeUp 0.4s ease both;
  animation-delay: calc(var(--i) * 0.06s);
}
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
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--brand-soft);
  color: var(--brand);
  font-size: var(--fs-xs);
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
}
.step-line {
  width: 2px;
  flex: 1;
  min-height: 16px;
  background: var(--border-2);
  margin: 4px 0;
}

.step-content {
  flex: 1;
  padding-bottom: var(--sp-4);
  min-width: 0;
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

.step-content p {
  font-size: var(--fs-sm);
  color: var(--text-2);
  line-height: var(--lh-loose);
  margin: 0;
  word-break: break-all;
}
.step-content code {
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
.brief-text {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
