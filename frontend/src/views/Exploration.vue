<template>
  <!-- 100vh dashboard: no page-level scrollbar; sections share height by flex ratios -->
  <div class="h-screen overflow-hidden bg-gray-100 explore-accent flex flex-col">
    <div class="bg-white shadow-lg flex-1 flex flex-col min-h-0">
      <AppHeader />

      <div class="px-4 pt-1.5 pb-2 flex-1 flex flex-col min-h-0 gap-2">
        <!-- Title row (subtitle and usage hint merged into one line to save height) -->
        <div class="flex items-baseline gap-3 shrink-0 min-w-0">
          <h2 class="text-lg font-bold whitespace-nowrap">🗺 Ensemble Landscape</h2>
          <span class="text-[12px] text-gray-400 truncate">
            {{ members.length || 380 }} Nyx members (training / calibration / testing of the evidential INR)
            · (mean, std) of log10(ρ) · click a point, search on the left, or brush the parallel
            coordinates — the focused member renders on the right
          </span>
        </div>

        <div v-if="loadError" class="text-red-400 text-center py-10">{{ loadError }}</div>

        <template v-else>
          <!-- Main row: Filters+Search | Landscape | Focused member -->
          <div class="grid grid-cols-[260px_minmax(0,1fr)_420px] gap-2 flex-[5.6] min-h-0">
            <!-- Left: Filters on top / Search below -->
            <div class="flex flex-col gap-2 min-h-0">
              <div class="border border-[#e5e5e5] rounded-[10px] px-3 py-2 bg-white shrink-0">
                <div class="flex items-baseline justify-between">
                  <h3 class="font-semibold text-[13.5px]">🔧 Filters</h3>
                  <span class="text-[11px] text-gray-400"><b class="text-gray-600">{{ matchCount }}</b>/{{ members.length }}</span>
                </div>

                <div v-for="p in PARAM_DEFS" :key="p.key" class="mb-1">
                  <div class="flex justify-between text-[11.5px]">
                    <span class="font-semibold">{{ p.key }}</span>
                    <span class="font-mono text-gray-400">
                      {{ fmt(ranges[p.key]?.[0], p.digits) }} – {{ fmt(ranges[p.key]?.[1], p.digits) }}
                    </span>
                  </div>
                  <el-slider
                    v-if="ranges[p.key]"
                    v-model="ranges[p.key]" range
                    :min="bounds[p.key][0]" :max="bounds[p.key][1]"
                    :step="(bounds[p.key][1] - bounds[p.key][0]) / 200"
                    :format-tooltip="(v: number) => fmt(v, p.digits)"
                    size="small" class="!my-0"
                  />
                </div>

                <div class="flex items-center gap-1 mt-1">
                  <el-radio-group v-model="outlierFilter" size="small">
                    <el-radio-button value="all">all</el-radio-button>
                    <el-radio-button value="maha">stat outlier</el-radio-button>
                    <el-radio-button value="struct">struct</el-radio-button>
                  </el-radio-group>
                </div>
                <el-button size="small" class="mt-1.5 w-full" @click="clearFilters">✕ clear filters</el-button>
              </div>

              <MemberSearch class="flex-1 min-h-0" :members="members" :selectedId="selectedId" @select="selectMember" />
            </div>

            <!-- Middle: Landscape scatter plot -->
            <div class="border border-[#e5e5e5] rounded-[10px] p-1.5 flex flex-col bg-white min-w-0 min-h-0 overflow-hidden">
              <div class="flex items-center justify-between px-1.5 shrink-0">
                <div class="text-[13px] font-semibold">
                  {{ matchCount }} of {{ members.length }} members ·
                  <span class="font-normal text-gray-400">💡 click a point to focus</span>
                </div>
                <div class="flex items-center gap-1.5 text-[12px] text-gray-500">
                  <el-button size="small" @click="scatterRef?.autoscale()" title="Reset wheel zoom/pan to the full data view">
                    ⤢ autoscale
                  </el-button>
                  Colour by
                  <el-select v-model="colorBy" size="small" style="width: 96px">
                    <el-option v-for="c in ['split', 'cluster', 'h', 'OmM', 'OmB', 'w90']" :key="c" :label="c" :value="c" />
                  </el-select>
                </div>
              </div>
              <EnsembleScatter
                ref="scatterRef"
                class="flex-1 min-h-0"
                :members="members" :summary="summary" :histograms="histograms"
                :selectedId="selectedId" :brushedIds="visibleIds" :colorBy="colorBy"
                :categories="categoryMeta" :catKey="categoryKey"
                @select="selectMember"
              />
            </div>

            <!-- Right: Focused member (cube and stats arranged to fit the shorter main row) -->
            <div class="border-2 rounded-[10px] bg-white flex flex-col min-h-0 overflow-hidden"
                 :class="selectedMember ? 'border-[#ACACFF]' : 'border-[#e5e5e5]'">
              <div class="px-3 py-1.5 border-b border-[#eee] bg-gray-50 flex justify-between items-center shrink-0">
                <span class="text-[13px] font-semibold whitespace-nowrap">
                  🧊 Focused member{{ selectedMember ? ` — #${selectedMember.id}` : '' }}
                </span>
                <span v-if="selectedMember" class="font-mono text-[10.5px] text-gray-400 truncate ml-2">
                  {{ selectedMember.dir }}
                </span>
              </div>

              <div v-if="!selectedMember" class="flex-1 flex flex-col items-center justify-center text-gray-400 text-[13px] text-center px-6">
                <div class="text-3xl mb-2">🪐</div>
                No member focused yet —<br/>click a point on the landscape<br/>or search on the left.
              </div>

              <div v-else class="p-2 flex-1 min-h-0 flex flex-col">
                <!-- Volume rendering (directly interactive, on top; stats below — the original vertical layout) -->
                <div class="flex items-center justify-center bg-black/90 rounded-[8px] shrink-0" style="min-height: 236px">
                  <Cube3d2 v-if="vtiUrl" ref="cubeRef" :key="vtiUrl" :url="vtiUrl" :size="230" :autoLive="true" />
                  <div v-else class="text-gray-300 text-[12px]">
                    {{ volLoading ? 'Rendering volume…' : 'volume unavailable' }}
                  </div>
                </div>
                <div class="flex items-center justify-between mt-1 mb-1.5 shrink-0">
                  <span class="text-[10.5px] text-gray-400">log10 density · drag to rotate, scroll to zoom</span>
                  <span class="flex gap-1.5">
                    <button v-if="vtiUrl" @click="cubeRef?.resetCamera()"
                            class="text-[11px] border border-[#e5e5e5] rounded-[6px] px-2 py-0.5 whitespace-nowrap
                                   hover:border-[#ACACFF] hover:text-[#ACACFF] transition-colors">⤢ fit to view</button>
                    <a v-if="vtiUrl" :href="vtiUrl" download
                       class="text-[11px] border border-[#e5e5e5] rounded-[6px] px-2 py-0.5 whitespace-nowrap
                              hover:border-[#ACACFF] hover:text-[#ACACFF] transition-colors">⬇ VTI</a>
                  </span>
                </div>
                <!-- Stats card (on very short viewports only the card scrolls, not the page) -->
                <MemberDetail class="flex-1 min-h-0" :member="selectedMember" :role="ROLE_META[selectedMember._role]" />
              </div>
            </div>
          </div>

          <!-- Parallel coordinates (flexible height) -->
          <div class="border border-[#e5e5e5] rounded-[10px] px-2 py-1 bg-white flex flex-col min-h-0 flex-[1.8]">
            <h3 class="font-semibold text-[13px] px-1 shrink-0">🧵 Parameters → statistics (parallel coordinates)</h3>
            <EnsemblePCP
              class="flex-1 min-h-0"
              :members="members" :selectedId="selectedId" :colorBy="colorBy"
              :categories="categoryMeta" :catKey="categoryKey"
              @brush="(ids: Set<number> | null) => (brushedIds = ids)" @select="selectMember"
            />
          </div>

          <!-- Parameter sensitivity line chart (flexible height) -->
          <div class="border border-[#e5e5e5] rounded-[10px] px-2 py-1 bg-white flex flex-col min-h-0 flex-[2.4]">
            <h3 class="font-semibold text-[13px] px-1 shrink-0">📈 Parameter sensitivity — mean &amp; std vs each parameter</h3>
            <ParamSensitivity
              class="flex-1 min-h-0"
              :members="members" :sensitivity="sensitivity" :selectedMember="selectedMember"
            />
          </div>
        </template>
      </div>
    </div>

    <AIAssistant />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import AppHeader from '@/components/AppHeader.vue'
import AIAssistant from '@/components/AIAssistant.vue'
import EnsembleScatter from '@/components/EnsembleScatter.vue'
import EnsemblePCP from '@/components/EnsemblePCP.vue'
import MemberDetail from '@/components/MemberDetail.vue'
import MemberSearch from '@/components/MemberSearch.vue'
import ParamSensitivity from '@/components/ParamSensitivity.vue'
import Cube3d2 from '@/components/Cube3d2.vue'

const PARAM_DEFS = [
  { key: 'OmM', digits: 3 },
  { key: 'OmB', digits: 4 },
  { key: 'h', digits: 3 },
] as const

const members = ref<any[]>([])
const summary = ref<any>(null)
const histograms = ref<any>(null)
const sensitivity = ref<any>(null)
const loadError = ref('')

const selectedId = ref<number | null>(null)
const brushedIds = ref<Set<number> | null>(null)   // PCP axis brushing
const vtiUrl = ref('')
const volLoading = ref(false)
const scatterRef = ref()   // Scatter component (for the autoscale button)
const cubeRef = ref()      // Volume rendering component (for the fit-to-view button)
// Coloring mode shared by the scatter and PCP: split = data split of the evidential INR (default),
// cluster = statistical clustering, the rest are continuous parameters
const colorBy = ref('split')

// ---- Data split of the evidential INR (source: Evidential_INR/fg_*_nyx_evidential*.sh) ----
// Training = id 0–149, Calibration = id 200–399, Testing = id 400–429;
// ids 150–199 are unused by the training pipeline and dropped from the UI (see the filter in onMounted)
// Colors: project green/purple + terracotta orange; the trio passes CVD checks (min ΔE≈87)
const ROLE_META = [
  { label: 'Training', color: '#8fbf6f', count: 150 },
  { label: 'Calibration', color: '#7c74d8', count: 200 },
  { label: 'Testing', color: '#e8935c', count: 30 },
]
const roleOf = (id: number) => (id < 150 ? 0 : id >= 400 ? 2 : 1)

// ---- k-means clustering: group members into 5 classes by statistical features (the cluster semantics of the paper's landscape) ----
// Categorical colors are the first 5 slots of the validated categorical palette (fixed order; avoids the outlier red ring and selection magenta)
const CLUSTER_COLORS = ['#2a78d6', '#1baf7a', '#eda100', '#008300', '#4a3aa7']
const CLUSTER_FEATS = ['mean', 'std', 'w90', 'skew', 'kurt']
const clusterMeta = ref<{ label: string; color: string; count: number }[]>([])

// Deterministic k-means (quantile seeding + 25 iterations, no randomness -> identical clusters on every refresh)
const clusterMembers = (ms: any[], k = 5) => {
  const nf = CLUSTER_FEATS.length
  // Standardize to z space
  const mu = CLUSTER_FEATS.map(f => ms.reduce((s, m) => s + m[f], 0) / ms.length)
  const sd = CLUSTER_FEATS.map((f, j) =>
    Math.sqrt(ms.reduce((s, m) => s + (m[f] - mu[j]) ** 2, 0) / ms.length) || 1)
  const X = ms.map(m => CLUSTER_FEATS.map((f, j) => (m[f] - mu[j]) / sd[j]))
  // Seeds: sort by the std dimension and take k quantile points (deterministic, covers both tails of the distribution)
  const order = X.map((_, i) => i).sort((a, b) => X[a][1] - X[b][1])
  let cent = Array.from({ length: k }, (_, c) =>
    [...X[order[Math.floor((c + 0.5) * ms.length / k)]]])
  let assign = new Array(ms.length).fill(0)
  for (let it = 0; it < 25; it++) {
    assign = X.map(x => {
      let best = 0, bd = Infinity
      cent.forEach((c, ci) => {
        const d = c.reduce((s, v, j) => s + (v - x[j]) ** 2, 0)
        if (d < bd) { bd = d; best = ci }
      })
      return best
    })
    cent = cent.map((c, ci) => {
      const pts = X.filter((_, i) => assign[i] === ci)
      return pts.length ? CLUSTER_FEATS.map((_, j) => pts.reduce((s, p) => s + p[j], 0) / pts.length) : c
    })
  }
  // Renumber clusters by descending size (fixed categorical color order: largest cluster = slot 1)
  const sizes = Array.from({ length: k }, (_, ci) => assign.filter(a => a === ci).length)
  const rank = Array.from({ length: k }, (_, ci) => ci).sort((a, b) => sizes[b] - sizes[a])
  const remap = new Array(k); rank.forEach((old, neu) => (remap[old] = neu))
  ms.forEach((m, i) => (m._cluster = remap[assign[i]]))
  // Cluster naming: the 1-2 features with the largest |z-score| in the centroid -> descriptions like "high h · low std"
  const seen = new Set<string>()
  const meta = rank.map((old, neu) => {
    const c = cent[old]
    const dims = CLUSTER_FEATS.map((f, j) => ({ f, z: c[j] }))
      .sort((a, b) => Math.abs(b.z) - Math.abs(a.z))
    let parts = dims.filter(d => Math.abs(d.z) >= 0.45).slice(0, 2)
      .map(d => `${d.z > 0 ? 'high' : 'low'} ${d.f}`)
    if (!parts.length) parts = ['typical']
    let label = parts.join(' · ')
    if (seen.has(label)) label = `${label} · ${dims[2].z > 0 ? 'high' : 'low'} ${dims[2].f}`
    seen.add(label)
    return { label, color: CLUSTER_COLORS[neu], count: sizes[old] }
  })
  return meta
}

// ---- filters (TVCG left-column style: parameter ranges + outlier toggle) ----
const bounds = ref<Record<string, [number, number]>>({})
const ranges = ref<Record<string, [number, number]>>({})
const outlierFilter = ref<'all' | 'maha' | 'struct'>('all')

const fmt = (v: number | undefined, d = 3) => v == null ? '-' : Number(v).toFixed(d)

const selectedMember = computed(() =>
  selectedId.value == null ? null : members.value.find(m => m.id === selectedId.value) ?? null)

const filtersActive = computed(() => {
  if (outlierFilter.value !== 'all') return true
  return PARAM_DEFS.some(p => {
    const r = ranges.value[p.key], b = bounds.value[p.key]
    return r && b && (r[0] > b[0] || r[1] < b[1])
  })
})

const filteredIds = computed<Set<number> | null>(() => {
  if (!filtersActive.value) return null
  const ids = new Set<number>()
  for (const m of members.value) {
    if (PARAM_DEFS.some(p => {
      const r = ranges.value[p.key]
      return r && (m[p.key] < r[0] || m[p.key] > r[1])
    })) continue
    if (outlierFilter.value === 'maha' && m.outlier_maha <= 2.146) continue
    if (outlierFilter.value === 'struct' && m.outlier_struct <= 2.5) continue
    ids.add(m.id)
  }
  return ids
})

// filters ∩ PCP brushing -> non-matching points fade out on the scatter (TVCG match/dim semantics)
const visibleIds = computed<Set<number> | null>(() => {
  const a = filteredIds.value, b = brushedIds.value
  if (!a) return b
  if (!b) return a
  return new Set([...a].filter(id => b.has(id)))
})

const matchCount = computed(() => visibleIds.value ? visibleIds.value.size : members.value.length)

// Metadata for categorical coloring: split -> data-split role; cluster -> k-means cluster; continuous variables -> empty
const categoryMeta = computed(() =>
  colorBy.value === 'split' ? ROLE_META
  : colorBy.value === 'cluster' ? clusterMeta.value : [])
const categoryKey = computed(() =>
  colorBy.value === 'split' ? '_role'
  : colorBy.value === 'cluster' ? '_cluster' : '')

const clearFilters = () => {
  outlierFilter.value = 'all'
  for (const p of PARAM_DEFS) ranges.value[p.key] = [...bounds.value[p.key]] as [number, number]
}

onMounted(async () => {
  try {
    // Static statistics (symlinked to ensemble_stats_430, served directly by vite)
    const [m, s, h, sens] = await Promise.all([
      fetch('/ensemble/members.json').then(r => r.json()),
      fetch('/ensemble/ensemble_summary.json').then(r => r.json()),
      fetch('/ensemble/histograms.json').then(r => r.json()),
      fetch('/ensemble/sensitivity.json').then(r => r.json()).catch(() => null),
    ])
    // Drop the 150–199 range unused by the training pipeline; the UI shows only train/cal/test
    const kept = m.filter((x: any) => x.id < 150 || x.id >= 200)
    clusterMeta.value = clusterMembers(kept)   // Cluster first (writes _cluster), then hand off to the views
    kept.forEach((x: any) => (x._role = roleOf(x.id)))
    members.value = kept
    summary.value = s
    histograms.value = h
    sensitivity.value = sens
    // Initialize the parameter slider ranges
    for (const p of PARAM_DEFS) {
      const vals = m.map((x: any) => x[p.key])
      bounds.value[p.key] = [Math.min(...vals), Math.max(...vals)]
      ranges.value[p.key] = [...bounds.value[p.key]] as [number, number]
    }
  } catch (e: any) {
    loadError.value = 'Failed to load ensemble statistics: ' + e
  }
})

// Click a member -> request the vti of its log10 density field (the backend locates the raw data by dir, with file-level caching)
// The focus panel sits right next to the distribution, no scrolling needed
const selectMember = async (id: number) => {
  selectedId.value = id
  vtiUrl.value = ''
  volLoading.value = true
  try {
    const res = await fetch(`/api/ensemble/member/${id}`, { method: 'POST' }).then(r => r.json())
    if (res.code === 0 && selectedId.value === id) vtiUrl.value = res.data.vti
  } catch (e) {
    console.error('member volume failed', e)
  } finally {
    if (selectedId.value === id) volLoading.value = false
  }
}
</script>

<!-- The purple .explore-accent palette and compact slider style are shared by all
     three modules and live in src/index.css -->
