<template>
  <main>
    <BackgroundParticles />
    <TopBar
      :logged-in="login.loggedIn.value"
      :uid="login.uid.value"
      :alert-configured="alertConfigured"
      :xhs-logged-in="xhsLoggedIn"
      @open-login="login.openModal()"
      @open-xhs-login="xhsLoginShow = true"
      @open-settings="settingsShow = true"
      @open-alert="alertShow = true"
      @logout="login.doLogout()"
      @logout-xhs="doXhsLogout()"
    />

    <div class="wrap">
      <UnifiedInput
        @result="onResult"
        @topic-result="onTopicResult"
        @add="onAddMonitor"
      />

      <!-- 视频分析结果 -->
      <AnalysisResult :data="analysisData" />

      <!-- 话题分析结果 -->
      <TopicResult :data="topicData" />

      <!-- 无数据时的引导 -->
      <div v-if="!analysisData && !topicData && !monitors.monitors.value.length" class="first-run-hint card">
        <div class="hint-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="32" height="32"><path d="M12 2v4M12 18v4M2 12h4M18 12h4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" stroke-linecap="round"/></svg>
        </div>
        <p class="hint-title">开始你的第一次舆情分析</p>
        <p class="hint-desc">粘贴 B站视频链接一键分析，或输入话题关键词全网搜索聚合分析。也可以添加监测任务持续跟踪舆情变化。</p>
      </div>

      <!-- 监测任务区（白底卡片包裹） -->
      <div class="monitor-section">
        <div class="section-title section-title-compact">
          <div class="st-left">
            <h2>监测任务</h2>
            <span class="subtitle">每 15 秒自动刷新</span>
          </div>
          <div class="st-right">
            <button class="btn btn-sm btn-ghost" @click="() => monitors.load(false)">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14"><path d="M14 8a6 6 0 1 1-1.76-4.24M14 2v4h-4" stroke-linecap="round" stroke-linejoin="round"/></svg>
              刷新
            </button>
            <span v-if="monitors.monitors.value.length" class="badge badge-neutral">
              {{ monitors.monitors.value.length }}
            </span>
          </div>
        </div>

        <section class="monitor-list">
          <!-- 加载骨架 -->
          <template v-if="monitors.loading.value && !monitors.monitors.value.length">
            <div v-for="n in 3" :key="n" class="card monitor-item skeleton-row">
              <div class="skeleton" style="width:160px;aspect-ratio:16/10;border-radius:var(--r-lg)"></div>
              <div style="flex:1">
                <div class="skeleton skeleton-title"></div>
                <div class="skeleton skeleton-text"></div>
                <div class="skeleton skeleton-text" style="width:80%"></div>
              </div>
            </div>
          </template>

          <!-- 空状态 -->
          <EmptyState
            v-else-if="!monitors.monitors.value.length"
            title="还没有监测任务"
            description="添加一个或多个 B站视频链接，系统会按周期自动抓取评论并生成舆情分析。"
          />

          <!-- 任务卡片 -->
        <MonitorCard
          v-for="m in monitors.monitors.value"
          :key="m.id"
          :monitor="m"
          @run="monitors.run"
          @detail="onShowDetail"
          @toggle="monitors.toggle"
          @delete="monitors.remove"
        />
      </section>
      </div>

      <LoginModal
        :show="login.showModal.value"
        :qrcode-url="login.qrcodeUrl.value"
        :status="login.qrcodeStatus.value"
        :message="login.qrcodeMessage.value"
        @close="login.closeModal()"
        @refresh="login.startQrcode()"
      />

      <SettingsModal
        :show="settingsShow"
        @close="settingsShow = false"
        @saved="onSettingsSaved"
      />

      <AlertModal
        :show="alertShow"
        @close="alertShow = false"
        @saved="onAlertSaved"
      />

      <XhsLoginModal
        :show="xhsLoginShow"
        @close="xhsLoginShow = false"
        @success="loadXhsStatus"
      />
    </div>

    <!-- 全局 Toast -->
    <AppToast />
  </main>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import TopBar from './components/TopBar.vue'
import BackgroundParticles from './components/BackgroundParticles.vue'
import UnifiedInput from './components/UnifiedInput.vue'
import MonitorCard from './components/MonitorCard.vue'
import AnalysisResult from './components/AnalysisResult.vue'
import TopicResult from './components/TopicResult.vue'
import LoginModal from './components/LoginModal.vue'
import SettingsModal from './components/SettingsModal.vue'
import AlertModal from './components/AlertModal.vue'
import XhsLoginModal from './components/XhsLoginModal.vue'
import AppToast from './components/AppToast.vue'
import EmptyState from './components/ui/EmptyState.vue'
import { useLogin } from './composables/useLogin'
import { useMonitors } from './composables/useMonitors'
import { toast } from './composables/useToast'
import { getAlertConfig, initAuth, apiGet, xhsLogout } from './api'

const login = useLogin()
const monitors = useMonitors()

const analysisData = ref(null)
const topicData = ref(null)
const settingsShow = ref(false)
const alertShow = ref(false)
const alertConfigured = ref(false)
const xhsLoginShow = ref(false)
const xhsLoggedIn = ref(false)

// 检查小红书 Cookie 配置状态
async function loadXhsStatus() {
  try {
    const res = await apiGet('/api/xhs/login/status')
    xhsLoggedIn.value = !!res.data?.configured
  } catch {
    xhsLoggedIn.value = false
  }
}

// 退出小红书登录
async function doXhsLogout() {
  try {
    await xhsLogout()
    toast('小红书已退出登录', 'success')
  } catch (e) {
    toast('退出小红书失败：' + (e.message || e), 'error')
  }
  await loadXhsStatus()
}

// 启动时检查告警配置状态（用于 TopBar 铃铛上的绿点）
async function loadAlertStatus() {
  try {
    const res = await getAlertConfig()
    alertConfigured.value = !!res.configured
  } catch (e) {
    // 静默失败，不影响主流程
  }
}
onMounted(() => { initAuth(); loadAlertStatus(); loadXhsStatus() })

function onResult(data) {
  analysisData.value = data
  topicData.value = null // 切换时清空话题结果
}

function onTopicResult(data) {
  topicData.value = data
  analysisData.value = null // 切换时清空视频结果
}

function onAddMonitor(data) {
  if (data) monitors.add(data)
}

async function onShowDetail(id) {
  toast.info('正在加载历史结果…')
  try {
    const result = await monitors.getLatestResult(id)
    if (!result) {
      toast.warning('这个任务还没有可展示的成功检测结果')
      return
    }
    analysisData.value = result
    topicData.value = null
    toast.success('已加载历史结果')
    const el = document.querySelector('.analysis-result')
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  } catch (err) {
    toast.error(err.message || String(err))
  }
}

function onSettingsSaved(res) {
  // res.available 表示 LLM 是否已启用
  // 已在 SettingsModal 内部 toast，这里可做后续动作
}

function onAlertSaved(res) {
  alertConfigured.value = !!res.configured
}
</script>

<style scoped>
main { position: relative; z-index: 1; }
.skeleton-row { display: grid; grid-template-columns: 160px 1fr; gap: var(--sp-4); align-items: center; }

.section-title-compact {
  margin: var(--sp-4) 0 var(--sp-3);
}
.section-title-compact h2 {
  font-size: var(--fs-md);
  font-weight: 600;
  letter-spacing: 0;
}
.section-title-compact .subtitle {
  font-size: var(--fs-xs);
}
.section-title-compact .st-left {
  display: flex;
  align-items: baseline;
  gap: var(--sp-2);
}
.section-title-compact .st-right {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
}

/* 监测任务区白底卡片 */
.monitor-section {
  background: var(--bg-card);
  border-radius: var(--r-xl);
  box-shadow: var(--sh-sm);
  padding: var(--sp-5);
  margin-top: var(--sp-4);
}
.monitor-section + * {
  margin-top: var(--sp-4);
}

.first-run-hint {
  padding: var(--sp-7) var(--sp-5);
  text-align: center;
  color: var(--text-3);
}
.first-run-hint .hint-icon {
  color: var(--text-4);
  margin-bottom: var(--sp-3);
  opacity: 0.6;
}
.first-run-hint .hint-title {
  font-size: var(--fs-md);
  font-weight: 500;
  color: var(--text-2);
  margin-bottom: var(--sp-2);
}
.first-run-hint .hint-desc {
  font-size: var(--fs-sm);
  color: var(--text-3);
  max-width: 420px;
  margin: 0 auto;
  line-height: var(--lh-loose);
}
</style>
