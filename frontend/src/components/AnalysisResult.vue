<template>
  <section v-if="data" :key="animKey" class="analysis-result">
    <div class="section-title">
      <div>
        <h2>分析结果</h2>
        <span class="subtitle">{{ data.title || '未命名视频' }}</span>
      </div>
      <span class="badge badge-neutral">{{ data.fetchedAt || '' }}</span>
    </div>

    <div class="grid grid-analysis">
      <!-- 左主区 -->
      <div class="main-col">
        <!-- 视频概览 -->
        <section class="card anim-card" style="--i:0">
          <img class="cover" :src="proxyImage(data.pic || '')" alt="视频封面" @error="onCoverError" />
          <div class="video-info">
            <h2>{{ data.title || '未命名视频' }}</h2>
            <div class="meta">
              <span>{{ data.author || '未知作者' }}</span>
              <span>{{ data.platform || 'B站' }}</span>
              <span v-if="data.time">{{ data.time }}</span>
              <span class="font-mono">{{ data.bvid || '' }}</span>
            </div>
            <div v-if="data.risk" :class="['risk', `risk-${data.risk}`]">{{ riskText[data.risk] || '未知风险' }}</div>
            <p v-if="data.riskReason" class="risk-reason">{{ data.riskReason }}</p>

            <div v-if="data.needsLogin" class="login-hint">
              <strong>抓取不全</strong> · 仅抓到 {{ fmt(data.commentCount) }} 条，公开评论数 {{ fmt(data.replyCountFromVideo) }} 条。{{ data.loginHint || '' }}
            </div>

            <div class="stats">
              <div class="stat"><b>{{ fmt(data.views) }}</b><span>播放</span></div>
              <div class="stat"><b>{{ fmt(data.likes) }}</b><span>点赞</span></div>
              <div class="stat"><b>{{ fmt(data.replyCountFromVideo) }}</b><span>公开评论</span></div>
              <div class="stat"><b>{{ fmt(data.commentCount) }}</b><span>本次抓取</span></div>
            </div>
          </div>
        </section>

        <!-- 情绪分布（ECharts 环形图） -->
        <section class="card anim-card" style="--i:1">
          <h3>情绪分布</h3>
          <div class="sentiment-grid">
            <SentimentRing :sentiments="sentiments" :total="data.commentCount || 0" />
            <div class="sentiment-detail">
              <div v-for="k in sentimentOrder" :key="k" class="sentiment-item">
                <span :class="['legend-dot', segClass(k)]"></span>
                <span class="sentiment-label">{{ sentimentLabels[k] }}</span>
                <span class="sentiment-value">{{ sentiments?.[k] || 0 }}%</span>
              </div>
            </div>
          </div>
        </section>

        <!-- 观点聚类 -->
        <section class="card anim-card" style="--i:2">
          <h3>观点聚类</h3>
          <template v-if="(data.clusters || []).length">
            <div class="clusters">
              <div v-for="c in data.clusters" :key="c.topic" class="cluster">
                <div class="cluster-head">
                  <h4>{{ c.topic }}</h4>
                  <span :class="['badge', `badge-${sentimentBadge(c.sentiment)}`]">{{ sentimentLabels[c.sentiment] || c.sentiment }}</span>
                </div>
                <small>{{ fmt(c.size) }} 条评论</small>
                <p v-for="(e, i) in (c.examples || []).slice(0, 3)" :key="i">"{{ e }}"</p>
              </div>
            </div>
          </template>
          <EmptyState v-else title="暂无聚类结果" description="评论数过少或无明显主题聚集" />
        </section>

        <!-- 典型评论 -->
        <section class="card anim-card" style="--i:3">
          <div class="card-head">
            <h3>典型高赞评论</h3>
            <div v-if="(data.comments || []).length" class="comment-controls">
              <select v-model.number="commentLimit" class="select comment-limit-select" @change="showAllComments = false">
                <option :value="5">5 条</option>
                <option :value="10">10 条</option>
                <option :value="20">20 条</option>
                <option :value="9999">全部</option>
              </select>
            </div>
          </div>
          <template v-if="(data.comments || []).length">
            <transition-group name="comment-list" tag="div">
              <div v-for="c in displayedComments" :key="c.rpid" class="comment">
                <div class="comment-avatar">{{ (c.user || '匿').charAt(0) }}</div>
                <div class="comment-main">
                  <div class="comment-head">
                    <span class="comment-user">{{ c.user || '匿名用户' }} <span class="comment-time">{{ c.time || '' }}</span></span>
                    <span class="comment-meta">
                      <span :class="['label', segClass(c.sentiment)]">{{ sentimentLabels[c.sentiment] || c.sentiment }}</span>
                      <span v-if="c.likes" class="likes">
                        <svg viewBox="0 0 16 16" fill="currentColor" width="12" height="12"><path d="M8 1l2.2 4.5 5 .7-3.6 3.5.8 5L8 12.8 3.6 14.7l.8-5L.8 6.2l5-.7z"/></svg>
                        {{ fmt(c.likes) }}
                      </span>
                    </span>
                  </div>
                  <div class="comment-body">{{ c.text || '' }}</div>
                </div>
              </div>
            </transition-group>
            <button
              v-if="canExpand"
              class="comment-expand-btn"
              @click="showAllComments = !showAllComments"
            >
              {{ showAllComments ? '收起评论' : `展开剩余 ${hiddenCount} 条` }}
              <svg class="arrow" :class="{ up: showAllComments }" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" width="12" height="12"><path d="M4 6l4 4 4-4" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </button>
          </template>
          <EmptyState v-else title="暂无评论" />
        </section>
      </div>

      <!-- 右侧栏 -->
      <aside class="side-col">
        <!-- 关键词 -->
        <section class="card anim-card" style="--i:1">
          <h3>关键词</h3>
          <div v-if="kwList.length" class="chips">
            <span v-for="(kw, i) in kwList" :key="kw.word" :class="['chip', { 'chip-hl': i < 3 }]" :style="chipStyle(kw, i)">{{ kw.word }}</span>
          </div>
          <p v-else class="text-muted text-sm">暂无</p>
        </section>

        <!-- AI 报告 -->
        <section class="card report-card anim-card" style="--i:2">
          <h3>
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16" style="vertical-align:-3px;color:var(--brand)"><path d="M8 1l1.5 4.5L14 7l-4.5 1.5L8 13l-1.5-4.5L2 7l4.5-1.5z" stroke-linejoin="round"/></svg>
            AI 舆情分析报告
            <span v-if="data.report?.ai_generated" class="report-badge ai" title="由 LLM 生成">AI</span>
            <span v-else class="report-badge template" title="LLM 未启用，使用模板">模板</span>
          </h3>
          <div v-if="data.report" class="report-body">
            <div class="report-section">
              <div class="report-label">整体判断</div>
              <p>{{ data.report.summary || '' }}</p>
            </div>
            <div v-if="(data.report.positive || []).length" class="report-section">
              <div class="report-label report-pos">主要正面反馈</div>
              <ul class="report-list"><li v-for="(x, i) in data.report.positive" :key="i">{{ x }}</li></ul>
            </div>
            <div v-if="(data.report.negative || []).length" class="report-section">
              <div class="report-label report-neg">主要负面反馈</div>
              <ul class="report-list"><li v-for="(x, i) in data.report.negative" :key="i">{{ x }}</li></ul>
            </div>
            <div v-if="data.report.controversy" class="report-section">
              <div class="report-label">争议焦点</div>
              <p>{{ data.report.controversy }}</p>
            </div>
            <div v-if="data.report.suggestion" class="report-section">
              <div class="report-label">建议回应策略</div>
              <p>{{ data.report.suggestion }}</p>
            </div>
          </div>
          <p v-else class="text-muted text-sm">暂无报告</p>
        </section>

        <!-- Agent 推理轨迹 -->
        <AgentTrace :trace="data.report?.agent_trace || []" />

        <!-- AI 行动建议 -->
        <ActionsPanel :actions="data.report?.actions || []" @adopt="(a) => $emit('adoptAction', a)" />

        <!-- 数据来源（折叠）-->
        <section class="card anim-card" style="--i:3">
          <button class="collapse-head" @click="showSource = !showSource">
            <h3>数据来源</h3>
            <svg class="arrow" :class="{ up: showSource }" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14"><path d="M4 6l4 4 4-4" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </button>
          <transition name="expand">
            <div v-show="showSource" class="source-body">

              <!-- 数据质量指标 -->
              <div class="source-metrics" v-if="data">
                <div class="metric">
                  <span class="metric-val">{{ fmt(data.rawCommentCount) }}</span>
                  <span class="metric-label">原始评论</span>
                </div>
                <svg class="metric-arrow" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="var(--text-3)" stroke-width="1.5"><path d="M6 4l4 4-4 4" stroke-linecap="round" stroke-linejoin="round"/></svg>
                <div class="metric">
                  <span class="metric-val">{{ fmt(data.commentCount) }}</span>
                  <span class="metric-label">有效评论</span>
                </div>
                <template v-if="data.dedupeStats">
                  <svg class="metric-arrow" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="var(--text-3)" stroke-width="1.5"><path d="M6 4l4 4-4 4" stroke-linecap="round" stroke-linejoin="round"/></svg>
                  <div class="metric metric-highlight" :class="{ 'spam-found': data.dedupeStats.spamRemoved > 0 }">
                    <span class="metric-val">{{ fmt(data.dedupeStats.spamRemoved || 0) }}</span>
                    <span class="metric-label">疑似水军</span>
                  </div>
                </template>
                <div class="metric-spacer"></div>
                <div class="metric" v-if="data.replyCountFromVideo">
                  <span class="metric-val muted">{{ fmt(data.replyCountFromVideo) }}</span>
                  <span class="metric-label muted">视频总评</span>
                </div>
              </div>

              <!-- 链接 + 时间 -->
              <div class="source-fields">
                <div class="source-url-row">
                  <svg class="source-icon" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M7 2a4 4 0 014 4v1h1a2 2 0 012 2v3a2 2 0 01-2 2H4a2 2 0 01-2-2V9a2 2 0 012-2h1V6a4 4 0 014-4z" stroke-linecap="round" stroke-linejoin="round"/></svg>
                  <a :href="data.sourceUrl || '#'" target="_blank" rel="noopener" class="source-link" @click.stop>{{ data.finalUrl || data.sourceUrl || '-' }}</a>
                  <button class="copy-btn" title="Copy URL" @click.prevent="copyUrl" :class="{ copied: copied }">
                    <svg v-if="!copied" viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="5" y="5" width="8" height="8" rx="1.5"/><path d="M10 5V3a2 2 0 00-2-2H3a2 2 0 00-2 2v5a2 2 0 002 2h2"/></svg>
                    <svg v-else viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="var(--success)" stroke-width="1.5"><path d="M3 8l3 3 7-7" stroke-linecap="round" stroke-linejoin="round"/></svg>
                  </button>
                </div>
                <div class="source-meta-row">
                  <span class="source-time" :title="data.fetchedAt || ''">
                    <svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="8" cy="8" r="6"/><path d="M8 4v4l3 2" stroke-linecap="round"/></svg>
                    {{ relativeTime }}
                  </span>
                  <span class="source-platform" v-if="data.platform">
                    <svg viewBox="0 0 16 16" width="12" height="12" fill="currentColor"><path d="M4 2l8 6-8 6V2z"/></svg>
                    {{ data.platform }}
                  </span>
                  <span class="source-login-hint" v-if="data.needsLogin" title="More comments may be available after login">
                    <svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="var(--warning)" stroke-width="1.5"><path d="M8 8a2.5 2.5 0 100-5 2.5 2.5 0 000 5zM3 14a5 5 0 0110 0" stroke-linecap="round" stroke-linejoin="round"/></svg>
                    登录后可获取更多评论
                  </span>
                </div>
              </div>

              <!-- 分析方法标签 -->
              <div class="source-method-tags" v-if="data">
                <span class="method-tag">Lexicon</span>
                <span class="method-tag" v-if="data.dedupeStats?.spamRemoved > 0">Deduped</span>
                <span class="method-tag">TF-IDF</span>
                <span class="method-tag tag-llm" v-if="data.llmSentimentEnhanced">LLM 增强</span>
              </div>

              <!-- LLM 增强统计 -->
              <div v-if="data.llmSentimentEnhanced && data.llmSentimentStats" class="llm-enhance-info">
                <span class="llm-enhance-text">
                  {{ data.llmSentimentStats.total_neutral }} 条中性评论经 LLM 二次分类，
                  <b>{{ data.llmSentimentStats.enhanced }}</b> 条被重新判定
                </span>
              </div>

              <!-- 免责 -->
              <p class="source-disclaimer">分析基于本地情感词典与规则引擎，结果仅供参考。</p>
            </div>
          </transition>
        </section>
      </aside>
    </div>
  </section>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import SentimentRing from './charts/SentimentRing.vue'
import EmptyState from './ui/EmptyState.vue'
import AgentTrace from './AgentTrace.vue'
import ActionsPanel from './ActionsPanel.vue'

const props = defineProps({
  data: { type: Object, default: null },
})

const showSource = ref(false)
const copied = ref(false)
const sentiments = computed(() => props.data?.sentiments || {})

// 动画 key：数据变化时重新触发入场动画
const animKey = computed(() => `${props.data?.bvid || ''}-${props.data?.fetchedAt || ''}`)

// 评论折叠
const commentLimit = ref(5)
const showAllComments = ref(false)
const allComments = computed(() => props.data?.comments || [])
const displayedComments = computed(() => {
  if (showAllComments.value) return allComments.value
  return allComments.value.slice(0, commentLimit.value)
})
const hiddenCount = computed(() => Math.max(0, allComments.value.length - commentLimit.value))
const canExpand = computed(() => commentLimit.value < 9999 && allComments.value.length > commentLimit.value)

// 数据变化时重置评论状态
watch(() => props.data, () => {
  showAllComments.value = false
  commentLimit.value = 5
})

// 关键词列表：优先带 TF-IDF 权重的 keywordsWeighted，否则回退 keywords
const kwList = computed(() => {
  const w = props.data?.keywordsWeighted
  if (Array.isArray(w) && w.length) return w
  return (props.data?.keywords || []).map((k) => ({ word: k, weight: 1 }))
})

const riskText = { low: '低风险', medium: '中风险', high: '高风险', unknown: '未知' }
const sentimentLabels = { pos: '正向', neu: '中性', neg: '负向', con: '争议', risk: '风险' }
const sentimentOrder = ['pos', 'neu', 'neg', 'con', 'risk']

function segClass(k) {
  return { pos: 'pos', neu: 'neu', neg: 'neg', con: 'con', risk: 'riskSeg' }[k] || 'neu'
}
function sentimentBadge(k) {
  return { pos: 'success', neu: 'neutral', neg: 'danger', con: 'purple', risk: 'danger' }[k] || 'neutral'
}
function fmt(num) {
  return Number(num || 0).toLocaleString('zh-CN')
}
function chipStyle(kw, i) {
  // 用 TF-IDF 真实权重归一化到字号 12-17px
  const list = kwList.value
  const maxW = list.length ? Math.max(...list.map((k) => k.weight || 1)) : 1
  const ratio = maxW > 0 ? (kw.weight || 1) / maxW : 1
  const fs = (12 + ratio * 5).toFixed(1) + 'px'
  if (i === 0) return { fontSize: fs, fontWeight: 600, color: 'var(--brand)' }
  if (i < 3) return { fontSize: fs, fontWeight: 500, color: 'var(--text-1)' }
  return { fontSize: fs, color: 'var(--text-2)' }
}
function proxyImage(url) {
  if (!url) return ''
  const normalized = String(url).startsWith('//') ? `https:${url}` : String(url)
  return `/api/image?url=${encodeURIComponent(normalized)}`
}
function onCoverError(e) { e.target.style.display = 'none' }

// Relative time: "3 minutes ago", "just now"
const relativeTime = computed(() => {
  const ts = props.data?.fetchedAt
  if (!ts) return '-'
  const d = new Date(ts.replace(/\s/, 'T'))
  if (isNaN(d.getTime())) return ts
  const diff = Date.now() - d.getTime()
  if (diff < 0) return 'just now'
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
})

// Copy URL to clipboard
async function copyUrl() {
  const url = props.data?.finalUrl || props.data?.sourceUrl || ''
  try {
    await navigator.clipboard.writeText(url)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch {
    // fallback: textarea trick
    const ta = document.createElement('textarea')
    ta.value = url; ta.style.position = 'fixed'; document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  }
}
</script>

<style scoped>
/* ===== 入场动画 ===== */
.analysis-result { animation: resultIn 0.3s ease both; }
@keyframes resultIn {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}

.anim-card {
  animation: cardSlideIn 0.4s cubic-bezier(.4, 0, .2, 1) both;
  animation-delay: calc(var(--i, 0) * 0.07s);
}
@keyframes cardSlideIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

/* 评论列表项过渡 */
.comment-list-enter-active { transition: all 0.3s ease; }
.comment-list-leave-active { transition: all 0.2s ease; }
.comment-list-enter-from { opacity: 0; transform: translateY(-8px); }
.comment-list-leave-to { opacity: 0; transform: translateX(20px); }

.grid-analysis { display: grid; grid-template-columns: 1.3fr .7fr; gap: var(--sp-4); align-items: start; }
.main-col, .side-col { display: flex; flex-direction: column; gap: var(--sp-4); }

/* 视频卡 */
.video-card { display: grid; grid-template-columns: 220px 1fr; gap: var(--sp-4); padding: var(--sp-4); }
.cover { width: 100%; aspect-ratio: 16 / 10; object-fit: cover; border-radius: var(--r-lg); border: 1px solid var(--border-1); background: var(--fill-1); }
.video-info h2 { font-size: var(--fs-lg); font-weight: 600; margin-bottom: var(--sp-2); line-height: var(--lh-tight); }
.video-info .meta { margin-bottom: var(--sp-3); }
.risk-reason { color: var(--text-2); font-size: var(--fs-sm); margin: var(--sp-2) 0 0; line-height: var(--lh-base); }

/* 情绪区 */
.sentiment-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--sp-4); align-items: center; }
.sentiment-detail { display: flex; flex-direction: column; gap: var(--sp-3); }
.sentiment-item { display: flex; align-items: center; gap: var(--sp-2); font-size: var(--fs-sm); }
.sentiment-label { color: var(--text-2); flex: 1; }
.sentiment-value { color: var(--text-1); font-weight: 600; font-family: var(--font-mono); }
.legend-dot { width: 10px; height: 10px; border-radius: 3px; }

/* 卡片头 */
.card-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--sp-3); gap: var(--sp-2); }
.card-head h3 { margin: 0; }

/* 评论控制区 */
.comment-controls { display: flex; align-items: center; gap: var(--sp-2); }
.comment-limit-select {
  height: 28px;
  width: auto;
  font-size: var(--fs-xs);
  padding: 0 28px 0 8px;
  border-radius: var(--r-sm);
}

/* 评论展开按钮 */
.comment-expand-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  margin-top: var(--sp-3);
  padding: var(--sp-2);
  background: var(--fill-1);
  border: 1px dashed var(--border-1);
  border-radius: var(--r-md);
  color: var(--text-3);
  font-size: var(--fs-sm);
  cursor: pointer;
  transition: all var(--t-fast);
}
.comment-expand-btn:hover {
  background: var(--brand-soft);
  border-color: var(--brand-2);
  color: var(--brand);
}
.comment-expand-btn .arrow { transition: transform var(--t-fast); }
.comment-expand-btn .arrow.up { transform: rotate(180deg); }

/* 聚类 */
.cluster-head { display: flex; justify-content: space-between; align-items: flex-start; gap: var(--sp-2); margin-bottom: var(--sp-1); }

/* 评论 */
.comment { display: grid; grid-template-columns: 36px 1fr; gap: var(--sp-3); padding: var(--sp-3) 0; border-bottom: 1px solid var(--border-2); }
.comment:last-child { border-bottom: none; }
.comment-avatar { width: 36px; height: 36px; border-radius: 50%; background: var(--brand-soft); color: var(--brand); display: flex; align-items: center; justify-content: center; font-weight: 600; font-size: var(--fs-md); flex-shrink: 0; }
.comment-main { min-width: 0; }
.comment-head { display: flex; justify-content: space-between; gap: var(--sp-2); margin-bottom: 6px; }
.comment-user { font-size: var(--fs-sm); font-weight: 500; color: var(--text-1); }
.comment-time { color: var(--text-3); font-weight: 400; }
.comment-meta { display: flex; align-items: center; gap: var(--sp-2); }
.likes { display: inline-flex; align-items: center; gap: 3px; color: var(--text-3); font-size: var(--fs-xs); }
.likes svg { color: var(--warning); }
.comment-body { color: var(--text-1); font-size: var(--fs-sm); line-height: var(--lh-loose); }

/* 关键词高亮 */
.chip-hl { background: var(--brand-soft); border-color: var(--brand-soft-hover); }

/* 报告 */
.report-card h3 { display: flex; align-items: center; gap: 6px; }
.report-badge {
  font-size: var(--fs-2xs);
  font-weight: 600;
  padding: 1px 8px;
  border-radius: 999px;
  letter-spacing: 0.03em;
  margin-left: 4px;
  line-height: 1.6;
}
.report-badge.ai {
  background: rgba(0,47,167,0.1);
  color: var(--brand);
  border: 1px solid rgba(0,47,167,0.2);
}
.report-badge.template {
  background: var(--bg-soft);
  color: var(--text-3);
  border: 1px solid var(--border-2);
}
.report-body { display: flex; flex-direction: column; gap: var(--sp-3); }
.report-section { }
.report-label { font-size: var(--fs-xs); font-weight: 600; color: var(--text-3); margin-bottom: 4px; text-transform: uppercase; letter-spacing: .04em; }
.report-pos { color: var(--success); }
.report-neg { color: var(--danger); }
.report-section p { color: var(--text-1); font-size: var(--fs-sm); line-height: var(--lh-loose); word-break: break-word; overflow-wrap: break-word; }
.report-list { list-style: disc; padding-left: var(--sp-4); }
.report-list li { color: var(--text-2); font-size: var(--fs-sm); line-height: var(--lh-base); margin: 4px 0; word-break: break-word; overflow-wrap: break-word; }

/* 折叠头 */
.collapse-head { width: 100%; display: flex; justify-content: space-between; align-items: center; background: transparent; border: 0; cursor: pointer; padding: 0; }
.collapse-head h3 { margin: 0; }
.collapse-head .arrow { color: var(--text-3); transition: transform var(--t-fast); }
.collapse-head .arrow.up { transform: rotate(180deg); }
/* ===== Data Source Section (Redesigned) ===== */
.source-body {
  margin-top: var(--sp-3);
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  min-width: 0;
  overflow: hidden;
}

.source-metrics {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  flex-wrap: wrap;
  background: var(--bg-soft);
  border-radius: var(--r-md);
  padding: var(--sp-3) var(--sp-4);
}
.metric {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 52px;
}
.metric-val {
  font-size: var(--fs-lg);
  font-weight: 700;
  color: var(--text-1);
  line-height: 1.2;
}
.metric-val.muted { color: var(--text-3); font-weight: 500; }
.metric-label {
  font-size: var(--fs-2xs);
  color: var(--text-3);
  margin-top: 2px;
  white-space: nowrap;
}
.metric-label.muted { opacity: 0.7; }
.metric-arrow {
  flex-shrink: 0;
  margin-top: -6px;
  opacity: 0.5;
}
.metric-highlight { position: relative; }
.metric-highlight.spam-found .metric-val { color: var(--warning); }
.metric-spacer { width: 8px; }

.source-fields {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  min-width: 0;
  overflow: hidden;
}
.source-url-row {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-2) var(--sp-3);
  background: var(--bg);
  border-radius: var(--r-sm);
  border: 1px solid var(--border-2);
  transition: border-color 0.15s;
  overflow: hidden;
  min-width: 0;
}
.source-url-row:hover { border-color: var(--border-focus); }
.source-icon { flex-shrink: 0; color: var(--text-3); }
.source-link {
  font-size: var(--fs-xs);
  color: var(--brand);
  text-decoration: none;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
  max-width: 0;
  flex: 1 1 0%;
  word-break: break-all;
  overflow-wrap: anywhere;
}
.source-link:hover { text-decoration: underline; }
.copy-btn {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: var(--r-sm);
  border: 1px solid transparent;
  background: transparent;
  color: var(--text-3);
  cursor: pointer;
  transition: all 0.15s;
}
.copy-btn:hover { background: var(--bg-soft); color: var(--text-1); border-color: var(--border-2); }
.copy-btn.copied { color: var(--success); }

.source-meta-row {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  font-size: var(--fs-2xs);
  color: var(--text-3);
  padding-left: 2px;
}
.source-time,
.source-platform,
.source-login-hint {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.source-time svg { opacity: 0.6; }
.source-platform { color: var(--text-3); }
.source-platform svg { color: var(--brand); opacity: 0.7; }
.source-login-hint { color: var(--warning); }

.source-method-tags {
  display: flex;
  gap: var(--sp-1);
  flex-wrap: wrap;
}
.method-tag {
  font-size: var(--fs-2xs);
  padding: 2px 10px;
  border-radius: 999px;
  background: var(--bg-brand-subtle, rgba(0,47,167,0.06));
  color: var(--brand);
  border: 1px solid var(--brand-border, rgba(0,47,167,0.12));
  font-weight: 500;
  letter-spacing: 0.02em;
}
.method-tag.tag-llm {
  background: rgba(103, 17, 245, 0.08);
  color: #6f1ff5;
  border-color: rgba(103, 17, 245, 0.18);
}

/* LLM 增强统计信息 */
.llm-enhance-info {
  margin-top: var(--sp-2);
  padding: var(--sp-2) var(--sp-3);
  background: rgba(103, 17, 245, 0.04);
  border-left: 2px solid #6f1ff5;
  border-radius: 4px;
}
.llm-enhance-text {
  font-size: var(--fs-xs);
  color: var(--text-2);
  line-height: 1.6;
}
.llm-enhance-text b {
  color: #6f1ff5;
  font-weight: 600;
}

.source-disclaimer {
  font-size: var(--fs-2xs);
  color: var(--text-4);
  line-height: 1.6;
  margin: 0;
  padding-top: var(--sp-2);
  border-top: 1px dashed var(--border-2);
}

.expand-enter-active, .expand-leave-active { transition: all var(--t-base); overflow: hidden; }
.expand-enter-from, .expand-leave-to { opacity: 0; max-height: 0; }
.expand-enter-to, .expand-leave-from { opacity: 1; max-height: 500px; }

@media (max-width: 1024px) {
  .grid-analysis { grid-template-columns: 1fr; }
  .video-card { grid-template-columns: 180px 1fr; }
}
@media (max-width: 768px) {
  .video-card { grid-template-columns: 1fr; }
  .sentiment-grid { grid-template-columns: 1fr; }
}
</style>
