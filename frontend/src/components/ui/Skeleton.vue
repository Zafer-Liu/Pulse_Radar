<template>
  <div class="skeleton-wrap" :class="{ inline }">
    <div v-for="n in rows" :key="n" class="skeleton skeleton-text" :style="{ width: rowWidth(n) }"></div>
  </div>
</template>

<script setup>
const props = defineProps({
  rows: { type: Number, default: 3 },
  inline: { type: Boolean, default: false },
})
function rowWidth(n) {
  if (n === props.rows) return '60%'
  const widths = ['100%', '92%', '85%', '70%']
  return widths[(n - 1) % widths.length]
}
</script>

<style scoped>
.skeleton-wrap { width: 100%; }
.skeleton-wrap.inline { display: inline-block; }
</style>
