<template>
  <div class="relative" :style="{ width: size + 'px', height: size + 'px' }" @click="activate">
    <div ref="vtkContainer" :style="{ width: size + 'px', height: size + 'px' }" />
    <!-- Snapshot mode: click to enter 3D interaction (see useVtkView for notes on the WebGL context limit) -->
    <img v-if="snapshot && !live" :src="snapshot" @click="activate"
         class="absolute left-0 top-0 cursor-pointer z-10" :style="{ width: size + 'px', height: size + 'px' }"
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
    // Render size (px): default 200 keeps the old usage
    size:{
        type:Number,
        default:200
    },
    type:{
        type:[String,Number],
        default:1
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
    },
    // true = interactive 3D right at mount (no click-to-activate from snapshot), still managed by the MAX_LIVE pool
    autoLive:{
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

          const ctfun = vtkColorTransferFunction.newInstance();
          // Use the data's actual range for color mapping
    ctfun.addRGBPoint(0.01, 0.831373, 0.909804, 0.980392);  // light blue (lowest value)
    ctfun.addRGBPoint(0.03, 0.180392, 0.521569, 0.780392);  // blue gradient
    ctfun.addRGBPoint(0.05, 0.101961, 0.278431, 0.45098);   // dark blue
    ctfun.addRGBPoint(0.07, 0.062745, 0.4,      0.176471);  // blue-green transition
    ctfun.addRGBPoint(0.09, 0.254902, 0.541176, 0.188235);  // green transitioning to yellow
    ctfun.addRGBPoint(0.11,  0.741176, 0.788235, 0.490196);  // pale yellow-green
    ctfun.addRGBPoint(0.12,  0.901961, 0.729412, 0.494118);  // yellow-to-orange transition
    ctfun.addRGBPoint(0.14,  0.8,      0.439216, 0.321569);  // orange
    ctfun.addRGBPoint(0.15,  0.54902,  0.168627, 0.109804);  // reddish brown
    ctfun.addRGBPoint(0.16,  0.45098,  0.007843, 0.0);       // dark red (highest value)


        ctfun.build();

          // Set opacity mapping for better visualization
          const ofun = vtkPiecewiseFunction.newInstance();

          ofun.addPoint(0.01, 0.0);
          ofun.addPoint(0.2, 0.053);
          ofun.addPoint(0.25, 1.0);



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
          scalarBarActor.setBarPositionFrom([0,0])
          scalarBarActor.setBarPosition([1,1])
          scalarBarActor

          // Set colorbar position and size
          renderer.addActor(scalarBarActor);
          renderWindow.render();
          resolve({ fullScreenRenderer, renderWindow });
        }).catch((error) => {
          console.error('Error loading data:', error);
          resolve({ fullScreenRenderer, renderWindow });
        });
    });

    const { snapshot, live, loading, activate, rebuild } = useVtkView(
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
