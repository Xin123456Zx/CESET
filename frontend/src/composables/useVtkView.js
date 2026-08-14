import { ref, watch, onMounted, onBeforeUnmount, onActivated, onDeactivated } from 'vue'
import { adoptSharedCamera, registerLiveWindow, unregisterLiveWindow, lockedRender, cameraEpoch } from '@/store/viewCamera'

// Browsers hard-cap the number of WebGL contexts (Chrome ~16); beyond that the
// oldest one gets evicted and its canvas goes blank. Strategy here:
//   1. On first load, each cube renders one frame, saves a snapshot, then releases
//      its WebGL context and shows the snapshot;
//   2. Clicking the snapshot rebuilds it as a fully interactive 3D view
//      (rotate/zoom/pick all preserved);
//   3. At most MAX_LIVE 3D views are active globally; when exceeded, the earliest
//      activated one automatically falls back to snapshot mode (the snapshot uses
//      the view angle at fallback time, so the user's rotation is not lost).
//      12 live + MAX_CONCURRENT_BUILDS(3) transient contexts under construction = 15,
//      still within Chrome's ~16 limit; with a full Module 2 row (3 in View1 +
//      3 in View2) all autoLive, two rows can be interactive at the same time
const MAX_LIVE = 12
const livePool = [] // [{id, deactivate}]

// Builds (including the transient pre-snapshot contexts) must be throttled too:
// when many cubes load at once, creating contexts together can still blow past the
// browser limit, evicting the earliest before its snapshot completes and capturing
// a broken image. At most MAX_CONCURRENT_BUILDS build globally; the rest queue up.
const MAX_CONCURRENT_BUILDS = 3
let buildingCount = 0
const buildQueue = []
const acquireBuildSlot = () => new Promise((res) => {
  if (buildingCount < MAX_CONCURRENT_BUILDS) { buildingCount++; res() }
  else buildQueue.push(res)
})
const releaseBuildSlot = () => {
  const next = buildQueue.shift()
  if (next) next()
  else buildingCount--
}

/**
 * @param getContainer  () => HTMLElement  container the vtk view mounts into
 * @param buildScene    () => Promise<{fullScreenRenderer, renderWindow}|null>
 *                      builds the rendering pipeline, resolves after the first frame renders
 * @param opts          {autoLive?: boolean, syncCamera?: boolean}
 *                      autoLive=true mounts directly as interactive 3D
 *                      (skips snapshot mode; suited to a focus view that is alone on
 *                      screen, still managed by the MAX_LIVE pool)
 *                      syncCamera=true joins Module 2's global shared camera (store/viewCamera):
 *                      live views sync rotation/zoom instantly, snapshot-mode views re-render
 *                      a snapshot at the same view angle after interaction stops
 */
export function useVtkView(getContainer, buildScene, opts = {}) {
  const id = Symbol('vtk-view')
  const snapshot = ref('')   // snapshot dataURL; when non-empty and not live, the template shows <img>
  const live = ref(false)    // whether currently interactive 3D
  const loading = ref(false)
  let ctx = null
  let buildToken = 0

  const releaseWebGL = () => {
    if (!ctx) return
    if (opts.syncCamera) unregisterLiveWindow(ctx.renderWindow)
    const container = getContainer()
    const canvas = container && container.querySelector('canvas')
    try { ctx.fullScreenRenderer.delete() } catch (e) { /* already destroyed */ }
    // Explicitly lose the context after delete() to return the quota immediately instead of waiting for GC
    try {
      const gl = canvas && (canvas.getContext('webgl2') || canvas.getContext('webgl'))
      const ext = gl && gl.getExtension('WEBGL_lose_context')
      if (ext) ext.loseContext()
    } catch (e) { /* ignore */ }
    if (container) container.innerHTML = ''
    ctx = null
  }

  const capture = async () => {
    if (!ctx) return false
    try {
      const img = await ctx.renderWindow.captureImages()[0]
      // When the context is lost, toDataURL returns an empty image; a mid-render failure
      // captures a plain white frame. Both compress to very small files (a plain white
      // 200x200 png is ~1-2KB), so both are treated as failures and retried
      if (img && img.length > 6000) {
        snapshot.value = img
        return true
      }
      console.warn('snapshot too small (blank/lost frame), len =', img && img.length)
    } catch (e) {
      console.error('capture snapshot failed', e)
    }
    return false
  }

  const removeFromPool = () => {
    const i = livePool.findIndex((v) => v.id === id)
    if (i >= 0) livePool.splice(i, 1)
  }

  const deactivate = async () => {
    removeFromPool()
    if (!ctx) { live.value = false; return }
    await capture()
    releaseWebGL()
    live.value = false
  }

  const build = async (keepLive) => {
    const token = ++buildToken
    loading.value = true
    await acquireBuildSlot()
    try {
      // Rebuild once if the snapshot fails (e.g. the context got evicted)
      for (let attempt = 0; attempt < 2; attempt++) {
        let built = null
        try {
          built = await buildScene()
        } catch (e) {
          console.error('buildScene failed', e)
        }
        if (token !== buildToken) {
          // Component was unmounted/rebuilt during the build; discard this result
          if (built) try { built.fullScreenRenderer.delete() } catch (e) { /* ignore */ }
          return
        }
        ctx = built
        if (!ctx) return
        // Interaction downsampling uses vtk.js's default desiredUpdateRate=30 (downsample
        // more aggressively while dragging to keep the frame rate, restore detail on
        // release) — identical to Module 3 (RoiSelect3d leaves this parameter unchanged)
        // After switching to the global shared camera, render one more frame so both the
        // live view and the snapshot show the current shared view angle
        if (opts.syncCamera) {
          try {
            adoptSharedCamera(ctx.fullScreenRenderer.getRenderer())
            lockedRender(ctx.renderWindow)
          } catch (e) { /* ignore */ }
        }
        if (keepLive) {
          live.value = true
          if (opts.syncCamera) registerLiveWindow(ctx.renderWindow)
          livePool.push({ id, deactivate })
          while (livePool.length > MAX_LIVE) {
            livePool.shift().deactivate()
          }
          return
        }
        const ok = await capture()
        releaseWebGL()
        if (ok) return
        console.warn('snapshot invalid, retrying build...')
      }
    } finally {
      loading.value = false
      releaseBuildSlot()
    }
  }

  // Click the snapshot -> activate as interactive 3D
  const activate = () => {
    if (live.value || loading.value) return
    build(true)
  }

  // fit to view: reset the camera to frame the whole volume (only effective in live state)
  const resetCamera = () => {
    if (!ctx) return
    try {
      ctx.fullScreenRenderer.getRenderer().resetCamera()
      ctx.renderWindow.render()
    } catch (e) { /* already destroyed */ }
  }

  // Rebuild when scene parameters (e.g. the global ROI) change: live views rebuild as live, snapshot views re-render a snapshot
  const rebuild = () => { if (!loading.value) build(live.value) }

  // After the shared camera is rotated by another view, snapshot-mode views re-render a snapshot at the same view angle (live views already sync instantly)
  if (opts.syncCamera) {
    watch(cameraEpoch, () => { if (!live.value) rebuild() })
  }

  onMounted(() => build(!!opts.autoLive))
  onBeforeUnmount(() => {
    buildToken++
    removeFromPool()
    releaseWebGL()
  })

  // keep-alive route switching: release the WebGL context when navigating away (live
  // views take a snapshot first as a fallback), otherwise contexts stacking up across
  // modules would blow past the browser limit; live views rebuild automatically on return
  let wasLiveBeforeDeactivate = false
  let releasedByDeactivate = false
  onDeactivated(() => {
    releasedByDeactivate = true
    wasLiveBeforeDeactivate = live.value
    buildToken++          // Discard builds still in progress at the moment of navigating away
    if (live.value) deactivate()
    else { removeFromPool(); releaseWebGL() }
  })
  onActivated(() => {
    if (!releasedByDeactivate) return   // onActivated also fires on first mount; skip
    releasedByDeactivate = false
    if (wasLiveBeforeDeactivate && !loading.value) build(true)
  })

  return { snapshot, live, loading, activate, resetCamera, rebuild }
}
