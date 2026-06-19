<template>
  <canvas ref="canvasRef" class="bg-particles" aria-hidden="true"></canvas>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'

const canvasRef = ref(null)

let ctx = null
let rafId = null
let particles = []
let width = 0
let height = 0
let dpr = 1
let resizeObserver = null
let mutationObserver = null
let currentColor = '0, 47, 167'
let mouse = { x: -9999, y: -9999, active: false }

function readThemeColor() {
  const brand = getComputedStyle(document.documentElement)
    .getPropertyValue('--brand')
    .trim()
  const hex = brand.startsWith('#') ? brand : '#002FA7'
  const r = parseInt(hex.slice(1, 3), 16) || 0
  const g = parseInt(hex.slice(3, 5), 16) || 47
  const b = parseInt(hex.slice(5, 7), 16) || 167
  return `${r}, ${g}, ${b}`
}

function pickParticleColor() {
  // 70% 主色(半透) / 30% 中性灰
  return Math.random() < 0.7 ? currentColor : '150, 160, 175'
}

function createParticles() {
  // 中等密度：每 18000px 一个粒子，上限 100 个
  const target = Math.min(100, Math.max(40, Math.floor((width * height) / 18000)))
  particles = []
  for (let i = 0; i < target; i++) {
    particles.push({
      x: Math.random() * width,
      y: Math.random() * height,
      vx: (Math.random() - 0.5) * 0.18,
      vy: (Math.random() - 0.5) * 0.18,
      r: Math.random() * 1.6 + 0.5,     // 0.5 - 2.1
      baseAlpha: Math.random() * 0.25 + 0.15, // 0.15 - 0.40
      phase: Math.random() * Math.PI * 2,
      color: pickParticleColor(),
    })
  }
}

function resize() {
  const canvas = canvasRef.value
  if (!canvas) return
  dpr = window.devicePixelRatio || 1
  width = window.innerWidth
  height = window.innerHeight
  canvas.width = Math.floor(width * dpr)
  canvas.height = Math.floor(height * dpr)
  canvas.style.width = width + 'px'
  canvas.style.height = height + 'px'
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  createParticles()
}

const ATTRACT_RADIUS = 200

function draw() {
  ctx.clearRect(0, 0, width, height)
  const now = performance.now() * 0.001

  for (let i = 0; i < particles.length; i++) {
    const p = particles[i]

    // 温和跟随：鼠标附近的粒子被轻轻吸引
    if (mouse.active) {
      const dx = mouse.x - p.x
      const dy = mouse.y - p.y
      const distSq = dx * dx + dy * dy
      if (distSq < ATTRACT_RADIUS * ATTRACT_RADIUS && distSq > 400) {
        const dist = Math.sqrt(distSq)
        // 越近吸力越强，线性衰减
        const force = Math.max(0, 1 - dist / ATTRACT_RADIUS) * 0.08
        p.vx += (dx / dist) * force
        p.vy += (dy / dist) * force
      }
    }

    // 阻尼
    p.vx *= 0.95
    p.vy *= 0.95

    // 限速
    const sp = Math.sqrt(p.vx * p.vx + p.vy * p.vy)
    if (sp > 1.5) {
      p.vx = (p.vx / sp) * 1.5
      p.vy = (p.vy / sp) * 1.5
    }

    p.x += p.vx
    p.y += p.vy

    // 边界穿越
    if (p.x < -10) p.x = width + 10
    else if (p.x > width + 10) p.x = -10
    if (p.y < -10) p.y = height + 10
    else if (p.y > height + 10) p.y = -10

    // 呼吸透明度
    const alpha = p.baseAlpha + Math.sin(now * 0.8 + p.phase) * 0.08

    // 核心
    ctx.beginPath()
    ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
    ctx.fillStyle = `rgba(${p.color}, ${alpha})`
    ctx.fill()

    // 较大粒子加柔光晕
    if (p.r > 1.2) {
      const glowR = p.r * 2.8
      const grd = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, glowR)
      grd.addColorStop(0, `rgba(${p.color}, ${alpha * 0.2})`)
      grd.addColorStop(1, `rgba(${p.color}, 0)`)
      ctx.fillStyle = grd
      ctx.beginPath()
      ctx.arc(p.x, p.y, glowR, 0, Math.PI * 2)
      ctx.fill()
    }
  }

  rafId = requestAnimationFrame(draw)
}

function onMouseMove(e) {
  mouse.x = e.clientX
  mouse.y = e.clientY
  mouse.active = true
}
function onMouseLeave() {
  mouse.active = false
  mouse.x = -9999
  mouse.y = -9999
}

function start() {
  const canvas = canvasRef.value
  if (!canvas) return
  ctx = canvas.getContext('2d', { alpha: true })
  currentColor = readThemeColor()
  resize()

  mutationObserver = new MutationObserver(() => {
    currentColor = readThemeColor()
    for (const p of particles) p.color = pickParticleColor()
  })
  mutationObserver.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['data-theme'],
  })

  resizeObserver = new ResizeObserver(resize)
  resizeObserver.observe(document.documentElement)

  window.addEventListener('mousemove', onMouseMove, { passive: true })
  window.addEventListener('mouseleave', onMouseLeave)
  window.addEventListener('resize', resize)

  if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    rafId = requestAnimationFrame(draw)
  } else {
    draw()
    cancelAnimationFrame(rafId)
    rafId = null
  }
}

function stop() {
  if (rafId) cancelAnimationFrame(rafId)
  rafId = null
  if (resizeObserver) resizeObserver.disconnect()
  resizeObserver = null
  if (mutationObserver) mutationObserver.disconnect()
  mutationObserver = null
  window.removeEventListener('mousemove', onMouseMove)
  window.removeEventListener('mouseleave', onMouseLeave)
  window.removeEventListener('resize', resize)
}

onMounted(start)
onBeforeUnmount(stop)
</script>

<style scoped>
.bg-particles {
  position: fixed;
  inset: 0;
  width: 100vw;
  height: 100vh;
  pointer-events: none;
  z-index: 0;
}
</style>
