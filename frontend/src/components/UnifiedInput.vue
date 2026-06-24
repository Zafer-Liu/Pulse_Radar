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
        {{ topicLoading ? '分析中' : (compareMode ? '双平台对比' : '话题分析') }}
      </button>
    </form>

    <!-- 双平台对比开关（仅话题模式） -->
    <div v-if="mode === 'topic'" class="compare-toggle-row">
      <label class="compare-switch" :class="{ on: compareMode }">
        <input type="checkbox" v-model="compareMode" :disabled="topicLoading" />
        <span class="switch-track"><span class="switch-dot"></span></span>
        <span class="switch-label">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14"><rect x="1.5" y="3" width="5.5" height="10" rx="1"/><rect x="9" y="3" width="5.5" height="10" rx="1"/><path d="M8 1.5v13" stroke-dasharray="1.5 1.5"/></svg>
          双平台对比
        </span>
      </label>
      <span class="compare-hint">{{ compareMode ? '同时分析 B站 + 小红书，并排对比同一话题的舆情差异（耗时约为单平台 2 倍）' : '开启后无视上方平台选择，同时拉取两个平台对比' }}</span>
    </div>

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

    <div class="hero-readiness">
      <div class="readiness-head">
        <strong>{{ readinessTitle }}</strong>
        <span>{{ readinessSummary }}</span>
      </div>
      <div class="readiness-list">
        <div v-for="item in readinessItems" :key="item.key" class="readiness-item" :class="item.tone">
          <div class="readiness-top">
            <span class="readiness-name">{{ item.name }}</span>
            <span class="readiness-state">{{ item.status }}</span>
          </div>
          <p>{{ item.detail }}</p>
        </div>
      </div>
    </div>

    <!-- 雷达扫描（分析中旋转） -->
    <div class="hero-radar" :class="{ scanning: isWorking }">
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
        <circle cx="40" cy="40" r="2.5" fill="currentColor" :opacity="isWorking ? 1 : 0.3"/>
      </svg>
      <div class="radar-status">
        <span class="radar-text">{{ isWorking ? (currentStage?.label || '处理中…') : '待命中' }}</span>
        <span class="radar-subtext">{{ isWorking ? (currentStage?.description || '正在执行分析流程') : '开始分析后会显示阶段进度' }}</span>
      </div>
    </div>

    <div v-if="isWorking && currentStages.length" class="hero-flow">
      <div class="flow-head">
        <strong>分析流程</strong>
        <span>{{ currentStageIndex + 1 }} / {{ currentStages.length }}</span>
      </div>
      <div class="flow-steps">
        <div v-for="(stage, idx) in currentStages" :key="stage.key" class="flow-step" :class="{ done: idx < currentStageIndex, active: idx === currentStageIndex }">
          <span class="flow-index">{{ idx + 1 }}</span>
          <div class="flow-copy">
            <b>{{ stage.label }}</b>
            <span>{{ stage.description }}</span>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted, computed } from 'vue'
import { analyzeVideo, analyzeTopic, analyzeXhsNote, analyzeXhsTopic, compareTopic, apiGet, getLoginStatus } from '../api'
import { toast } from '../composables/useToast'

const emit = defineEmits(['result', 'topicResult', 'compareResult', 'add'])

// 登录状态（用于前置提示）
const biliLoggedIn = ref(false)
const xhsConfigured = ref(false)
const xhsPlaywrightMissing = ref(false)

onMounted(async () => {
  try {
    const res = await getLoginStatus()
    biliLoggedIn.value = res.loggedIn
  } catch { /* 静默 */ }
  try {
    const res = await apiGet('/api/xhs/login/status')
    xhsConfigured.value = !!res.data?.configured
    xhsPlaywrightMissing.value = !!res.data?.playwrightMissing
  } catch { /* 静默 */ }
})

const platform = ref('bilibili')  // 'bilibili' | 'xiaohongshu'
const mode = ref('video')

// 视频模式
const BILI_DEFAULT = 'https://www.bilibili.com/video/BV1aGLR6mEeK/'
const XHS_DEFAULT = 'http://xhslink.com/o/5qUQb0IKAoC'
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
const compareMode = ref(false)  // 双平台对比开关

const FLOW_PRESETS = {
  video: [
    { key: 'resolve', label: '解析链接', description: '识别平台、解析内容链接与基础信息' },
    { key: 'fetch', label: '抓取评论', description: '拉取公开评论并建立首批样本' },
    { key: 'paging', label: '翻页补全', description: '继续翻页补样，尽量提升评论覆盖率' },
    { key: 'sentiment', label: '情感分析', description: '计算正负向、争议与风险分布' },
    { key: 'cluster', label: '生成聚类', description: '提取关键词并整理观点主题' },
    { key: 'report', label: '生成报告', description: '输出诊断、可信度与 AI / 模板报告' },
  ],
  topic: [
    { key: 'search', label: '搜索内容', description: '检索相关视频或笔记并建立样本池' },
    { key: 'collect', label: '逐条抓取', description: '按搜索结果逐条拉取评论' },
    { key: 'paging', label: '翻页补全', description: '为每条内容继续翻页补样' },
    { key: 'sentiment', label: '情感分析', description: '统一计算聚合情绪分布' },
    { key: 'cluster', label: '生成聚类', description: '汇总关键词、观点与风险信号' },
    { key: 'report', label: '输出报告', description: '生成话题级诊断与总结' },
  ],
  compare: [
    { key: 'search', label: '双端搜索', description: '同时检索 B站与小红书相关内容' },
    { key: 'collect', label: '双端抓取', description: '分别抓取两边评论样本' },
    { key: 'paging', label: '翻页补全', description: '继续翻页，尽量拉齐双平台覆盖率' },
    { key: 'sentiment', label: '情感分析', description: '分别计算两边情绪分布与风险' },
    { key: 'cluster', label: '差异聚类', description: '生成共同热议点与平台分化点' },
    { key: 'report', label: '生成对比', description: '输出可信度、诊断与跨平台洞察' },
  ],
}
const activeFlowKey = ref('')
const currentStageIndex = ref(0)
let flowTimer = null
let flowResetTimer = null
const isWorking = computed(() => loading.value || topicLoading.value)
const currentStages = computed(() => FLOW_PRESETS[activeFlowKey.value] || [])
const currentStage = computed(() => currentStages.value[currentStageIndex.value] || null)
const readinessItems = computed(() => {
  const biliItem = {
    key: 'bilibili',
    name: 'B站登录态',
    tone: biliLoggedIn.value ? 'ready' : 'warn',
    status: biliLoggedIn.value ? '已登录' : '未登录',
    detail: biliLoggedIn.value ? '可抓取更多公开评论，样本完整度更高。' : '未登录时通常只能拿到约 3 条精选评论。',
  }
  const xhsItem = {
    key: 'xiaohongshu',
    name: '小红书链路',
    tone: xhsConfigured.value && !xhsPlaywrightMissing.value ? 'ready' : 'warn',
    status: xhsConfigured.value ? (xhsPlaywrightMissing.value ? '部分就绪' : '已就绪') : '未登录',
    detail: xhsConfigured.value
      ? (xhsPlaywrightMissing.value ? 'Cookie 已配置，但仍需安装 Playwright 才能稳定翻页抓取。' : 'Cookie 与签名依赖已就绪，可稳定获取更多评论。')
      : '未配置 Cookie 时评论可能为 0 条，建议先扫码登录。',
  }
  if (mode.value === 'topic' && compareMode.value) return [biliItem, xhsItem]
  return [platform.value === 'bilibili' ? biliItem : xhsItem]
})
const readinessTitle = computed(() => {
  if (mode.value === 'video') return '分析前检查'
  return compareMode.value ? '双平台就绪状态' : '话题分析前检查'
})
const readinessSummary = computed(() => {
  if (mode.value === 'topic' && compareMode.value) {
    const readyCount = readinessItems.value.filter((item) => item.tone === 'ready').length
    return readyCount === 2
      ? '双平台链路已就绪，可以直接做横向对比。'
      : '至少一侧链路受限，对比结果可能偏向成功平台。'
  }
  const current = readinessItems.value[0]
  return current?.tone === 'ready'
    ? '当前链路状态良好，结果更适合直接研判。'
    : '当前链路存在限制，建议先补登录后再分析。'
})

function clearFlowTimer() {
  if (flowTimer) {
    clearInterval(flowTimer)
    flowTimer = null
  }
}
function clearFlowReset() {
  if (flowResetTimer) {
    clearTimeout(flowResetTimer)
    flowResetTimer = null
  }
}
function startFlow(flowKey) {
  clearFlowReset()
  activeFlowKey.value = flowKey
  currentStageIndex.value = 0
  clearFlowTimer()
  flowTimer = setInterval(() => {
    const maxIndex = Math.max(0, currentStages.value.length - 1)
    if (currentStageIndex.value < maxIndex) currentStageIndex.value += 1
  }, 2200)
}
function stopFlow() {
  clearFlowTimer()
  clearFlowReset()
  const maxIndex = Math.max(0, currentStages.value.length - 1)
  currentStageIndex.value = maxIndex
  flowResetTimer = setTimeout(() => {
    activeFlowKey.value = ''
    currentStageIndex.value = 0
    flowResetTimer = null
  }, 400)
}

onUnmounted(() => {
  clearFlowTimer()
  clearFlowReset()
})

async function doAnalyze() {
  if (!url.value.trim()) {
    toast.warning(platform.value === 'bilibili' ? '请先输入视频链接' : '请先输入笔记链接')
    return
  }
  // 未登录前置提示（非阻断，仍然继续分析）
  if (platform.value === 'bilibili' && !biliLoggedIn.value) {
    toast.info('提示：未登录 B站，只能抓到约 3 条精选评论。点击右上角「登录 B站」后可获取全量评论。', 6000)
  }
  if (platform.value === 'xiaohongshu' && !xhsConfigured.value) {
    toast.warning('提示：小红书 Cookie 未配置，API 翻页将受限（评论可能为 0 条）。建议先点击右上角「登录 小红书」。', 7000)
  }
  if (platform.value === 'xiaohongshu' && xhsPlaywrightMissing.value) {
    toast.warning('提示：小红书签名依赖尚未安装，建议先执行 playwright install chromium，否则评论覆盖率会明显偏低。', 7000)
  }
  loading.value = true
  startFlow('video')
  toast.info('开始分析，正在抓取评论…')
  try {
    let payload
    if (platform.value === 'bilibili') {
      payload = await analyzeVideo(url.value.trim(), pages.value)
    } else {
      payload = await analyzeXhsNote(url.value.trim(), pages.value)
    }
    emit('result', payload.data)
    const publicCount = payload.data.publicCommentCount ?? payload.data.replyCountFromVideo ?? payload.data.replyCountFromNote
    const coverage = payload.data.coverageRate == null ? '覆盖率未知' : `覆盖率 ${payload.data.coverageRate}%`
    toast.success(`分析完成：抓取 ${payload.data.commentCount} 条${publicCount ? ` / 公开 ${publicCount} 条` : ''}，${coverage}`)
  } catch (err) {
    toast.error(err.message || String(err))
  } finally {
    loading.value = false
    stopFlow()
  }
}

async function doTopicAnalyze() {
  if (!topicKeyword.value.trim()) {
    toast.warning('请输入话题关键词')
    return
  }
  topicLoading.value = true
  startFlow(compareMode.value ? 'compare' : 'topic')

  if (!compareMode.value) {
    if (platform.value === 'bilibili' && !biliLoggedIn.value) {
      toast.info('提示：当前未登录 B站，话题聚合会明显偏向少量精选评论。建议先登录再分析。', 6000)
    }
    if (platform.value === 'xiaohongshu' && !xhsConfigured.value) {
      toast.warning('提示：当前未登录小红书，话题聚合可能拿不到评论或覆盖率极低。建议先登录再分析。', 7000)
    }
    if (platform.value === 'xiaohongshu' && xhsPlaywrightMissing.value) {
      toast.warning('提示：小红书签名依赖尚未安装，话题聚合的评论覆盖率会明显受限。', 7000)
    }
  }

  // 双平台对比模式
  if (compareMode.value) {
    if (!biliLoggedIn.value || !xhsConfigured.value || xhsPlaywrightMissing.value) {
      toast.warning('提示：双平台里至少一侧链路未完全就绪，最终对比可信度可能下降。', 7000)
    }
    toast.info('开始双平台对比，同时分析 B站与小红书，耗时较长请耐心等待...')
    try {
      const payload = await compareTopic(topicKeyword.value.trim(), topicTopN.value, topicPages.value)
      emit('compareResult', payload.data)
      const d = payload.data
      const okPlatforms = ['bilibili', 'xiaohongshu'].filter(p => d[p])
      if (okPlatforms.length === 2) {
        const biliComments = d.bilibili?.totalComments ?? 0
        const xhsComments = d.xiaohongshu?.totalComments ?? 0
        toast.success(`双平台对比完成：B站 ${biliComments} 条，小红书 ${xhsComments} 条评论样本`) 
      } else {
        const okName = d.bilibili ? 'B站' : '小红书'
        toast.warning(`仅 ${okName} 分析成功，另一平台失败（可能未登录或限流），已展示单平台结果`)
      }
    } catch (err) {
      toast.error(err.message || String(err))
    } finally {
      topicLoading.value = false
      stopFlow()
    }
    return
  }

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
    const coverage = d.coverageRate == null ? '覆盖率未知' : `覆盖率 ${d.coverageRate}%`
    toast.success(`话题分析完成：成功 ${d.successCount ?? d.analyzedCount}/${d.analyzedCount} 个内容，聚合 ${d.totalComments} 条评论，${coverage}`)
  } catch (err) {
    toast.error(err.message || String(err))
  } finally {
    topicLoading.value = false
    stopFlow()
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

/* 双平台对比开关 */
.compare-toggle-row {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  margin-top: var(--sp-3);
  flex-wrap: wrap;
}
.compare-switch {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
  cursor: pointer;
  user-select: none;
}
.compare-switch input { display: none; }
.switch-track {
  width: 38px;
  height: 22px;
  border-radius: var(--r-full);
  background: var(--fill-2);
  position: relative;
  transition: background var(--t-fast);
  flex-shrink: 0;
}
.switch-dot {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #fff;
  box-shadow: var(--sh-xs);
  transition: transform var(--t-fast);
}
.compare-switch.on .switch-track { background: var(--brand); }
.compare-switch.on .switch-dot { transform: translateX(16px); }
.switch-label {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: var(--fs-sm);
  font-weight: 500;
  color: var(--text-2);
}
.compare-switch.on .switch-label { color: var(--brand); }
.compare-hint {
  font-size: var(--fs-xs);
  color: var(--text-4);
  flex: 1;
  min-width: 200px;
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

.hero-advanced { margin-top: var(--sp-3); }.adv-toggle {
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

.hero-readiness {
  margin-top: var(--sp-3);
  padding: var(--sp-3);
  border-radius: var(--r-lg);
  background: var(--bg-soft);
  border: 1px solid var(--border-2);
}
.readiness-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-2);
  flex-wrap: wrap;
  margin-bottom: var(--sp-2);
}
.readiness-head strong {
  font-size: var(--fs-sm);
  color: var(--text-1);
}
.readiness-head span {
  font-size: var(--fs-xs);
  color: var(--text-3);
}
.readiness-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--sp-2);
}
.readiness-item {
  padding: var(--sp-3);
  border-radius: var(--r-md);
  border: 1px solid var(--border-2);
  background: rgba(255,255,255,0.82);
}
.readiness-item.ready {
  border-color: rgba(22,163,74,0.16);
  background: rgba(22,163,74,0.05);
}
.readiness-item.warn {
  border-color: rgba(217,119,6,0.16);
  background: rgba(217,119,6,0.05);
}
.readiness-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-2);
  margin-bottom: 6px;
}
.readiness-name {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text-1);
}
.readiness-state {
  font-size: var(--fs-2xs);
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--fill-1);
  color: var(--text-3);
}
.readiness-item.ready .readiness-state {
  background: rgba(22,163,74,0.1);
  color: #15803d;
}
.readiness-item.warn .readiness-state {
  background: rgba(217,119,6,0.1);
  color: #b45309;
}
.readiness-item p {
  margin: 0;
  font-size: var(--fs-xs);
  line-height: var(--lh-base);
  color: var(--text-2);
}

/* 雷达扫描 */
.hero-radar {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
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
.radar-status { display: flex; flex-direction: column; gap: 2px; }
.radar-text {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: inherit;
  letter-spacing: 0.02em;
}
.radar-subtext {
  font-size: var(--fs-xs);
  color: var(--text-4);
  line-height: var(--lh-base);
}
.hero-flow {
  margin-top: var(--sp-3);
  padding: var(--sp-3);
  border-radius: var(--r-lg);
  background: linear-gradient(180deg, rgba(0,47,167,0.04), rgba(0,47,167,0.02));
  border: 1px solid rgba(0,47,167,0.12);
}
.flow-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--sp-2);
  margin-bottom: var(--sp-2);
  font-size: var(--fs-xs);
  color: var(--text-3);
}
.flow-steps { display: flex; flex-direction: column; gap: var(--sp-2); }
.flow-step {
  display: flex;
  align-items: flex-start;
  gap: var(--sp-2);
  padding: var(--sp-2);
  border-radius: var(--r-md);
  background: rgba(255,255,255,0.55);
  border: 1px solid var(--border-2);
  opacity: 0.6;
}
.flow-step.active {
  opacity: 1;
  border-color: rgba(0,47,167,0.22);
  box-shadow: 0 0 0 1px rgba(0,47,167,0.08) inset;
}
.flow-step.done {
  opacity: 0.95;
  background: rgba(22,163,74,0.06);
  border-color: rgba(22,163,74,0.16);
}
.flow-index {
  width: 22px;
  height: 22px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  color: var(--text-3);
  background: var(--fill-1);
  flex-shrink: 0;
}
.flow-step.active .flow-index {
  color: #ffffff;
  background: #002FA7;
}
.flow-step.done .flow-index {
  color: #15803d;
  background: rgba(22,163,74,0.14);
}
.flow-copy { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.flow-copy b { font-size: var(--fs-sm); color: var(--text-1); }
.flow-copy span { font-size: var(--fs-xs); color: var(--text-3); line-height: var(--lh-base); }

@media (max-width: 768px) {
  .hero-form, .hero-form-topic { grid-template-columns: 1fr 1fr; }
  .hero-form > :first-child, .hero-form-topic > :first-child { grid-column: 1 / -1; }
  .hero-head h1 { font-size: var(--fs-xl); }
  .hero-radar { align-items: flex-start; }
}
@media (max-width: 640px) {
  .hero-flow { padding: var(--sp-2); }
  .flow-step { padding: 10px; }
}
</style>
