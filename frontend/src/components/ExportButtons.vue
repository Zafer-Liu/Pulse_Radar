<template>
  <div class="export-btns no-print">
    <button class="export-btn" @click="onImage" :disabled="busy" title="导出为 PNG 图片">
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" width="14" height="14"><rect x="2" y="3" width="12" height="10" rx="1.5"/><circle cx="5.5" cy="6.5" r="1.2"/><path d="M2.5 12l3.5-3.5 2.5 2.5 2-2 3 3" stroke-linecap="round" stroke-linejoin="round"/></svg>
      图片
    </button>
    <button class="export-btn" @click="onPDF" :disabled="busy" title="打印 / 另存为 PDF">
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" width="14" height="14"><path d="M4 6V2h8v4M4 12H3a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v4a1 1 0 0 1-1 1h-1" stroke-linejoin="round"/><rect x="4" y="10" width="8" height="4" rx="1"/></svg>
      PDF
    </button>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useExport } from '../composables/useExport'

const props = defineProps({
  targetId: { type: String, required: true },
  fileName: { type: String, default: '声浪雷达分析' },
})

const { exportPDF, exportImage } = useExport()
const busy = ref(false)

async function onImage() {
  busy.value = true
  try {
    await exportImage(props.targetId, props.fileName)
  } finally {
    busy.value = false
  }
}
function onPDF() {
  exportPDF(props.targetId, props.fileName)
}
</script>

<style scoped>
.export-btns { display: inline-flex; gap: 6px; }
.export-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px;
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: var(--bg-card);
  color: var(--text-2);
  font-size: var(--fs-xs);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--t-fast);
}
.export-btn:hover:not(:disabled) {
  border-color: var(--brand);
  color: var(--brand);
  background: var(--brand-soft);
}
.export-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.export-btn svg { flex-shrink: 0; }
</style>
