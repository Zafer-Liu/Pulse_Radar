<template>
  <div class="toast-wrap" role="region" aria-label="通知">
    <transition-group name="toast">
      <div
        v-for="t in list"
        :key="t.id"
        :class="['toast', t.type, { leaving: t.leaving }]"
        role="alert"
      >
        <svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <template v-if="t.type === 'success'">
            <path d="M20 6L9 17l-5-5" stroke-linecap="round" stroke-linejoin="round" />
          </template>
          <template v-else-if="t.type === 'error'">
            <circle cx="12" cy="12" r="10" /><line x1="15" y1="9" x2="9" y2="15" stroke-linecap="round" /><line x1="9" y1="9" x2="15" y2="15" stroke-linecap="round" />
          </template>
          <template v-else-if="t.type === 'warning'">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" stroke-linejoin="round" /><line x1="12" y1="9" x2="12" y2="13" stroke-linecap="round" /><circle cx="12" cy="17" r="0.5" fill="currentColor" />
          </template>
          <template v-else>
            <circle cx="12" cy="12" r="10" /><line x1="12" y1="16" x2="12" y2="12" stroke-linecap="round" /><circle cx="12" cy="8" r="0.5" fill="currentColor" />
          </template>
        </svg>
        <div class="toast-content">{{ t.message }}</div>
        <button class="toast-close" aria-label="关闭" @click="remove(t.id)">×</button>
      </div>
    </transition-group>
  </div>
</template>

<script setup>
import { toast } from '../composables/useToast'
const { list, remove } = toast
</script>

<style scoped>
/* transition-group 内联类（覆盖 main.css 的全局动画）*/
.toast-enter-active { transition: all .25s cubic-bezier(.34, 1.56, .64, 1); }
.toast-leave-active { transition: all .2s ease; position: absolute; right: 0; }
.toast-enter-from { opacity: 0; transform: translateX(100%); }
.toast-leave-to { opacity: 0; transform: translateX(100%); }
.toast-move { transition: transform .25s ease; }
</style>
