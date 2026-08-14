<template>
  <div class="relative" :style="{ width: size + 'px', height: size + 'px' }" @click="activate">
    <div ref="vtkContainer" :style="{ width: size + 'px', height: size + 'px' }" />
    <!-- Snapshot mode: click to enter 3D interaction (see useVtkView for notes on the WebGL context limit) -->
    <img v-if="snapshot && !live" :src="snapshot" @click="activate"
         class="absolute left-0 top-0 cursor-pointer z-10"
         :style="{ width: size + 'px', height: size + 'px' }"
         title="Click to enter 3D interaction" />
  </div>
</template>

<script>
import { ref, watch } from 'vue';
import { useVtkView } from '@/composables/useVtkView';
import { viewRoi, applyRoiClipping } from '@/store/viewRoi';
import '@kitware/vtk.js/Rendering/Profiles/Geometry';
import '@kitware/vtk.js/Rendering/Profiles/Volume';
import vtkXMLImageDataReader from '@kitware/vtk.js/IO/XML/XMLImageDataReader';
import vtkFullScreenRenderWindow from '@kitware/vtk.js/Rendering/Misc/FullScreenRenderWindow';
import vtkVolume from '@kitware/vtk.js/Rendering/Core/Volume';
import vtkVolumeMapper from '@kitware/vtk.js/Rendering/Core/VolumeMapper';
import vtkColorTransferFunction from '@kitware/vtk.js/Rendering/Core/ColorTransferFunction';
import vtkPiecewiseFunction from '@kitware/vtk.js/Common/DataModel/PiecewiseFunction';
import vtkScalarBarActor from '@kitware/vtk.js/Rendering/Core/ScalarBarActor';

export default {
  props:{
    url:{
        type:String,
        default:""
    },
    type:{
        type:[String,Number],
        default:1
    },
    // Render size (px): default 200 keeps the old usage; the focus panel passes a larger value
    size:{
        type:Number,
        default:200
    },
    // true = interactive 3D right at mount (no click-to-activate from snapshot); use when it's the only one on screen
    autoLive:{
        type:Boolean,
        default:false
    },
    // true = follow Module 2's global ROI clipping (viewRoi); rebuild automatically when the ROI changes
    roiClip:{
        type:Boolean,
        default:false
    },
    // true = join Module 2's global shared camera (viewCamera); all views move with the same viewpoint
    syncCamera:{
        type:Boolean,
        default:false
    }
   },
  setup(props) {
    const vtkContainer = ref(null);
    let liveScene = null;   // { mapper, renderWindow } — used to update ROI clipping instantly while the scene is alive

    // Build the rendering pipeline; resolve once the first frame has rendered (reused by useVtkView for snapshot/activation)
    const buildScene = () => new Promise((resolve) => {
      if (!props.url || !vtkContainer.value) { resolve(null); return; }
        const fullScreenRenderer = vtkFullScreenRenderWindow.newInstance({
          rootContainer: vtkContainer.value,
          background: [1, 1, 1], // white background
          containerStyle: {height: `${props.size}px`, width: `${props.size}px`},
        });
        const renderer = fullScreenRenderer.getRenderer();
        const renderWindow = fullScreenRenderer.getRenderWindow();

        const reader = vtkXMLImageDataReader.newInstance();
        reader.setUrl(props.url).then(() => {
          const data = reader.getOutputData();

          // Get data range (important step!)
          const dataRange = data.getPointData().getScalars().getRange();
          console.log('Data range:', dataRange);

          const mapper = vtkVolumeMapper.newInstance();
          mapper.setInputData(data);
          if (props.roiClip) applyRoiClipping(mapper);
          liveScene = { mapper, renderWindow };

          const actor = vtkVolume.newInstance();
          actor.setMapper(mapper);

          // Use the data's actual range for color mapping
          const ctfun = vtkColorTransferFunction.newInstance();
          ctfun.addRGBPoint(9.0, 0.831373, 0.909804, 0.980392);
          ctfun.addRGBPoint(9.0225, 0.74902, 0.862745, 0.960784);
          ctfun.addRGBPoint(9.045, 0.694118, 0.827451, 0.941176);
          ctfun.addRGBPoint(9.09, 0.568627, 0.760784, 0.921569);
          ctfun.addRGBPoint(9.135, 0.45098, 0.705882, 0.901961);
          ctfun.addRGBPoint(9.18, 0.345098, 0.643137, 0.858824);
          ctfun.addRGBPoint(9.225, 0.247059, 0.572549, 0.819608);
          ctfun.addRGBPoint(9.27, 0.180392, 0.521569, 0.780392);
          ctfun.addRGBPoint(9.288, 0.14902, 0.490196, 0.74902);
          ctfun.addRGBPoint(9.324, 0.129412, 0.447059, 0.709804);
          ctfun.addRGBPoint(9.36, 0.101961, 0.427451, 0.690196);
          ctfun.addRGBPoint(9.378, 0.094118, 0.403922, 0.658824);
          ctfun.addRGBPoint(9.396, 0.090196, 0.392157, 0.639216);
          ctfun.addRGBPoint(9.414, 0.082353, 0.568627, 0.619608);
          ctfun.addRGBPoint(9.432, 0.070588, 0.529412, 0.6);
          ctfun.addRGBPoint(9.45, 0.066667, 0.429412, 0.568627);
          ctfun.addRGBPoint(9.468, 0.047451, 0.313725, 0.541176);
          ctfun.addRGBPoint(9.486, 0.047059, 0.34902, 0.498039);
          ctfun.addRGBPoint(9.54, 0.109804, 0.266667, 0.411765);
          ctfun.addRGBPoint(9.558, 0.113725, 0.258824, 0.380392);
          ctfun.addRGBPoint(9.576, 0.105882, 0.29098, 0.34902);
          ctfun.addRGBPoint(9.594, 0.101961, 0.25098, 0.321569);
          ctfun.addRGBPoint(9.612, 0.105882, 0.301961, 0.262745);
          ctfun.addRGBPoint(9.63, 0.094118, 0.309804, 0.243137);
          ctfun.addRGBPoint(9.648, 0.082353, 0.321569, 0.227451);
          ctfun.addRGBPoint(9.666, 0.07451, 0.341176, 0.219608);
          ctfun.addRGBPoint(9.684, 0.070588, 0.360784, 0.211765);
          ctfun.addRGBPoint(9.702, 0.066667, 0.380392, 0.215686);
          ctfun.addRGBPoint(9.72, 0.062745, 0.4, 0.176471);
          ctfun.addRGBPoint(9.74498, 0.0705882, 0.411765, 0.156863);
          ctfun.addRGBPoint(9.765, 0.07451, 0.419608, 0.145098);
          ctfun.addRGBPoint(9.81, 0.086275, 0.439216, 0.117647);
          ctfun.addRGBPoint(9.855, 0.121569, 0.470588, 0.117647);
          ctfun.addRGBPoint(9.9, 0.184314, 0.501961, 0.14902);
          ctfun.addRGBPoint(9.945, 0.254902, 0.541176, 0.188235);
          ctfun.addRGBPoint(9.99, 0.32549, 0.580392, 0.231373);
          ctfun.addRGBPoint(10.035, 0.403922, 0.619608, 0.278431);
          ctfun.addRGBPoint(10.08, 0.501961, 0.670588, 0.333333);
          ctfun.addRGBPoint(10.17, 0.741176, 0.788235, 0.490196);
          ctfun.addRGBPoint(10.206, 0.858824, 0.858824, 0.603922);
          ctfun.addRGBPoint(10.26, 0.921569, 0.835294, 0.580392);
          ctfun.addRGBPoint(10.35, 0.901961, 0.729412, 0.494118);
          ctfun.addRGBPoint(10.44, 0.858824, 0.584314, 0.388235);
          ctfun.addRGBPoint(10.53, 0.8, 0.439216, 0.321569);
          ctfun.addRGBPoint(10.62, 0.678431, 0.298039, 0.203922);
          ctfun.addRGBPoint(10.71, 0.54902, 0.168627, 0.109804);
          ctfun.addRGBPoint(10.755, 0.478431, 0.082353, 0.047059);
          ctfun.addRGBPoint(10.8, 0.45098, 0.007843, 0);

          // Set opacity mapping for better visualization
          const ofun = vtkPiecewiseFunction.newInstance();
          ofun.addPoint(9.0, 0.0);      // fully transparent
          ofun.addPoint(9.5, 0.025);  // faintly visible
          ofun.addPoint(10.8, 1.0);     // fully opaque



          actor.getProperty().setRGBTransferFunction(0, ctfun);
          actor.getProperty().setScalarOpacity(0, ofun);

          // Add the actor to the renderer and reset the camera
          renderer.addVolume(actor);
          renderer.resetCamera();
          renderWindow.render();

            // === Add colorbar === //
          const scalarBarActor = vtkScalarBarActor.newInstance({barPosition:[10,10],boxPosition:[10,10]});
          scalarBarActor.setScalarsToColors(ctfun);
          scalarBarActor.setAxisLabel(''); // label left empty as requested
          scalarBarActor.setDrawNanAnnotation(false);
          scalarBarActor.getProperty().setColor(0, 0, 0); // black font color

          // Set colorbar position and size
          renderer.addActor(scalarBarActor);
          renderWindow.render();
          resolve({ fullScreenRenderer, renderWindow });
        }).catch((error) => {
          console.error('Error loading data:', error);
          resolve({ fullScreenRenderer, renderWindow });
        });
    });

    const { snapshot, live, loading, activate, resetCamera, rebuild } = useVtkView(
      () => vtkContainer.value, buildScene,
      { autoLive: props.autoLive, syncCamera: props.syncCamera });

    // ROI changes: live views update the clipping planes directly and re-render instantly
    // (exactly like Module 3 — no rebuild, no new rows); snapshot-mode views debounce and
    // re-emit a clipped snapshot
    if (props.roiClip) {
      let roiTimer = null;
      watch(() => [...viewRoi.roi, viewRoi.crop], () => {
        if (live.value && liveScene) {
          try {
            applyRoiClipping(liveScene.mapper);
            liveScene.renderWindow.render();
            return;
          } catch (e) { /* scene already destroyed, fall back to rebuild */ }
        }
        clearTimeout(roiTimer);
        roiTimer = setTimeout(rebuild, 400);
      });
    }

    return {
      vtkContainer,
      snapshot,
      live,
      loading,
      activate,
      resetCamera,   // called by the parent's "fit to view" button via ref
    };
  }
};
</script>

<style scoped>
.controls {
  position: absolute;
  top: 25px;
  left: 25px;
  background: white;
  padding: 12px;
}
</style>
