import { ref, onMounted, onUnmounted } from 'vue'
import { getLoginStatus, requestQrcode, pollQrcode, logout as apiLogout } from '../api'
import { toast } from './useToast'

/**
 * 登录状态与扫码登录 composable
 */
export function useLogin() {
  const loggedIn = ref(false)
  const uid = ref('')
  const hint = ref('')
  const showModal = ref(false)
  const qrcodeUrl = ref('')
  const qrcodeKey = ref('')
  const qrcodeStatus = ref('')       // '' | 'loading' | 'scanning' | 'confirmed' | 'expired' | 'success'
  const qrcodeMessage = ref('')

  let pollTimer = null

  async function refreshStatus() {
    try {
      const data = await getLoginStatus()
      loggedIn.value = data.loggedIn
      uid.value = data.uid || ''
      hint.value = data.hint || ''
    } catch (err) {
      console.warn('获取登录状态失败', err)
    }
  }

  function stopPoll() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  async function startQrcode() {
    stopPoll()
    qrcodeStatus.value = 'loading'
    qrcodeMessage.value = '正在申请二维码...'
    qrcodeUrl.value = ''
    try {
      const payload = await requestQrcode()
      qrcodeKey.value = payload.data.qrcodeKey
      qrcodeUrl.value = payload.data.url
      qrcodeStatus.value = 'scanning'
      qrcodeMessage.value = '请用 B站手机 App 扫描二维码'
      pollTimer = setInterval(doPoll, 2000)
    } catch (err) {
      qrcodeStatus.value = 'expired'
      qrcodeMessage.value = '获取二维码失败：' + (err.message || err)
    }
  }

  async function doPoll() {
    if (!qrcodeKey.value) return
    try {
      const payload = await pollQrcode(qrcodeKey.value)
      const info = payload.data || {}
      if (info.code === 0) {
        stopPoll()
        qrcodeStatus.value = 'success'
        qrcodeMessage.value = '登录成功！正在写入登录态...'
        await refreshStatus()
        setTimeout(() => {
          showModal.value = false
        }, 800)
      } else if (info.code === 86090) {
        qrcodeStatus.value = 'confirmed'
        qrcodeMessage.value = '已扫码，请在手机上点确认'
      } else if (info.code === 86101) {
        qrcodeStatus.value = 'scanning'
        qrcodeMessage.value = '请用 B站手机 App 扫描二维码'
      } else if (info.code === 86038) {
        stopPoll()
        qrcodeStatus.value = 'expired'
        qrcodeMessage.value = '二维码已过期，请点击"刷新二维码"'
      } else {
        qrcodeStatus.value = 'expired'
        qrcodeMessage.value = info.message || ('未知状态 code=' + info.code)
      }
    } catch (err) {
      console.warn('poll error', err)
    }
  }

  function openModal() {
    showModal.value = true
    startQrcode()
  }

  function closeModal() {
    showModal.value = false
    stopPoll()
  }

  async function doLogout() {
    try {
      await apiLogout()
      toast('B站已退出登录', 'success')
    } catch (_) { /* ignore */ }
    await refreshStatus()
  }

  onMounted(() => {
    refreshStatus()
  })

  onUnmounted(() => {
    stopPoll()
  })

  return {
    loggedIn, uid, hint,
    showModal, qrcodeUrl, qrcodeStatus, qrcodeMessage,
    refreshStatus, openModal, closeModal, doLogout, startQrcode,
  }
}
