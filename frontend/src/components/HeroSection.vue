<template>
  <section class="hero card card-pad-lg">
    <div class="hero-head">
      <h1>输入 B站视频链接<br/>生成实时舆情分析报告</h1>
      <p class="hero-desc">支持 bilibili.com/video/BV… 长链与 b23.tv 短链。后端真实解析视频、抓取公开评论，本地完成情绪、风险、关键词与聚类分析。</p>
    </div>

    <form class="hero-form" @submit.prevent="doAnalyze">
      <input
        v-model="url"
        class="input hero-url"
        placeholder="粘贴 B站视频链接，例如 https://www.bilibili.com/video/BV..."
        :disabled="loading"
      />
      <select v-model.number="pages" class="select hero-pages" :disabled="loading">
        <option :value="3">3 页</option>
        <option :value="5">5 页</option>
        <option :value="10">10 页</option>
        <option :value="20">20 页</option>
      </select>
      <button class="btn btn-lg hero-submit" :disabled="loading" type="submit">
        <span v-if="loading" class="spinner"></span>
        {{ loading ? '分析中' : '开始分析' }}
      </button>
    </form>

    <div class="hero-tips">
      <span class="tip-item">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="8" cy="8" r="6.5"/><path d="M8 5v3.5l2 1.5" stroke-linecap="round"/></svg>
        建议使用浏览器地址栏的 BV 长链
      </span>
      <span class="tip-item">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 8l4 4 8-8" stroke-linecap="round" stroke-linejoin="round"/></svg>
        短链偶尔触发 412 风控
      </span>
    </div>
  </section>
</template>

<script setup>
import { ref } from 'vue'
import { analyzeVideo } from '../api'
import { toast } from '../composables/useToast'

const emit = defineEmits(['result', 'status'])

const url = ref('https://www.bilibili.com/video/BV1aGLR6mEeK/')
const pages = ref(5)
const loading = ref(false)

async function doAnalyze() {
  if (!url.value.trim()) {
    toast.warning('请先输入视频链接')
    return
  }
  loading.value = true
  emit('status', '正在解析短链、获取视频信息和抓取真实评论，请稍候...', false)
  toast.info('开始分析，正在抓取评论…')
  try {
    const payload = await analyzeVideo(url.value.trim(), pages.value)
    emit('result', payload.data)
    const msg = `分析完成：实际抓取 ${payload.data.commentCount} 条公开评论。`
    emit('status', msg, false)
    toast.success(msg)
  } catch (err) {
    const msg = err.message || String(err)
    emit('status', msg, true)
    toast.error(msg)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.hero { margin-bottom: var(--sp-5); background: var(--bg-card); }
.hero-head { margin-bottom: var(--sp-5); }
.hero-head h1 {
  font-size: var(--fs-3xl);
  font-weight: 700;
  line-height: var(--lh-tight);
  letter-spacing: -.02em;
  color: var(--text-1);
  margin-bottom: var(--sp-3);
}
.hero-desc {
  color: var(--text-2);
  font-size: var(--fs-md);
  line-height: var(--lh-loose);
  max-width: 720px;
}
.hero-form {
  display: grid;
  grid-template-columns: 1fr 110px 140px;
  gap: var(--sp-2);
  align-items: stretch;
}
.hero-url { height: 40px; font-size: var(--fs-md); }
.hero-pages { height: 40px; }
.hero-submit { height: 40px; font-size: var(--fs-md); font-weight: 600; }
.hero-tips {
  display: flex; gap: var(--sp-5); flex-wrap: wrap;
  margin-top: var(--sp-4);
  color: var(--text-3);
  font-size: var(--fs-sm);
}
.tip-item { display: inline-flex; align-items: center; gap: 6px; }
.tip-item svg { width: 14px; height: 14px; color: var(--text-4); }

@media (max-width: 768px) {
  .hero-form { grid-template-columns: 1fr; }
  .hero-head h1 { font-size: var(--fs-2xl); }
}
</style>
