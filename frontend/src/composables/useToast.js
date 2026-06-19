/**
 * useToast · 全局 Toast 通知系统
 * 单例模式，任意组件 import { toast } from '@/composables/useToast'
 */
import { reactive } from 'vue'

const state = reactive({
  list: [],
})
let seq = 0

function add(type, message, duration) {
  const id = ++seq
  const item = { id, type, message }
  state.list.push(item)
  if (duration > 0) {
    setTimeout(() => remove(id), duration)
  }
  return id
}

function remove(id) {
  const idx = state.list.findIndex(t => t.id === id)
  if (idx === -1) return
  // 触发离场动画
  const item = state.list[idx]
  item.leaving = true
  setTimeout(() => {
    const i = state.list.findIndex(t => t.id === id)
    if (i !== -1) state.list.splice(i, 1)
  }, 200)
}

export const toast = {
  list: state.list,
  success(msg, duration = 3000) { return add('success', msg, duration) },
  error(msg, duration = 5000) { return add('error', msg, duration) },
  warning(msg, duration = 4000) { return add('warning', msg, duration) },
  info(msg, duration = 3000) { return add('info', msg, duration) },
  remove,
}

/**
 * 把旧的 (msg, isError) 回调风格转成 toast
 * 兼容现有 useMonitors / HeroSection 的 onStatus
 */
export function statusToToast(msg, isError) {
  if (!msg) return
  if (isError) toast.error(msg)
  else toast.success(msg)
}
