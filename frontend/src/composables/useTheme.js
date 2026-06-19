/**
 * useTheme · 暗色模式切换
 * - localStorage 持久化
 * - data-theme 属性挂在 <html>
 * - 跟随系统偏好初始化
 */
import { ref, watch } from 'vue'

const STORAGE_KEY = 'sl-radar-theme'
const theme = ref('light')

function apply(val) {
  document.documentElement.setAttribute('data-theme', val)
}

function detect() {
  const saved = localStorage.getItem(STORAGE_KEY)
  if (saved === 'light' || saved === 'dark') return saved
  if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) return 'dark'
  return 'light'
}

export function useTheme() {
  // 首次调用时初始化
  if (!document.documentElement.getAttribute('data-theme')) {
    theme.value = detect()
    apply(theme.value)
  }

  function toggle() {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
  }

  function set(val) {
    theme.value = val
  }

  watch(theme, (val) => {
    apply(val)
    localStorage.setItem(STORAGE_KEY, val)
  })

  return { theme, toggle, set }
}
