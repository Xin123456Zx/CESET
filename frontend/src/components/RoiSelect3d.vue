<template>
  <div class="relative mx-auto" :style="{ width: size + 'px', height: size + 'px' }">
    <div ref="vtkContainer" :style="{ width: size + 'px', height: size + 'px' }" />
    <div v-if="!url" class="absolute inset-0 flex items-center justify-center text-gray-400 border border-dashed border-gray-300 rounded-md">
      Load a context field to start
    </div>
  </div>
</template>

<script>
import { ref, watch, onMounted, onBeforeUnmount, onActivated, onDeactivated } from 'vue';
import '@kitware/vtk.js/Rendering/Profiles/Geometry';
import '@kitware/vtk.js/Rendering/Profiles/Volume';
import vtkFullScreenRenderWindow from '@kitware/vtk.js/Rendering/Misc/FullScreenRenderWindow';
import vtkXMLImageDataReader from '@kitware/vtk.js/IO/XML/XMLImageDataReader';
import vtkVolume from '@kitware/vtk.js/Rendering/Core/Volume';
import vtkVolumeMapper from '@kitware/vtk.js/Rendering/Core/VolumeMapper';
import vtkColorTransferFunction from '@kitware/vtk.js/Rendering/Core/ColorTransferFunction';
import vtkPiecewiseFunction from '@kitware/vtk.js/Common/DataModel/PiecewiseFunction';
import vtkPlane from '@kitware/vtk.js/Common/DataModel/Plane';
import vtkActor from '@kitware/vtk.js/Rendering/Core/Actor';
import vtkMapper from '@kitware/vtk.js/Rendering/Core/Mapper';
import vtkPolyData from '@kitware/vtk.js/Common/DataModel/PolyData';
import vtkScalarBarActor from '@kitware/vtk.js/Rendering/Core/ScalarBarActor';
import vtkCamera from '@kitware/vtk.js/Rendering/Core/Camera';

// Camera sync group: instances with sync=true share the same camera — rotating/zooming
// in any one view moves all the others. When the camera is modified, use rAF to coalesce
// frames and re-render all members at once; syncLock prevents camera changes made during
// the re-render (e.g. clippingRange) from cascading and re-triggering the sync.
const syncViews = new Set();
let syncCamera = null;
let syncLock = false;
let syncScheduled = false;
const scheduleSyncRender = () => {
  if (syncScheduled) return;
  syncScheduled = true;
  requestAnimationFrame(() => {
    syncLock = true;
    syncViews.forEach((v) => { try { v.renderWindow.render(); } catch (e) { /* already destroyed */ } });
    syncLock = false;
    syncScheduled = false;
  });
};

// 'density' preset: exactly the same log10 density colormap / opacity as Module 2's
// Cube3d2.vue, so View3's Pred / Lower / Upper volume rendering looks consistent
// with View1 and View2
const DENSITY_CTF = [
  [9.0, 0.831373, 0.909804, 0.980392], [9.0225, 0.74902, 0.862745, 0.960784],
  [9.045, 0.694118, 0.827451, 0.941176], [9.09, 0.568627, 0.760784, 0.921569],
  [9.135, 0.45098, 0.705882, 0.901961], [9.18, 0.345098, 0.643137, 0.858824],
  [9.225, 0.247059, 0.572549, 0.819608], [9.27, 0.180392, 0.521569, 0.780392],
  [9.288, 0.14902, 0.490196, 0.74902], [9.324, 0.129412, 0.447059, 0.709804],
  [9.36, 0.101961, 0.427451, 0.690196], [9.378, 0.094118, 0.403922, 0.658824],
  [9.396, 0.090196, 0.392157, 0.639216], [9.414, 0.082353, 0.568627, 0.619608],
  [9.432, 0.070588, 0.529412, 0.6], [9.45, 0.066667, 0.429412, 0.568627],
  [9.468, 0.047451, 0.313725, 0.541176], [9.486, 0.047059, 0.34902, 0.498039],
  [9.54, 0.109804, 0.266667, 0.411765], [9.558, 0.113725, 0.258824, 0.380392],
  [9.576, 0.105882, 0.29098, 0.34902], [9.594, 0.101961, 0.25098, 0.321569],
  [9.612, 0.105882, 0.301961, 0.262745], [9.63, 0.094118, 0.309804, 0.243137],
  [9.648, 0.082353, 0.321569, 0.227451], [9.666, 0.07451, 0.341176, 0.219608],
  [9.684, 0.070588, 0.360784, 0.211765], [9.702, 0.066667, 0.380392, 0.215686],
  [9.72, 0.062745, 0.4, 0.176471], [9.74498, 0.0705882, 0.411765, 0.156863],
  [9.765, 0.07451, 0.419608, 0.145098], [9.81, 0.086275, 0.439216, 0.117647],
  [9.855, 0.121569, 0.470588, 0.117647], [9.9, 0.184314, 0.501961, 0.14902],
  [9.945, 0.254902, 0.541176, 0.188235], [9.99, 0.32549, 0.580392, 0.231373],
  [10.035, 0.403922, 0.619608, 0.278431], [10.08, 0.501961, 0.670588, 0.333333],
  [10.17, 0.741176, 0.788235, 0.490196], [10.206, 0.858824, 0.858824, 0.603922],
  [10.26, 0.921569, 0.835294, 0.580392], [10.35, 0.901961, 0.729412, 0.494118],
  [10.44, 0.858824, 0.584314, 0.388235], [10.53, 0.8, 0.439216, 0.321569],
  [10.62, 0.678431, 0.298039, 0.203922], [10.71, 0.54902, 0.168627, 0.109804],
  [10.755, 0.478431, 0.082353, 0.047059], [10.8, 0.45098, 0.007843, 0],
];

// ROI preview view: volume rendering + a wireframe box drawn from the ROI entered on
// the left (read-only display, no drag interaction).
// roi is inclusive voxel indices [xmin,xmax,ymin,ymax,zmin,zmax] in display coordinates
// (VTK ijk); the conversion to backend voxel axes (x/z swapped) is the parent's job.
export default {
  props: {
    url: { type: String, default: '' },
    roi: { type: Array, default: () => [0, 255, 0, 255, 0, 255] },
    crop: { type: Boolean, default: true },   // true = clip the volume rendering to the ROI so the box contents are directly visible
    size: { type: Number, default: 480 },
    // 'density' = same log10 density mapping as Module 2 (used for Pred/Lower/Upper);
    // 'auto' = cool-warm spread over the data's actual range (for uncertainty or any other field)
    preset: { type: String, default: 'auto' },
    // true = join the global camera sync group (all sync views share the viewpoint; rotate/zoom together)
    sync: { type: Boolean, default: false },
  },
  setup(props) {
    const vtkContainer = ref(null);
    let ctx = null;   // {fullScreenRenderer, renderWindow, renderer, volumeMapper, boxPoints, boxData}
    let buildToken = 0;

    // Inclusive voxel indices -> voxel boundary coordinates (data has origin=0 spacing=1, so world matches ijk)
    const roiBounds = () => {
      const r = props.roi;
      return [r[0], r[1] + 1, r[2], r[3] + 1, r[4], r[5] + 1];
    };

    const destroy = () => {
      if (!ctx) return;
      syncViews.delete(ctx);
      const canvas = vtkContainer.value && vtkContainer.value.querySelector('canvas');
      try { ctx.fullScreenRenderer.delete(); } catch (e) { /* already destroyed */ }
      try {
        const gl = canvas && (canvas.getContext('webgl2') || canvas.getContext('webgl'));
        const ext = gl && gl.getExtension('WEBGL_lose_context');
        if (ext) ext.loseContext();
      } catch (e) { /* ignore */ }
      if (vtkContainer.value) vtkContainer.value.innerHTML = '';
      ctx = null;
    };

    // ROI wireframe: 8 vertices + 12 edges
    const boxEdges = new Uint32Array([
      2, 0, 1, 2, 1, 3, 2, 3, 2, 2, 2, 0,   // bottom face
      2, 4, 5, 2, 5, 7, 2, 7, 6, 2, 6, 4,   // top face
      2, 0, 4, 2, 1, 5, 2, 3, 7, 2, 2, 6,   // vertical edges
    ]);
    const boxCorners = (b) => Float32Array.from([
      b[0], b[2], b[4], b[1], b[2], b[4], b[0], b[3], b[4], b[1], b[3], b[4],
      b[0], b[2], b[5], b[1], b[2], b[5], b[0], b[3], b[5], b[1], b[3], b[5],
    ]);

    const updateRoiDisplay = () => {
      if (!ctx) return;
      const b = roiBounds();
      // Wireframe vertices
      ctx.boxData.getPoints().setData(boxCorners(b), 3);
      ctx.boxData.modified();
      // Volume rendering clipping
      ctx.volumeMapper.removeAllClippingPlanes();
      if (props.crop) {
        ctx.volumeMapper.addClippingPlane(vtkPlane.newInstance({ normal: [1, 0, 0], origin: [b[0], 0, 0] }));
        ctx.volumeMapper.addClippingPlane(vtkPlane.newInstance({ normal: [-1, 0, 0], origin: [b[1], 0, 0] }));
        ctx.volumeMapper.addClippingPlane(vtkPlane.newInstance({ normal: [0, 1, 0], origin: [0, b[2], 0] }));
        ctx.volumeMapper.addClippingPlane(vtkPlane.newInstance({ normal: [0, -1, 0], origin: [0, b[3], 0] }));
        ctx.volumeMapper.addClippingPlane(vtkPlane.newInstance({ normal: [0, 0, 1], origin: [0, 0, b[4]] }));
        ctx.volumeMapper.addClippingPlane(vtkPlane.newInstance({ normal: [0, 0, -1], origin: [0, 0, b[5]] }));
      }
      ctx.volumeMapper.modified();
      ctx.renderWindow.render();
    };

    const build = (url) => {
      const token = ++buildToken;
      destroy();
      if (!url || !vtkContainer.value) return;

      // WebGL context creation may fail (browser context count limit / no-GPU environment):
      // a failure should only affect this view, never break rendering of the whole page
      let fullScreenRenderer;
      try {
        fullScreenRenderer = vtkFullScreenRenderWindow.newInstance({
          rootContainer: vtkContainer.value,
          background: [1, 1, 1],
          containerStyle: { height: `${props.size}px`, width: `${props.size}px` },
        });
      } catch (e) {
        console.error('RoiSelect3d: WebGL init failed', e);
        return;
      }
      const renderer = fullScreenRenderer.getRenderer();
      const renderWindow = fullScreenRenderer.getRenderWindow();

      if (props.sync) {
        if (!syncCamera) {
          syncCamera = vtkCamera.newInstance();
          syncCamera.onModified(() => { if (!syncLock) scheduleSyncRender(); });
        }
        renderer.setActiveCamera(syncCamera);
      }

      const reader = vtkXMLImageDataReader.newInstance();
      reader.setUrl(url).then(() => {
        if (token !== buildToken) return;   // url changed, discard this build
        const data = reader.getOutputData();
        const [dmin, dmax] = data.getPointData().getScalars().getRange();
        const span = (dmax - dmin) || 1;

        const volumeMapper = vtkVolumeMapper.newInstance();
        volumeMapper.setInputData(data);
        const volume = vtkVolume.newInstance();
        volume.setMapper(volumeMapper);

        const ctfun = vtkColorTransferFunction.newInstance();
        const ofun = vtkPiecewiseFunction.newInstance();
        if (props.preset === 'density') {
          // Exactly the same log10 density colormap / opacity as Module 2 (Cube3d2)
          DENSITY_CTF.forEach(([x, r, g, b]) => ctfun.addRGBPoint(x, r, g, b));
          ofun.addPoint(9.0, 0.0);
          ofun.addPoint(9.5, 0.025);
          ofun.addPoint(10.8, 1.0);
        } else {
          // Generic cool-warm gradient: uncertainty or any other field colored over its actual data range
          ctfun.addRGBPoint(dmin, 0.23, 0.30, 0.75);
          ctfun.addRGBPoint(dmin + 0.5 * span, 0.87, 0.87, 0.87);
          ctfun.addRGBPoint(dmax, 0.71, 0.02, 0.15);
          ofun.addPoint(dmin, 0.0);
          ofun.addPoint(dmin + 0.3 * span, 0.05);
          ofun.addPoint(dmax, 0.85);
        }
        volume.getProperty().setRGBTransferFunction(0, ctfun);
        volume.getProperty().setScalarOpacity(0, ofun);
        renderer.addVolume(volume);

        // Same colorbar as Module 2
        const scalarBarActor = vtkScalarBarActor.newInstance({ barPosition: [10, 10], boxPosition: [10, 10] });
        scalarBarActor.setScalarsToColors(ctfun);
        scalarBarActor.setAxisLabel('');
        scalarBarActor.setDrawNanAnnotation(false);
        scalarBarActor.getProperty().setColor(0, 0, 0);
        renderer.addActor(scalarBarActor);

        // ROI wireframe
        const boxData = vtkPolyData.newInstance();
        boxData.getPoints().setData(boxCorners(roiBounds()), 3);
        boxData.getLines().setData(boxEdges);
        const boxMapper = vtkMapper.newInstance();
        boxMapper.setInputData(boxData);
        const boxActor = vtkActor.newInstance();
        boxActor.setMapper(boxMapper);
        boxActor.getProperty().setColor(1.0, 0.45, 0.25);
        boxActor.getProperty().setLineWidth(2.5);
        boxActor.getProperty().setLighting(false);
        renderer.addActor(boxActor);

        ctx = { fullScreenRenderer, renderWindow, renderer, volumeMapper, boxData };
        if (props.sync) {
          // The sync group's initial viewpoint is set by the first view to join; later
          // views adopt the current shared viewpoint, so loading another view doesn't
          // reset the angle the user has already dialed in back to the default
          if (syncViews.size === 0) renderer.resetCamera();
          syncViews.add(ctx);
        } else {
          renderer.resetCamera();
        }
        updateRoiDisplay();
      }).catch((e) => console.error('RoiSelect3d load failed:', e));
    };

    // watch only catches url changes after mount; when the url is already set at mount
    // time (e.g. the Pred view appearing together with v-if), we must build once in
    // onMounted or the view stays blank forever
    watch(() => props.url, (url) => build(url));
    onMounted(() => build(props.url));
    watch(() => [...props.roi], updateRoiDisplay);
    watch(() => props.crop, updateRoiDisplay);

    onBeforeUnmount(() => { buildToken++; destroy(); });

    // keep-alive route switching: release the WebGL context when navigating away
    // (otherwise stacking with Module 2's contexts blows past the browser limit),
    // and rebuild from the current url when returning; the shared camera lives at
    // module scope, so the viewpoint is not lost
    let releasedByDeactivate = false;
    onDeactivated(() => {
      buildToken++;
      if (ctx) { destroy(); releasedByDeactivate = true; }
    });
    onActivated(() => {
      if (!releasedByDeactivate) return;   // onActivated also fires on first mount; skip it
      releasedByDeactivate = false;
      build(props.url);
    });

    return { vtkContainer };
  },
};
</script>
