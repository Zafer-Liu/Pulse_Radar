<template>
  <section class="card monitor-form-card">
    <div class="form-head">
      <div>
        <h2>多视频监测中心</h2>
        <p class="form-subtitle">添加视频后自动进入监测队列，按周期抓取并对比舆情变化</p>
      </div>
      <button class="btn btn-sm btn-ghost" @click="$emit('refresh')">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14"><path d="M14 8a6 6 0 1 1-1.76-4.24M14 2v4h-4" stroke-linecap="round" stroke-linejoin="round"/></svg>
        刷新
      </button>
    </div>

    <form class="monitor-form" @submit.prevent="doAdd">
      <input
        v-model="url"
        class="input"
        placeholder="添加要监测的 B站视频链接"
        :disabled="adding"
        @keyup.enter="doAdd"
      />
      <select v-model.number="pages" class="select" :disabled="adding">
        <option :value="3">3 页</option>
        <option :value="5">5 页</option>
        <option :value="10">10 页</option>
        <option :value="20">20 页</option>
      </select>
      <input v-model.number="intervalValue" type="number" min="1" class="input interval-input" placeholder="周期" :disabled="adding" />
      <select v-model="intervalUnit" class="select" :disabled="adding">
        <option value="小时">小时</option>
        <option value="天">天</option>
      </select>
      <button class="btn" :disabled="adding" type="submit">
        <span v-if="adding" class="spinner"></span>
        {{ adding ? '添加中' : '添加监测' }}
      </button>
    </form>

    <div class="notice">添加后自动进入监测队列。后端常驻运行时按周期自动检测，也可点击「立即检测」手动触发。</div>
  </section>
</template>

<script setup>
import { ref } from 'vue'
import { toast } from '../composables/useToast'

const emit = defineEmits(['add', 'refresh'])

const url = ref('')
const pages = ref(5)
const intervalValue = ref(6)
const intervalUnit = ref('小时')
const adding = ref(false)

async function doAdd() {
  if (!url.value.trim()) {
    toast.warning('请先输入要监测的视频链接')
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
.monitor-form-card { margin-bottom: var(--sp-5); }
.form-head { display: flex; justify-content: space-between; align-items: flex-start; gap: var(--sp-3); margin-bottom: var(--sp-4); }
.form-head h2 { font-size: var(--fs-lg); font-weight: 600; color: var(--text-1); margin-bottom: 4px; }
.form-subtitle { font-size: var(--fs-sm); color: var(--text-3); }
.monitor-form {
  display: grid;
  grid-template-columns: 1fr 100px 90px 90px 120px;
  gap: var(--sp-2);
  align-items: center;
}
.interval-input { text-align: center; padding-left: var(--sp-2); padding-right: var(--sp-2); }

@media (max-width: 1024px) {
  .monitor-form { grid-template-columns: 1fr 100px 90px 90px 110px; }
}
@media (max-width: 768px) {
  .monitor-form { grid-template-columns: 1fr 1fr; }
  .monitor-form > :first-child { grid-column: 1 / -1; }
  .monitor-form > :last-child { grid-column: 1 / -1; }
}
</style>
