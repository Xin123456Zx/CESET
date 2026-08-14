<template>
  <div class="w-[100px] h-[100px] relative bar">
<!--    <div ref="vtkContainer" style="width: 100px; height: 100px;" class="mt-[40px]" ></div>-->
    <div class="absolute left-1/2 top-1/2 transform -translate-x-1/2 -translate-y-1/2">
      <slot/>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, onBeforeUnmount } from 'vue';
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
    }
   },
  setup(props) {
    const vtkContainer = ref(null);
    const context = ref(null);

    // onMounted(() => {
    //
    //   const scalarBarRenderer = vtkFullScreenRenderWindow.newInstance({
    //     background: [0, 0, 0, 0],
    //     container: vtkContainer.value,
    //     containerStyle: { height: '3px', width: '100px' },
    //   });
    //
    //   scalarBarRenderer.getInteractor().unbindEvents();
    //   const ctfun = vtkColorTransferFunction.newInstance();
    //
    //   ctfun.addRGBPoint(9.0, 0.831373, 0.909804, 0.980392);
    //   ctfun.addRGBPoint(9.0225, 0.74902, 0.862745, 0.960784);
    //   ctfun.addRGBPoint(9.045, 0.694118, 0.827451, 0.941176);
    //   ctfun.addRGBPoint(9.09, 0.568627, 0.760784, 0.921569);
    //   ctfun.addRGBPoint(9.135, 0.45098, 0.705882, 0.901961);
    //   ctfun.addRGBPoint(9.18, 0.345098, 0.643137, 0.858824);
    //   ctfun.addRGBPoint(9.225, 0.247059, 0.572549, 0.819608);
    //   ctfun.addRGBPoint(9.27, 0.180392, 0.521569, 0.780392);
    //   ctfun.addRGBPoint(9.288, 0.14902, 0.490196, 0.74902);
    //   ctfun.addRGBPoint(9.324, 0.129412, 0.447059, 0.709804);
    //   ctfun.addRGBPoint(9.36, 0.101961, 0.427451, 0.690196);
    //   ctfun.addRGBPoint(9.378, 0.094118, 0.403922, 0.658824);
    //   ctfun.addRGBPoint(9.396, 0.090196, 0.392157, 0.639216);
    //   ctfun.addRGBPoint(9.414, 0.082353, 0.568627, 0.619608);
    //   ctfun.addRGBPoint(9.432, 0.070588, 0.529412, 0.6);
    //   ctfun.addRGBPoint(9.45, 0.066667, 0.429412, 0.568627);
    //   ctfun.addRGBPoint(9.468, 0.047451, 0.313725, 0.541176);
    //   ctfun.addRGBPoint(9.486, 0.047059, 0.34902, 0.498039);
    //   ctfun.addRGBPoint(9.54, 0.109804, 0.266667, 0.411765);
    //   ctfun.addRGBPoint(9.558, 0.113725, 0.258824, 0.380392);
    //   ctfun.addRGBPoint(9.576, 0.105882, 0.29098, 0.34902);
    //   ctfun.addRGBPoint(9.594, 0.101961, 0.25098, 0.321569);
    //   ctfun.addRGBPoint(9.612, 0.105882, 0.301961, 0.262745);
    //   ctfun.addRGBPoint(9.63, 0.094118, 0.309804, 0.243137);
    //   ctfun.addRGBPoint(9.648, 0.082353, 0.321569, 0.227451);
    //   ctfun.addRGBPoint(9.666, 0.07451, 0.341176, 0.219608);
    //   ctfun.addRGBPoint(9.684, 0.070588, 0.360784, 0.211765);
    //   ctfun.addRGBPoint(9.702, 0.066667, 0.380392, 0.215686);
    //   ctfun.addRGBPoint(9.72, 0.062745, 0.4, 0.176471);
    //   ctfun.addRGBPoint(9.74498, 0.0705882, 0.411765, 0.156863);
    //   ctfun.addRGBPoint(9.765, 0.07451, 0.419608, 0.145098);
    //   ctfun.addRGBPoint(9.81, 0.086275, 0.439216, 0.117647);
    //   ctfun.addRGBPoint(9.855, 0.121569, 0.470588, 0.117647);
    //   ctfun.addRGBPoint(9.9, 0.184314, 0.501961, 0.14902);
    //   ctfun.addRGBPoint(9.945, 0.254902, 0.541176, 0.188235);
    //   ctfun.addRGBPoint(9.99, 0.32549, 0.580392, 0.231373);
    //   ctfun.addRGBPoint(10.035, 0.403922, 0.619608, 0.278431);
    //   ctfun.addRGBPoint(10.08, 0.501961, 0.670588, 0.333333);
    //   ctfun.addRGBPoint(10.17, 0.741176, 0.788235, 0.490196);
    //   ctfun.addRGBPoint(10.206, 0.858824, 0.858824, 0.603922);
    //   ctfun.addRGBPoint(10.26, 0.921569, 0.835294, 0.580392);
    //   ctfun.addRGBPoint(10.35, 0.901961, 0.729412, 0.494118);
    //   ctfun.addRGBPoint(10.44, 0.858824, 0.584314, 0.388235);
    //   ctfun.addRGBPoint(10.53, 0.8, 0.439216, 0.321569);
    //   ctfun.addRGBPoint(10.62, 0.678431, 0.298039, 0.203922);
    //   ctfun.addRGBPoint(10.71, 0.54902, 0.168627, 0.109804);
    //   ctfun.addRGBPoint(10.755, 0.478431, 0.082353, 0.047059);
    //   ctfun.addRGBPoint(10.8, 0.45098, 0.007843, 0);
    //
    //     // Create the ScalarBarActor and add it to the renderer
    //     const scalarBarActor = vtkScalarBarActor.newInstance();
    //         scalarBarActor.setScalarsToColors(ctfun);
    //         scalarBarActor.setAxisLabel('');
    //         scalarBarActor.setDrawNanAnnotation(false);
    //         scalarBarActor.getProperty().setColor(0, 0, 0);
    //
    //         // Set the ScalarBarActor's position and size
    //         scalarBarActor.setBarPosition([0.85, 0.15]); // move to a suitable spot on the right
    //         scalarBarActor.setBarSize([0.08, 0.7]);
    //
    //         // Force-enable the 2D overlay
    //         scalarBarActor.setVisibility(true);
    //
    //     // Add the actor to a dedicated renderer
    //     scalarBarRenderer.getRenderer().addActor(scalarBarActor);
    //
    //     // Render the colorbar
    //     scalarBarRenderer.getRenderWindow().render();
    //
    //
    // });


    onBeforeUnmount(() => {
      if (context.value) {
        const { fullScreenRenderer } = context.value;
        fullScreenRenderer.delete();
        context.value = null;
      }
    });

    return {
      vtkContainer,
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
