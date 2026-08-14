<template>
  <div class="h-full flex flex-col min-h-0">
    <div class="text-[11.5px] text-gray-400 px-2 shrink-0 truncate">
      each parameter vs member statistics (log10 ρ) · top =
      <span class="text-[#2a78d6] font-semibold">mean</span>, bottom =
      <span class="text-[#1baf7a] font-semibold">std</span> ·
      line = binned average ({{ N_BINS }} bins) · y-axis zoomed to the trend line so its
      fluctuation is visible · ρ = Spearman rank correlation
    </div>
    <!-- Flexible height: the three charts scale with the viewport -->
    <div class="grid grid-cols-3 gap-2 flex-1 min-h-0">
      <div v-for="p in PARAMS" :key="p" class="border border-[#f0f0f0] rounded-[8px] min-h-0">
        <div :ref="el => setEl(p, el)" class="h-full"></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import * as echarts from 'echarts'
import { onMounted, onBeforeUnmount, watch } from 'vue'

const props = defineProps<{
  members: any[]
  sensitivity: any | null       // ensemble_stats/sensitivity.json (Spearman ρ table)
  selectedMember: any | null    // selected member → vertical dashed line marks its parameter position
}>()

const PARAMS = ['OmM', 'OmB', 'h'] as const
const N_BINS = 20
const X_DIGITS: Record<string, number> = { OmM: 3, OmB: 4, h: 2 }

// The y-axis hugs the binned trend line (±25% padding): if ranged to the raw scatter, member-to-member
// spread would flatten the trend line — here seeing how mean/std vary with the parameter comes first; out-of-range points are clipped
const lineExtent = (line: number[][]) => {
  const vs = line.map(p => p[1])
  const [lo, hi] = [Math.min(...vs), Math.max(...vs)]
  const pad = (hi - lo) * 0.25 || 0.01
  return [lo - pad, hi + pad]
}

// dataviz palette: mean = categorical slot 1 (blue), std = categorical slot 2 (aqua); passes the validator
const C_MEAN = '#2a78d6', C_MEAN_BG = '#9ec5f4'
const C_STD = '#1baf7a', C_STD_BG = '#8fd9bd'

const els: Record<string, HTMLElement | null> = {}
const charts: Record<string, echarts.ECharts> = {}
let ro: ResizeObserver | undefined
const setEl = (p: string, el: any) => { els[p] = el }

const fmtRho = (r: number) => (r >= 0 ? '+' : '−') + Math.abs(r).toFixed(2)

// Bin members by parameter and average each bin's mean/std → clean trend polyline (scatter kept as background to convey the distribution)
const binned = (param: string) => {
  const xs = props.members.map(m => m[param])
  const [lo, hi] = [Math.min(...xs), Math.max(...xs)]
  const w = (hi - lo) / N_BINS || 1
  const acc = Array.from({ length: N_BINS }, () => ({ n: 0, mean: 0, std: 0 }))
  for (const m of props.members) {
    const i = Math.min(N_BINS - 1, Math.floor((m[param] - lo) / w))
    acc[i].n++; acc[i].mean += m.mean; acc[i].std += m.std
  }
  const meanLine: number[][] = [], stdLine: number[][] = []
  acc.forEach((a, i) => {
    if (!a.n) return
    const x = lo + (i + 0.5) * w
    meanLine.push([x, a.mean / a.n])
    stdLine.push([x, a.std / a.n])
  })
  return { lo, hi, meanLine, stdLine }
}

const buildOption = (param: string) => {
  const { lo, hi, meanLine, stdLine } = binned(param)
  const rho = props.sensitivity?.table?.[param]
  const sub = rho
    ? `ρ(mean) = ${fmtRho(rho.mean.rho)}   ·   ρ(std) = ${fmtRho(rho.std.rho)}`
    : ''
  const sel = props.selectedMember
  const d = X_DIGITS[param] ?? 3

  // Selected member → one vertical dashed line in each of the two subplots
  const selMark = (labelShow: boolean) => sel ? {
    silent: true, symbol: 'none',
    lineStyle: { color: '#191919', type: 'dashed', width: 1.2 },
    label: { show: labelShow, formatter: `#${sel.id}`, fontSize: 10 },
    data: [{ xAxis: sel[param] }],
  } : undefined

  const xAxisCommon = {
    type: 'value', min: lo, max: hi,
    axisLabel: { formatter: (v: number) => v.toFixed(d), fontSize: 10.5 },
    splitLine: { show: false },
  }

  return {
    animation: false,
    title: {
      text: param, subtext: sub, left: 'center', top: 2,
      textStyle: { fontSize: 14, fontWeight: 700 },
      subtextStyle: { fontSize: 11.5, color: '#888' },
    },
    // Top and bottom subplots share x (single-axis small multiples instead of dual y-axes);
    // percentage layout → both subplots scale proportionally as the panel height tracks the viewport
    grid: [
      { left: 56, right: 14, top: 42, height: '31%' },
      { left: 56, right: 14, top: '61%', bottom: 20 },
    ],
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    tooltip: {
      trigger: 'axis', confine: true,
      valueFormatter: (v: any) => Number(v).toFixed(3),
    },
    // No axis name at the bottom (the parameter name is already in the chart title; a flush label would get partially clipped)
    xAxis: [
      { ...xAxisCommon, gridIndex: 0, axisLabel: { show: false } },
      { ...xAxisCommon, gridIndex: 1 },
    ],
    yAxis: [
      { type: 'value', gridIndex: 0, name: 'mean',
        min: lineExtent(meanLine)[0], max: lineExtent(meanLine)[1],
        axisLabel: { formatter: (v: number) => v.toFixed(3), fontSize: 10.5, color: C_MEAN },
        nameTextStyle: { color: C_MEAN, fontWeight: 600 },
        splitLine: { lineStyle: { color: '#f2f2f2' } } },
      { type: 'value', gridIndex: 1, name: 'std',
        min: lineExtent(stdLine)[0], max: lineExtent(stdLine)[1],
        axisLabel: { formatter: (v: number) => v.toFixed(3), fontSize: 10.5, color: C_STD },
        nameTextStyle: { color: C_STD, fontWeight: 600 },
        splitLine: { lineStyle: { color: '#f2f2f2' } } },
    ],
    series: [
      { // Top: mean background scatter + binned trend line
        name: 'members (mean)', type: 'scatter', xAxisIndex: 0, yAxisIndex: 0, silent: true, z: 1,
        symbolSize: 3, itemStyle: { color: C_MEAN_BG, opacity: 0.18 },
        data: props.members.map(m => [m[param], m.mean]),
      },
      {
        name: 'mean', type: 'line', xAxisIndex: 0, yAxisIndex: 0, z: 3,
        showSymbol: false, smooth: 0.3,
        lineStyle: { color: C_MEAN, width: 2.5 }, itemStyle: { color: C_MEAN },
        data: meanLine,
        markLine: selMark(true),
      },
      { // Bottom: std background scatter + binned trend line
        name: 'members (std)', type: 'scatter', xAxisIndex: 1, yAxisIndex: 1, silent: true, z: 1,
        symbolSize: 3, itemStyle: { color: C_STD_BG, opacity: 0.18 },
        data: props.members.map(m => [m[param], m.std]),
      },
      {
        name: 'std', type: 'line', xAxisIndex: 1, yAxisIndex: 1, z: 3,
        showSymbol: false, smooth: 0.3,
        lineStyle: { color: C_STD, width: 2.5 }, itemStyle: { color: C_STD },
        data: stdLine,
        markLine: selMark(false),
      },
    ],
  }
}

const render = () => {
  if (!props.members.length) return
  for (const p of PARAMS) {
    if (!els[p]) continue
    if (!charts[p]) charts[p] = echarts.init(els[p]!)
    charts[p].setOption(buildOption(p) as any, { notMerge: true })
  }
}

onMounted(() => {
  render()
  ro = new ResizeObserver(() => Object.values(charts).forEach(c => c.resize()))
  for (const p of PARAMS) if (els[p]) ro.observe(els[p]!)
})
onBeforeUnmount(() => { ro?.disconnect(); Object.values(charts).forEach(c => c.dispose()) })

watch(() => [props.members, props.sensitivity, props.selectedMember], render)
</script>
