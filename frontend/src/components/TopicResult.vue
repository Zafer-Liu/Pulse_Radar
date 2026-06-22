<template>
  <section v-if="data" class="topic-result">
    <div class="section-title">
      <div>
        <h2>话题分析结果</h2>
        <span class="subtitle">{{ data.keyword }}</span>
      </div>
      <span class="badge badge-neutral">{{ data.fetchedAt || '' }}</span>
    </div>

    <!-- 话题概览 -->
    <section class="card topic-overview">
      <div class="overview-head">
        <h3>话题概览</h3>
        <div v-if="data.risk" :class="['risk', `risk-${data.risk}`]">{{ riskText[data.risk] || '未知风险' }}</div>
      </div>
      <p v-if="data.riskReason" class="risk-reason">{{ data.riskReason }}</p>
      <div class="overview-stats">
        <div class="stat"><b>{{ fmt(data.searchTotal) }}</b><span>搜索结果</span></div>
        <div class="stat"><b>{{ data.analyzedCount }}</b><span>{{ isXhs ? '分析笔记' : '分析视频' }}</span></div>
        <div class="stat"><b>{{ fmt(data.totalComments) }}</b><span>聚合评论</span></div>
      </div>
    </section>

    <div class="grid grid-topic">
      <!-- 左主区 -->
      <div class="main-col">
        <!-- 整体情绪分布 -->
        <section class="card anim-card" style="--i:0">
          <h3>整体情绪分布（{{ data.totalComments }} 条评论聚合）</h3>
          <div class="sentiment-grid">
            <SentimentRing :sentiments="data.sentiments" :total="data.totalComments || 0" />
            <div class="sentiment-detail">
              <div v-for="k in sentimentOrder" :key="k" class="sentiment-item">
                <span :class="['legend-dot', segClass(k)]"></span>
                <span class="sentiment-label">{{ sentimentLabels[k] }}</span>
                <span class="sentiment-value">{{ data.sentiments?.[k] || 0 }}%</span>
              </div>
            </div>
          </div>
        </section>

        <!-- 关键词 -->
        <section class="card anim-card" style="--i:1">
          <h3>热门关键词</h3>
          <div v-if="(data.keywords || []).length" class="keyword-tags">
            <span v-for="(kw, i) in data.keywords" :key="i" class="kw-tag">{{ kw }}</span>
          </div>
          <EmptyState v-else title="暂无关键词" description="评论数过少" />
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

        <!-- 热门评论 -->
        <section class="card anim-card" style="--i:3">
          <h3>热门评论（{{ isXhs ? '跨笔记' : '跨视频' }}聚合）</h3>
          <div v-if="(data.comments || []).length" class="comments">
            <div v-for="c in data.comments.slice(0, 20)" :key="c.rpid" class="comment">
              <div class="comment-head">
                <span class="comment-user">{{ c.user || '匿名' }}</span>
                <span :class="['badge', `badge-${sentimentBadge(c.sentiment)}`]">{{ sentimentLabels[c.sentiment] || c.sentiment }}</span>
                <span class="comment-likes">{{ c.likes || 0 }} 赞</span>
              </div>
              <p class="comment-text">{{ c.text }}</p>
              <span class="comment-time">{{ c.time }}</span>
            </div>
          </div>
          <EmptyState v-else title="暂无评论" description="未抓取到评论" />
        </section>
      </div>

      <!-- 右侧栏 -->
      <div class="side-col">
        <!-- 各内容分析 -->
        <section class="card anim-card" style="--i:0">
          <h3>{{ isXhs ? '各笔记分析' : '各视频分析' }}</h3>
          <div class="video-list">
            <div v-for="(v, i) in (data.videos || [])" :key="v.bvid || v.noteId || i" class="video-item">
              <div class="vi-rank">{{ i + 1 }}</div>
              <img class="vi-cover" :src="proxyImage(v.pic || '')" alt="" @error="onCoverError" />
              <div class="vi-info">
                <a :href="v.arcurl || v.noteUrl || '#'" target="_blank" class="vi-title">{{ v.title || '未知' }}</a>
                <div class="vi-meta">
                  <span>{{ v.author || '' }}</span>
                  <span v-if="!isXhs">播放 {{ fmt(v.views) }}</span>
                  <span v-else>评论 {{ fmt(v.commentCount) }}</span>
                </div>
                <div v-if="v.error" class="vi-error">分析失败：{{ v.error }}</div>
                <template v-else>
                  <div class="vi-sentiments">
                    <span v-for="k in sentimentOrder" :key="k" class="vi-sent" :style="{ flex: (v.sentimentCounts?.[k] || 0) || 0.1 }">
                      {{ sentimentLabels[k] }} {{ v.sentiments?.[k] || 0 }}%
                    </span>
                  </div>
                  <div v-if="v.risk" :class="['risk-sm', `risk-${v.risk}`]">{{ riskText[v.risk] }}</div>
                  <div v-if="(v.keywords || []).length" class="vi-kws">
                    <span v-for="kw in v.keywords.slice(0, 4)" :key="kw" class="kw-tag-sm">{{ kw }}</span>
                  </div>
                </template>
              </div>
            </div>
          </div>
        </section>

        <!-- 话题报告 -->
        <section v-if="data.report" class="card anim-card" style="--i:1">
          <h3>话题报告</h3>
          <div class="report-text" v-html="renderMd(data.report)"></div>
        </section>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import SentimentRing from './charts/SentimentRing.vue'
import EmptyState from './ui/EmptyState.vue'

const props = defineProps({ data: Object })

const sentimentOrder = ['pos', 'neu', 'neg', 'con', 'risk']
const sentimentLabels = { pos: '正面', neu: '中性', neg: '负面', con: '争议', risk: '风险' }
const riskText = { low: '低风险', medium: '中风险', high: '高风险', unknown: '未知' }

// 判断是否为小红书话题分析结果
const isXhs = computed(() => props.data?.type === 'xhs_topic')

function segClass(k) {
  return { pos: 'seg-pos', neu: 'seg-neu', neg: 'seg-neg', con: 'seg-con', risk: 'seg-risk' }[k] || ''
}
function sentimentBadge(s) {
  return { pos: 'success', neu: 'neutral', neg: 'danger', con: 'warn', risk: 'danger' }[s] || 'neutral'
}
function fmt(n) {
  if (n == null) return '0'
  if (n >= 10000) return (n / 10000).toFixed(1) + '万'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return String(n)
}
function proxyImage(url) {
  if (!url) return ''
  if (url.startsWith('//')) url = 'https:' + url
  return '/api/image?url=' + encodeURIComponent(url)
}
function onCoverError(e) { e.target.src = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="160" height="90"><rect fill="%23f0f0f0" width="160" height="90"/><text x="50%" y="50%" text-anchor="middle" fill="%23999" font-size="12">无封面</text></svg>' }
function renderMd(text) {
  return text
    .replace(/^## (.+)$/gm, '<h3>$1</h3>')
    .replace(/^### (.+)$/gm, '<h4>$1</h4>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>')
    .replace(/\n/g, '<br>')
}
</script>

<style scoped>
.topic-result { margin-bottom: var(--sp-5); }

.topic-overview { margin-bottom: var(--sp-4); }
.overview-head {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  margin-bottom: var(--sp-3);
}
.overview-head h3 { font-size: var(--fs-md); font-weight: 600; }
.overview-stats {
  display: flex;
  gap: var(--sp-6);
  flex-wrap: wrap;
}
.overview-stats .stat { text-align: center; }
.overview-stats .stat b { display: block; font-size: var(--fs-xl); color: var(--text-1); }
.overview-stats .stat span { font-size: var(--fs-xs); color: var(--text-3); }

.grid-topic {
  display: grid;
  grid-template-columns: 1fr 380px;
  gap: var(--sp-4);
}
.main-col { min-width: 0; overflow: hidden; }
.side-col { min-width: 0; overflow: hidden; }

/* 风险标签 */
.risk {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 12px;
  border-radius: var(--r-full);
  font-size: var(--fs-sm);
  font-weight: 500;
}
.risk-low { background: rgba(34,197,94,.1); color: #16a34a; }
.risk-medium { background: rgba(234,179,8,.1); color: #ca8a04; }
.risk-high { background: rgba(239,68,68,.1); color: #dc2626; }
.risk-reason { font-size: var(--fs-sm); color: var(--text-3); margin-bottom: var(--sp-3); }
.risk-sm { font-size: var(--fs-xs); padding: 2px 8px; }

/* 情绪分布 */
.sentiment-grid { display: flex; gap: var(--sp-5); align-items: center; }
.sentiment-detail { flex: 1; }
.sentiment-item { display: flex; align-items: center; gap: var(--sp-2); padding: 6px 0; }
.legend-dot { width: 10px; height: 10px; border-radius: 50%; }
.seg-pos { background: #22c55e; }
.seg-neu { background: #94a3b8; }
.seg-neg { background: #ef4444; }
.seg-con { background: #f59e0b; }
.seg-risk { background: #dc2626; }
.sentiment-label { font-size: var(--fs-sm); color: var(--text-2); flex: 1; }
.sentiment-value { font-size: var(--fs-sm); font-weight: 600; color: var(--text-1); font-variant-numeric: tabular-nums; }

/* 关键词 */
.keyword-tags { display: flex; flex-wrap: wrap; gap: var(--sp-2); }
.kw-tag {
  display: inline-block;
  padding: 4px 12px;
  background: var(--fill-1);
  border-radius: var(--r-full);
  font-size: var(--fs-sm);
  color: var(--text-2);
}
.kw-tag-sm {
  display: inline-block;
  padding: 2px 8px;
  background: var(--fill-1);
  border-radius: var(--r-full);
  font-size: var(--fs-xs);
  color: var(--text-3);
}

/* 聚类 */
.clusters { display: grid; grid-template-columns: 1fr 1fr; gap: var(--sp-3); }
.cluster {
  padding: var(--sp-3);
  background: var(--fill-1);
  border-radius: var(--r-lg);
  min-width: 0;
  overflow: hidden;
}
.cluster-head { display: flex; align-items: center; gap: var(--sp-2); margin-bottom: var(--sp-2); }
.cluster h4 { font-size: var(--fs-sm); font-weight: 600; }
.cluster small { font-size: var(--fs-xs); color: var(--text-3); }
.cluster p {
  font-size: var(--fs-xs);
  color: var(--text-2);
  margin-top: var(--sp-1);
  line-height: var(--lh-loose);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-all;
}

/* 评论 */
.comments { display: flex; flex-direction: column; gap: var(--sp-3); }
.comment { padding: var(--sp-3); background: var(--fill-1); border-radius: var(--r-lg); }
.comment-head { display: flex; align-items: center; gap: var(--sp-2); margin-bottom: var(--sp-2); }
.comment-user { font-size: var(--fs-sm); font-weight: 500; color: var(--text-1); }
.comment-likes { font-size: var(--fs-xs); color: var(--text-4); margin-left: auto; }
.comment-text { font-size: var(--fs-sm); color: var(--text-2); line-height: var(--lh-loose); word-break: break-all; overflow-wrap: break-word; }
.comment-time { font-size: var(--fs-xs); color: var(--text-4); margin-top: var(--sp-1); display: block; }

/* 视频列表 */
.video-list { display: flex; flex-direction: column; gap: var(--sp-3); }
.video-item {
  display: flex;
  gap: var(--sp-3);
  padding: var(--sp-3);
  background: var(--fill-1);
  border-radius: var(--r-lg);
}
.vi-rank {
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
  flex-shrink: 0;
  margin-top: 2px;
}
.vi-cover {
  width: 80px;
  height: 50px;
  object-fit: cover;
  border-radius: var(--r-md);
  flex-shrink: 0;
}
.vi-info { flex: 1; min-width: 0; }
.vi-title {
  font-size: var(--fs-sm);
  font-weight: 500;
  color: var(--text-1);
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-decoration: none;
}
.vi-title:hover { color: var(--brand); }
.vi-meta {
  display: flex;
  gap: var(--sp-2);
  font-size: var(--fs-xs);
  color: var(--text-3);
  margin-top: 2px;
}
.vi-sentiments {
  display: flex;
  gap: 2px;
  margin-top: 4px;
  border-radius: var(--r-sm);
  overflow: hidden;
}
.vi-sent {
  padding: 1px 4px;
  font-size: 10px;
  background: var(--fill-2);
  color: var(--text-3);
  text-align: center;
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
}
.vi-error { font-size: var(--fs-xs); color: #dc2626; margin-top: 4px; }
.vi-kws { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }

/* 报告 */
.report-text {
  font-size: var(--fs-sm);
  color: var(--text-2);
  line-height: var(--lh-loose);
}
.report-text :deep(h3) { font-size: var(--fs-md); font-weight: 600; color: var(--text-1); margin: var(--sp-3) 0 var(--sp-2); }
.report-text :deep(h4) { font-size: var(--fs-sm); font-weight: 600; color: var(--text-1); margin: var(--sp-2) 0 var(--sp-1); }
.report-text :deep(ul) { padding-left: var(--sp-4); margin: var(--sp-1) 0; }
.report-text :deep(li) { list-style: disc; margin-bottom: 2px; }

/* 动画 */
.anim-card {
  animation: fadeUp 0.5s ease both;
  animation-delay: calc(var(--i) * 0.08s);
}
@keyframes fadeUp {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

@media (max-width: 900px) {
  .grid-topic { grid-template-columns: 1fr; }
  .clusters { grid-template-columns: 1fr; }
}
</style>
