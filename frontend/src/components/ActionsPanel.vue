<template>
  <section v-if="actions && actions.length" class="actions-panel card">
    <h3>
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16"><path d="M2 8h12M8 2v12" stroke-linecap="round"/><circle cx="4" cy="4" r="1.5"/><circle cx="12" cy="4" r="1.5"/><circle cx="4" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/></svg>
      AI 行动建议
    </h3>
    <div class="actions-list">
      <div v-for="(action, i) in actions" :key="i" :class="['action-card', `action-${action.type}`]">
        <div class="action-icon">{{ actionIcon(action.type) }}</div>
        <div class="action-body">
          <div class="action-type">{{ actionLabel(action.type) }}</div>
          <p v-if="action.draft" class="action-draft">{{ action.draft }}</p>
          <p v-if="action.reason" class="action-reason">{{ action.reason }}</p>
        </div>
        <div class="action-btns">
          <button v-if="action.draft" class="btn btn-sm" @click="copyDraft(action.draft)">
            复制草稿
          </button>
          <button v-if="action.type === 'monitor_more'" class="btn btn-sm btn-secondary" @click="$emit('adopt', action)">
            采纳
          </button>
          <button v-if="action.type === 'alert_team'" class="btn btn-sm btn-secondary" @click="$emit('adopt', action)">
            执行
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { toast } from '../composables/useToast'

defineProps({
  actions: { type: Array, default: () => [] },
})
defineEmits(['adopt'])

function actionIcon(type) {
  const icons = {
    reply: '💬',
    pin: '📌',
    monitor_more: '🔍',
    alert_team: '🔔',
  }
  return icons[type] || '📋'
}

function actionLabel(type) {
  const labels = {
    reply: '回复建议',
    pin: '置顶推荐',
    monitor_more: '加密监控',
    alert_team: '团队通知',
  }
  return labels[type] || type
}

function copyDraft(text) {
  navigator.clipboard.writeText(text).then(() => {
    toast.success('已复制到剪贴板')
  }).catch(() => {
    toast.error('复制失败')
  })
}
</script>

<style scoped>
.actions-panel { margin-top: var(--sp-4); }
.actions-panel h3 {
  font-size: var(--fs-md);
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  color: var(--text-1);
  margin-bottom: var(--sp-3);
}

.actions-list {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}

.action-card {
  display: flex;
  align-items: flex-start;
  gap: var(--sp-3);
  padding: var(--sp-3);
  background: var(--fill-1);
  border-radius: var(--r-lg);
  border-left: 3px solid var(--border-2);
  transition: border-color var(--t-fast);
}
.action-card:hover { border-left-color: var(--brand); }
.action-reply { border-left-color: #6366f1; }
.action-pin { border-left-color: #22c55e; }
.action-monitor_more { border-left-color: #f59e0b; }
.action-alert_team { border-left-color: #ef4444; }

.action-icon {
  font-size: var(--fs-lg);
  flex-shrink: 0;
  margin-top: 2px;
}

.action-body { flex: 1; min-width: 0; }
.action-type {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-1);
  margin-bottom: 2px;
}
.action-draft {
  font-size: var(--fs-sm);
  color: var(--text-2);
  line-height: var(--lh-loose);
  margin: 4px 0;
  padding: var(--sp-2);
  background: var(--bg-card);
  border-radius: var(--r-md);
  border: 1px solid var(--border-2);
  word-break: break-all;
}
.action-reason {
  font-size: var(--fs-xs);
  color: var(--text-3);
  margin: 2px 0 0;
}

.action-btns {
  display: flex;
  gap: var(--sp-2);
  flex-shrink: 0;
  align-items: flex-start;
}
</style>
