<template>
  <section class="hero card">
    <div class="hero-head">
      <h1>声浪雷达 <span class="hero-tag">B站舆情分析</span></h1>
      <p class="hero-desc">粘贴 B站视频链接一键分析，或输入话题关键词全网搜索聚合分析。</p>
    </div>

    <!-- 平台选择 -->
    <div class="platform-tabs">
      <button :class="{ active: platform === 'bilibili' }" @click="platform = 'bilibili'">B站</button>
      <button :class="{ active: platform === 'xiaohongshu' }" @click="platform = 'xiaohongshu'">小红书</button>
    </div>

    <!-- 模式切换 -->
    <div class="mode-tabs">
      <button
        type="button"
        :class="['mode-tab', { active: mode === 'video' }]"
        @click="mode = 'video'"
      >
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14"><rect x="2" y="2" width="12" height="12" rx="2"/><path d="M5 6h6M5 8.5h4" stroke-linecap="round"/></svg>
        视频分析
      </button>
      <button
        type="button"
        :class="['mode-tab', { active: mode === 'topic' }]"
        @click="mode = 'topic'"
      >
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14"><circle cx="8" cy="8" r="5"/><path d="M8 5v3l2 1.5" stroke-linecap="round" stroke-linejoin="round"/><path d="M2 8h1M13 8h1M8 2v1M8 13v1" stroke-linecap="round"/></svg>
        话题雷达
      </button>
    </div>

    <!-- 视频模式 -->
    <form v-if="mode === 'video'" class="hero-form" @submit.prevent="doAnalyze">
      <input
        v-model="url"
        class="input hero-url"
        :placeholder="platform === 'bilibili' ? '粘贴 B站视频链接，例如 https://www.bilibili.com/video/BV...' : '粘贴小红书笔记链接，例如 https://www.xiaohongshu.com/explore/...'"
        :disabled="loading || adding"
      />
      <select v-model.number="pages" class="select hero-pages" :disabled="loading || adding">
        <option :value="3">3 页</option>
        <option :value="5">5 页</option>
        <option :value="10">10 页</option>
        <option :value="20">20 页</option>
      </select>
      <button class="btn btn-lg hero-submit" :disabled="loading" type="submit">
        <span v-if="loading" class="spinner"></span>
        {{ loading ? '分析中' : '立即分析' }}
      </button>
      <button class="btn btn-lg btn-secondary hero-monitor" :disabled="adding" type="button" @click="doAddMonitor">
        <span v-if="adding" class="spinner"></span>
        {{ adding ? '添加中' : '加入监测' }}
      </button>
    </form>

    <!-- 话题模式 -->
    <form v-else class="hero-form hero-form-topic" @submit.prevent="doTopicAnalyze">
      <input
        v-model="topicKeyword"
        class="input hero-url"
        placeholder="输入话题关键词，例如：AI大模型、新能源、高考..."
        :disabled="topicLoading"
      />
      <select v-model.number="topicTopN" class="select hero-pages" :disabled="topicLoading">
        <option :value="3">Top 3</option>
        <option :value="5">Top 5</option>
        <option :value="8">Top 8</option>
        <option :value="10">Top 10</option>
      </select>
      <select v-model.number="topicPages" class="select hero-pages" :disabled="topicLoading">
        <option :value="2">2 页/视频</option>
        <option :value="3">3 页/视频</option>
        <option :value="5">5 页/视频</option>
      </select>
      <button class="btn btn-lg hero-submit" :disabled="topicLoading || !topicKeyword.trim()" type="submit">
        <span v-if="topicLoading" class="spinner"></span>
        {{ topicLoading ? '分析中' : '话题分析' }}
      </button>
    </form>

    <!-- 高级选项：监测周期（仅视频模式） -->
    <div v-if="mode === 'video'" class="hero-advanced">
      <button type="button" class="adv-toggle" @click="showAdvanced = !showAdvanced">
        <svg class="arrow" :class="{ up: showAdvanced }" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" width="12" height="12"><path d="M4 6l4 4 4-4" stroke-linecap="round" stroke-linejoin="round"/></svg>
        监测周期设置<span v-if="showAdvanced" class="adv-hint">·加入监测时生效</span>
      </button>
      <transition name="expand">
        <div v-show="showAdvanced" class="adv-body">
          <label class="adv-field">
            <span class="adv-label">周期</span>
            <input v-model.number="intervalValue" type="number" min="1" class="input adv-input" :disabled="adding" />
          </label>
          <label class="adv-field">
            <span class="adv-label">单位</span>
            <select v-model="intervalUnit" class="select adv-input" :disabled="adding">
              <option value="小时">小时</option>
              <option value="天">天</option>
            </select>
          </label>
          <span class="adv-tip">添加监测后自动按此周期抓取评论并对比舆情变化</span>
        </div>
      </transition>
    </div>

    <!-- 雷达扫描（分析中旋转） -->
    <div class="hero-radar" :class="{ scanning: loading || topicLoading }">
      <svg viewBox="0 0 80 80" width="56" height="56">
        <circle cx="40" cy="40" r="36" fill="none" stroke="currentColor" stroke-width="1.2" opacity="0.2"/>
        <circle cx="40" cy="40" r="24" fill="none" stroke="currentColor" stroke-width="1" opacity="0.15"/>
        <circle cx="40" cy="40" r="12" fill="none" stroke="currentColor" stroke-width="0.8" opacity="0.12"/>
        <line x1="4" y1="40" x2="76" y2="40" stroke="currentColor" stroke-width="0.5" opacity="0.12"/>
        <line x1="40" y1="4" x2="40" y2="76" stroke="currentColor" stroke-width="0.5" opacity="0.12"/>
        <line x1="12.6" y1="12.6" x2="67.4" y2="67.4" stroke="currentColor" stroke-width="0.45" opacity="0.08"/>
        <line x1="12.6" y1="67.4" x2="67.4" y2="12.6" stroke="currentColor" stroke-width="0.45" opacity="0.08"/>
        <g class="radar-sweep">
          <defs>
            <radialGradient id="sweep-grad" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stop-color="#002FA7" stop-opacity="0.35"/>
              <stop offset="70%" stop-color="#002FA7" stop-opacity="0.08"/>
              <stop offset="100%" stop-color="#002FA7" stop-opacity="0"/>
            </radialGradient>
          </defs>
          <path d="M40,40 L40,4 A36,36 0 0,1 71.3,22 Z" fill="url(#sweep-grad)"/>
        </g>
        <circle cx="40" cy="40" r="2.5" fill="currentColor" :opacity="loading || topicLoading ? 1 : 0.3"/>
      </svg>
      <span class="radar-text">{{ (loading || topicLoading) ? '扫描中…' : '待命中' }}</span>
    </div>
  </section>
</template>

<script setup>
import { ref, watch } from 'vue'
import { analyzeVideo, analyzeTopic, analyzeXhsNote, analyzeXhsTopic } from '../api'
import { toast } from '../composables/useToast'

const emit = defineEmits(['result', 'topicResult', 'add'])

const platform = ref('bilibili')  // 'bilibili' | 'xiaohongshu'
const mode = ref('video')

// 视频模式
const BILI_DEFAULT = 'https://www.bilibili.com/video/BV1aGLR6mEeK/'
const XHS_DEFAULT = 'http://xhslink.com/o/95N0n1vuoQd'
const url = ref(BILI_DEFAULT)

// 切换平台时更新默认 URL
watch(platform, (val) => {
  url.value = val === 'bilibili' ? BILI_DEFAULT : XHS_DEFAULT
})
const pages = ref(5)
const intervalValue = ref(6)
const intervalUnit = ref('小时')
const loading = ref(false)
const adding = ref(false)
const showAdvanced = ref(false)

// 话题模式
const topicKeyword = ref('')
const topicTopN = ref(5)
const topicPages = ref(3)
const topicLoading = ref(false)

async function doAnalyze() {
  if (!url.value.trim()) {
    toast.warning(platform.value === 'bilibili' ? '请先输入视频链接' : '请先输入笔记链接')
    return
  }
  loading.value = true
  toast.info('开始分析，正在抓取评论…')
  try {
    let payload
    if (platform.value === 'bilibili') {
      payload = await analyzeVideo(url.value.trim(), pages.value)
    } else {
      payload = await analyzeXhsNote(url.value.trim(), pages.value)
    }
    emit('result', payload.data)
    toast.success(`分析完成：实际抓取 ${payload.data.commentCount} 条公开评论`)
  } catch (err) {
    toast.error(err.message || String(err))
  } finally {
    loading.value = false
  }
}

async function doTopicAnalyze() {
  if (!topicKeyword.value.trim()) {
    toast.warning('请输入话题关键词')
    return
  }
  topicLoading.value = true
  toast.info('开始话题分析，搜索相关内容并抓取评论，可能需要较长时间...')
  try {
    let payload
    if (platform.value === 'bilibili') {
      payload = await analyzeTopic(topicKeyword.value.trim(), topicTopN.value, topicPages.value)
    } else {
      payload = await analyzeXhsTopic(topicKeyword.value.trim(), topicTopN.value, topicPages.value)
    }
    emit('topicResult', payload.data)
    const d = payload.data
    toast.success(`话题分析完成：${d.analyzedCount} 个内容，共 ${d.totalComments} 条评论`)
  } catch (err) {
    toast.error(err.message || String(err))
  } finally {
    topicLoading.value = false
  }
}

async function doAddMonitor() {
  if (!url.value.trim()) {
    toast.warning('请先输入视频链接')
    return
  }
  adding.value = true
  try {
    emit('add', {
      url: url.value.trim(),
      pages: pages.value,
      intervalValue: intervalValue.value,
      intervalUnit: intervalUnit.value,
      enabled: true,
    })
    url.value = ''
  } finally {
    adding.value = false
  }
}
</script>

<style scoped>
.hero { margin-bottom: var(--sp-5); background: var(--bg-card); }
.hero-head { margin-bottom: var(--sp-4); }
.hero-head h1 {
  font-size: var(--fs-2xl);
  font-weight: 600;
  line-height: var(--lh-tight);
  letter-spacing: -.02em;
  color: var(--text-1);
  margin-bottom: var(--sp-2);
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  flex-wrap: wrap;
}
.hero-tag {
  font-size: var(--fs-xs);
  font-weight: 500;
  color: var(--brand);
  background: var(--brand-soft);
  padding: 3px 10px;
  border-radius: var(--r-full);
  letter-spacing: 0;
}
.hero-desc {
  color: var(--text-2);
  font-size: var(--fs-sm);
  line-height: var(--lh-loose);
  max-width: 720px;
}

/* 平台选择 */
.platform-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.platform-tabs button {
  padding: 6px 16px;
  border: 1px solid var(--border);
  border-radius: 20px;
  background: transparent;
  color: var(--text2);
  cursor: pointer;
  font-size: var(--fs-sm);
  transition: all 0.2s;
}
.platform-tabs button.active {
  background: var(--brand);
  color: #fff;
  border-color: var(--brand);
}

/* 模式切换 */
.mode-tabs {
  display: inline-flex;
  gap: 2px;
  background: var(--fill-1);
  border-radius: var(--r-lg);
  padding: 3px;
  margin-bottom: var(--sp-4);
}
.mode-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 16px;
  border: none;
  border-radius: var(--r-md);
  font-size: var(--fs-sm);
  font-weight: 500;
  color: var(--text-3);
  background: transparent;
  cursor: pointer;
  transition: all var(--t-fast);
}
.mode-tab:hover { color: var(--text-1); }
.mode-tab.active {
  background: var(--bg-card);
  color: var(--brand);
  box-shadow: var(--sh-xs);
}

.hero-form {
  display: grid;
  grid-template-columns: 1fr 100px 130px 130px;
  gap: var(--sp-2);
  align-items: stretch;
}
.hero-form-topic {
  grid-template-columns: 1fr 100px 130px 130px;
}
.hero-url { height: 40px; font-size: var(--fs-base); }
.hero-pages { height: 40px; }
.hero-submit { height: 40px; font-size: var(--fs-base); font-weight: 500; }
.hero-monitor { height: 40px; font-size: var(--fs-base); font-weight: 500; }

.hero-advanced { margin-top: var(--sp-3); }
.adv-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: transparent;
  border: 0;
  padding: 4px 0;
  color: var(--text-3);
  font-size: var(--fs-sm);
  cursor: pointer;
  transition: color var(--t-fast);
}
.adv-toggle:hover { color: var(--text-1); }
.adv-toggle .arrow { transition: transform var(--t-fast); }
.adv-toggle .arrow.up { transform: rotate(180deg); }
.adv-hint { color: var(--text-4); margin-left: 4px; }

.adv-body {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  flex-wrap: wrap;
  margin-top: var(--sp-2);
  padding: var(--sp-3);
  background: var(--fill-1);
  border-radius: var(--r-md);
}
.adv-field { display: inline-flex; align-items: center; gap: var(--sp-2); }
.adv-label { font-size: var(--fs-xs); color: var(--text-3); }
.adv-input { height: 28px; width: 80px; font-size: var(--fs-sm); }
.adv-tip { font-size: var(--fs-xs); color: var(--text-4); flex: 1; min-width: 200px; }

.expand-enter-active, .expand-leave-active { transition: all var(--t-base); overflow: hidden; }
.expand-enter-from, .expand-leave-to { opacity: 0; max-height: 0; margin-top: 0; }
.expand-enter-to, .expand-leave-from { opacity: 1; max-height: 120px; }

/* 雷达扫描 */
.hero-radar {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  margin-top: var(--sp-4);
  padding-top: var(--sp-3);
  border-top: 1px solid var(--border-2);
  color: var(--text-4);
}
.hero-radar:not(.scanning) svg { animation: radar-pulse 4s ease-in-out infinite; }
@keyframes radar-pulse {
  0%, 100% { opacity: 0.6; }
  50% { opacity: 1; }
}
.hero-radar.scanning {
  color: var(--brand);
}
.hero-radar.scanning .radar-sweep {
  transform-origin: 40px 40px;
  animation: radar-spin 2.4s linear infinite;
}
@keyframes radar-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
.radar-text {
  font-size: var(--fs-xs);
  color: inherit;
  letter-spacing: 0.04em;
}

@media (max-width: 768px) {
  .hero-form, .hero-form-topic { grid-template-columns: 1fr 1fr; }
  .hero-form > :first-child, .hero-form-topic > :first-child { grid-column: 1 / -1; }
  .hero-head h1 { font-size: var(--fs-xl); }
}
</style>
