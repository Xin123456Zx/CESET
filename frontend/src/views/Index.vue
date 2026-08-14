<template>
  <!-- Same 100vh dashboard shell as Module 1: no page-level scrollbar, panels scroll internally -->
  <div class="h-screen overflow-hidden bg-gray-100 explore-accent flex flex-col">
    <div class="bg-white shadow-lg flex-1 flex flex-col min-h-0">
      <AppHeader />

      <div class="px-4 pt-1.5 pb-2 flex-1 flex flex-col min-h-0 gap-2">
        <!-- Title row (same pattern as Module 1: bold title + gray usage hint) -->
        <div class="flex items-baseline gap-3 shrink-0 min-w-0">
          <h2 class="text-lg font-bold whitespace-nowrap">🔭 Surrogate Prediction &amp; Uncertainty</h2>
          <span class="text-[12px] text-gray-400 truncate">
            set simulation parameters and submit — the evidential INR predicts the density field
            with aleatoric / epistemic uncertainty (middle) and confidence intervals before/after
            conformal calibration (right)
          </span>
        </div>

        <!-- Three-column layout -->
        <div class="grid grid-cols-[minmax(400px,2fr)_2fr_3fr] gap-2 flex-1 min-h-0">
          <ParamasContextProvider :value="value">
            <!-- Left: parameter input, ROI, and prediction history -->
            <ParameterView />

            <!-- Middle: predicted field + aleatoric/epistemic uncertainty per run -->
            <VisualizationView1 ref="ref1" />

            <!-- Right: confidence intervals (Student-t and conformally calibrated) per run -->
            <VisualizationView2 ref="ref2" />

            <!-- AI assistant (floating, bottom right) -->
            <AIAssistant />
          </ParamasContextProvider>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import ParameterView from '@/components/ParameterView.vue';
import VisualizationView1 from '@/components/VisualizationView1.vue';
import VisualizationView2 from '@/components/VisualizationView2.vue';
import AIAssistant from '@/components/AIAssistant.vue';
import AppHeader from '@/components/AppHeader.vue';
import {ParamasContextProvider,paramsUsecontext} from '../contexts/paramsContext';
import {ref} from "vue"

const ref1 = ref()
const ref2 = ref()

const value = paramsUsecontext();
value.value = {
   methods: {
      call1:()=>{
        ref1.value.callBack()
      },
      call2:()=>{
         ref2.value.callBack()
      }
   },
   data:{

  }
}

</script>
