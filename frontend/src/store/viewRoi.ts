import { reactive } from 'vue'
import vtkPlane from '@kitware/vtk.js/Common/DataModel/Plane'

// Module 2's global ROI: shared by all volume renderings in View1 / View2 (VTK ijk
// display coordinates, endpoints inclusive).
// Only cube components that explicitly pass roiClip apply it; Module 1 / Module 3
// volume renderings are unaffected.
export const viewRoi = reactive({
  roi: [0, 255, 0, 255, 0, 255] as number[],
  crop: true,
})

export const resetViewRoi = () => { viewRoi.roi = [0, 255, 0, 255, 0, 255] }

// Attach 6 clipping planes to the volume mapper for the current ROI (data has origin=0 spacing=1, so world matches ijk)
export const applyRoiClipping = (mapper: any) => {
  mapper.removeAllClippingPlanes()
  if (viewRoi.crop) {
    const r = viewRoi.roi
    const b = [r[0], r[1] + 1, r[2], r[3] + 1, r[4], r[5] + 1]
    mapper.addClippingPlane(vtkPlane.newInstance({ normal: [1, 0, 0], origin: [b[0], 0, 0] }))
    mapper.addClippingPlane(vtkPlane.newInstance({ normal: [-1, 0, 0], origin: [b[1], 0, 0] }))
    mapper.addClippingPlane(vtkPlane.newInstance({ normal: [0, 1, 0], origin: [0, b[2], 0] }))
    mapper.addClippingPlane(vtkPlane.newInstance({ normal: [0, -1, 0], origin: [0, b[3], 0] }))
    mapper.addClippingPlane(vtkPlane.newInstance({ normal: [0, 0, 1], origin: [0, 0, b[4]] }))
    mapper.addClippingPlane(vtkPlane.newInstance({ normal: [0, 0, -1], origin: [0, 0, b[5]] }))
  }
  mapper.modified()
}
