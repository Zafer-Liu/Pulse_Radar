<template>
  <transition name="modal-fade">
    <div
      v-if="show"
      class="modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="alert-modal-title"
      @keydown.esc="$emit('close')"
    >
      <div class="modal-mask" @click="$emit('close')"></div>
      <div class="modal-card alert-card" ref="cardRef" tabindex="-1">
        <div class="modal-head">
          <div>
            <h3 id="alert-modal-title">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16" style="vertical-align:-3px;color:var(--warning)">
                <path d="M8 1.5L1.5 13.5h13L8 1.5z" stroke-linejoin="round"/>
                <path d="M8 6v3.5" stroke-linecap="round"/>
                <circle cx="8" cy="11.5" r="0.5" fill="currentColor"/>
              </svg>
              告警通知配置
            </h3>
            <p class="modal-tip" style="margin:4px 0 0">配置 Webhook 后，监测任务检测到高风险时会自动推送到飞书/钉钉/企业微信群。配置写入 .env 立即生效。</p>
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
          <div :class="['status-banner', config.configured ? 'status-ok' : 'status-warn']">
            <svg v-if="config.configured" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M3 8l3.5 3.5L13 5" stroke-linecap="round" stroke-linejoin="round"/></svg>
            <svg v-else viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><circle cx="8" cy="8" r="6.5"/><path d="M8 5v3.5" stroke-linecap="round"/></svg>
            <span v-if="config.configured">告警已启用 · 平台 {{ platformLabel }} · 阈值 {{ form.minRisk }}</span>
            <span v-else>告警未启用 · 高风险时不会推送通知</span>
          </div>

          <!-- 平台预设按钮 -->
          <div class="preset-row">
            <span class="preset-label">平台：</span>
            <button
              v-for="p in platforms"
              :key="p.key"
              :class="['preset-btn', { active: config.platform === p.key }]"
              @click="applyPlatform(p)"
            >{{ p.label }}</button>
          </div>

          <!-- 表单 -->
          <div class="form-grid">
            <div class="form-row">
              <label for="alert-webhook">Webhook 地址</label>
              <input
                id="alert-webhook"
                type="text"
                v-model="form.webhookUrl"
                placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
                spellcheck="false"
              />
              <p class="form-hint">粘贴机器人的完整 Webhook URL，系统会自动识别平台格式</p>
            </div>

            <div class="form-row">
              <label for="alert-risk">触发阈值</label>
              <select id="alert-risk" v-model="form.minRisk">
                <option value="low">低风险及以上（所有检测都推送）</option>
                <option value="medium">中风险及以上</option>
                <option value="high">仅高风险（推荐）</option>
              </select>
            </div>

            <div class="form-row">
              <label for="alert-cooldown">冷却时间（秒）</label>
              <input id="alert-cooldown" type="number" v-model.number="form.cooldown" min="60" max="86400" step="60" />
              <p class="form-hint">同一任务在冷却期内不重复告警，默认 3600（1 小时）</p>
            </div>
          </div>

          <!-- 操作 -->
          <div class="modal-actions">
            <button
              class="btn btn-sm btn-secondary"
              :disabled="!form.webhookUrl || testing"
              @click="onTest"
            >
              <span v-if="testing" class="spinner" style="width:12px;height:12px;border-width:2px;vertical-align:-1px"></span>
              {{ testing ? '发送中…' : '发送测试' }}
            </button>
            <button class="btn btn-sm btn-secondary" @click="$emit('close')">取消</button>
            <button
              class="btn btn-sm"
              :disabled="saving"
              @click="onSave"
            >
              <span v-if="saving" class="spinner" style="width:12px;height:12px;border-width:2px;vertical-align:-1px"></span>
              {{ saving ? '保存中…' : '保存配置' }}
            </button>
          </div>

          <div class="modal-security">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" width="13" height="13"><path d="M8 1l5 2v5c0 3-2 5-5 6-3-1-5-3-5-6V3z" stroke-linejoin="round"/></svg>
            配置仅写入本机 .env 文件（已被 .gitignore 忽略）。Webhook 地址不发送任何第三方。
          </div>

          <!-- 平台申请教程 -->
          <details class="help-section">
            <summary>如何获取 Webhook 地址？</summary>
            <div class="help-content">
              <div class="help-item">
                <strong>飞书</strong>
                <p>群设置 → 群机器人 → 添加机器人 → 自定义机器人 → 复制 Webhook 地址</p>
              </div>
              <div class="help-item">
                <strong>钉钉</strong>
                <p>群设置 → 智能群助手 → 添加机器人 → 自定义 → 安全设置选"加签" → 复制 Webhook 地址</p>
              </div>
              <div class="help-item">
                <strong>企业微信</strong>
                <p>群聊 → 右上角 → 群机器人 → 添加机器人 → 复制 Webhook 地址</p>
              </div>
            </div>
          </details>
        </template>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { ref, reactive, watch, nextTick, computed } from 'vue'
import { getAlertConfig, saveAlertConfig, testAlert } from '../api'
import { toast } from '../composables/useToast'

const props = defineProps({
  show: Boolean,
})
const emit = defineEmits(['close', 'saved'])

const cardRef = ref(null)
const loading = ref(false)
const saving = ref(false)
const testing = ref(false)

const config = reactive({
  configured: false,
  webhookUrl: '',
  minRisk: 'high',
  cooldown: 3600,
  platform: 'none',
})

const form = reactive({
  webhookUrl: '',
  minRisk: 'high',
  cooldown: 3600,
})

const platforms = [
  { key: 'feishu', label: '飞书', url: 'https://open.feishu.cn/open-apis/bot/v2/hook/' },
  { key: 'dingtalk', label: '钉钉', url: 'https://oapi.dingtalk.com/robot/send?access_token=' },
  { key: 'wecom', label: '企业微信', url: 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=' },
]

const platformLabel = computed(() => {
  const map = { feishu: '飞书', dingtalk: '钉钉', wecom: '企业微信', generic: '通用', none: '未配置' }
  return map[config.platform] || '通用'
})

function applyPlatform(p) {
  // 只填充前缀，用户需要补全 token
  if (!form.webhookUrl || !form.webhookUrl.startsWith(p.url)) {
    form.webhookUrl = p.url
    toast.info(`已填入${p.label}地址前缀，请补全机器人 token`)
  }
}

async function loadConfig() {
  loading.value = true
  try {
    const res = await getAlertConfig()
    const d = res
    config.configured = d.configured
    config.webhookUrl = d.webhookUrl || ''
    config.minRisk = d.minRisk || 'high'
    config.cooldown = d.cooldown || 3600
    config.platform = d.platform || 'none'
    form.webhookUrl = d.webhookUrl || ''
    form.minRisk = d.minRisk || 'high'
    form.cooldown = d.cooldown || 3600
  } catch (err) {
    toast.error(err.message || '加载配置失败')
  } finally {
    loading.value = false
  }
}

async function onSave() {
  saving.value = true
  try {
    const payload = {
      webhookUrl: form.webhookUrl.trim(),
      minRisk: form.minRisk,
      cooldown: form.cooldown,
    }
    const res = await saveAlertConfig(payload)
    if (res.configured) {
      toast.success('告警配置已保存并生效')
    } else {
      toast.info('已清空告警配置')
    }
    config.configured = res.configured
    emit('saved', res)
    emit('close')
  } catch (err) {
    toast.error(err.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function onTest() {
  testing.value = true
  try {
    // 先保存再测试
    await saveAlertConfig({
      webhookUrl: form.webhookUrl.trim(),
      minRisk: form.minRisk,
      cooldown: form.cooldown,
    })
    const res = await testAlert()
    if (res.sent) {
      toast.success(`测试告警已发送（${res.platform}），请检查群消息`)
    } else {
      toast.warning(res.message || '发送失败，请检查 Webhook 地址')
    }
  } catch (err) {
    toast.error(err.message || '测试失败')
  } finally {
    testing.value = false
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
.alert-card {
  width: min(540px, calc(100% - 32px));
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
.form-row input,
.form-row select {
  padding: 8px 10px;
  font-size: var(--fs-sm);
  border: 1px solid var(--border-1);
  border-radius: var(--r-md);
  background: var(--bg-card);
  color: var(--text-1);
  transition: border-color var(--t-fast), box-shadow var(--t-fast);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
.form-row select {
  font-family: inherit;
  cursor: pointer;
}
.form-row input:focus,
.form-row select:focus {
  outline: none;
  border-color: var(--brand);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--brand) 15%, transparent);
}

.form-hint {
  font-size: 11px;
  color: var(--text-3);
  margin-top: 2px;
}

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

.help-section {
  margin-top: var(--sp-3);
  padding: var(--sp-2) var(--sp-3);
  background: var(--fill-1);
  border-radius: var(--r-md);
  font-size: var(--fs-xs);
}
.help-section summary {
  cursor: pointer;
  color: var(--text-3);
  outline: none;
}
.help-section summary:hover { color: var(--text-1); }
.help-content {
  margin-top: var(--sp-2);
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.help-item strong {
  color: var(--text-1);
  font-weight: 600;
}
.help-item p {
  margin: 2px 0 0;
  color: var(--text-3);
  line-height: var(--lh-base);
}

.spinner { display: inline-block; border: 2px solid var(--border-1); border-top-color: var(--brand-2); border-radius: 50%; animation: spin .7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.modal-fade-enter-active, .modal-fade-leave-active { transition: opacity var(--t-base); }
.modal-fade-enter-from, .modal-fade-leave-to { opacity: 0; }
</style>
