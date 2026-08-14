<template>
  <div class="h-full flex flex-col min-h-0">
    <div class="text-[11.5px] text-gray-400 px-2 shrink-0 truncate">
      surrogate response inside the current ROI (log10 ρ) · each parameter swept over its
      range, the other two fixed at context values · top =
      <span class="text-[#2a78d6] font-semibold">ROI mean</span>, bottom =
      <span class="text-[#1baf7a] font-semibold">ROI std</span> ·
      S = mean |∂mean/∂u| over the sweep via autograd (normalized parameter, comparable
      across panels) · dashed line = context value
    </div>
    <div class="grid grid-cols-3 gap-2 flex-1 min-h-0">
      <div v-for="(c, i) in result.curves" :key="c.param" class="border border-[#f0f0f0] rounded-[8px] min-h-0">
        <div :ref="el => setEl(i, el)" class="h-full"></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import * as echarts from 'echarts'
import { onMounted, onBeforeUnmount, watch } from 'vue'

// Parameter sensitivity line charts for Module 3 (same structure as Module 1's ParamSensitivity):
// curves are computed by the backend /param_sensitivity via the Evidential INR's differentiability,
// not from ensemble member statistics — the S metric is the sweep mean of exact autograd gradients
const props = defineProps<{
  result: {
    curves: { param: string, min: number, max: number, current: number,
              points: { x: number, mean: number, std: number, grad: number }[] }[],
    sensitivity: number[],
  }
}>()

const X_DIGITS: Record<string, number> = { OmM: 3, OmB: 4, h: 2 }

// The y-axis hugs the curve (±25% padding), consistent with Module 1
const lineExtent = (vs: number[]) => {
  const [lo, hi] = [Math.min(...vs), Math.max(...vs)]
  const pad = (hi - lo) * 0.25 || 0.01
  return [lo - pad, hi + pad]
}

// Same dataviz colors as Module 1: mean = blue, std = aqua
const C_MEAN = '#2a78d6'
const C_STD = '#1baf7a'

const els: Record<number, HTMLElement | null> = {}
const charts: Record<number, echarts.ECharts> = {}
let ro: ResizeObserver | undefined
const setEl = (i: number, el: any) => { els[i] = el }

const buildOption = (i: number) => {
  const c = props.result.curves[i]
  const d = X_DIGITS[c.param] ?? 3
  const meanLine = c.points.map(p => [p.x, p.mean])
  const stdLine = c.points.map(p => [p.x, p.std])
  const [mLo, mHi] = lineExtent(c.points.map(p => p.mean))
  const [sLo, sHi] = lineExtent(c.points.map(p => p.std))

  // Current context parameter position: one vertical dashed line in each subplot
  const ctxMark = (labelShow: boolean) => ({
    silent: true, symbol: 'none',
    lineStyle: { color: '#191919', type: 'dashed', width: 1.2 },
    label: { show: labelShow, formatter: 'ctx', fontSize: 10 },
    data: [{ xAxis: c.current }],
  })

  const xAxisCommon = {
    type: 'value', min: c.min, max: c.max,
    axisLabel: { formatter: (v: number) => v.toFixed(d), fontSize: 10.5 },
    splitLine: { show: false },
  }

  return {
    animation: false,
    title: {
      text: c.param,
      subtext: `S = ${props.result.sensitivity[i].toFixed(3)}`,
      left: 'center', top: 2,
      textStyle: { fontSize: 14, fontWeight: 700 },
      subtextStyle: { fontSize: 11.5, color: '#888' },
    },
    grid: [
      { left: 56, right: 14, top: 42, height: '31%' },
      { left: 56, right: 14, top: '61%', bottom: 20 },
    ],
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    tooltip: {
      trigger: 'axis', confine: true,
      valueFormatter: (v: any) => Number(v).toFixed(4),
    },
    xAxis: [
      { ...xAxisCommon, gridIndex: 0, axisLabel: { show: false } },
      { ...xAxisCommon, gridIndex: 1 },
    ],
    yAxis: [
      { type: 'value', gridIndex: 0, name: 'ROI mean', min: mLo, max: mHi,
        axisLabel: { formatter: (v: number) => v.toFixed(3), fontSize: 10.5, color: C_MEAN },
        nameTextStyle: { color: C_MEAN, fontWeight: 600 },
        splitLine: { lineStyle: { color: '#f2f2f2' } } },
      { type: 'value', gridIndex: 1, name: 'ROI std', min: sLo, max: sHi,
        axisLabel: { formatter: (v: number) => v.toFixed(3), fontSize: 10.5, color: C_STD },
        nameTextStyle: { color: C_STD, fontWeight: 600 },
        splitLine: { lineStyle: { color: '#f2f2f2' } } },
    ],
    series: [
      {
        name: 'ROI mean', type: 'line', xAxisIndex: 0, yAxisIndex: 0, z: 3,
        showSymbol: false, smooth: 0.3,
        lineStyle: { color: C_MEAN, width: 2.5 }, itemStyle: { color: C_MEAN },
        data: meanLine,
        markLine: ctxMark(true),
      },
      {
        name: 'ROI std', type: 'line', xAxisIndex: 1, yAxisIndex: 1, z: 3,
        showSymbol: false, smooth: 0.3,
        lineStyle: { color: C_STD, width: 2.5 }, itemStyle: { color: C_STD },
        data: stdLine,
        markLine: ctxMark(false),
      },
    ],
  }
}

const render = () => {
  if (!props.result?.curves?.length) return
  props.result.curves.forEach((_, i) => {
    if (!els[i]) return
    if (!charts[i]) charts[i] = echarts.init(els[i]!)
    charts[i].setOption(buildOption(i) as any, { notMerge: true })
  })
}

onMounted(() => {
  render()
  ro = new ResizeObserver(() => Object.values(charts).forEach(c => c.resize()))
  Object.values(els).forEach(el => { if (el) ro!.observe(el) })
})
onBeforeUnmount(() => { ro?.disconnect(); Object.values(charts).forEach(c => c.dispose()) })

watch(() => props.result, render, { deep: true })
</script>
