<template>
  <transition name="modal-fade">
    <div
      v-if="show"
      class="modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="settings-modal-title"
      @keydown.esc="$emit('close')"
    >
      <div class="modal-mask" @click="$emit('close')"></div>
      <div class="modal-card settings-card" ref="cardRef" tabindex="-1">
        <div class="modal-head">
          <div>
            <h3 id="settings-modal-title">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16" style="vertical-align:-3px;color:var(--brand)"><circle cx="8" cy="8" r="2.5"/><path d="M8 1v2M8 13v2M1 8h2M13 8h2M3.05 3.05l1.41 1.41M11.54 11.54l1.41 1.41M3.05 12.95l1.41-1.41M11.54 4.46l1.41-1.41" stroke-linecap="round"/></svg>
              LLM 配置
            </h3>
            <p class="modal-tip" style="margin:4px 0 0">配置 AI 舆情分析报告的模型。配置后自动写入 .env 并热重载，无需重启服务。</p>
          </div>
          <button class="modal-close" aria-label="关闭" @click="$emit('close')">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M4 4l8 8M12 4l-8 8" stroke-linecap="round"/></svg>
          </button>
        </div>

        <!-- 加载态 -->
        <div v-if="loading" class="loading-box">
          <span class="spinner" style="width:24px;height:24px;border-width:3px"></span>
          <span style="margin-left:10px;color:var(--text-3)">加载配置中…</span>
        </div>

        <template v-else>
          <!-- 当前状态 -->
          <div :class="['status-banner', config.available ? 'status-ok' : 'status-warn']">
            <svg v-if="config.available" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M3 8l3.5 3.5L13 5" stroke-linecap="round" stroke-linejoin="round"/></svg>
            <svg v-else viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><circle cx="8" cy="8" r="6.5"/><path d="M8 5v3.5" stroke-linecap="round"/></svg>
            <span v-if="config.available">LLM 已启用 · 模型 {{ config.model }}</span>
            <span v-else>LLM 未启用 · 报告将使用模板降级</span>
          </div>

          <!-- 预设按钮 -->
          <div class="preset-row">
            <span class="preset-label">快速选择：</span>
            <button
              v-for="p in presets"
              :key="p.key"
              :class="['preset-btn', { active: isPresetActive(p.key) }]"
              @click="applyPreset(p.key)"
            >{{ p.label }}</button>
          </div>

          <!-- 表单 -->
          <div class="form-grid">
            <div class="form-row">
              <label for="llm-key">API Key</label>
              <div class="input-wrap">
                <input
                  id="llm-key"
                  :type="showKey ? 'text' : 'password'"
                  v-model="form.apiKey"
                  :placeholder="config.apiKeySet ? config.apiKey : 'sk-...'"
                  autocomplete="off"
                  spellcheck="false"
                />
                <button
                  type="button"
                  class="toggle-eye"
                  :aria-label="showKey ? '隐藏' : '显示'"
                  @click="showKey = !showKey"
                  tabindex="-1"
                >
                  <svg v-if="showKey" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14"><path d="M1 8s2.5-5 7-5 7 5 7 5-2.5 5-7 5-7-5-7-5z"/><circle cx="8" cy="8" r="2"/></svg>
                  <svg v-else viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14"><path d="M1 8s2.5-5 7-5 7 5 7 5-2.5 5-7 5-7-5-7-5z"/><path d="M2 2l12 12" stroke-linecap="round"/></svg>
                </button>
              </div>
              <p class="form-hint">
                <span v-if="config.apiKeySet && !form.apiKey">已配置（保留原值，留空保存即不修改）</span>
                <span v-else-if="form.apiKey && form.apiKey.endsWith('***')">掩码值不可保存，请输入完整 key 或留空保留</span>
              </p>
            </div>

            <div class="form-row">
              <label for="llm-base">Base URL</label>
              <input id="llm-base" type="text" v-model="form.baseUrl" placeholder="https://api.deepseek.com/v1" spellcheck="false" />
            </div>

            <div class="form-row">
              <label for="llm-model">模型名称</label>
              <input id="llm-model" type="text" v-model="form.model" placeholder="deepseek-chat" spellcheck="false" />
            </div>

            <div class="form-row">
              <label for="llm-timeout">超时（秒）</label>
              <input id="llm-timeout" type="number" v-model.number="form.timeout" min="5" max="120" step="5" />
            </div>
          </div>

          <!-- 高级：清空 key -->
          <details class="advanced">
            <summary>高级</summary>
            <label class="checkbox-row">
              <input type="checkbox" v-model="form.clearKey" />
              <span>保存时清空 API Key（关闭 LLM，强制走模板）</span>
            </label>
          </details>

          <!-- 操作 -->
          <div class="modal-actions">
            <button class="btn btn-sm btn-secondary" @click="$emit('close')">取消</button>
            <button
              class="btn btn-sm"
              :disabled="saving || (form.apiKey && form.apiKey.endsWith('***'))"
              @click="onSave"
            >
              <span v-if="saving" class="spinner" style="width:12px;height:12px;border-width:2px;vertical-align:-1px"></span>
              {{ saving ? '保存中…' : '保存配置' }}
            </button>
          </div>

          <div class="modal-security">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" width="13" height="13"><path d="M8 1l5 2v5c0 3-2 5-5 6-3-1-5-3-5-6V3z" stroke-linejoin="round"/></svg>
            配置仅写入本机 .env 文件（已被 .gitignore 忽略），不发送任何第三方。修改后立即生效，无需重启。
          </div>
        </template>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { ref, reactive, watch, nextTick, computed } from 'vue'
import { getLLMConfig, saveLLMConfig } from '../api'
import { toast } from '../composables/useToast'

const props = defineProps({
  show: Boolean,
})
const emit = defineEmits(['close', 'saved'])

const cardRef = ref(null)
const loading = ref(false)
const saving = ref(false)
const showKey = ref(false)

const config = reactive({
  available: false,
  apiKey: '',
  apiKeySet: false,
  baseUrl: 'https://api.deepseek.com/v1',
  model: 'deepseek-chat',
  timeout: 30,
})

const presets = ref([])

const form = reactive({
  apiKey: '',
  baseUrl: 'https://api.deepseek.com/v1',
  model: 'deepseek-chat',
  timeout: 30,
  clearKey: false,
})

function isPresetActive(key) {
  const p = presets.value.find(x => x.key === key)
  if (!p) return false
  return form.baseUrl === p.base_url && form.model === p.model
}

function applyPreset(key) {
  const p = presets.value.find(x => x.key === key)
  if (!p) return
  form.baseUrl = p.base_url
  form.model = p.model
}

async function loadConfig() {
  loading.value = true
  try {
    const res = await getLLMConfig()
    const d = res
    config.available = d.available
    config.apiKey = d.apiKey || ''
    config.apiKeySet = d.apiKeySet
    config.baseUrl = d.baseUrl
    config.model = d.model
    config.timeout = d.timeout
    // form 不预填 key（避免掩码被误存），其他字段预填
    form.apiKey = ''
    form.baseUrl = d.baseUrl
    form.model = d.model
    form.timeout = d.timeout
    form.clearKey = false
    // presets 转数组
    presets.value = Object.entries(d.presets || {}).map(([k, v]) => ({ key: k, ...v }))
  } catch (err) {
    toast.error(err.message || '加载配置失败')
  } finally {
    loading.value = false
  }
}

async function onSave() {
  if (form.apiKey && form.apiKey.endsWith('***')) {
    toast.warning('API Key 字段是掩码值，请清空后重新输入完整 key，或留空保留原值')
    return
  }
  saving.value = true
  try {
    const payload = {
      apiKey: form.apiKey,
      baseUrl: form.baseUrl,
      model: form.model,
      timeout: form.timeout,
      clearKey: form.clearKey,
    }
    const res = await saveLLMConfig(payload)
    if (res.available) {
      toast.success(`LLM 已启用 · 模型 ${form.model}`)
    } else {
      toast.info('配置已保存，但 LLM 未启用（请检查 API Key）')
    }
    emit('saved', res)
    emit('close')
  } catch (err) {
    toast.error(err.message || '保存失败')
  } finally {
    saving.value = false
  }
}

watch(
  () => props.show,
  async (val) => {
    if (val) {
      await nextTick()
      cardRef.value?.focus()
      document.body.style.overflow = 'hidden'
      await loadConfig()
    } else {
      document.body.style.overflow = ''
    }
  }
)
</script>

<style scoped>
.settings-card {
  width: min(520px, calc(100% - 32px));
}

.loading-box {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--sp-6) 0;
  color: var(--text-3);
}

.status-banner {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: var(--sp-2) var(--sp-3);
  border-radius: var(--r-md);
  font-size: var(--fs-sm);
  margin-bottom: var(--sp-3);
}
.status-ok {
  background: color-mix(in srgb, var(--success) 12%, transparent);
  color: var(--success);
  border: 1px solid color-mix(in srgb, var(--success) 30%, transparent);
}
.status-warn {
  background: color-mix(in srgb, var(--warning) 12%, transparent);
  color: var(--warning);
  border: 1px solid color-mix(in srgb, var(--warning) 30%, transparent);
}

.preset-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--sp-2);
  margin-bottom: var(--sp-3);
}
.preset-label {
  font-size: var(--fs-xs);
  color: var(--text-3);
}
.preset-btn {
  padding: 4px 10px;
  font-size: var(--fs-xs);
  border: 1px solid var(--border-1);
  background: var(--bg-card);
  color: var(--text-2);
  border-radius: var(--r-sm);
  cursor: pointer;
  transition: all var(--t-fast);
}
.preset-btn:hover {
  border-color: var(--brand);
  color: var(--brand);
}
.preset-btn.active {
  background: var(--brand);
  border-color: var(--brand);
  color: #fff;
}

.form-grid {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
.form-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.form-row label {
  font-size: var(--fs-xs);
  color: var(--text-2);
  font-weight: 500;
}
.form-row input {
  padding: 8px 10px;
  font-size: var(--fs-sm);
  border: 1px solid var(--border-1);
  border-radius: var(--r-md);
  background: var(--bg-card);
  color: var(--text-1);
  transition: border-color var(--t-fast), box-shadow var(--t-fast);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
.form-row input:focus {
  outline: none;
  border-color: var(--brand);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--brand) 15%, transparent);
}
.input-wrap {
  position: relative;
}
.input-wrap input {
  width: 100%;
  padding-right: 36px;
}
.toggle-eye {
  position: absolute;
  right: 6px;
  top: 50%;
  transform: translateY(-50%);
  width: 26px;
  height: 26px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: var(--text-3);
  cursor: pointer;
  border-radius: var(--r-sm);
}
.toggle-eye:hover { color: var(--text-1); background: var(--fill-1); }

.form-hint {
  font-size: 11px;
  color: var(--text-3);
  margin-top: 2px;
  min-height: 14px;
}

.advanced {
  margin-top: var(--sp-3);
  padding: var(--sp-2) var(--sp-3);
  background: var(--fill-1);
  border-radius: var(--r-md);
  font-size: var(--fs-xs);
}
.advanced summary {
  cursor: pointer;
  color: var(--text-3);
  outline: none;
}
.advanced summary:hover { color: var(--text-1); }
.checkbox-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: var(--sp-2);
  color: var(--text-2);
  cursor: pointer;
}
.checkbox-row input { cursor: pointer; }

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--sp-2);
  margin-top: var(--sp-4);
}

.modal-security {
  display: flex;
  align-items: flex-start;
  gap: 6px;
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
