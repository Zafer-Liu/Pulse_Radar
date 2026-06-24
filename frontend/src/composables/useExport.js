/**
 * useExport · 分析结果导出
 *
 * 提供两种导出方式：
 * 1. exportPDF(elementId)    —— 仅打印指定结果区域，便于直接另存为 PDF
 * 2. exportImage(elementId)  —— 用 html2canvas 把指定区域渲染为 PNG 图片下载
 *
 * html2canvas 采用按需动态加载（CDN），不增加构建依赖；加载失败时自动降级为打印。
 */
import { toast } from './useToast'

let _html2canvasPromise = null

function loadHtml2Canvas() {
  if (window.html2canvas) return Promise.resolve(window.html2canvas)
  if (_html2canvasPromise) return _html2canvasPromise
  _html2canvasPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script')
    // 同时备用两个 CDN
    script.src = 'https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js'
    script.onload = () => resolve(window.html2canvas)
    script.onerror = () => {
      // 主 CDN 失败，尝试备用
      const s2 = document.createElement('script')
      s2.src = 'https://unpkg.com/html2canvas@1.4.1/dist/html2canvas.min.js'
      s2.onload = () => resolve(window.html2canvas)
      s2.onerror = () => { _html2canvasPromise = null; reject(new Error('html2canvas 加载失败')) }
      document.head.appendChild(s2)
    }
    document.head.appendChild(script)
  })
  return _html2canvasPromise
}

function ts() {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}`
}

function buildExportFileName(fileName = '声浪雷达分析') {
  return `${fileName}_${ts()}`
}

function cloneWithCanvasSnapshot(el) {
  const clone = el.cloneNode(true)
  const sourceCanvases = el.querySelectorAll('canvas')
  const clonedCanvases = clone.querySelectorAll('canvas')
  sourceCanvases.forEach((canvas, idx) => {
    const target = clonedCanvases[idx]
    if (!target) return
    try {
      const img = document.createElement('img')
      img.src = canvas.toDataURL('image/png')
      img.style.width = `${canvas.offsetWidth || canvas.width}px`
      img.style.height = `${canvas.offsetHeight || canvas.height}px`
      img.style.display = 'block'
      img.style.maxWidth = '100%'
      target.replaceWith(img)
    } catch {
      // 跨域 canvas 无法转图时保留原样
    }
  })
  return clone
}

function collectHeadMarkup() {
  const styles = Array.from(document.querySelectorAll('style'))
    .map((node) => node.outerHTML)
    .join('\n')
  const links = Array.from(document.querySelectorAll('link[rel="stylesheet"]'))
    .map((node) => node.outerHTML)
    .join('\n')
  return `${links}\n${styles}`
}

/** 从当前主题读取实际背景色（兼容 CSS 变量 + 计算样式） */
function getPageBg() {
  // 先从 :root 读 CSS 变量
  const rootStyle = getComputedStyle(document.documentElement)
  const varVal = rootStyle.getPropertyValue('--bg-page').trim()
  if (varVal && varVal !== 'transparent') return varVal
  // 兜底：取 body 的 background-color
  const bodyBg = getComputedStyle(document.body).backgroundColor
  if (bodyBg && bodyBg !== 'transparent' && bodyBg !== 'rgba(0, 0, 0, 0)') return bodyBg
  return '#ffffff'
}

export function useExport() {
  /** 打印导出：仅打印指定结果区域，便于直接另存为 PDF */
  function exportPDF(elementId, fileName = '声浪雷达分析') {
    const el = document.getElementById(elementId)
    if (!el) {
      toast.error('未找到要导出的内容区域，请确认结果已加载')
      return
    }

    const printWindow = window.open('', '_blank', 'noopener,noreferrer,width=1280,height=900')
    if (!printWindow) {
      toast.warning('浏览器拦截了新窗口，已切换为当前页打印')
      setTimeout(() => window.print(), 120)
      return
    }

    const exportName = buildExportFileName(fileName)
    const clone = cloneWithCanvasSnapshot(el)
    const wrapper = document.createElement('div')
    wrapper.className = 'wb-print-shell'
    wrapper.appendChild(clone)

    const extraStyles = `
      <style>
        :root { color-scheme: light; }
        body { margin: 0; background: #ffffff; color: #111827; }
        .wb-print-shell { max-width: 1200px; margin: 0 auto; padding: 24px; box-sizing: border-box; }
        .no-print { display: none !important; }
        main, .wrap { margin: 0 !important; padding: 0 !important; }
        .card, .compare-quality-card, .topic-quality-card, .monitor-section {
          box-shadow: none !important;
          break-inside: avoid;
          page-break-inside: avoid;
        }
        img { max-width: 100%; }
        @page { size: A4 portrait; margin: 14mm; }
      </style>
    `

    printWindow.document.open()
    printWindow.document.write(`<!DOCTYPE html><html><head><meta charset="utf-8" /><title>${exportName}</title>${collectHeadMarkup()}${extraStyles}</head><body>${wrapper.outerHTML}</body></html>`)
    printWindow.document.close()

    toast.info('已生成打印预览窗口，可直接另存为 PDF')
    const finalize = () => {
      printWindow.focus()
      setTimeout(() => {
        printWindow.print()
      }, 180)
    }
    if (printWindow.document.readyState === 'complete') {
      finalize()
    } else {
      printWindow.onload = finalize
    }
  }

  /** 图片导出：把指定元素渲染为 PNG 下载 */
  async function exportImage(elementId, fileName = '声浪雷达分析') {
    const el = document.getElementById(elementId)
    if (!el) {
      toast.error('未找到要导出的内容区域，请确认结果已加载')
      return
    }
    const toastId = toast.info('正在生成图片（ECharts 图表需要约 2 秒），请稍候…', 0)
    try {
      const html2canvas = await loadHtml2Canvas()
      const bg = getPageBg()

      // 将 ECharts canvas 转为 image 临时替换，避免跨域问题
      const echarts = el.querySelectorAll('canvas')
      const replacements = []
      echarts.forEach(c => {
        try {
          const img = document.createElement('img')
          img.src = c.toDataURL('image/png')
          img.style.width = c.style.width || c.offsetWidth + 'px'
          img.style.height = c.style.height || c.offsetHeight + 'px'
          img.style.display = 'block'
          c.parentNode.insertBefore(img, c)
          c.style.display = 'none'
          replacements.push({ canvas: c, img })
        } catch (e) { /* 跨域 canvas 跳过 */ }
      })

      const canvas = await html2canvas(el, {
        backgroundColor: bg,
        scale: Math.min(2, window.devicePixelRatio || 1.5),
        useCORS: true,
        allowTaint: true,
        logging: false,
        width: el.scrollWidth,
        height: el.scrollHeight,
        windowWidth: document.documentElement.scrollWidth,
        windowHeight: document.documentElement.scrollHeight,
        scrollX: -window.scrollX,
        scrollY: -window.scrollY,
        ignoreElements: (node) => node.classList?.contains('no-print'),
      })

      // 还原 ECharts canvas
      replacements.forEach(({ canvas: c, img }) => {
        c.style.display = ''
        img.parentNode?.removeChild(img)
      })

      toast.remove(toastId)
      canvas.toBlob((blob) => {
        if (!blob) { toast.error('图片生成失败，请尝试 PDF 导出'); return }
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `${buildExportFileName(fileName)}.png`
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        setTimeout(() => URL.revokeObjectURL(url), 1000)
        toast.success('图片已保存')
      }, 'image/png')
    } catch (err) {
      toast.remove(toastId)
      toast.warning('图片导出遇到问题，已切换为打印方式（可另存为 PDF）')
      exportPDF(elementId, fileName)
    }
  }

  return { exportPDF, exportImage }
}

