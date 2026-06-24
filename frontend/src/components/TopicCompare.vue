<template>
  <section v-if="data" class="topic-compare" id="export-capture-compare">
    <div class="section-title">
      <div>
        <h2>双平台对比分析</h2>
        <span class="subtitle">{{ data.keyword }} · B站 vs 小红书</span>
      </div>
      <div class="title-actions">
        <ExportButtons target-id="export-capture-compare" :file-name="`双平台对比_${data.keyword}`" />
        <span class="badge badge-neutral">{{ data.fetchedAt || '' }}</span>
      </div>
    </div>

    <section class="card export-summary-card">
      <div class="export-summary-head">
        <div>
          <h3>汇报摘要</h3>
          <p>先把双平台可比性讲清楚，再展开差异细节。</p>
        </div>
        <span class="export-summary-tag">阶段二 · 差异解释版</span>
      </div>
      <div class="export-summary-grid">
        <div class="summary-item">
          <span>对比状态</span>
          <b>{{ compareStatusLabel }}</b>
        </div>
        <div class="summary-item">
          <span>总体可信度</span>
          <b>{{ confidenceMeta.grade }} · {{ confidenceMeta.score }} 分</b>
        </div>
        <div class="summary-item">
          <span>可比性</span>
          <b>{{ bothOk ? '双平台完整' : '仅单平台可用' }}</b>
        </div>
        <div class="summary-item">
          <span>B站样本</span>
          <b>{{ bili ? `${fmt(bili.totalComments)} 条 / ${platformCoverageText(bili)}` : '无结果' }}</b>
        </div>
        <div class="summary-item">
          <span>小红书样本</span>
          <b>{{ xhs ? `${fmt(xhs.totalComments)} 条 / ${platformCoverageText(xhs)}` : '无结果' }}</b>
        </div>
        <div class="summary-item wide">
          <span>核心判断</span>
          <b>{{ explanation?.headline || (diagnostics.length ? diagnostics[0].title : '双平台链路正常，可直接查看对比结果') }}</b>
        </div>
      </div>
    </section>

    <section class="card compare-quality-card">
      <div class="quality-head">
        <div>
          <h3>对比可信度与诊断</h3>
          <p class="quality-subtitle">先判断双平台样本是否站得住，再解读差异本身。</p>
        </div>
        <div class="confidence-pill" :class="confidenceToneClass">
          <span class="confidence-grade">{{ confidenceMeta.grade }}</span>
          <span class="confidence-score">{{ confidenceMeta.score }} 分</span>
        </div>
      </div>
      <div class="quality-metrics">
        <div class="quality-metric">
          <span class="metric-k">当前状态</span>
          <strong class="metric-v">{{ compareStatusLabel }}</strong>
          <span class="metric-note">{{ compareStatusDesc }}</span>
        </div>
        <div class="quality-metric">
          <span class="metric-k">B站可信度</span>
          <strong class="metric-v">{{ platformConfidenceText(bili) }}</strong>
          <span class="metric-note">{{ platformCoverageText(bili) }}</span>
        </div>
        <div class="quality-metric">
          <span class="metric-k">小红书可信度</span>
          <strong class="metric-v">{{ platformConfidenceText(xhs) }}</strong>
          <span class="metric-note">{{ platformCoverageText(xhs) }}</span>
        </div>
        <div class="quality-metric">
          <span class="metric-k">可比性</span>
          <strong class="metric-v">{{ bothOk ? '完整' : '受限' }}</strong>
          <span class="metric-note">{{ bothOk ? '双平台均已返回结果' : '当前仅能参考单平台' }}</span>
        </div>
      </div>
      <div class="quality-summary">{{ confidenceMeta.summary }}</div>
      <ul v-if="confidenceMeta.reasons?.length" class="quality-reasons">
        <li v-for="(reason, idx) in confidenceMeta.reasons" :key="idx">{{ reason }}</li>
      </ul>
    </section>

    <section v-if="diagnostics.length" class="card diagnostics-card">
      <div class="diagnostics-head">
        <h3>对比诊断</h3>
        <span class="diagnostics-count">{{ diagnostics.length }} 项</span>
      </div>
      <div class="diagnostics-list">
        <div v-for="item in diagnostics" :key="item.code" class="diagnosis-item" :class="item.level">
          <div class="diagnosis-top">
            <strong>{{ item.title }}</strong>
            <span class="diagnosis-continue" :class="{ off: item.canContinue === false }">
              {{ item.canContinue === false ? '建议先修复' : '可继续查看结果' }}
            </span>
          </div>
          <p><span>影响：</span>{{ item.impact }}</p>
          <p><span>建议：</span>{{ item.action }}</p>
        </div>
      </div>
    </section>

    <section v-if="bothOk && explanation" class="card explain-engine-card">
      <div class="explain-head">
        <div>
          <h3>差异解释引擎</h3>
          <p>{{ explanation.headline }}</p>
        </div>
        <span class="explain-badge">阶段二 · 洞察版</span>
      </div>

      <div class="signal-grid">
        <div v-for="item in keySignals" :key="item.key" class="signal-card" :class="item.tone">
          <span class="signal-label">{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
          <p>{{ item.desc }}</p>
        </div>
      </div>

      <div class="explain-grid">
        <section class="explain-block">
          <h4>为什么会这样</h4>
          <ul class="explain-list">
            <li v-for="(item, idx) in explanation.why" :key="idx">{{ item }}</li>
          </ul>
        </section>
        <section class="explain-block">
          <h4>共同热议点</h4>
          <div class="focus-tags">
            <span v-for="item in explanation.sharedFocus" :key="item" class="focus-tag shared">{{ item }}</span>
            <span v-if="!explanation.sharedFocus?.length" class="focus-empty">暂无明显交集</span>
          </div>
        </section>
        <section class="explain-block">
          <h4>平台分化点</h4>
          <div class="split-focus">
            <div class="split-col">
              <span class="split-title bili">B站更在意</span>
              <div class="focus-tags">
                <span v-for="item in explanation.divergentFocus?.bilibili || []" :key="`b-${item}`" class="focus-tag bili">{{ item }}</span>
                <span v-if="!(explanation.divergentFocus?.bilibili || []).length" class="focus-empty">暂无</span>
              </div>
            </div>
            <div class="split-col">
              <span class="split-title xhs">小红书更在意</span>
              <div class="focus-tags">
                <span v-for="item in explanation.divergentFocus?.xiaohongshu || []" :key="`x-${item}`" class="focus-tag xhs">{{ item }}</span>
                <span v-if="!(explanation.divergentFocus?.xiaohongshu || []).length" class="focus-empty">暂无</span>
              </div>
            </div>
          </div>
        </section>
      </div>

      <div class="persona-row">
        <div class="persona-card bili">
          <span class="persona-label">B站气质</span>
          <strong>{{ biliTone?.tone || '待评估' }}</strong>
          <p>{{ biliTone?.summary || '暂无描述' }}</p>
        </div>
        <div class="persona-card xhs">
          <span class="persona-label">小红书气质</span>
          <strong>{{ xhsTone?.tone || '待评估' }}</strong>
          <p>{{ xhsTone?.summary || '暂无描述' }}</p>
        </div>
      </div>

      <div v-if="explanation.actions?.length" class="action-list">
        <div v-for="(item, idx) in explanation.actions" :key="idx" class="action-item">
          <span class="action-index">{{ idx + 1 }}</span>
          <p>{{ item }}</p>
        </div>
      </div>
    </section>

    <!-- 核心洞察条 -->
    <section v-if="diff.bothOk && (diff.insights || []).length" class="card insight-card">
      <div class="insight-head">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16"><path d="M8 1.5a4.5 4.5 0 0 0-2.7 8.1c.5.4.7.8.7 1.4v.5h4v-.5c0-.6.2-1 .7-1.4A4.5 4.5 0 0 0 8 1.5z" stroke-linejoin="round"/><path d="M6 14h4M6.5 12.5h3" stroke-linecap="round"/></svg>
        <h3>跨平台洞察</h3>
      </div>
      <ul class="insight-list">
        <li v-for="(s, i) in diff.insights" :key="i">{{ s }}</li>
      </ul>
    </section>

    <!-- 单平台失败提示 -->
    <section v-if="!diff.bothOk" class="card warn-card">
      <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M8 1L1 14h14L8 1z" stroke-linejoin="round"/><path d="M8 6v4M8 12h.01" stroke-linecap="round"/></svg>
      <div>
        <strong>仅单平台分析成功</strong>
        <p>另一平台分析失败（可能未配置 Cookie / 登录态或触发限流）。已展示成功平台的结果。
          <template v-if="data.errors?.bilibili">B站：{{ data.errors.bilibili }}；</template>
          <template v-if="data.errors?.xiaohongshu">小红书：{{ data.errors.xiaohongshu }}。</template>
        </p>
      </div>
    </section>

    <!-- 顶部指标对比卡 -->
    <section class="card metric-compare">
      <div class="mc-col mc-bili">
        <div class="mc-platform"><span class="dot dot-bili"></span>B站</div>
        <div class="mc-stats">
          <div class="mc-stat"><b>{{ fmt(bili?.totalComments) }}</b><span>聚合评论</span></div>
          <div class="mc-stat"><b>{{ bili?.analyzedCount ?? '—' }}</b><span>分析视频</span></div>
          <div class="mc-stat">
            <b :class="negClass(diff.biliNegRatio)">{{ bothOk ? diff.biliNegRatio + '%' : (negRatio(bili) + '%') }}</b>
            <span>负面占比</span>
          </div>
          <div class="mc-stat"><span :class="['risk-pill', `risk-${bili?.risk || 'unknown'}`]">{{ riskText[bili?.risk] || '—' }}</span></div>
        </div>
      </div>

      <div class="mc-vs">VS</div>

      <div class="mc-col mc-xhs">
        <div class="mc-platform"><span class="dot dot-xhs"></span>小红书</div>
        <div class="mc-stats">
          <div class="mc-stat"><b>{{ fmt(xhs?.totalComments) }}</b><span>聚合评论</span></div>
          <div class="mc-stat"><b>{{ xhs?.analyzedCount ?? '—' }}</b><span>分析笔记</span></div>
          <div class="mc-stat">
            <b :class="negClass(diff.xhsNegRatio)">{{ bothOk ? diff.xhsNegRatio + '%' : (negRatio(xhs) + '%') }}</b>
            <span>负面占比</span>
          </div>
          <div class="mc-stat"><span :class="['risk-pill', `risk-${xhs?.risk || 'unknown'}`]">{{ riskText[xhs?.risk] || '—' }}</span></div>
        </div>
      </div>
    </section>

    <!-- 情绪分布并排 -->
    <section class="card">
      <h3>情绪分布对比</h3>
      <div class="ring-compare">
        <div class="ring-side">
          <div class="ring-title"><span class="dot dot-bili"></span>B站</div>
          <SentimentRing v-if="bili" :sentiments="bili.sentiments" :total="bili.totalComments || 0" />
          <EmptyState v-else title="无数据" description="该平台分析失败" />
        </div>
        <div class="ring-side">
          <div class="ring-title"><span class="dot dot-xhs"></span>小红书</div>
          <SentimentRing v-if="xhs" :sentiments="xhs.sentiments" :total="xhs.totalComments || 0" />
          <EmptyState v-else title="无数据" description="该平台分析失败" />
        </div>
      </div>

      <!-- 情绪差异对比条 -->
      <div v-if="bothOk" class="delta-bars">
        <div v-for="k in sentimentOrder" :key="k" class="delta-row">
          <span class="delta-label">{{ sentimentLabels[k] }}</span>
          <div class="delta-track">
            <div class="delta-bili" :style="{ width: (bili.sentiments?.[k] || 0) + '%' }"></div>
          </div>
          <span class="delta-val">{{ bili.sentiments?.[k] || 0 }}%</span>
          <span class="delta-gap" :class="gapClass(diff.sentimentDelta?.[k])">{{ fmtDelta(diff.sentimentDelta?.[k]) }}</span>
          <span class="delta-val">{{ xhs.sentiments?.[k] || 0 }}%</span>
          <div class="delta-track right">
            <div class="delta-xhs" :style="{ width: (xhs.sentiments?.[k] || 0) + '%' }"></div>
          </div>
        </div>
        <div class="delta-legend">
          <span><span class="dot dot-bili"></span>B站</span>
          <span class="delta-mid">中间为差值（B站 − 小红书）</span>
          <span><span class="dot dot-xhs"></span>小红书</span>
        </div>
      </div>
    </section>

    <!-- 关键词对比（交集 + 各自独有） -->
    <section class="card">
      <h3>关键词对比</h3>
      <div class="kw-compare">
        <div class="kw-group">
          <div class="kw-group-head bili"><span class="dot dot-bili"></span>B站独有</div>
          <div class="kw-tags">
            <span v-for="kw in (bothOk ? diff.biliOnlyKeywords : (bili?.keywords || []))" :key="'b'+kw" class="kw-tag kw-bili">{{ kw }}</span>
            <span v-if="!(bothOk ? diff.biliOnlyKeywords : bili?.keywords || []).length" class="kw-empty">无</span>
          </div>
        </div>
        <div class="kw-group kw-common">
          <div class="kw-group-head common"><svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="6" cy="8" r="4"/><circle cx="10" cy="8" r="4"/></svg>共同热议</div>
          <div class="kw-tags">
            <span v-for="kw in diff.commonKeywords || []" :key="'c'+kw" class="kw-tag kw-common-tag">{{ kw }}</span>
            <span v-if="!(diff.commonKeywords || []).length" class="kw-empty">{{ bothOk ? '无重叠' : '需双平台数据' }}</span>
          </div>
        </div>
        <div class="kw-group">
          <div class="kw-group-head xhs"><span class="dot dot-xhs"></span>小红书独有</div>
          <div class="kw-tags">
            <span v-for="kw in (bothOk ? diff.xhsOnlyKeywords : (xhs?.keywords || []))" :key="'x'+kw" class="kw-tag kw-xhs">{{ kw }}</span>
            <span v-if="!(bothOk ? diff.xhsOnlyKeywords : xhs?.keywords || []).length" class="kw-empty">无</span>
          </div>
        </div>
      </div>
    </section>

    <!-- 各平台内容列表并排 -->
    <div class="list-compare">
      <section class="card">
        <h3><span class="dot dot-bili"></span>B站 热门视频</h3>
        <div v-if="(bili?.videos || []).length" class="content-list">
          <div v-for="(v, i) in bili.videos.slice(0, 5)" :key="v.bvid || i" class="content-item">
            <span class="ci-rank">{{ i + 1 }}</span>
            <div class="ci-info">
              <a :href="v.arcurl || '#'" target="_blank" class="ci-title">{{ v.title || '未知' }}</a>
              <div class="ci-meta"><span>{{ v.author }}</span><span :class="['risk-tag', `risk-${v.risk}`]">{{ riskText[v.risk] }}</span></div>
            </div>
          </div>
        </div>
        <EmptyState v-else title="无数据" />
      </section>
      <section class="card">
        <h3><span class="dot dot-xhs"></span>小红书 热门笔记</h3>
        <div v-if="(xhs?.videos || []).length" class="content-list">
          <div v-for="(v, i) in xhs.videos.slice(0, 5)" :key="v.noteId || i" class="content-item">
            <span class="ci-rank">{{ i + 1 }}</span>
            <div class="ci-info">
              <a :href="v.noteUrl || '#'" target="_blank" class="ci-title">{{ v.title || '未知' }}</a>
              <div class="ci-meta"><span>{{ v.author }}</span><span :class="['risk-tag', `risk-${v.risk}`]">{{ riskText[v.risk] }}</span></div>
            </div>
          </div>
        </div>
        <EmptyState v-else title="无数据" />
      </section>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import SentimentRing from './charts/SentimentRing.vue'
import EmptyState from './ui/EmptyState.vue'
import ExportButtons from './ExportButtons.vue'

const props = defineProps({ data: Object })

const sentimentOrder = ['pos', 'neu', 'neg', 'con', 'risk']
const sentimentLabels = { pos: '正面', neu: '中性', neg: '负面', con: '争议', risk: '风险' }
const riskText = { low: '低风险', medium: '中风险', high: '高风险', unknown: '未知' }

const bili = computed(() => props.data?.bilibili || null)
const xhs = computed(() => props.data?.xiaohongshu || null)
const diff = computed(() => props.data?.diff || {})
const bothOk = computed(() => !!diff.value.bothOk)
const diagnostics = computed(() => props.data?.diagnostics || [])
const confidenceMeta = computed(() => props.data?.confidence || { grade: 'C', score: 60, summary: '当前缺少对比可信度评估数据。', reasons: [] })
const confidenceToneClass = computed(() => ({ A: 'tone-a', B: 'tone-b', C: 'tone-c', D: 'tone-d' }[confidenceMeta.value.grade] || 'tone-c'))
const explanation = computed(() => diff.value?.explanation || null)
const biliTone = computed(() => diff.value?.biliTone || null)
const xhsTone = computed(() => diff.value?.xhsTone || null)
const compareStatusLabel = computed(() => {
  if (!bili.value && !xhs.value) return '失败'
  if (!bothOk.value) return '受限'
  if ((bili.value?.confidence?.grade === 'D') || (xhs.value?.confidence?.grade === 'D')) return '谨慎'
  return '正常'
})
const compareStatusDesc = computed(() => {
  if (!bili.value && !xhs.value) return '当前没有可用的平台结果'
  if (!bothOk.value) return '仅单平台成功，横向比较暂不完整'
  if ((bili.value?.confidence?.grade === 'D') || (xhs.value?.confidence?.grade === 'D')) return '至少一侧样本可信度很低'
  return '双平台样本可用于当前差异判断'
})
const keySignals = computed(() => {
  if (!bothOk.value) return []
  const negWinner = diff.value?.moreNegativePlatform === 'bilibili'
    ? 'B站更高'
    : diff.value?.moreNegativePlatform === 'xiaohongshu'
      ? '小红书更高'
      : '两边接近'
  const posWinner = diff.value?.morePositivePlatform === 'bilibili'
    ? 'B站更强'
    : diff.value?.morePositivePlatform === 'xiaohongshu'
      ? '小红书更强'
      : '两边接近'
  const conWinner = diff.value?.moreControversialPlatform === 'bilibili'
    ? 'B站更集中'
    : diff.value?.moreControversialPlatform === 'xiaohongshu'
      ? '小红书更集中'
      : '两边接近'
  return [
    {
      key: 'negative',
      label: '负面压力',
      value: negWinner,
      desc: `负面/风险差值 ${diff.value?.negRatioDiff ?? '—'} 个百分点`,
      tone: 'tone-negative',
    },
    {
      key: 'positive',
      label: '正向承接',
      value: posWinner,
      desc: `正面差值 ${diff.value?.posRatioDiff ?? '—'} 个百分点`,
      tone: 'tone-positive',
    },
    {
      key: 'controversy',
      label: '争议密度',
      value: conWinner,
      desc: `争议/风险差值 ${diff.value?.controversyDiff ?? '—'} 个百分点`,
      tone: 'tone-neutral',
    },
  ]
})

function fmt(n) {
  if (n == null) return '—'
  if (n >= 10000) return (n / 10000).toFixed(1) + '万'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return String(n)
}
function negRatio(p) {
  if (!p?.sentiments) return 0
  return Math.round((p.sentiments.neg || 0) + (p.sentiments.risk || 0))
}
function negClass(v) {
  if (v == null) return ''
  if (v >= 30) return 'neg-high'
  if (v >= 15) return 'neg-mid'
  return 'neg-low'
}
function fmtDelta(v) {
  if (v == null) return '—'
  if (v > 0) return '+' + v
  return String(v)
}
function gapClass(v) {
  if (v == null || v === 0) return 'gap-eq'
  return v > 0 ? 'gap-bili' : 'gap-xhs'
}
function platformConfidenceText(platformData) {
  if (!platformData?.confidence) return '—'
  return `${platformData.confidence.grade} · ${platformData.confidence.score} 分`
}
function platformCoverageText(platformData) {
  if (!platformData) return '该平台无结果'
  if (platformData.coverageRate == null) return '覆盖率未知'
  return `覆盖率 ${platformData.coverageRate}%`
}
</script>

<style scoped>
.topic-compare { margin-bottom: var(--sp-5); }
.title-actions { display: flex; align-items: center; gap: var(--sp-3); }
.export-summary-card { margin-bottom: var(--sp-4); }
.export-summary-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--sp-3);
  margin-bottom: var(--sp-3);
}
.export-summary-head h3 { margin: 0; }
.export-summary-head p {
  margin: 4px 0 0;
  font-size: var(--fs-xs);
  color: var(--text-3);
  line-height: var(--lh-base);
}
.export-summary-tag {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(0,47,167,0.08);
  border: 1px solid rgba(0,47,167,0.16);
  color: var(--brand);
  font-size: var(--fs-2xs);
  font-weight: 600;
}
.export-summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--sp-3);
}
.summary-item {
  padding: var(--sp-3);
  border-radius: var(--r-lg);
  background: var(--fill-1);
  border: 1px solid var(--border-2);
}
.summary-item.wide { grid-column: span 2; }
.summary-item span { display: block; font-size: var(--fs-2xs); color: var(--text-3); }
.summary-item b {
  display: block;
  margin-top: 6px;
  font-size: var(--fs-sm);
  color: var(--text-1);
  line-height: var(--lh-base);
}
.compare-quality-card { margin-bottom: var(--sp-4); }
.quality-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--sp-3);
  margin-bottom: var(--sp-3);
}
.quality-subtitle { margin-top: 4px; font-size: var(--fs-xs); color: var(--text-3); line-height: var(--lh-base); }
.quality-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--sp-3);
  margin-bottom: var(--sp-3);
}
.quality-metric {
  padding: var(--sp-3);
  border-radius: var(--r-lg);
  background: var(--fill-1);
  border: 1px solid var(--border-2);
}
.metric-k { display: block; font-size: var(--fs-xs); color: var(--text-3); }
.metric-v { display: block; margin-top: 6px; font-size: var(--fs-lg); color: var(--text-1); font-variant-numeric: tabular-nums; }
.metric-note { display: block; margin-top: 4px; font-size: var(--fs-2xs); color: var(--text-4); }
.quality-summary {
  padding: var(--sp-3);
  border-radius: var(--r-md);
  background: rgba(0,47,167,0.05);
  border: 1px solid rgba(0,47,167,0.12);
  color: var(--text-1);
  font-size: var(--fs-sm);
  line-height: var(--lh-loose);
}
.quality-reasons {
  margin: var(--sp-3) 0 0;
  padding-left: 18px;
  color: var(--text-2);
  font-size: var(--fs-xs);
  line-height: var(--lh-loose);
}
.confidence-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 999px;
  border: 1px solid transparent;
}
.confidence-grade { font-size: var(--fs-sm); font-weight: 700; }
.confidence-score { font-size: var(--fs-xs); color: inherit; opacity: 0.9; }
.confidence-pill.tone-a { background: rgba(22,163,74,0.08); border-color: rgba(22,163,74,0.18); color: #15803d; }
.confidence-pill.tone-b { background: rgba(0,47,167,0.08); border-color: rgba(0,47,167,0.18); color: var(--brand); }
.confidence-pill.tone-c { background: rgba(217,119,6,0.08); border-color: rgba(217,119,6,0.18); color: #b45309; }
.confidence-pill.tone-d { background: rgba(220,38,38,0.08); border-color: rgba(220,38,38,0.18); color: #dc2626; }
.diagnostics-card { margin-bottom: var(--sp-4); }
.diagnostics-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--sp-3); }
.diagnostics-count {
  font-size: var(--fs-2xs);
  color: var(--text-3);
  padding: 3px 8px;
  border-radius: 999px;
  background: var(--bg-soft);
  border: 1px solid var(--border-2);
}
.diagnostics-list { display: flex; flex-direction: column; gap: var(--sp-3); }
.diagnosis-item { padding: var(--sp-3); border-radius: var(--r-md); border: 1px solid var(--border-2); background: var(--bg-soft); }
.diagnosis-item.warning { background: rgba(217,119,6,0.06); border-color: rgba(217,119,6,0.18); }
.diagnosis-item.danger { background: rgba(220,38,38,0.05); border-color: rgba(220,38,38,0.16); }
.diagnosis-top { display: flex; justify-content: space-between; align-items: flex-start; gap: var(--sp-2); margin-bottom: 6px; }
.diagnosis-top strong { color: var(--text-1); font-size: var(--fs-sm); }
.diagnosis-continue { flex-shrink: 0; font-size: var(--fs-2xs); color: #15803d; background: rgba(22,163,74,0.08); border: 1px solid rgba(22,163,74,0.16); padding: 2px 8px; border-radius: 999px; }
.diagnosis-continue.off { color: #b45309; background: rgba(217,119,6,0.08); border-color: rgba(217,119,6,0.16); }
.diagnosis-item p { margin: 0; color: var(--text-2); font-size: var(--fs-xs); line-height: var(--lh-loose); }
.diagnosis-item p + p { margin-top: 4px; }
.diagnosis-item p span { color: var(--text-3); margin-right: 4px; }

.explain-engine-card {
  margin-bottom: var(--sp-4);
  border: 1px solid rgba(0,47,167,0.12);
  background: linear-gradient(180deg, rgba(0,47,167,0.03), rgba(255,255,255,0));
}
.explain-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--sp-3);
  margin-bottom: var(--sp-3);
}
.explain-head h3 { margin: 0; }
.explain-head p {
  margin: 6px 0 0;
  color: var(--text-2);
  font-size: var(--fs-sm);
  line-height: var(--lh-loose);
}
.explain-badge {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(0,47,167,0.08);
  border: 1px solid rgba(0,47,167,0.16);
  color: var(--brand);
  font-size: var(--fs-2xs);
  font-weight: 600;
}
.signal-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--sp-3);
  margin-bottom: var(--sp-3);
}
.signal-card {
  padding: var(--sp-3);
  border-radius: var(--r-lg);
  border: 1px solid var(--border-2);
  background: var(--fill-1);
}
.signal-card strong {
  display: block;
  margin-top: 8px;
  font-size: var(--fs-lg);
  color: var(--text-1);
}
.signal-card p {
  margin: 6px 0 0;
  font-size: var(--fs-xs);
  color: var(--text-3);
  line-height: var(--lh-base);
}
.signal-label {
  display: inline-flex;
  align-items: center;
  font-size: var(--fs-2xs);
  color: var(--text-4);
}
.signal-card.tone-negative { border-color: rgba(220,38,38,0.16); background: rgba(220,38,38,0.04); }
.signal-card.tone-positive { border-color: rgba(22,163,74,0.16); background: rgba(22,163,74,0.04); }
.signal-card.tone-neutral { border-color: rgba(0,47,167,0.14); background: rgba(0,47,167,0.04); }
.explain-grid {
  display: grid;
  grid-template-columns: 1.1fr 0.9fr 1fr;
  gap: var(--sp-3);
}
.explain-block {
  padding: var(--sp-3);
  border-radius: var(--r-lg);
  border: 1px solid var(--border-2);
  background: #ffffff;
}
.explain-block h4 {
  margin: 0 0 var(--sp-2);
  font-size: var(--fs-sm);
  color: var(--text-1);
}
.explain-list {
  margin: 0;
  padding-left: 18px;
  color: var(--text-2);
  font-size: var(--fs-xs);
  line-height: var(--lh-loose);
}
.explain-list li + li { margin-top: 6px; }
.focus-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.focus-tag {
  display: inline-flex;
  align-items: center;
  padding: 5px 10px;
  border-radius: 999px;
  font-size: var(--fs-xs);
  border: 1px solid transparent;
}
.focus-tag.shared { background: rgba(0,47,167,0.08); border-color: rgba(0,47,167,0.14); color: var(--brand); }
.focus-tag.bili { background: rgba(0,174,236,0.1); border-color: rgba(0,174,236,0.18); color: #0284c7; }
.focus-tag.xhs { background: rgba(255,36,66,0.08); border-color: rgba(255,36,66,0.16); color: #e11d48; }
.focus-empty {
  font-size: var(--fs-xs);
  color: var(--text-4);
}
.split-focus {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--sp-3);
}
.split-col {
  padding: var(--sp-2);
  border-radius: var(--r-md);
  background: var(--fill-1);
}
.split-title {
  display: inline-block;
  margin-bottom: var(--sp-2);
  font-size: var(--fs-2xs);
  font-weight: 600;
}
.split-title.bili { color: #0284c7; }
.split-title.xhs { color: #e11d48; }
.persona-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--sp-3);
  margin-top: var(--sp-3);
}
.persona-card {
  padding: var(--sp-3);
  border-radius: var(--r-lg);
  border: 1px solid var(--border-2);
  background: var(--fill-1);
}
.persona-card strong {
  display: block;
  margin-top: 6px;
  font-size: var(--fs-lg);
  color: var(--text-1);
}
.persona-card p {
  margin: 8px 0 0;
  color: var(--text-2);
  font-size: var(--fs-xs);
  line-height: var(--lh-loose);
}
.persona-card.bili { border-color: rgba(0,174,236,0.18); }
.persona-card.xhs { border-color: rgba(255,36,66,0.16); }
.persona-label {
  font-size: var(--fs-2xs);
  color: var(--text-4);
}
.action-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--sp-3);
  margin-top: var(--sp-3);
}
.action-item {
  display: flex;
  gap: var(--sp-2);
  align-items: flex-start;
  padding: var(--sp-3);
  border-radius: var(--r-md);
  background: rgba(0,47,167,0.05);
  border: 1px solid rgba(0,47,167,0.12);
}
.action-index {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--brand);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  flex-shrink: 0;
}
.action-item p {
  margin: 0;
  color: var(--text-2);
  font-size: var(--fs-xs);
  line-height: var(--lh-loose);
}

/* 平台标识点 */
.dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 5px; vertical-align: middle; }
.dot-bili { background: #00AEEC; }
.dot-xhs { background: #FF2442; }

/* 洞察卡 */
.insight-card { margin-bottom: var(--sp-4); border-left: 3px solid var(--brand); }
.insight-head { display: flex; align-items: center; gap: var(--sp-2); margin-bottom: var(--sp-2); }
.insight-head svg { color: var(--brand); }
.insight-head h3 { font-size: var(--fs-md); font-weight: 600; }
.insight-list { padding-left: var(--sp-4); }
.insight-list li { list-style: disc; font-size: var(--fs-sm); color: var(--text-2); line-height: var(--lh-loose); margin-bottom: 4px; }

/* 警告卡 */
.warn-card { display: flex; gap: var(--sp-3); margin-bottom: var(--sp-4); background: rgba(234,179,8,.08); border: 1px solid rgba(234,179,8,.25); }
.warn-card svg { color: #ca8a04; flex-shrink: 0; margin-top: 2px; }
.warn-card strong { font-size: var(--fs-sm); color: var(--text-1); }
.warn-card p { font-size: var(--fs-xs); color: var(--text-3); margin-top: 2px; line-height: var(--lh-loose); }

/* 指标对比 */
.metric-compare { display: flex; align-items: stretch; gap: var(--sp-3); margin-bottom: var(--sp-4); }
.mc-col { flex: 1; min-width: 0; }
.mc-platform { font-size: var(--fs-sm); font-weight: 600; color: var(--text-1); margin-bottom: var(--sp-3); }
.mc-stats { display: flex; gap: var(--sp-4); flex-wrap: wrap; }
.mc-stat { text-align: center; }
.mc-stat b { display: block; font-size: var(--fs-lg); color: var(--text-1); font-variant-numeric: tabular-nums; }
.mc-stat span { font-size: var(--fs-xs); color: var(--text-3); }
.mc-stat b.neg-high { color: #dc2626; }
.mc-stat b.neg-mid { color: #ca8a04; }
.mc-stat b.neg-low { color: #16a34a; }
.mc-vs {
  display: flex; align-items: center; justify-content: center;
  font-size: var(--fs-sm); font-weight: 700; color: var(--text-4);
  padding: 0 var(--sp-2); border-left: 1px dashed var(--border-2); border-right: 1px dashed var(--border-2);
}
.risk-pill { display: inline-block; padding: 2px 10px; border-radius: var(--r-full); font-size: var(--fs-xs); font-weight: 500; }
.risk-low { background: rgba(34,197,94,.12); color: #16a34a; }
.risk-medium { background: rgba(234,179,8,.12); color: #ca8a04; }
.risk-high { background: rgba(239,68,68,.12); color: #dc2626; }
.risk-unknown { background: var(--fill-1); color: var(--text-3); }

/* 情绪环并排 */
.ring-compare { display: grid; grid-template-columns: 1fr 1fr; gap: var(--sp-4); margin-top: var(--sp-2); }
.ring-side { text-align: center; }
.ring-title { font-size: var(--fs-sm); font-weight: 600; color: var(--text-2); margin-bottom: var(--sp-2); }

/* 差异条 */
.delta-bars { margin-top: var(--sp-4); padding-top: var(--sp-3); border-top: 1px solid var(--border-2); }
.delta-row {
  display: grid;
  grid-template-columns: 48px 1fr 40px 52px 40px 1fr;
  align-items: center;
  gap: var(--sp-2);
  margin-bottom: var(--sp-2);
}
.delta-label { font-size: var(--fs-xs); color: var(--text-2); }
.delta-track { height: 8px; background: var(--fill-1); border-radius: var(--r-full); overflow: hidden; display: flex; }
.delta-track:not(.right) { justify-content: flex-end; }
.delta-bili { height: 100%; background: #00AEEC; border-radius: var(--r-full); }
.delta-xhs { height: 100%; background: #FF2442; border-radius: var(--r-full); }
.delta-val { font-size: var(--fs-xs); color: var(--text-3); font-variant-numeric: tabular-nums; text-align: center; }
.delta-gap { font-size: var(--fs-xs); font-weight: 600; text-align: center; font-variant-numeric: tabular-nums; }
.gap-eq { color: var(--text-4); }
.gap-bili { color: #00AEEC; }
.gap-xhs { color: #FF2442; }
.delta-legend { display: flex; justify-content: space-between; font-size: var(--fs-xs); color: var(--text-3); margin-top: var(--sp-2); }
.delta-mid { color: var(--text-4); }

/* 关键词对比 */
.kw-compare { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: var(--sp-3); margin-top: var(--sp-2); }
.kw-group { min-width: 0; }
.kw-group-head { display: flex; align-items: center; gap: 4px; font-size: var(--fs-sm); font-weight: 600; margin-bottom: var(--sp-2); }
.kw-group-head.bili { color: #00AEEC; }
.kw-group-head.xhs { color: #FF2442; }
.kw-group-head.common { color: var(--brand); }
.kw-group-head.common svg { color: var(--brand); }
.kw-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.kw-tag { display: inline-block; padding: 3px 10px; border-radius: var(--r-full); font-size: var(--fs-xs); }
.kw-bili { background: rgba(0,174,236,.1); color: #0284c7; }
.kw-xhs { background: rgba(255,36,66,.1); color: #e11d48; }
.kw-common-tag { background: var(--brand-soft); color: var(--brand); font-weight: 500; }
.kw-empty { font-size: var(--fs-xs); color: var(--text-4); }

/* 内容列表并排 */
.list-compare { display: grid; grid-template-columns: 1fr 1fr; gap: var(--sp-4); }
.list-compare h3 { display: flex; align-items: center; }
.content-list { display: flex; flex-direction: column; gap: var(--sp-2); margin-top: var(--sp-2); }
.content-item { display: flex; gap: var(--sp-2); align-items: flex-start; padding: var(--sp-2); background: var(--fill-1); border-radius: var(--r-md); }
.ci-rank { width: 20px; height: 20px; border-radius: 50%; background: var(--brand-soft); color: var(--brand); font-size: 11px; font-weight: 600; display: flex; align-items: center; justify-content: center; flex-shrink: 0; margin-top: 1px; }
.ci-info { flex: 1; min-width: 0; }
.ci-title { font-size: var(--fs-sm); color: var(--text-1); text-decoration: none; display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ci-title:hover { color: var(--brand); }
.ci-meta { display: flex; gap: var(--sp-2); align-items: center; font-size: var(--fs-xs); color: var(--text-3); margin-top: 2px; }
.risk-tag { padding: 0 6px; border-radius: var(--r-sm); font-size: 10px; }

.card { margin-bottom: var(--sp-4); }
.card h3 { font-size: var(--fs-md); font-weight: 600; margin-bottom: var(--sp-2); }

@media (max-width: 900px) {
  .ring-compare, .kw-compare, .list-compare, .persona-row { grid-template-columns: 1fr; }
  .metric-compare { flex-direction: column; }
  .quality-metrics, .export-summary-grid, .signal-grid, .action-list { grid-template-columns: 1fr 1fr; }
  .explain-grid { grid-template-columns: 1fr; }
  .split-focus { grid-template-columns: 1fr; }
  .mc-vs { border: none; border-top: 1px dashed var(--border-2); border-bottom: 1px dashed var(--border-2); padding: var(--sp-2) 0; }
  .delta-row { grid-template-columns: 40px 1fr 36px 44px 36px 1fr; }
}
@media (max-width: 640px) {
  .quality-head, .export-summary-head, .explain-head { flex-direction: column; }
  .quality-metrics, .export-summary-grid, .signal-grid, .action-list { grid-template-columns: 1fr; }
  .summary-item.wide { grid-column: span 1; }
}
</style>
