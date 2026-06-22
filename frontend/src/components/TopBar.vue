<template>
  <header class="topbar">
    <div class="topbar-inner">
      <!-- 品牌 -->
      <div class="brand">
        <svg class="brand-icon" viewBox="0 0 32 32" fill="none">
          <circle cx="16" cy="16" r="3" fill="currentColor" />
          <circle cx="16" cy="16" r="8" stroke="currentColor" stroke-width="1.5" opacity=".55" />
          <circle cx="16" cy="16" r="13" stroke="currentColor" stroke-width="1.5" opacity=".3" />
          <path d="M16 3 L16 9 M16 23 L16 29 M3 16 L9 16 M23 16 L29 16" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" opacity=".4" />
          <path d="M22 10 L16 16" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
        </svg>
        <div class="brand-text">
          <span class="brand-name">声浪雷达</span>
          <span class="brand-sub">B站舆情分析</span>
        </div>
      </div>

      <!-- 右侧操作 -->
      <div class="topbar-actions">
        <!-- 功能图标 -->
        <button
          class="icon-btn"
          :class="{ 'icon-btn-active': alertConfigured }"
          aria-label="告警配置"
          title="Webhook 告警配置"
          @click="$emit('open-alert')"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M13.73 21a2 2 0 0 1-3.46 0" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <span v-if="alertConfigured" class="icon-dot"></span>
        </button>

        <button
          class="icon-btn"
          aria-label="设置"
          title="LLM 配置"
          @click="$emit('open-settings')"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>

        <button
          class="icon-btn"
          :aria-label="theme === 'dark' ? '切换到浅色' : '切换到深色'"
          :title="theme === 'dark' ? '浅色模式' : '深色模式'"
          @click="toggle"
        >
          <svg v-if="theme === 'dark'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="4" />
            <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" stroke-linecap="round" />
          </svg>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" stroke-linejoin="round" />
          </svg>
        </button>

        <!-- 分隔线 -->
        <span class="action-divider"></span>

        <!-- B站登录状态 -->
        <span v-if="loggedIn" :class="['badge', 'badge-success', 'badge-dot']">
          B站 · UID {{ uid }}
        </span>
        <button v-else class="btn btn-sm" @click="$emit('open-login')">登录 B站</button>

        <!-- 小红书登录状态 -->
        <span v-if="xhsLoggedIn" :class="['badge', 'badge-success', 'badge-dot']">
          小红书已登录
        </span>
        <button v-else class="btn btn-sm btn-secondary" @click="$emit('open-xhs-login')">登录 小红书</button>

        <!-- 退出按钮（任一平台登录后显示，最右侧）- 点击展开下拉菜单 -->
        <div v-if="loggedIn || xhsLoggedIn" class="logout-wrap">
          <button class="btn btn-sm btn-secondary" @click.stop="logoutMenuOpen = !logoutMenuOpen">
            退出
            <svg class="caret" :class="{ 'caret-open': logoutMenuOpen }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </button>
          <transition name="logout-menu">
            <div v-if="logoutMenuOpen" class="logout-menu" @click.stop>
              <div class="logout-menu-header">选择要退出的平台</div>
              <button v-if="loggedIn" class="logout-menu-item" @click="onLogoutBili">
                <span class="logout-menu-icon bili">B</span>
                <span class="logout-menu-text">
                  <span class="logout-menu-title">退出 B站</span>
                  <span class="logout-menu-desc">UID {{ uid }}</span>
                </span>
              </button>
              <button v-if="xhsLoggedIn" class="logout-menu-item" @click="onLogoutXhs">
                <span class="logout-menu-icon xhs">红</span>
                <span class="logout-menu-text">
                  <span class="logout-menu-title">退出 小红书</span>
                  <span class="logout-menu-desc">清除已保存的 Cookie</span>
                </span>
              </button>
              <button class="logout-menu-item logout-menu-cancel" @click="logoutMenuOpen = false">
                <span class="logout-menu-text">取消</span>
              </button>
            </div>
          </transition>
        </div>
      </div>
    </div>
  </header>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useTheme } from '../composables/useTheme'

defineProps({
  loggedIn: Boolean,
  uid: { type: String, default: '' },
  alertConfigured: { type: Boolean, default: false },
  xhsLoggedIn: { type: Boolean, default: false },
})
const emit = defineEmits(['open-login', 'open-settings', 'open-alert', 'logout', 'logout-xhs', 'open-xhs-login'])

const { theme, toggle } = useTheme()

// 退出下拉菜单
const logoutMenuOpen = ref(false)

function onLogoutBili() {
  logoutMenuOpen.value = false
  emit('logout')
}
function onLogoutXhs() {
  logoutMenuOpen.value = false
  emit('logout-xhs')
}

// 点击外部关闭下拉菜单
function onDocClick() {
  logoutMenuOpen.value = false
}
onMounted(() => document.addEventListener('click', onDocClick))
onUnmounted(() => document.removeEventListener('click', onDocClick))
</script>

<style scoped>
.topbar {
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
  background: color-mix(in srgb, var(--bg-card) 82%, transparent);
  backdrop-filter: saturate(180%) blur(12px);
  -webkit-backdrop-filter: saturate(180%) blur(12px);
  border-bottom: 1px solid var(--border-1);
  transition: background var(--t-base), border-color var(--t-base);
}
.topbar-inner {
  width: min(1200px, calc(100% - 40px));
  height: 60px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-4);
}
.brand { display: flex; align-items: center; gap: var(--sp-3); }
.brand-icon {
  width: 32px; height: 32px;
  color: var(--brand);
  flex-shrink: 0;
}
.brand-text { display: flex; flex-direction: column; line-height: 1.15; }
.brand-name {
  font-size: var(--fs-md);
  font-weight: 700;
  letter-spacing: -.01em;
  color: var(--text-1);
}
.brand-sub {
  font-size: 11px;
  color: var(--text-3);
  letter-spacing: .02em;
}
.topbar-actions { display: flex; align-items: center; gap: var(--sp-3); }
.action-divider {
  width: 1px;
  height: 20px;
  background: var(--border-1);
  margin: 0 var(--sp-1);
}
.icon-btn {
  width: 32px; height: 32px;
  display: inline-flex; align-items: center; justify-content: center;
  border-radius: var(--r-md);
  color: var(--text-2);
  background: transparent;
  border: 1px solid transparent;
  transition: all var(--t-fast);
}
.icon-btn:hover { background: var(--fill-1); color: var(--text-1); }
.icon-btn svg { width: 18px; height: 18px; }
.icon-btn-active { color: var(--warning); }
.icon-btn-active:hover { color: var(--warning); background: color-mix(in srgb, var(--warning) 12%, transparent); }
.icon-dot {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--success);
  border: 2px solid var(--bg-card);
}
.icon-btn { position: relative; }

@media (max-width: 480px) {
  .topbar-inner { height: auto; padding: var(--sp-3) 0; flex-direction: column; align-items: stretch; gap: var(--sp-3); }
  .topbar-actions { justify-content: space-between; }
  .brand-sub { display: none; }
}

/* 退出下拉菜单 */
.logout-wrap { position: relative; display: inline-flex; }
.caret {
  width: 14px; height: 14px;
  margin-left: 4px;
  transition: transform var(--t-fast);
}
.caret-open { transform: rotate(180deg); }
.logout-menu {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  min-width: 240px;
  background: var(--bg-card);
  border: 1px solid var(--border-1);
  border-radius: var(--r-lg);
  box-shadow: 0 8px 24px rgba(0,0,0,.12), 0 2px 8px rgba(0,0,0,.06);
  padding: var(--sp-2);
  z-index: var(--z-dropdown, 1000);
}
.logout-menu-header {
  font-size: 12px;
  color: var(--text-3);
  padding: var(--sp-1) var(--sp-2) var(--sp-2);
  border-bottom: 1px solid var(--border-1);
  margin-bottom: var(--sp-1);
}
.logout-menu-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-2);
  border: none;
  background: transparent;
  border-radius: var(--r-md);
  cursor: pointer;
  text-align: left;
  transition: background var(--t-fast);
}
.logout-menu-item:hover { background: var(--fill-1); }
.logout-menu-icon {
  width: 32px; height: 32px;
  display: inline-flex; align-items: center; justify-content: center;
  border-radius: var(--r-md);
  font-size: 14px;
  font-weight: 700;
  color: #fff;
  flex-shrink: 0;
}
.logout-menu-icon.bili { background: #fb7299; }
.logout-menu-icon.xhs { background: #ff2442; }
.logout-menu-text { display: flex; flex-direction: column; gap: 2px; }
.logout-menu-title { font-size: var(--fs-sm); font-weight: 600; color: var(--text-1); }
.logout-menu-desc { font-size: 11px; color: var(--text-3); }
.logout-menu-cancel {
  justify-content: center;
  margin-top: var(--sp-1);
  border-top: 1px solid var(--border-1);
  border-radius: 0 0 var(--r-lg) var(--r-lg);
  padding-top: var(--sp-2);
}
.logout-menu-cancel .logout-menu-text { align-items: center; color: var(--text-2); font-size: var(--fs-sm); }

/* 下拉菜单过渡动画 */
.logout-menu-enter-active, .logout-menu-leave-active {
  transition: opacity var(--t-fast), transform var(--t-fast);
}
.logout-menu-enter-from, .logout-menu-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
