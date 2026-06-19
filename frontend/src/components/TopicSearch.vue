<template>
  <section class="topic-search card">
    <div class="topic-head">
      <h2>话题雷达 <span class="topic-tag">全网搜索</span></h2>
      <p class="topic-desc">输入话题关键词，自动搜索 B站相关视频，聚合多视频评论进行整体舆情分析。</p>
    </div>

    <form class="topic-form" @submit.prevent="doSearch">
      <input
        v-model="keyword"
        class="input topic-input"
        placeholder="输入话题关键词，例如：AI大模型、新能源、高考..."
        :disabled="loading"
      />
      <select v-model.number="topN" class="select topic-select" :disabled="loading">
        <option :value="3">Top 3 视频</option>
        <option :value="5">Top 5 视频</option>
        <option :value="8">Top 8 视频</option>
        <option :value="10">Top 10 视频</option>
      </select>
      <select v-model.number="pages" class="select topic-select" :disabled="loading">
        <option :value="2">每视频 2 页</option>
        <option :value="3">每视频 3 页</option>
        <option :value="5">每视频 5 页</option>
      </select>
      <button class="btn btn-lg topic-submit" :disabled="loading || !keyword.trim()" type="submit">
        <span v-if="loading" class="spinner"></span>
        {{ loading ? '分析中' : '话题分析' }}
      </button>
    </form>

    <div v-if="loading" class="topic-progress">
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: progressPct + '%' }"></div>
      </div>
      <span class="progress-text">{{ progressText }}</span>
    </div>
  </section>
</template>

<script setup>
import { ref, computed } from 'vue'
import { analyzeTopic } from '../api'
import { toast } from '../composables/useToast'

const emit = defineEmits(['result'])

const keyword = ref('')
const topN = ref(5)
const pages = ref(3)
const loading = ref(false)
const progressText = ref('')

// 模拟进度（话题分析耗时较长，给用户反馈）
const progressPct = computed(() => {
  if (!loading.value) return 0
  const text = progressText.value
  if (text.includes('搜索')) return 10
  if (text.includes('视频 1')) return 25
  if (text.includes('视频 2')) return 40
  if (text.includes('视频 3')) return 55
  if (text.includes('视频 4')) return 65
  if (text.includes('视频 5')) return 75
  if (text.includes('聚合')) return 90
  return 95
})

async function doSearch() {
  if (!keyword.value.trim()) {
    toast.warning('请输入话题关键词')
    return
  }
  loading.value = true
  progressText.value = '正在搜索相关视频...'
  toast.info('开始话题分析，搜索相关视频并抓取评论，可能需要较长时间...')
  try {
    const payload = await analyzeTopic(keyword.value.trim(), topN.value, pages.value)
    emit('result', payload.data)
    const d = payload.data
    toast.success(`话题分析完成：${d.analyzedCount} 个视频，共 ${d.totalComments} 条评论`)
  } catch (err) {
    toast.error(err.message || String(err))
  } finally {
    loading.value = false
    progressText.value = ''
  }
}
</script>

<style scoped>
.topic-search { margin-bottom: var(--sp-5); background: var(--bg-card); }
.topic-head { margin-bottom: var(--sp-4); }
.topic-head h2 {
  font-size: var(--fs-xl);
  font-weight: 600;
  color: var(--text-1);
  margin-bottom: var(--sp-2);
  display: flex;
  align-items: center;
  gap: var(--sp-3);
}
.topic-tag {
  font-size: var(--fs-xs);
  font-weight: 500;
  color: #e8684a;
  background: rgba(232, 104, 74, 0.1);
  padding: 3px 10px;
  border-radius: var(--r-full);
}
.topic-desc {
  color: var(--text-2);
  font-size: var(--fs-sm);
  line-height: var(--lh-loose);
  max-width: 720px;
}

.topic-form {
  display: grid;
  grid-template-columns: 1fr 130px 130px 130px;
  gap: var(--sp-2);
  align-items: stretch;
}
.topic-input { height: 40px; font-size: var(--fs-base); }
.topic-select { height: 40px; }
.topic-submit { height: 40px; font-size: var(--fs-base); font-weight: 500; }

.topic-progress {
  margin-top: var(--sp-3);
  display: flex;
  align-items: center;
  gap: var(--sp-3);
}
.progress-bar {
  flex: 1;
  height: 6px;
  background: var(--fill-1);
  border-radius: var(--r-full);
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--brand), #e8684a);
  border-radius: var(--r-full);
  transition: width 0.6s ease;
}
.progress-text {
  font-size: var(--fs-xs);
  color: var(--text-3);
  white-space: nowrap;
  min-width: 120px;
}

@media (max-width: 768px) {
  .topic-form { grid-template-columns: 1fr 1fr; }
  .topic-form > :first-child { grid-column: 1 / -1; }
  .topic-head h2 { font-size: var(--fs-lg); }
}
</style>
