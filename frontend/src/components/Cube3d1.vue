<template>
  <div class="w-[200px] h-[200px] relative" @click="activate">
    <div ref="vtkContainer" style="width: 200px; height: 200px;" />
    <!-- Snapshot mode: click to enter 3D interaction (see useVtkView for notes on the WebGL context limit) -->
    <img v-if="snapshot && !live" :src="snapshot" @click="activate"
         class="absolute left-0 top-0 w-[200px] h-[200px] cursor-pointer z-10"
         title="Click to enter 3D interaction" />
    <div
    ref="tooltip"
    v-show="showTooltip && tooltipText"
    class="absolute bg-black bg-opacity-60 text-white text-xs rounded p-1 pointer-events-none z-50 w-[150px] flex items-center justify-center"
  >
    {{ tooltipText }}
  </div>
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
import vtkCellPicker from '@kitware/vtk.js/Rendering/Core/CellPicker'
import vtkImageData from '@kitware/vtk.js/Common/DataModel/ImageData'
import vtkDataArray from '@kitware/vtk.js/Common/Core/DataArray'

export default {
  props:{
    url1:{
        type:String,
        default:""
    },
    url2:{
        type:String,
        default:""
    },
    width:{
      type:String,
      default:"100px"
    },
   height:{
    type:String,
    default:"100px"
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
    const context = ref(null);
    const tooltipText = ref('')
    const showTooltip = ref(false)
    const tooltip = ref()

    // Build the rendering pipeline; resolve once the first frame has rendered (reused by useVtkView for snapshot/activation)
    const buildScene = () => new Promise((resolveScene) => {
      if (!props.url1 || !vtkContainer.value) { resolveScene(null); return; }
        const fullScreenRenderer = vtkFullScreenRenderWindow.newInstance({
          rootContainer: vtkContainer.value,
          background: [1, 1, 1], // white background
          containerStyle: {height: props.width,width:props.height},
        });
        const renderer = fullScreenRenderer.getRenderer();
        const renderWindow = fullScreenRenderer.getRenderWindow();

        const readerLower = vtkXMLImageDataReader.newInstance();
        const readerUpper = vtkXMLImageDataReader.newInstance();


        Promise.all([
            readerLower.setUrl(props.url1).then(() => readerLower.loadData()),
            readerUpper.setUrl(props.url2).then(() => readerUpper.loadData())
          ]).then(() => {
            const lowerData = readerLower.getOutputData();
            const upperData = readerUpper.getOutputData();

            const lowerArray = lowerData.getPointData().getScalars().getData();
            const upperArray = upperData.getPointData().getScalars().getData();

            const diffArray = lowerArray.map((l, i) => upperArray[i] - l);

            let minVal = Infinity;
            let maxVal = -Infinity;

          for (let i = 0; i < diffArray.length; i++) {
            const val = diffArray[i];
            if (val < minVal) minVal = val;
            if (val > maxVal) maxVal = val;
          }

          const dataRange = [minVal, maxVal];


            const intervalData = vtkImageData.newInstance();
            intervalData.shallowCopy(lowerData);
            intervalData.getPointData().setScalars(
              vtkDataArray.newInstance({
                numberOfComponents: 1,
                values: Float32Array.from(diffArray),
              })
            );



            for (let i = 0; i < diffArray.length; i++) {
              if (diffArray[i] < minVal) minVal = diffArray[i];
              if (diffArray[i] > maxVal) maxVal = diffArray[i];
            }
            // const ctfun = vtkColorTransferFunction.newInstance();
            // ctfun.addRGBPoint(minVal, 0, 0, 1);
            // ctfun.addRGBPoint((minVal + maxVal) / 2, 0, 1, 0);
            // ctfun.addRGBPoint(maxVal, 1, 0, 0);

            // const ofun = vtkPiecewiseFunction.newInstance();
            // ofun.addPoint(minVal, 0.0);
            // ofun.addPoint((minVal + maxVal) / 2, 0.3);
            // ofun.addPoint(maxVal, 0.9);

            // Define the color transfer function
          const ctfun = vtkColorTransferFunction.newInstance();
        ctfun.addRGBPoint(0.0, 0.8, 0.9, 1.0);     // light blue (minimum)
        ctfun.addRGBPoint(0.75, 0.0, 0.2, 0.7);    // dark blue
        ctfun.addRGBPoint(1.0, 0.0, 0.4, 0.0);     // dark green
        ctfun.addRGBPoint(1.5, 1.0, 1.0, 0.7);     // light yellow
        ctfun.addRGBPoint(3.0, 0.6, 0.0, 0.0);
        ctfun.build();
          // Set opacity mapping for better visualization
          //
          const ofun = vtkPiecewiseFunction.newInstance();
         ofun.addPoint(0.0, 0.0);
         ofun.addPoint(1.0, 0.05);
         ofun.addPoint(3.0, 1.0);



            const mapper = vtkVolumeMapper.newInstance();
            mapper.setInputData(intervalData);
            if (props.roiClip) applyRoiClipping(mapper);
            liveScene = { mapper, renderWindow };

            const actor = vtkVolume.newInstance();
            actor.setMapper(mapper);
            actor.getProperty().setRGBTransferFunction(0, ctfun);
            actor.getProperty().setScalarOpacity(0, ofun);

            // Create the ScalarBarActor (2D mode)
            const scalarBarActor = vtkScalarBarActor.newInstance();
            scalarBarActor.setScalarsToColors(ctfun);
            scalarBarActor.setAxisLabel('');
            scalarBarActor.setDrawNanAnnotation(false);
            scalarBarActor.getProperty().setColor(0, 0, 0);

            // Set the ScalarBarActor's position and size
            scalarBarActor.setBarPosition([0.85, 0.15]); // move it to a suitable spot on the right
            scalarBarActor.setBarSize([0.08, 0.7]);

            // Force-enable the 2D overlay
            scalarBarActor.setVisibility(true);

            renderer.addActor(scalarBarActor);
            // Add the ScalarBarActor via renderer.getOverlayRenderer() to avoid conflicts
            // const overlayRenderer = fullScreenRenderer.getRenderer().getRenderWindow().getRenderers()[1] || fullScreenRenderer.getRenderer();
            // overlayRenderer.addActor(scalarBarActor);

            // The volume is added via the renderer separately; unaffected
            renderer.addVolume(actor);

            // Refresh the render
            renderer.resetCamera();
            renderWindow.render();



            const picker = vtkCellPicker.newInstance();
            picker.setPickFromList(true);
            picker.initializePickList();
            picker.addPickList(actor);

            renderWindow.getInteractor().onLeftButtonPress((callData) => {

              const pos = callData.position;
              const dims = lowerData.getDimensions();

              console.log(callData)

              const container = fullScreenRenderer.getContainer();
              const glRenderWindow = renderWindow.getViews()[0];

              // Note: the y coordinate must be flipped here
              const displayX = pos.x;
              const displayY = container.clientHeight - pos.y;

              // Get the ray's near and far world-coordinate points
              const worldCoordNear = glRenderWindow.displayToWorld(displayX, displayY, 0, renderer);
              const worldCoordFar = glRenderWindow.displayToWorld(displayX, displayY, 1, renderer);

              const rayOrigin = worldCoordNear;
              const rayDirection = [
                worldCoordFar[0] - worldCoordNear[0],
                worldCoordFar[1] - worldCoordNear[1],
                worldCoordFar[2] - worldCoordNear[2],
              ];

              // Define the data bounds
              const bounds = lowerData.getBounds();
              let tmin = -Infinity;
              let tmax = Infinity;

              for (let i = 0; i < 3; i++) {
                if (Math.abs(rayDirection[i]) < 1e-6) {
                  if (rayOrigin[i] < bounds[i * 2] || rayOrigin[i] > bounds[i * 2 + 1]) {

                    showTooltip.value = false
                    return;
                  }
                } else {
                  const t1 = (bounds[i * 2] - rayOrigin[i]) / rayDirection[i];
                  const t2 = (bounds[i * 2 + 1] - rayOrigin[i]) / rayDirection[i];

                  const tEntry = Math.min(t1, t2);
                  const tExit = Math.max(t1, t2);

                  tmin = Math.max(tmin, tEntry);
                  tmax = Math.min(tmax, tExit);

                  if (tmin > tmax || tmax < 0) {
                    showTooltip.value = false
                    return;
                  }
                }
              }

              // Compute the intersection point
              const intersection = [
                rayOrigin[0] + tmin * rayDirection[0],
                rayOrigin[1] + tmin * rayDirection[1],
                rayOrigin[2] + tmin * rayDirection[2],
              ];

              const ijk = lowerData.worldToIndex(intersection).map(Math.round);

              if (
                ijk[0] >= 0 && ijk[0] < dims[0] &&
                ijk[1] >= 0 && ijk[1] < dims[1] &&
                ijk[2] >= 0 && ijk[2] < dims[2]
              ) {
                const idx = ijk[0] + ijk[1] * dims[0] + ijk[2] * dims[0] * dims[1];
                const lowerVal = lowerArray[idx].toFixed(3);
                const upperVal = upperArray[idx].toFixed(3);

                tooltip.value.style.left = `${pos.x- lowerVal}px`;
                tooltip.value.style.top = `${pos.y - upperVal}px`;
                tooltipText.value = `Interval: [${lowerVal}, ${upperVal}]`;
                showTooltip.value = true
              } else {
                showTooltip.value = false
              }

              renderWindow.render();
            });




            renderWindow.getInteractor().onMouseLeave(() => {
                showTooltip.value = false
              });

            resolveScene({ fullScreenRenderer, renderWindow });
          }).catch((error) => {
            console.error('Error loading data:', error);
            resolveScene({ fullScreenRenderer, renderWindow });
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
      tooltipText,
      tooltip,
      showTooltip,
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
