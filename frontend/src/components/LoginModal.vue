<template>
  <transition name="modal-fade">
    <div
      v-if="show"
      class="modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="login-modal-title"
      @keydown.esc="$emit('close')"
    >
      <div class="modal-mask" @click="$emit('close')"></div>
      <div class="modal-card" ref="cardRef" tabindex="-1">
        <div class="modal-head">
          <div>
            <h3 id="login-modal-title">扫码登录 B站</h3>
            <p class="modal-tip" style="margin:4px 0 0">用 B站手机 App 扫码，自动写入 Cookie</p>
          </div>
          <button class="modal-close" aria-label="关闭" @click="$emit('close')">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M4 4l8 8M12 4l-8 8" stroke-linecap="round"/></svg>
          </button>
        </div>

        <div class="qrcode-box">
          <div class="qrcode-img">
            <img v-if="qrcodeDataUrl" :src="qrcodeDataUrl" alt="B站登录二维码" />
            <div v-else class="qrcode-loading">
              <span class="spinner" style="width:24px;height:24px;border-width:3px"></span>
            </div>
          </div>
          <div :class="['qrcode-status', statusClass]">
            <svg v-if="status === 'success'" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14" style="vertical-align:-2px"><path d="M3 8l3.5 3.5L13 5" stroke-linecap="round" stroke-linejoin="round"/></svg>
            <svg v-else-if="status === 'expired'" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14" style="vertical-align:-2px"><circle cx="8" cy="8" r="6.5"/><path d="M8 5v3.5" stroke-linecap="round"/></svg>
            {{ message }}
          </div>
        </div>

        <div class="modal-actions">
          <button class="btn btn-sm btn-secondary" @click="$emit('refresh')">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" width="13" height="13"><path d="M14 8a6 6 0 1 1-1.76-4.24M14 2v4h-4" stroke-linecap="round" stroke-linejoin="round"/></svg>
            刷新二维码
          </button>
        </div>

        <div class="modal-security">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" width="13" height="13"><path d="M8 1l5 2v5c0 3-2 5-5 6-3-1-5-3-5-6V3z" stroke-linejoin="round"/></svg>
          登录态仅写入本机 cookies.txt，二维码本地生成，不发送第三方。请勿截图分享。
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import QRCode from 'qrcode'

const props = defineProps({
  show: Boolean,
  qrcodeUrl: { type: String, default: '' },
  status: { type: String, default: '' },
  message: { type: String, default: '' },
})

defineEmits(['close', 'refresh'])

const cardRef = ref(null)
const qrcodeDataUrl = ref('')

watch(
  () => props.qrcodeUrl,
  async (url) => {
    qrcodeDataUrl.value = ''
    if (!url) return
    try {
      qrcodeDataUrl.value = await QRCode.toDataURL(url, {
        width: 200,
        margin: 1,
        color: { dark: '#000000', light: '#ffffff' },
      })
    } catch (err) {
      console.warn('本地二维码生成失败', err)
    }
  },
  { immediate: true }
)

// 打开时自动聚焦
watch(
  () => props.show,
  async (val) => {
    if (val) {
      await nextTick()
      cardRef.value?.focus()
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
  }
)

const statusClass = computed(() => {
  const map = { success: 'success', expired: 'warn', confirmed: '', scanning: '', loading: '' }
  return map[props.status] || ''
})
</script>

<style scoped>
.modal-head { align-items: flex-start; }
.modal-head h3 { font-size: var(--fs-lg); font-weight: 600; }
.modal-tip { color: var(--text-3); font-size: var(--fs-sm); }

.qrcode-loading { display: flex; align-items: center; justify-content: center; width: 100%; height: 100%; color: var(--text-3); }
.qrcode-status { display: inline-flex; align-items: center; gap: 6px; }

.modal-security {
  display: flex; align-items: flex-start; gap: 6px;
  margin-top: var(--sp-3);
  padding: var(--sp-2) var(--sp-3);
  background: var(--fill-1);
  border-radius: var(--r-md);
  color: var(--text-3);
  font-size: var(--fs-xs);
  line-height: var(--lh-base);
}
.modal-security svg { color: var(--success); flex-shrink: 0; margin-top: 2px; }

.spinner { display: inline-block; border: 2px solid var(--border-1); border-top-color: var(--brand-2); border-radius: 50%; animation: spin .7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.modal-fade-enter-active, .modal-fade-leave-active { transition: opacity var(--t-base); }
.modal-fade-enter-from, .modal-fade-leave-to { opacity: 0; }
</style>
