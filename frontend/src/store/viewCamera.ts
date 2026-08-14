import { ref } from 'vue'
import vtkCamera from '@kitware/vtk.js/Rendering/Core/Camera'

// Module 2's global shared camera: all volume renderings in View1 / View2 share one
// vtkCamera instance — rotate/zoom any one view and the rest show the same viewpoint.
// Only cube components that explicitly pass syncCamera join; Module 1 / Module 3
// volume renderings are unaffected.
// The sync mechanism is exactly the same as Module 3 (syncViews in RoiSelect3d.vue):
// when the camera is modified, use rAF to coalesce frames and re-render all members at
// once; syncLock prevents camera changes made during the re-render (e.g. clippingRange)
// from cascading and re-triggering the sync (otherwise rendering loops forever after
// the interaction ends).
export const sharedCamera = vtkCamera.newInstance()
let initialized = false
let syncLock = false
let syncScheduled = false

// Registry of live views: they trigger each other's re-renders when the shared camera changes (merged within the same frame)
const liveWindows = new Set<any>()

// Snapshot-mode views watch this epoch: 400ms after interaction stops, re-emit a snapshot from the same viewpoint
export const cameraEpoch = ref(0)
let epochTimer: any = null

const scheduleSyncRender = () => {
  if (syncScheduled) return
  syncScheduled = true
  requestAnimationFrame(() => {
    syncLock = true
    liveWindows.forEach((rw) => {
      try { rw.render() } catch (e) { liveWindows.delete(rw) }
    })
    syncLock = false
    syncScheduled = false
  })
}

sharedCamera.onModified(() => {
  if (syncLock) return
  scheduleSyncRender()
  clearTimeout(epochTimer)
  epochTimer = setTimeout(() => { cameraEpoch.value++ }, 400)
})

// Swap the renderer's camera for the shared camera. The first view writes its own
// resetCamera result into the shared camera as the initial viewpoint (all volumes are
// the same 256³ size, so the default viewpoints already match across views).
export const adoptSharedCamera = (renderer: any) => {
  syncLock = true
  try {
    renderer.setActiveCamera(sharedCamera)
    if (!initialized) {
      initialized = true
      renderer.resetCamera()
    }
  } finally {
    syncLock = false
  }
}

// Use this for programmatic re-renders (not user interaction): renders under the lock,
// so camera side effects like clippingRange don't trigger a sync/snapshot-refresh cascade
export const lockedRender = (rw: any) => {
  syncLock = true
  try { rw.render() } finally { syncLock = false }
}

export const registerLiveWindow = (rw: any) => { liveWindows.add(rw) }
export const unregisterLiveWindow = (rw: any) => { liveWindows.delete(rw) }
