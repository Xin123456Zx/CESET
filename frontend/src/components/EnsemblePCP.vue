<template>
  <div class="h-full flex flex-col min-h-0">
    <div class="flex items-center justify-between px-2 shrink-0">
      <div class="text-[11.5px] text-gray-400 truncate">
        drag on an axis to brush (linked with the landscape) · line colour =
        {{ catKey ? `${colorBy} (same colours as the landscape)` : `${colorBy} (light → dark purple)` }}
        · h dominates: ρ(h, std) ≈ −0.96, ρ(h, mean) ≈ +0.90
      </div>
      <el-button size="small" text @click="clearBrush">clear brush</el-button>
    </div>
    <!-- Flexible height: allocated by the parent card, scales with the viewport; the page itself never scrolls -->
    <div ref="chartRef" class="flex-1 min-h-0 overflow-hidden"></div>
  </div>
</template>

<script setup lang="ts">
import * as echarts from 'echarts'
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'

const props = defineProps<{
  members: any[]
  selectedId: number | null
  colorBy: string   // 'split'/'cluster' = categorical coloring (same colors as the scatter); h/OmM/OmB/w90 = continuous coloring
  categories: { label: string; color: string; count: number }[]
  catKey: string    // category field name on members ('_role' / '_cluster'); empty = continuous mode
}>()
const emit = defineEmits<{
  (e: 'brush', ids: Set<number> | null): void
  (e: 'select', id: number): void
}>()

const chartRef = ref<HTMLDivElement>()
let chart: echarts.ECharts | undefined
let ro: ResizeObserver | undefined

// Axis order: three simulation parameters → statistics (README recommendation; h vs. the statistics shows striking crossing/parallel patterns)
const DIMS = ['OmM', 'OmB', 'h', 'mean', 'std', 'q95', 'q05']

// Sequential ramp in the project's purple family (light → dark violet) — keeps the brand color while adding tonal variation
const PURPLE_RAMP = ['#e8e6fb', '#cfcaf5', '#b3aeee', '#958ee2', '#7a71d0', '#5f54bc', '#4a3aa7']

const buildOption = () => {
  const clusterMode = !!props.catKey && props.categories.length > 0
  const dim = DIMS.indexOf(props.colorBy)
  const cVals = clusterMode ? [0, 1] : props.members.map(m => m[props.colorBy])
  return {
    animation: false,
    // Each axis ranges over its data min/max ± 5% padding — not from 0, so data isn't squeezed at the top of the axis
    parallelAxis: DIMS.map((d, i) => {
      const vals = props.members.map(m => m[d])
      const [lo, hi] = [Math.min(...vals), Math.max(...vals)]
      const pad = (hi - lo) * 0.05 || 0.5
      return {
        dim: i, name: d, nameTextStyle: { fontWeight: 600 },
        min: lo - pad, max: hi + pad,
        axisLabel: { formatter: (v: number) => Number(v).toPrecision(3) },
      }
    }),
    parallel: { left: 55, right: 55, top: 26, bottom: 10, axisExpandable: false },
    // Hidden color mapping for continuous mode (cluster mode uses each line's own cluster color, no visualMap needed)
    visualMap: clusterMode ? undefined : {
      type: 'continuous', show: false, seriesIndex: 0,
      dimension: dim >= 0 ? dim : 2,
      min: Math.min(...cVals), max: Math.max(...cVals),
      inRange: { color: PURPLE_RAMP },
    },
    series: [
      {
        id: 'pcp', type: 'parallel', smooth: false,
        lineStyle: { width: 1.2, opacity: 0.3 },
        emphasis: { lineStyle: { width: 2.5, opacity: 1 } },
        inactiveOpacity: 0.02, activeOpacity: 0.5,
        data: props.members.map(m => ({
          value: DIMS.map(d => m[d]),
          name: m.id,
          // Categorical mode: line color = the color of the member's category (matches the scatter legend)
          ...(clusterMode ? { lineStyle: { color: props.categories[m[props.catKey]]?.color } } : {}),
        })),
      },
      { // Highlight line for the selected member (magenta, matches the selected point in the scatter)
        id: 'pcp-selected', type: 'parallel', silent: true,
        lineStyle: { color: '#d6336c', width: 4, opacity: 1 },
        data: props.selectedId != null
          ? props.members.filter(m => m.id === props.selectedId).map(m => ({ value: DIMS.map(d => m[d]) }))
          : [],
      },
    ],
  }
}

// notMerge only when switching between cluster/continuous mode (fully removes the stale visualMap);
// normal refreshes use merge to preserve the user's axis brush state
let lastMode = ''
const render = () => {
  if (!chart || !props.members.length) return
  const nm = lastMode !== props.colorBy
  lastMode = props.colorBy
  chart.setOption(buildOption() as any, { notMerge: nm })
}

// Axis brush → compute the selected member set → notify the parent to link with the scatter
const onAreaSelected = () => {
  if (!chart) return
  try {
    const model = (chart as any).getModel()
    const series = model.getSeriesByIndex(0)
    const indices: number[] = series.getRawIndicesByActiveState('active')
    emit('brush', indices.length ? new Set(indices.map(i => props.members[i].id)) : null)
  } catch (e) {
    console.error('brush link failed', e)
  }
}

const clearBrush = () => {
  // Clear the brush region on every axis
  chart?.setOption({ parallelAxis: DIMS.map((_d, i) => ({ dim: i, areaSelectStyle: {}, activeIntervals: [] })) } as any)
  emit('brush', null)
}

onMounted(() => {
  chart = echarts.init(chartRef.value!)
  chart.on('axisareaselected', onAreaSelected)
  chart.on('click', (p: any) => { if (p.seriesId === 'pcp' && p.name != null) emit('select', Number(p.name)) })
  ro = new ResizeObserver(() => chart?.resize())
  ro.observe(chartRef.value!)
  render()
})
onBeforeUnmount(() => { ro?.disconnect(); chart?.dispose() })

watch(() => [props.members, props.selectedId, props.colorBy, props.categories], render)
</script>
