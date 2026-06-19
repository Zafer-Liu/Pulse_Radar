<template>
  <div class="empty-state">
    <svg class="empty-icon" viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="1.5">
      <rect x="10" y="14" width="44" height="36" rx="4" />
      <path d="M10 24h44M20 34h16M20 42h12" stroke-linecap="round" />
      <circle cx="48" cy="40" r="6" stroke-dasharray="3 3" />
    </svg>
    <div class="empty-title">{{ title }}</div>
    <div class="empty-desc">{{ description }}</div>
    <slot />
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, default: '暂无数据' },
  description: { type: String, default: '' },
})
</script>
