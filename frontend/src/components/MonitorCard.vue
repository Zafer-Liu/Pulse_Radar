<template>
  <section v-if="monitor" class="card card-hover monitor-item">
    <img
      class="monitor-cover"
      :src="proxyImage(monitor.pic || result.pic || '')"
      alt="视频封面"
      loading="lazy"
      @error="onCoverError"
    />
    <div class="monitor-body">
      <!-- 主信息区 -->
      <div class="monitor-title">
        <h3>{{ monitor.title || result.title || '等待首次检测' }}</h3>
        <span :class="['status-pill', `status-${monitor.status || 'pending'}`, monitor.status === 'running' ? 'badge-dot pulse' : 'badge-dot']">
          {{ statusText[monitor.status] || monitor.status || '待检测' }}
        </span>
      </div>

      <!-- 风险 + 元信息 -->
      <div class="monitor-meta-row">
        <span v-if="result.risk" :class="['risk', `risk-${result.risk}`]">
          {{ riskText[result.risk] || '未知风险' }}
        </span>
        <div class="meta">
          <span>每 {{ monitor.intervalValue }} {{ monitor.intervalUnit }}</span>
          <span>{{ monitor.pages }} 页评论</span>
          <span>下次：{{ monitor.nextRun || '待计算' }}</span>
          <span>上次：{{ monitor.lastRun || '尚未检测' }}</span>
        </div>
      </div>

      <p v-if="monitor.lastError" class="error-text">{{ monitor.lastError }}</p>

      <div v-if="result.needsLogin" class="login-hint">
        <strong>抓取不全</strong> · 实抓 {{ fmt(result.commentCount || 0) }} 条 / 公开 {{ fmt(result.replyCountFromVideo || 0) }} 条。{{ result.loginHint || '请配置 SESSDATA 后再检测。' }}
      </div>

      <p v-if="result.riskReason" class="risk-reason">{{ result.riskReason }}</p>
      <p v-else-if="!result.risk" class="text-muted text-sm">添加后会在后台自动执行首次检测。</p>

      <!-- 关键词 -->
      <div v-if="(result.keywords || []).length" class="chips mt-3">
        <span v-for="k in (result.keywords || []).slice(0, 8)" :key="k" class="chip">{{ k }}</span>
      </div>

      <!-- 操作区 -->
      <div class="monitor-actions">
        <button class="btn btn-sm" @click="$emit('run', monitor.id)">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" width="13" height="13"><path d="M4 2.5v11l9-5.5z" stroke-linejoin="round"/></svg>
          立即检测
        </button>
        <button class="btn btn-sm btn-secondary" @click="$emit('detail', monitor.id)">查看结果</button>
        <button class="btn btn-sm btn-ghost" @click="$emit('toggle', monitor.id, !monitor.enabled)">
          {{ monitor.enabled ? '暂停' : '恢复' }}
        </button>
        <button class="btn btn-sm btn-danger" @click="$emit('delete', monitor.id)">删除</button>
      </div>

      <!-- 历史记录 -->
      <div v-if="(monitor.history || []).length" class="history-section">
        <button class="history-toggle" @click="showHistory = !showHistory">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" width="13" height="13"><circle cx="8" cy="8" r="6.5"/><path d="M8 5v3.5l2 1.5" stroke-linecap="round"/></svg>
          检测历史 · {{ (monitor.history || []).length }} 条
          <svg class="arrow" :class="{ up: showHistory }" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" width="12" height="12"><path d="M4 6l4 4 4-4" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </button>
        <transition name="expand">
          <div v-show="showHistory" class="history-list">
            <!-- 情感趋势图：3 条 mini 折线，正/中/负 -->
            <div v-if="trendData.length >= 2" class="history-trend">
              <div class="trend-item">
                <span class="trend-label trend-pos">正面</span>
                <TrendMini :data="trendPosData" color="success" :height="36" />
              </div>
              <div class="trend-item">
                <span class="trend-label trend-neu">中性</span>
                <TrendMini :data="trendNeuData" color="brand" :height="36" />
              </div>
              <div class="trend-item">
                <span class="trend-label trend-neg">负面</span>
                <TrendMini :data="trendNegData" color="danger" :height="36" />
              </div>
            </div>
            <div v-for="h in (monitor.history || []).slice(0, 8)" :key="h.id" class="history-row">
              <span class="history-time">{{ h.finishedAt }}</span>
              <template v-if="h.ok">
                <span :class="['badge', `badge-${riskBadgeClass(h.summary?.risk)}`, 'badge-dot']">{{ riskText[h.summary?.risk] || '未知' }}</span>
                <span class="text-muted">抓取 {{ fmt(h.summary?.commentCount) }} 条</span>
              </template>
              <template v-else>
                <span class="badge badge-danger badge-dot">失败</span>
                <span class="text-muted">{{ h.error || '' }}</span>
              </template>
            </div>
          </div>
        </transition>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, computed } from 'vue'
import TrendMini from './charts/TrendMini.vue'

const props = defineProps({
  monitor: { type: Object, default: null },
})
defineEmits(['run', 'detail', 'toggle', 'delete'])

const showHistory = ref(false)
const result = computed(() => props.monitor?.lastResult || {})

const riskText = { low: '低风险', medium: '中风险', high: '高风险', unknown: '未知' }
const statusText = { ok: '正常', running: '检测中', error: '异常', pending: '待检测' }

// 历史情感趋势数据：取最近 8 条成功记录，按时间正序（左旧右新）
const trendData = computed(() => {
  const history = props.monitor?.history || []
  return history
    .filter(h => h.ok && h.summary?.sentimentCounts)
    .slice(0, 8)
    .reverse()
    .map((h, idx) => {
      const sc = h.summary.sentimentCounts
      return {
        label: `#${idx + 1}`,
        pos: sc.pos || 0,
        neu: (sc.neu || 0) + (sc.con || 0),
        neg: (sc.neg || 0) + (sc.risk || 0),
      }
    })
})

const trendPosData = computed(() => trendData.value.map(d => ({ label: d.label, value: d.pos })))
const trendNeuData = computed(() => trendData.value.map(d => ({ label: d.label, value: d.neu })))
const trendNegData = computed(() => trendData.value.map(d => ({ label: d.label, value: d.neg })))

function riskBadgeClass(risk) {
  return { low: 'success', medium: 'warning', high: 'danger', unknown: 'neutral' }[risk] || 'neutral'
}

function fmt(num) {
  return Number(num || 0).toLocaleString('zh-CN')
}

function proxyImage(url) {
  if (!url) return ''
  const normalized = String(url).startsWith('//') ? `https:${url}` : String(url)
  return `/api/image?url=${encodeURIComponent(normalized)}`
}

function onCoverError(e) {
  e.target.style.display = 'none'
}
</script>

<style scoped>
.monitor-item { display: grid; grid-template-columns: 160px 1fr; gap: var(--sp-4); padding: var(--sp-4); }
.monitor-cover { width: 160px; aspect-ratio: 16 / 10; object-fit: cover; border-radius: var(--r-lg); border: 1px solid var(--border-1); background: var(--fill-1); }
.monitor-body { display: flex; flex-direction: column; min-width: 0; }
.monitor-title { display: flex; justify-content: space-between; gap: var(--sp-3); margin-bottom: var(--sp-2); align-items: flex-start; }
.monitor-title h3 { font-size: var(--fs-md); font-weight: 600; line-height: var(--lh-tight); color: var(--text-1); flex: 1; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.monitor-meta-row { display: flex; align-items: center; gap: var(--sp-3); flex-wrap: wrap; margin-bottom: var(--sp-2); }
.error-text { color: var(--danger); font-size: var(--fs-sm); margin: var(--sp-1) 0; }
.risk-reason { color: var(--text-2); font-size: var(--fs-sm); line-height: var(--lh-base); margin: var(--sp-1) 0 0; }
.monitor-actions { display: flex; gap: var(--sp-2); flex-wrap: wrap; margin-top: var(--sp-3); }

.history-section { margin-top: var(--sp-3); border-top: 1px solid var(--border-2); padding-top: var(--sp-2); }
.history-toggle {
  display: inline-flex; align-items: center; gap: 6px;
  color: var(--text-3); font-size: var(--fs-sm);
  background: transparent; border: 0; cursor: pointer;
  padding: 4px 8px; border-radius: var(--r-sm);
  transition: background var(--t-fast), color var(--t-fast);
}
.history-toggle:hover { background: var(--fill-1); color: var(--text-1); }
.history-toggle .arrow { transition: transform var(--t-fast); }
.history-toggle .arrow.up { transform: rotate(180deg); }
.history-list { margin-top: var(--sp-2); display: flex; flex-direction: column; gap: var(--sp-1); }
.history-row { display: flex; align-items: center; gap: var(--sp-2); font-size: var(--fs-xs); color: var(--text-3); padding: 4px 0; }
.history-time { font-family: var(--font-mono); color: var(--text-2); }

/* 情感趋势 mini 折线 */
.history-trend {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: var(--sp-2);
  padding: var(--sp-2) var(--sp-3);
  margin-bottom: var(--sp-2);
  background: var(--fill-1);
  border-radius: var(--r-md);
  border: 1px solid var(--border-1);
}
.trend-item { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.trend-label {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.trend-label::before {
  content: '';
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}
.trend-pos { color: var(--success, #16a34a); }
.trend-neu { color: var(--brand, #002FA7); }
.trend-neg { color: var(--danger, #dc2626); }

.expand-enter-active, .expand-leave-active { transition: all var(--t-base); overflow: hidden; }
.expand-enter-from, .expand-leave-to { opacity: 0; max-height: 0; }
.expand-enter-to, .expand-leave-from { opacity: 1; max-height: 600px; }

@media (max-width: 1024px) {
  .monitor-item { grid-template-columns: 140px 1fr; }
  .monitor-cover { width: 140px; }
}
@media (max-width: 768px) {
  .monitor-item { grid-template-columns: 1fr; }
  .monitor-cover { width: 100%; max-height: 180px; }
}
</style>
