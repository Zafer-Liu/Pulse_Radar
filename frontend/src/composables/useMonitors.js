import { ref, onMounted, onUnmounted } from 'vue'
import { loadMonitors as apiLoad, addMonitor as apiAdd, runMonitor as apiRun, updateMonitor as apiUpdate, deleteMonitor as apiDelete, loadMonitorHistory as apiHistory } from '../api'
import { toast } from './useToast'

/**
 * 监测任务列表 composable
 * 状态消息走 Toast；保留 statusMsg/statusError 供 App.vue 兼容
 */
export function useMonitors() {
  const monitors = ref([])
  const loading = ref(false)
  const statusMsg = ref('')
  const statusError = ref(false)

  let refreshTimer = null

  async function load(silent = true) {
    if (!silent) loading.value = true
    try {
      const payload = await apiLoad()
      monitors.value = payload.monitors || []
    } catch (err) {
      const msg = err.message || String(err)
      statusMsg.value = msg
      statusError.value = true
      if (!silent) toast.error(`加载监测列表失败：${msg}`)
    } finally {
      loading.value = false
    }
  }

  async function add(data) {
    statusMsg.value = '正在添加监测任务...'
    statusError.value = false
    const t = toast.info('正在添加监测任务…', 0)
    try {
      await apiAdd(data)
      toast.remove(t)
      toast.success('已添加监测任务，后台会按周期自动检测')
      statusMsg.value = '已添加监测任务，后台会按周期自动检测。'
      statusError.value = false
      await load()
    } catch (err) {
      const msg = err.message || String(err)
      toast.remove(t)
      toast.error(`添加失败：${msg}`)
      statusMsg.value = msg
      statusError.value = true
    }
  }

  async function run(id) {
    const t = toast.info('正在执行真实检测，请稍候…', 0)
    statusMsg.value = '正在执行真实检测，请稍候...'
    statusError.value = false
    try {
      await apiRun(id)
      toast.remove(t)
      toast.success('检测完成')
      statusMsg.value = '检测完成。'
      statusError.value = false
      await load()
    } catch (err) {
      const msg = err.message || String(err)
      toast.remove(t)
      toast.error(`检测失败：${msg}`)
      statusMsg.value = msg
      statusError.value = true
      await load()
    }
  }

  async function toggle(id, enabled) {
    try {
      await apiUpdate({ id, enabled })
      toast.success(enabled ? '已恢复自动检测' : '已暂停自动检测')
      await load()
    } catch (err) {
      const msg = err.message || String(err)
      toast.error(`操作失败：${msg}`)
      statusMsg.value = msg
      statusError.value = true
    }
  }

  async function remove(id) {
    if (!confirm('确定删除这个监测任务吗？历史记录也会一起删除。')) return
    try {
      await apiDelete(id)
      toast.success('监测任务已删除')
      statusMsg.value = '监测任务已删除。'
      statusError.value = false
      await load()
    } catch (err) {
      const msg = err.message || String(err)
      toast.error(`删除失败：${msg}`)
      statusMsg.value = msg
      statusError.value = true
    }
  }

  async function getLatestResult(id) {
    const payload = await apiHistory(id)
    const latest = (payload.history || []).find(h => h.ok && h.result)
    return latest ? latest.result : null
  }

  onMounted(() => {
    load(true)
    refreshTimer = setInterval(() => load(true), 15000)
  })

  onUnmounted(() => {
    if (refreshTimer) clearInterval(refreshTimer)
  })

  return { monitors, loading, statusMsg, statusError, load, add, run, toggle, remove, getLatestResult }
}
