/**
 * 后端 API 统一封装
 */

let _authToken = null

/** 启动时从后端获取 AUTH_TOKEN（远程部署时 POST 鉴权需要） */
export async function initAuth() {
  try {
    const res = await fetch('/api/auth/token')
    const payload = await res.json()
    if (payload.ok && payload.token) {
      _authToken = payload.token
    }
  } catch {
    // 本地运行时 AUTH_TOKEN 为空，无需携带
  }
}

export async function apiGet(url) {
  const res = await fetch(url)
  const payload = await res.json()
  if (!payload.ok) throw new Error(payload.error || '请求失败')
  return payload
}

export async function apiPost(url, data) {
  const headers = { 'Content-Type': 'application/json' }
  if (_authToken) {
    headers['Authorization'] = `Bearer ${_authToken}`
  }
  const res = await fetch(url, {
    method: 'POST',
    headers,
    body: JSON.stringify(data || {}),
  })
  const payload = await res.json()
  if (!payload.ok) throw new Error(payload.error || '操作失败')
  return payload
}

// ---- 分析 ----
export function analyzeVideo(url, pages) {
  return apiGet(`/api/analyze?url=${encodeURIComponent(url)}&pages=${encodeURIComponent(pages)}`)
}

// ---- 监测 ----
export function loadMonitors() {
  return apiGet('/api/monitors')
}

export function addMonitor(data) {
  return apiPost('/api/monitor/add', data)
}

export function updateMonitor(data) {
  return apiPost('/api/monitor/update', data)
}

export function deleteMonitor(id) {
  return apiPost('/api/monitor/delete', { id })
}

export function runMonitor(id) {
  return apiPost('/api/monitor/run', { id })
}

export function loadMonitorHistory(id) {
  return apiGet(`/api/monitor/history?id=${encodeURIComponent(id)}`)
}

// ---- 登录 ----
export function getLoginStatus() {
  return apiGet('/api/login/status')
}

export function requestQrcode() {
  return apiPost('/api/login/qrcode')
}

export function pollQrcode(qrcodeKey) {
  return apiPost('/api/login/poll', { qrcodeKey })
}

export function logout() {
  return apiPost('/api/login/logout')
}

// ---- LLM 配置 ----
export function getLLMConfig() {
  return apiGet('/api/config/llm')
}

export function saveLLMConfig(data) {
  return apiPost('/api/config/llm', data)
}

// ---- Webhook 告警配置 ----
export function getAlertConfig() {
  return apiGet('/api/config/alert')
}

export function saveAlertConfig(data) {
  return apiPost('/api/config/alert', data)
}

export function testAlert() {
  return apiPost('/api/config/alert/test', {})
}

// ---- 话题搜索 ----
export function searchTopic(keyword, page = 1, pageSize = 20, order = 'totalrank') {
  return apiGet(`/api/topic/search?keyword=${encodeURIComponent(keyword)}&page=${page}&pageSize=${pageSize}&order=${order}`)
}

export function analyzeTopic(keyword, topN = 5, pages = 3) {
  return apiGet(`/api/topic/analyze?keyword=${encodeURIComponent(keyword)}&topN=${topN}&pages=${pages}`)
}

// ---- Agent ----
export function getAgentTrace(monitorId) {
  return apiGet(`/api/agent/trace?monitor_id=${encodeURIComponent(monitorId)}`)
}

// ---- 趋势 ----
export function getUpTrend(author, limit = 5) {
  return apiGet(`/api/trend/up?author=${encodeURIComponent(author)}&limit=${limit}`)
}

export function getTopicTrend(keyword, limit = 5) {
  return apiGet(`/api/trend/topic?keyword=${encodeURIComponent(keyword)}&limit=${limit}`)
}

// ---- 小红书 ----
export function analyzeXhsNote(url, pages) {
  return apiGet(`/api/xhs/analyze?url=${encodeURIComponent(url)}&pages=${encodeURIComponent(pages)}`)
}

export function searchXhsNotes(keyword, page = 1, pageSize = 20) {
  return apiGet(`/api/xhs/search?keyword=${encodeURIComponent(keyword)}&page=${page}&pageSize=${pageSize}`)
}

export function analyzeXhsTopic(keyword, topN = 5, pages = 3) {
  return apiGet(`/api/xhs/topic/analyze?keyword=${encodeURIComponent(keyword)}&topN=${topN}&pages=${pages}`)
}
