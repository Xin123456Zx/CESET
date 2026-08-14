<template>
  <div class="h-full flex flex-col">
    <div class="flex items-center justify-between px-2 pb-1">
      <div class="text-[12.5px] text-gray-400">
        x = mean, y = std (log10 ρ) · point size = w90 spread · colour =
        {{ colorBy === 'split' ? 'INR data split (legend →)' : colorBy === 'cluster' ? 'statistical cluster (legend →)' : colorBy }}
        · dashed = 90% ellipse · red ring = outlier
      </div>
      <!-- The two outlier scores are complementary; expose them as a toggleable border encoding (README design) -->
      <el-radio-group v-model="outlierMode" size="small">
        <el-radio-button value="maha">statistical outlier</el-radio-button>
        <el-radio-button value="struct">structural outlier</el-radio-button>
      </el-radio-group>
    </div>
    <!-- min-h-0 lets flex shrinking take effect; height is fully driven by the parent card, so the canvas no longer overflows -->
    <div ref="chartRef" class="flex-1 min-h-0 overflow-hidden"></div>
  </div>
</template>

<script setup lang="ts">
import * as echarts from 'echarts'
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'

const props = defineProps<{
  members: any[]
  summary: any
  histograms: any
  selectedId: number | null
  brushedIds: Set<number> | null   // filters ∩ PCP axis brush; null = all visible
  colorBy: string                  // 'split'/'cluster' = categorical coloring; h/OmM/OmB/w90 = continuous coloring
  categories: { label: string; color: string; count: number }[]   // category metadata (split roles or k-means clusters)
  catKey: string                   // category field name on members ('_role' / '_cluster'); empty = continuous mode
}>()
const emit = defineEmits<{ (e: 'select', id: number): void }>()

const chartRef = ref<HTMLDivElement>()
const outlierMode = ref<'maha' | 'struct'>('maha')
let chart: echarts.ECharts | undefined
let ro: ResizeObserver | undefined

const OUTLIER_THRESH = { maha: 2.146, struct: 2.5 }

// Continuous mode: single-hue gradient (sequential blue ramp, passes the dataviz validator)
const SEQ_RAMP = ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95', '#0d366b']

const isOutlier = (m: any) =>
  outlierMode.value === 'maha' ? m.outlier_maha > OUTLIER_THRESH.maha
                               : m.outlier_struct > OUTLIER_THRESH.struct

// Sample the 90% ellipse as a polygon in data coordinates (x/y scales differ, so pixel-space rotation would distort it; sampling is mathematically correct)
const ellipsePoints = () => {
  const e = props.summary.ellipse90
  const th = (e.angle_deg * Math.PI) / 180
  const pts: number[][] = []
  for (let i = 0; i <= 100; i++) {
    const t = (i / 100) * 2 * Math.PI
    const ex = e.semi_axes[0] * Math.cos(t), ey = e.semi_axes[1] * Math.sin(t)
    pts.push([e.center[0] + ex * Math.cos(th) - ey * Math.sin(th),
              e.center[1] + ex * Math.sin(th) + ey * Math.cos(th)])
  }
  return pts
}

// Mini histogram for the tooltip (64 bins → inline SVG area chart)
const miniHist = (id: number) => {
  const counts = props.histograms?.counts?.[id]
  if (!counts) return ''
  const w = 140, h = 34, max = Math.max(...counts)
  const pts = counts.map((c: number, i: number) =>
    `${(i / (counts.length - 1)) * w},${h - (c / max) * h}`).join(' ')
  return `<svg width="${w}" height="${h}" style="display:block;margin-top:4px">
    <polygon points="0,${h} ${pts} ${w},${h}" fill="#6da7ec" opacity="0.55"/></svg>`
}

const fmt = (v: number, d = 3) => v == null ? '-' : Number(v).toFixed(d)

const tooltipFmt = (p: any) => {
  const m = p.data?.id != null ? props.members.find(x => x.id === p.data.id) : null
  if (!m) return ''
  const cl = props.catKey ? props.categories[m[props.catKey]] : null
  return `<b>Member #${m.id}</b> <span style="color:#999">${m.dir}</span><br/>
    ${cl ? `<span style="color:${cl.color}">●</span> ${cl.label}<br/>` : ''}
    OmM=${fmt(m.OmM, 4)} · OmB=${fmt(m.OmB, 5)} · h=${fmt(m.h, 4)}<br/>
    mean=${fmt(m.mean)} · median=${fmt(m.median)} · std=${fmt(m.std)}<br/>
    min=${fmt(m.min)} · max=${fmt(m.max)} · range=${fmt(m.range)}<br/>
    q05=${fmt(m.q05)} · q25=${fmt(m.q25)} · q75=${fmt(m.q75)} · q95=${fmt(m.q95)}<br/>
    w90=${fmt(m.w90)} · outlier<sub>maha</sub>=${fmt(m.outlier_maha, 2)} · outlier<sub>struct</sub>=${fmt(m.outlier_struct, 2)}
    ${miniHist(m.id)}`
}

const buildOption = () => {
  const s = props.summary
  const clusterMode = !!props.catKey && props.categories.length > 0
  const w90s = props.members.map(m => m.w90)
  const [w90min, w90max] = [Math.min(...w90s), Math.max(...w90s)]
  // Clamp the size encoding to 5–15px: keeps the w90 contrast without large points swallowing small ones
  const sizeOf = (w: number) => 5 + ((w - w90min) / (w90max - w90min + 1e-12)) * 10

  // Axis range: envelope of the data + 90% ellipse with 8% padding on each side — lets the point cloud fill the canvas
  const ell = ellipsePoints()
  const xsAll = [...props.members.map(m => m.mean), ...ell.map(p => p[0])]
  const ysAll = [...props.members.map(m => m.std), ...ell.map(p => p[1])]
  const [xmin, xmax] = [Math.min(...xsAll), Math.max(...xsAll)]
  const [ymin, ymax] = [Math.min(...ysAll), Math.max(...ysAll)]
  const padX = (xmax - xmin) * 0.08, padY = (ymax - ymin) * 0.08

  const itemOf = (m: any) => {
    const dimmed = props.brushedIds && !props.brushedIds.has(m.id)
    const outlier = isOutlier(m)
    return {
      value: clusterMode ? [m.mean, m.std] : [m.mean, m.std, m[props.colorBy]],
      id: m.id,
      symbolSize: sizeOf(m.w90),
      itemStyle: {
        opacity: dimmed ? 0.05 : 0.85,
        borderColor: outlier ? '#d03b3b' : 'rgba(0,0,0,0.22)',
        borderWidth: outlier ? 2 : 0.6,
      },
    }
  }

  const sel = props.selectedId != null ? props.members.find(m => m.id === props.selectedId) : null

  // Member scatter: cluster mode = one series per cluster (right-side legend toggles visibility, TVCG style);
  //                 continuous mode = single series + visualMap color bar
  const memberSeries = clusterMode
    ? props.categories.map((c, ci) => ({
        id: `members-${ci}`, name: c.label, type: 'scatter', z: 3,
        color: c.color,
        data: props.members.filter(m => m[props.catKey] === ci).map(itemOf),
        emphasis: { itemStyle: { borderColor: '#191919', borderWidth: 2 } },
      }))
    : [{
        id: 'members', type: 'scatter', z: 3,
        data: props.members.map(itemOf),
        emphasis: { itemStyle: { borderColor: '#191919', borderWidth: 2 } },
      }]

  // Mean reference dashed lines are attached to the first member series
  ;(memberSeries[0] as any).markLine = {
    silent: true, symbol: 'none',
    lineStyle: { color: '#aaa', type: 'dashed', width: 1.2 },
    label: { show: false },
    data: [{ xAxis: s.mean_of_member_means }, { yAxis: s.mean_of_member_stds }],
  }

  const cVals = props.members.map(m => m[props.colorBy])

  return {
    animation: false,
    grid: { left: 58, right: clusterMode ? 150 : 86, top: 18, bottom: 42 },
    xAxis: { name: 'mean (log10 ρ)', nameLocation: 'middle', nameGap: 26,
             min: xmin - padX, max: xmax + padX,
             axisLabel: { formatter: (v: number) => v.toFixed(2) },
             axisLine: { lineStyle: { color: '#999' } } },
    yAxis: { name: 'std', nameLocation: 'middle', nameGap: 42,
             min: ymin - padY, max: ymax + padY,
             axisLabel: { formatter: (v: number) => v.toFixed(2) },
             axisLine: { lineStyle: { color: '#999' } } },
    // Cluster mode: right-side categorical legend (click to toggle cluster visibility)
    legend: clusterMode ? {
      orient: 'vertical', right: 0, top: 'middle',
      itemWidth: 12, itemHeight: 12, itemGap: 10,
      data: props.categories.map(c => c.label),
      formatter: (name: string) => name.length > 24 ? name.slice(0, 23) + '…' : name,
      textStyle: { fontSize: 11.5, color: '#52514e' },
    } : undefined,
    // Wheel zoom / drag pan (filterMode none: zooming only changes the viewport, never filters points)
    dataZoom: [
      { type: 'inside', xAxisIndex: 0, filterMode: 'none' },
      { type: 'inside', yAxisIndex: 0, filterMode: 'none' },
    ],
    // Continuous mode: right-side continuous color bar (shares the same variable with the PCP)
    visualMap: clusterMode ? undefined : {
      type: 'continuous', dimension: 2, seriesIndex: 0,
      min: Math.min(...cVals), max: Math.max(...cVals), calculable: false,
      inRange: { color: SEQ_RAMP },
      right: 6, top: 'middle', itemWidth: 12, itemHeight: 130,
      text: [props.colorBy, ''],
      textStyle: { fontSize: 11, color: '#52514e' },
      precision: 3,
    },
    tooltip: { trigger: 'item', confine: true, formatter: tooltipFmt },
    series: [
      ...memberSeries,
      { // 90% Gaussian ellipse (dashed polygon)
        id: 'ellipse', type: 'custom', silent: true, z: 2,
        renderItem: (_p: any, api: any) => ({
          type: 'polygon',
          points: ellipsePoints().map(pt => api.coord(pt)),
          style: { fill: 'none', stroke: '#9a9a9a', lineDash: [6, 4], lineWidth: 1.5 },
        }),
        // Placeholder at the ellipse center, so the axis range isn't dragged to 0
        data: [[s.ellipse90.center[0], s.ellipse90.center[1]]],
      },
      { // Selected member: EQUINE-style large dot with black ring (magenta, same color as the info card's #id, avoids amber/red rings)
        id: 'selected', type: 'scatter', silent: true, z: 4,
        symbolSize: sel ? sizeOf(sel.w90) + 8 : 0,
        itemStyle: { color: '#d6336c', borderColor: '#191919', borderWidth: 3 },
        data: sel ? [[sel.mean, sel.std]] : [],
      },
    ],
  }
}

// notMerge only when switching between cluster/continuous mode (clears the stale visualMap/legend);
// normal refreshes use merge to preserve the user's legend visibility state
let lastMode = ''
const render = () => {
  if (!chart || !props.members.length || !props.summary) return
  const nm = lastMode !== props.colorBy
  lastMode = props.colorBy
  chart.setOption(buildOption() as any, { notMerge: nm })
}

onMounted(() => {
  chart = echarts.init(chartRef.value!)
  chart.on('click', (p: any) => { if (p.seriesType === 'scatter' && p.data?.id != null) emit('select', p.data.id) })
  ro = new ResizeObserver(() => chart?.resize())
  ro.observe(chartRef.value!)
  render()
})
onBeforeUnmount(() => { ro?.disconnect(); chart?.dispose() })

// Reset wheel zoom/pan to the full data view (called by the parent's autoscale button)
const autoscale = () => {
  if (!chart) return
  chart.dispatchAction({ type: 'dataZoom', dataZoomIndex: 0, start: 0, end: 100 })
  chart.dispatchAction({ type: 'dataZoom', dataZoomIndex: 1, start: 0, end: 100 })
}
defineExpose({ autoscale })

watch(() => [props.members, props.summary, props.selectedId, props.brushedIds, outlierMode.value, props.colorBy, props.categories], render, { deep: false })
</script>
