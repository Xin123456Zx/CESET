<template>
  <div class="min-h-screen bg-gray-100 explore-accent">
    <!-- Sensitivity panel added at the bottom, so the page may grow vertically (was locked to 100vh) -->
    <div class="max-w-full mx-auto bg-white shadow-lg min-h-[100vh]">
      <AppHeader />

      <!-- Title row (same pattern as Modules 1 & 2: bold title + gray usage hint) -->
      <div class="flex items-baseline gap-3 min-w-0 px-4 pt-1.5">
        <h2 class="text-lg font-bold whitespace-nowrap">🧭 Parameter-Space Exploration</h2>
        <span class="text-[12px] text-gray-400 truncate">
          load a context field, box a region of interest, and let a gradient search over (OmM, OmB, h)
          recommend parameter settings matching your target — preview them or send them to Module 2
        </span>
      </div>

      <!-- Module 3: ROI parameter recommendation (activation maximization) -->
      <div class="grid grid-cols-[minmax(330px,1.1fr)_2fr_minmax(380px,1.5fr)] gap-2 mt-2 px-4">

        <!-- Left: ROI and objective settings -->
        <div class="panel flex flex-col">
          <div class="panel-head">
            <h2 class="panel-title">⚙️ ROI &amp; Objective</h2>
          </div>
          <div class="px-3 py-2 h-[calc(100vh-190px)] overflow-y-auto">

            <div class="flex items-baseline justify-between">
              <h3 class="font-semibold text-[13px]">Context field parameters</h3>
              <span class="hint">base field for ROI selection</span>
            </div>
            <div class="flex items-center gap-2 mt-1" v-for="item in ctxParams" :key="item.key">
              <span class="text-[12px] font-semibold w-[48px] text-right shrink-0">{{ item.name }}</span>
              <el-slider :step="item.step" :max="item.max" :min="item.min" v-model="item.value" size="small" class="flex-1 !my-0" />
              <el-input-number v-model="item.value" :min="item.min" :max="item.max" :step="item.step"
                               :controls="false" size="small" class="!w-[84px] shrink-0" />
            </div>
            <el-button type="primary" size="small" class="w-full mt-2" @click="loadField">▶ Load field</el-button>

            <h3 class="font-semibold text-[13px] mt-4">
              📦 Region of Interest
              <span class="hint font-normal">(voxel index range, view axes)</span>
            </h3>
            <div class="grid grid-cols-[24px_1fr_1fr] gap-x-2 gap-y-1.5 items-center mt-1">
              <span></span>
              <span class="text-[11px] text-gray-400 text-center">from (voxel)</span>
              <span class="text-[11px] text-gray-400 text-center">to (voxel)</span>
              <template v-for="(axis, ai) in ['X', 'Y', 'Z']" :key="axis">
                <span class="font-semibold text-gray-600 text-[12px]">{{ axis }}</span>
                <el-input-number v-model="roi[ai * 2]" :min="0" :max="roi[ai * 2 + 1]" :step="1" size="small" class="!w-full" />
                <el-input-number v-model="roi[ai * 2 + 1]" :min="roi[ai * 2]" :max="255" :step="1" size="small" class="!w-full" />
              </template>
            </div>
            <div class="flex items-center justify-between mt-2">
              <el-checkbox v-model="cropPreview" label="Crop view to ROI" size="small" />
              <el-button size="small" @click="roi = [0, 255, 0, 255, 0, 255]">Reset ROI</el-button>
            </div>

            <h3 class="font-semibold text-[13px] mt-4 mb-1">🎯 Optimization target</h3>
            <p class="hint mb-2 leading-5">
              Recommend parameters whose <b>prediction is closest to one of the five volumes</b>
              in the middle panel; among equally-close candidates, prefer the uncertainty levels below.
            </p>
            <div class="grid grid-cols-[110px_1fr] gap-y-2 items-center text-[12px]">
              <span class="text-gray-600">Reference field:</span>
              <el-select v-model="refField" size="small">
                <el-option value="pred" label="Predicted field (mean)" />
                <el-option value="lower" label="Lower bound (before cal.)" />
                <el-option value="upper" label="Upper bound (before cal.)" />
                <el-option value="lower_cal" label="Lower bound (after cal.)" />
                <el-option value="upper_cal" label="Upper bound (after cal.)" />
              </el-select>
              <span class="text-gray-600">Data uncertainty:</span>
              <el-radio-group v-model="prefData" size="small">
                <el-radio-button label="max">Maximize</el-radio-button>
                <el-radio-button label="min">Minimize</el-radio-button>
              </el-radio-group>
              <span class="text-gray-600">Model uncertainty:</span>
              <el-radio-group v-model="prefModel" size="small">
                <el-radio-button label="max">Maximize</el-radio-button>
                <el-radio-button label="min">Minimize</el-radio-button>
              </el-radio-group>
            </div>

            <el-button type="primary" :loading="optimizing" class="w-full mt-4" @click="recommend">
              ⭐ Recommend parameters
            </el-button>
            <p class="hint mt-2 leading-5">{{ explainText }}</p>
          </div>
        </div>

        <!-- Middle: predicted field + interval bounds (before/after calibration) with ROI -->
        <div class="panel flex flex-col">
          <div class="panel-head">
            <h2 class="panel-title">🧊 Predicted Field &amp; Interval Bounds</h2>
            <span v-if="fieldParamsLabel" class="hint font-mono truncate">{{ fieldParamsLabel }}</span>
          </div>
          <div class="h-[calc(100vh-190px)] overflow-y-auto px-2 py-1">

            <div v-if="!fieldUrls" class="flex flex-col items-center justify-center text-gray-400 text-[13px] text-center h-[70%]">
              <div class="text-3xl mb-2">🪐</div>
              <p>Set context parameters on the left and click <b>▶ Load field</b> —<br/>
              the predicted field and its interval bounds render here with the ROI box.</p>
            </div>

            <template v-else>
              <!-- Confidence distribution sketch: dragging the slider refreshes both uncalibrated and calibrated intervals automatically (Load Field already fetches everything at once, no button needed) -->
              <ChartView :initial="confidence" :buttons="false"
                         @confidenceChange="onConfidenceChange" />

              <!-- Before calibration: Student-t prediction interval -->
              <h3 class="text-left font-semibold text-[13px] mt-1">
                Before calibration
                <span class="hint font-normal">Student-t interval · confidence {{ confBefore }}</span>
              </h3>
              <div class="grid grid-cols-3 gap-1 place-items-center">
                <p class="col-title"><span class="name">Predicted field</span><span class="desc">mean of log10 density</span></p>
                <p class="col-title"><span class="name">Lower bound</span><span class="desc">of Student-t interval</span></p>
                <p class="col-title"><span class="name">Upper bound</span><span class="desc">of Student-t interval</span></p>
                <RoiSelect3d preset="density" sync :url="fieldUrls.output" :roi="roi" :crop="cropPreview" :size="cubeSize" />
                <RoiSelect3d preset="density" sync :url="beforeUrls ? beforeUrls.lower : ''" :roi="roi" :crop="cropPreview" :size="cubeSize" />
                <RoiSelect3d preset="density" sync :url="beforeUrls ? beforeUrls.upper : ''" :roi="roi" :crop="cropPreview" :size="cubeSize" />
              </div>

              <!-- After calibration: interval after conformal calibration (Pred unchanged, only the bounds are corrected) -->
              <h3 class="text-left font-semibold text-[13px] mt-2">
                After calibration
                <span class="hint font-normal">
                  conformal<template v-if="calLevel != null"> · level {{ calLevel }}</template>
                </span>
              </h3>
              <div class="grid grid-cols-3 gap-1 place-items-center">
                <p class="col-title"><span class="name text-gray-400 font-normal">Predicted field</span><span class="desc">unchanged by calibration</span></p>
                <p class="col-title"><span class="name">Lower bound</span><span class="desc">conformally calibrated</span></p>
                <p class="col-title"><span class="name">Upper bound</span><span class="desc">conformally calibrated</span></p>
                <div class="flex items-center justify-center text-gray-300 text-[12px] border border-dashed border-gray-200 rounded-md"
                     :style="{ width: cubeSize + 'px', height: cubeSize + 'px' }">same as above</div>
                <RoiSelect3d preset="density" sync :url="afterUrls ? afterUrls.lower : ''" :roi="roi" :crop="cropPreview" :size="cubeSize" />
                <RoiSelect3d preset="density" sync :url="afterUrls ? afterUrls.upper : ''" :roi="roi" :crop="cropPreview" :size="cubeSize" />
              </div>

              <p class="text-[11.5px] text-gray-400 mt-1 px-2 text-center">
                Orange box = ROI (set voxel indices on the left) · drag to rotate, scroll to zoom
              </p>
            </template>
          </div>
        </div>

        <!-- Right: recommendation results -->
        <div class="panel flex flex-col">
          <div class="panel-head">
            <h2 class="panel-title">⭐ Recommended Parameters</h2>
            <span v-if="recs.length" class="hint">ranked by your uncertainty preference</span>
          </div>
          <div class="px-3 py-2 h-[calc(100vh-190px)] overflow-y-auto">

            <div v-if="!recs.length" class="flex flex-col items-center justify-center text-gray-400 text-[13px] text-center h-[60%]">
              <div class="text-3xl mb-2">✨</div>
              <p>No recommendations yet —<br/>set an ROI and click <b>⭐ Recommend parameters</b>.</p>
            </div>

            <div v-if="currentEval" class="border border-[#e5e5e5] rounded-[10px] p-3 mb-3 bg-gray-50">
              <div class="text-[13px] text-gray-500">Current parameters ({{ objLabel }})</div>
              <div class="flex justify-between items-center mt-1">
                <span class="font-mono text-[14px]">{{ fmtParams(currentEval.params) }}</span>
                <span class="font-semibold">{{ currentEval.value.toFixed(5) }}</span>
              </div>
              <div v-if="currentEval.aleatoric != null" class="text-[12px] text-gray-400 mt-0.5">
                Data unc. {{ currentEval.aleatoric.toPrecision(4) }} · Model unc. {{ currentEval.epistemic.toPrecision(4) }}
              </div>
            </div>

            <div v-for="(rec, i) in recs" :key="i"
                 class="border rounded-[10px] p-3 mb-3 transition-colors"
                 :class="previewIndex === i ? 'border-[#ACACFF] border-2 bg-[#ACACFF]/5' : 'border-[#e5e5e5]'">
              <div class="flex justify-between items-center">
                <span class="bg-[#ACACFF] text-white rounded-full w-[24px] h-[24px] inline-flex items-center justify-center text-[12px] font-bold"
                      :title="`Recommendation rank ${i + 1}`">{{ i + 1 }}</span>
                <span class="text-[12px] text-gray-400">RMSE vs {{ refLabel }}
                  <b class="text-[15px] text-[#191919] ml-1">{{ rec.value.toFixed(5) }}</b>
                </span>
              </div>
              <div class="grid grid-cols-3 gap-1 mt-2 text-center">
                <div v-for="(name, j) in ['OmM', 'OmB', 'h']" :key="name" class="bg-gray-50 rounded p-1">
                  <div class="text-[11px] text-gray-400">{{ name }}</div>
                  <div class="font-mono text-[13px]">{{ rec.params[j].toPrecision(4) }}</div>
                </div>
              </div>
              <div v-if="rec.aleatoric != null" class="grid grid-cols-2 gap-1 mt-1 text-center">
                <div class="rounded p-1" :class="prefData === 'max' ? 'bg-[#f2f1fc]' : 'bg-gray-50'">
                  <div class="text-[11px] text-gray-400">Data unc. ({{ prefData === 'max' ? 'prefer high' : 'prefer low' }})</div>
                  <div class="font-mono text-[13px]">{{ rec.aleatoric.toPrecision(4) }}</div>
                </div>
                <div class="rounded p-1" :class="prefModel === 'max' ? 'bg-[#f2f1fc]' : 'bg-gray-50'">
                  <div class="text-[11px] text-gray-400">Model unc. ({{ prefModel === 'max' ? 'prefer high' : 'prefer low' }})</div>
                  <div class="font-mono text-[13px]">{{ rec.epistemic.toPrecision(4) }}</div>
                </div>
              </div>
              <div v-if="currentEval" class="text-[12px] mt-1"
                   :class="improves(rec) ? 'text-green-600' : 'text-gray-400'">
                {{ deltaLabel(rec) }}
              </div>
              <div class="flex gap-2 mt-2">
                <el-button size="small" :loading="previewLoading && previewIndex === i" @click="preview(rec, i)">👁 Preview</el-button>
                <el-button size="small" type="primary" title="Predict with these parameters in Module 2"
                           @click="sendToIndex(rec)">→ Send to Module 2</el-button>
              </div>
            </div>

            <!-- Triple preview of the selected recommendation (same three fields as a View1 row) -->
            <div v-if="previewUrls" class="mt-4">
              <h3 class="font-semibold text-[13px] mb-1">
                Preview · recommendation #{{ previewIndex + 1 }}
                <span class="hint font-mono font-normal">{{ fmtParams(recs[previewIndex].params) }}</span>
              </h3>
              <div class="grid grid-cols-3 gap-1 place-items-center">
                <p class="col-title"><span class="name">Predicted field</span><span class="desc">mean of log10 density</span></p>
                <p class="col-title"><span class="name">Aleatoric uncertainty</span><span class="desc">data noise</span></p>
                <p class="col-title"><span class="name">Epistemic uncertainty</span><span class="desc">model knowledge</span></p>
                <Cube3d2 :key="'p' + previewUrls.output" :url="previewUrls.output" :size="140" />
                <Cube3dData :key="'a' + previewUrls.data" :url="previewUrls.data" :size="140" />
                <Cube3dModel :key="'e' + previewUrls.model" :url="previewUrls.model" :size="140" />
              </div>
            </div>

          </div>
        </div>
      </div>

      <!-- Parameter sensitivity analysis (differentiable NN version): same structure as the
           line chart at the bottom of Module 1; curves/gradients come from autograd on the
           Evidential INR and follow the current ROI and context parameters -->
      <div class="mt-2 mx-4 pb-4">
        <div class="panel flex flex-col">
          <div class="panel-head">
            <h2 class="panel-title">📈 Parameter Sensitivity — prediction mean &amp; std vs each parameter</h2>
            <span class="hint">{{ sensLoading ? 'computing…' : 'surrogate autograd gradients within the current ROI' }}</span>
          </div>
          <div class="h-[360px] p-2">
            <div v-if="!sensData" class="flex flex-col items-center justify-center text-gray-400 text-[13px] text-center h-full">
              <div class="text-3xl mb-2">📈</div>
              <p>Click <b>▶ Load field</b> — sensitivity curves of the surrogate over each parameter<br/>
              (inside the current ROI) render here.</p>
            </div>
            <NNParamSensitivity v-else :result="sensData" />
          </div>
        </div>
      </div>

      <!-- AI assistant (floating, bottom right), carries Module 3's UI state -->
      <AIAssistant :extra-state="aiState" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onActivated } from 'vue'
import { useRouter } from 'vue-router'
import { ElLoading, ElMessage } from 'element-plus'
import AppHeader from '@/components/AppHeader.vue'
import AIAssistant from '@/components/AIAssistant.vue'
import RoiSelect3d from '@/components/RoiSelect3d.vue'
import ChartView from '@/components/ChartView.vue'
import Cube3d2 from '@/components/Cube3d2.vue'
import Cube3dData from '@/components/Cube3dData.vue'
import Cube3dModel from '@/components/Cube3dModel.vue'
import NNParamSensitivity from '@/components/NNParamSensitivity.vue'
import { generateApi, calibrationApi, roiOptimizeApi, paramSensitivityApi } from '@/api'

const router = useRouter()

// Context field parameters (used to render the base field for ROI selection)
const ctxParams = ref([
  { name: 'OmM', min: 0.12, max: 0.155, value: 0.149, step: 0.001, key: 'omM' },
  { name: 'OmB', min: 0.0215, max: 0.0235, value: 0.0218, step: 0.0001, key: 'omB' },
  { name: 'h', min: 0.55, max: 0.85, value: 0.685, step: 0.01, key: 'h' },
])
const fieldUrls = ref<{ output: string, data: string, model: string } | null>(null)
const fieldParams = ref<number[] | null>(null)
const fieldParamsLabel = computed(() => fieldParams.value ? fmtParams(fieldParams.value) : '')

// Interval bounds (before = uncalibrated Student-t; after = conformal calibration)
const cubeSize = 165
const confidence = ref(0.9)           // Initial confidence (starting value of the ChartView slider)
const confBefore = ref<number | null>(null)   // Confidence actually used by beforeUrls
const calLevel = ref<number | null>(null)     // Calibration level actually used by the backend
const beforeUrls = ref<{ lower: string, upper: string } | null>(null)
const afterUrls = ref<{ lower: string, upper: string } | null>(null)

// ROI (display coordinates, VTK ijk) and optimization settings.
// Objective is fixed to match (prediction closest to the reference); multi-start/Top-K are hardcoded, not exposed, to keep the demo easy to explain
const roi = ref([0, 255, 0, 255, 0, 255])
const cropPreview = ref(true)
// Reference = one of the 5 volume renderings in the middle panel (computed on the fly from the current context params + confidence)
const refField = ref<'pred' | 'lower' | 'upper' | 'lower_cal' | 'upper_cal'>('pred')
const agg = ref('mean')   // Aggregation fixed to ROI mean (not exposed in the UI)
const N_STARTS = 16
const TOP_K = 6

// User preference: among candidates equally close to the reference, prefer higher or lower data / model uncertainty
const prefData = ref<'max' | 'min'>('max')
const prefModel = ref<'max' | 'min'>('max')

const recs = ref<any[]>([])
const currentEval = ref<any>(null)
const optimizing = ref(false)
const previewUrls = ref<{ output: string, data: string, model: string } | null>(null)
const previewIndex = ref(-1)
const previewLoading = ref(false)

const REF_LABELS: Record<string, string> = {
  pred: 'Pred', lower: 'Lower (before cal.)', upper: 'Upper (before cal.)',
  lower_cal: 'Lower (after cal.)', upper_cal: 'Upper (after cal.)',
}
const refLabel = computed(() => REF_LABELS[refField.value])
const objLabel = computed(() => `RMSE vs ${refLabel.value}, log10`)
const explainText = computed(() =>
  `Gradient-based search over (OmM, OmB, h) for predictions closest to ${refLabel.value} inside the ROI; ` +
  `candidates are then ranked preferring ${prefData.value === 'max' ? 'high' : 'low'} data uncertainty ` +
  `and ${prefModel.value === 'max' ? 'high' : 'low'} model uncertainty.`)
const fmtParams = (p: number[]) => `OmM=${(+p[0]).toPrecision(4)}, OmB=${(+p[1]).toPrecision(4)}, h=${(+p[2]).toPrecision(4)}`
const curParamArr = () => ctxParams.value.map(i => i.value)

const improves = (rec: any) => currentEval.value && rec.value < currentEval.value.value
const deltaLabel = (rec: any) => {
  const cur = currentEval.value.value
  const pct = cur !== 0 ? Math.abs(rec.value - cur) / Math.abs(cur) * 100 : 0
  return improves(rec) ? `−${pct.toFixed(1)}% closer than current` : 'no closer than current'
}

// Re-rank candidates by user preference: normalize aleatoric/epistemic each to [0,1],
// sum the scores along the preferred directions, highest first (all candidates are already local optima of match, i.e. all very close to the reference)
const sortByPref = (list: any[]) => {
  if (list.length <= 1 || list[0]?.aleatoric == null) return list
  const norm = (v: number, arr: number[]) => {
    const lo = Math.min(...arr), hi = Math.max(...arr)
    return hi > lo ? (v - lo) / (hi - lo) : 0.5
  }
  const ales = list.map(r => r.aleatoric), epis = list.map(r => r.epistemic)
  const score = (r: any) =>
    (prefData.value === 'max' ? norm(r.aleatoric, ales) : 1 - norm(r.aleatoric, ales)) +
    (prefModel.value === 'max' ? norm(r.epistemic, epis) : 1 - norm(r.epistemic, epis))
  return [...list].sort((a, b) => score(b) - score(a))
}

// If results are already in hand, toggling the preference switches just re-ranks them — no re-optimization needed
watch([prefData, prefModel], () => {
  if (recs.value.length) {
    recs.value = sortByPref(recs.value)
    previewUrls.value = null
    previewIndex.value = -1
  }
})

// Display coordinates (VTK ijk) -> backend voxel axes: in the backend's flattened array x is the slowest dim (meshgrid ij + C-order),
// while in VTK voxel order x is the fastest dim, so the displayed X/Z axes are swapped with the backend's x/z
const roiToBackend = (r: number[]) => [r[4], r[5], r[2], r[3], r[0], r[1]]

// Uncalibrated interval: same as Module 2's render (/generate datatype=2)
const renderBounds = async (conf: number, silentFail = false) => {
  if (!fieldParams.value) return
  let loading
  try {
    loading = ElLoading.service({ lock: true, text: 'Rendering interval…', background: 'rgba(0,0,0,0.7)' })
    const { data } = await generateApi.create({
      data: { dataname: 'nyx', param: fieldParams.value, datatype: 2, confidence_level: conf },
    }) as any
    beforeUrls.value = { lower: '/nyx/' + data[0], upper: '/nyx/' + data[1] }
    confBefore.value = conf
    confidence.value = conf
  } catch (err) {
    console.error(err)
    if (!silentFail) ElMessage.error('Interval rendering failed: ' + err)
  } finally {
    loading?.close()
  }
}

// Interval after conformal calibration: same as Module 2's calibration (/calibration, matched to the nearest precomputed level)
const renderCalibrated = async (conf: number, silentFail = false) => {
  if (!fieldParams.value) return
  let loading
  try {
    loading = ElLoading.service({ lock: true, text: 'Calibrating…', background: 'rgba(0,0,0,0.7)' })
    const res: any = await calibrationApi.create({
      data: { dataname: 'nyx', param: fieldParams.value, confidence_level: conf },
    })
    afterUrls.value = { lower: '/nyx/' + res.data[0], upper: '/nyx/' + res.data[1] }
    calLevel.value = res.calibration_level ?? conf
    if (res.calibration_level != null && Math.abs(res.calibration_level - conf) > 1e-6) {
      ElMessage.info(`Confidence ${conf} used calibration data from the nearest level ${res.calibration_level}`)
    }
  } catch (err) {
    console.error(err)
    if (!silentFail) ElMessage.error('Calibration failed: ' + err)
  } finally {
    loading?.close()
  }
}

// Slider changes confidence: automatically re-fetch both the uncalibrated and calibrated bounds (same params hit the backend cache, returns instantly)
const onConfidenceChange = async (conf: number) => {
  confidence.value = conf
  await renderBounds(conf)
  await renderCalibrated(conf)
}

// Parameter sensitivity (differentiable NN version): sweep curves of the prediction mean/std within the ROI over each parameter + autograd gradients.
// Computed automatically after Load Field; recomputed on ROI change (debounced). A fixed seed guarantees identical results for the same ROI and params
const sensData = ref<any>(null)
const sensLoading = ref(false)
const fetchSensitivity = async () => {
  if (!fieldParams.value) return
  sensLoading.value = true
  try {
    const res: any = await paramSensitivityApi.create({
      data: { roi: roiToBackend(roi.value), params: fieldParams.value },
    })
    sensData.value = res
  } catch (err) {
    console.error('param sensitivity failed', err)
  } finally {
    sensLoading.value = false
  }
}
let sensTimer: any = null
watch(() => [...roi.value], () => {
  if (!fieldParams.value) return
  clearTimeout(sensTimer)
  sensTimer = setTimeout(fetchSensitivity, 800)
})

// Load Field: fetch Pred + uncalibrated bounds + calibrated bounds all at once (default confidence 0.9)
const loadField = async () => {
  const p = curParamArr()
  let loading
  try {
    loading = ElLoading.service({ lock: true, text: 'Generating field…', background: 'rgba(0,0,0,0.7)' })
    const { data } = await generateApi.create({ data: { dataname: 'nyx', param: p, datatype: 1 } }) as any
    fieldUrls.value = { output: '/nyx/' + data[0], data: '/nyx/' + data[1], model: '/nyx/' + data[2] }
    fieldParams.value = p
    beforeUrls.value = null
    afterUrls.value = null
  } catch (err) {
    console.error(err)
    ElMessage.error('Field generation failed: ' + err)
    return
  } finally {
    loading?.close()
  }
  await renderBounds(confidence.value, true)
  await renderCalibrated(confidence.value, true)
  fetchSensitivity()
}

const recommend = async () => {
  if (!fieldParams.value) {
    ElMessage.warning('Click "Load field" first — the reference is one of the 5 volume renderings in the middle panel')
    return
  }
  optimizing.value = true
  try {
    const body: any = {
      roi: roiToBackend(roi.value),
      objective: 'match',
      agg: agg.value,
      direction: 'min',
      n_starts: N_STARTS,
      top_k: TOP_K,
      eval_params: [curParamArr()],
      // The reference field is computed on the backend on the fly from the context params at load time + current confidence (direct NIG cache hit)
      ref: { type: 'field', kind: refField.value, params: fieldParams.value, confidence: confidence.value },
    }
    const res: any = await roiOptimizeApi.create({ data: body })
    recs.value = sortByPref(res.recommendations || [])
    currentEval.value = res.eval ? res.eval[0] : null
    previewUrls.value = null
    previewIndex.value = -1
    if (!recs.value.length) ElMessage.warning('No recommendation returned')
  } catch (err) {
    console.error(err)
    ElMessage.error('Optimization failed: ' + err)
  } finally {
    optimizing.value = false
  }
}

const preview = async (rec: any, i: number) => {
  previewIndex.value = i
  previewLoading.value = true
  try {
    const { data } = await generateApi.create({ data: { dataname: 'nyx', param: rec.params, datatype: 1 } }) as any
    previewUrls.value = { output: '/nyx/' + data[0], data: '/nyx/' + data[1], model: '/nyx/' + data[2] }
  } catch (err) {
    console.error(err)
    ElMessage.error('Preview failed: ' + err)
  } finally {
    previewLoading.value = false
  }
}

// Parameter handoff: save to localStorage then jump to Index; ParameterView reads it on mount and auto-Submits
const sendToIndex = (rec: any) => {
  localStorage.setItem('nyx_pending_params', JSON.stringify({
    omM: rec.params[0], omB: rec.params[1], h: rec.params[2],
  }))
  router.push('/index')
}

// Reverse handoff: the "Optimize" button on a Module 2 history row passes params via nyx_pending_ctx;
// auto-fill Context Field and Load Field (with keep-alive, both onMounted and onActivated must consume it)
const consumePendingCtx = () => {
  try {
    const raw = localStorage.getItem('nyx_pending_ctx')
    if (!raw) return
    localStorage.removeItem('nyx_pending_ctx')
    const p = JSON.parse(raw)
    ctxParams.value.find(i => i.key === 'omM')!.value = p.omM
    ctxParams.value.find(i => i.key === 'omB')!.value = p.omB
    ctxParams.value.find(i => i.key === 'h')!.value = p.h
    loadField()
  } catch (e) {
    console.warn('pending ctx handoff failed', e)
  }
}
onMounted(consumePendingCtx)
onActivated(consumePendingCtx)

// Module 3's UI state: sent to the backend with AI questions so the AI can answer
// things like "what is the current ROI / reference, and why were these parameters recommended"
const aiState = () => ({
  view: 'paraspace (View 3, ROI parameter recommendation)',
  context_params: fieldParams.value
    ? { omM: fieldParams.value[0], omB: fieldParams.value[1], h: fieldParams.value[2] }
    : null,
  roi_view_axes: [...roi.value],
  crop_to_roi: cropPreview.value,
  confidence: confidence.value,
  calibration_level: calLevel.value,
  reference: refField.value,
  uncertainty_preference: { data: prefData.value, model: prefModel.value },
  current_eval: currentEval.value,
  recommendations: recs.value.map((r: any, i: number) => ({
    rank: i + 1, params: r.params, rmse_vs_reference: r.value,
    aleatoric: r.aleatoric, epistemic: r.epistemic,
  })),
  parameter_sensitivity: sensData.value ? {
    note: 'mean |d(ROI-mean prediction)/d(normalized param)| over a full-range sweep, computed by autograd on the surrogate',
    OmM: sensData.value.sensitivity[0],
    OmB: sensData.value.sensitivity[1],
    h: sensData.value.sensitivity[2],
  } : null,
})
</script>

<!-- Sliders/buttons inherit the shared purple .explore-accent palette from src/index.css -->

