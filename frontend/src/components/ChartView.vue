<template>
  <div class="flex flex-col">
    <div class="flex items-center ">
      <div class="flex flex-col px-[10px] w-full">
        <div style="width: 100%; height: 200px" class="-mt-10" ref="echartRef"></div>
        <div class="px-[30px] w-full relative flex flex-col -mt-[70px] ">
          <el-slider @change="sliderChange" :step="0.1" :max="1" v-model="value" />
          <div class="flex justify-between items-center">
            <div>0</div>
            <div>1</div>
          </div>
          <div class="flex items-center justify-center absolute left-1/2 top-1/2 -translate-x-1/2 w-full">
            <el-input class="!w-[50px]" v-model="value" />
          </div>
        </div>
      </div>

      <div v-if="buttons" class="flex flex-col">
        <el-button size="small" type="primary" class="!w-[76px]"
                   title="Render the uncalibrated Student-t prediction interval at this confidence level"
                   @click="genaration">Render</el-button>
        <el-button size="small" class="!w-[76px] !ml-0 mt-1.5"
                   title="Conformally calibrate the interval bounds at this confidence level"
                   @click="calibration">Calibrate</el-button>
      </div>
    </div>
  </div>
</template>

<script lang="ts" setup>

import * as echarts from "echarts";
import { onMounted, onBeforeUnmount, ref } from "vue";
// @ts-ignore
import { jStat } from "jstat";

interface ChartInterFace {
  (e:"changeData",value:number):void
  (e:"calibration",value:number):void
  (e:"confidenceChange",value:number):void   // slider change (used by View3's buttonless mode)
}

const echartRef = ref<HTMLDivElement>();

// Initial confidence (starts at 0 in View2; View3 passes 0.9 as a sensible default);
// buttons=false hides the render/calibration buttons (View3 fetches everything at once, so the slider triggers refresh directly)
const props = withDefaults(defineProps<{ initial?: number, buttons?: boolean }>(), { initial: 0, buttons: true })

const value = ref(props.initial)

const chart = ref<echarts.ECharts>()

const emits = defineEmits<ChartInterFace>()


// Auto-resize the chart when the container size changes (View2 column widths shift as content loads;
// otherwise earlier-created rows keep their small initial size)
let resizeObserver: ResizeObserver | undefined

onMounted(() => {
  initChart(value.value);
  if (echartRef.value) {
    resizeObserver = new ResizeObserver(() => chart.value?.resize())
    resizeObserver.observe(echartRef.value)
  }
});

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  chart.value?.dispose()
});

const sliderChange = ()=>{
  initChart(value.value)
  emits("confidenceChange", value.value)
}
function normalDistribution(mean: number, stdDev: number, numPoints = 200, confidenceLevel = 0.90) {
  let xData = [];
  let yData = [];
  let shadedYData = [];
  let step = (6 * stdDev) / numPoints;
  let startX = mean - 3 * stdDev;

  // Z-value lookup table for confidence levels
  const zTable: { [key: number]: number } = {
    0.1: 0.13, 0.2: 0.25, 0.3: 0.32, 0.4: 0.41, 0.5: 0.52,
    0.6: 0.67, 0.7: 1.04, 0.75: 1.15, 0.8: 1.28, 0.85: 1.44,
    0.9: 1.645, 0.92: 1.75, 0.95: 1.96, 0.96: 2.05, 0.97: 2.17,
    0.98: 2.33, 0.99: 2.58,
  };

  // Get the Z value (lookup table first, compute if absent)
  let z = zTable[confidenceLevel] ?? jStat.normal.inv((1 + confidenceLevel) / 2, 0, 1);

  for (let i = 0; i < numPoints; i++) {
    let x = startX + i * step;
    let y =
      (1 / (stdDev * Math.sqrt(2 * Math.PI))) *
      Math.exp(-0.5 * ((x - mean) / stdDev) ** 2);

    xData.push(x.toFixed(2));
    yData.push(y);

    // Compute the confidence interval shading
    if (x >= mean - z * stdDev && x <= mean + z * stdDev) {
      shadedYData.push(y);
    } else {
      shadedYData.push(null); // keep the curve continuous
    }
  }

  return { xData, yData, shadedYData };
}

const initChart = (confidenceLevel = 0.9) => {
   if(!chart.value){
    chart.value = echarts.init(echartRef.value);
   }
 
  // Mean and standard deviation
  let mean = 0,
    stdDev = 1;
  let { xData, yData, shadedYData } = normalDistribution(mean, stdDev,200,confidenceLevel);

  // Configure ECharts
  var option = {
    xAxis: { type: "category", data: xData, name: "𝑥̄" ,
      nameGap:2,  

      axisLabel: {
        show: false
    },
      "axisTick":{
      "show":false ,//hide x-axis ticks
    }},
    yAxis: {
      type: "value",
      name: "",
      axisLine: { show: false }, // hide the y-axis line
      axisTick: { show: false }, // hide y-axis ticks
      axisLabel: { show: false }, // hide y-axis labels
      splitLine: { show: false }, // hide y-axis grid lines
    },
    grid: { show: false },
    series: [
      {
        type: "line",
        data: yData,
        name: "student-t-distribution",
        lineStyle: { color: "#5f56c0", width: 2 },   // project purple (matches --el-color-primary)
        symbol: "none",
      },
      {
        type: "line",
        data: shadedYData,
        name: "90% confidence interval",
        symbol: "none",
        lineStyle: { width: 0 }, // hide the line
        areaStyle: { color: "#beb9ef" }, // solid fill (accent light-5)
      },
    ],
  };

  chart.value.setOption(option);
};
const genaration = async ()=>{
  emits("changeData",value.value)

}
const calibration = async ()=>{
   emits("calibration",value.value)
}
</script>

<!-- Sliders/inputs inherit the shared purple .explore-accent palette from src/index.css -->
