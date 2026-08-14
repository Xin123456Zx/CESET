<template>
  <div class="panel flex flex-col min-h-0">
    <div class="panel-head">
      <h2 class="panel-title">📏 Prediction Intervals &amp; Calibration</h2>
      <span class="hint truncate">per run: pick a confidence level, then Render (Student-t) or Calibrate (conformal)</span>
    </div>

    <div class="flex-1 min-h-0 overflow-y-auto px-2 pb-2">
      <div class="grid grid-cols-[2fr_1fr_1fr_1fr] gap-y-3">
        <!-- Column headers: what each column shows (sticky while the rows scroll) -->
        <div v-for="(itm,index) in titleList" :key="index"
             class="col-title sticky top-0 bg-white w-full py-1.5 z-10 border-b border-[#f0f0f0]">
          <span class="name">{{ itm.name }}</span>
          <span class="desc">{{ itm.desc }}</span>
        </div>

        <template v-for="(item,index) in dataList" :key="index">
            <div class="relative w-full">
              <span class="absolute left-1 top-1 z-10 bg-[#ACACFF] text-white rounded-full w-[24px] h-[24px] inline-flex items-center justify-center text-[12px] font-bold"
                    :title="`Run #${index + 1} of the Prediction History`">{{ index + 1 }}</span>
              <ChartView @changeData="((value)=>genaration(value,index))" @calibration="((value:any)=>calibration(value,index))"></ChartView>
            </div>
            <!-- The component only loads data in onMounted; bind the URL via :key so it rebuilds exactly once when the URL changes -->
            <div class="place-self-center">
              <Cube3d1 v-if="item.data" roi-clip sync-camera auto-live :key="'i'+item.data+item.model" width="200px" height="200px" :url1="item.data" :url2="item.model"/>
              <div class="w-[120px] h-[120px] flex items-center justify-center hint text-center" v-else>choose a level,<br/>then Render</div>
            </div>
            <div class="place-self-center">
              <Cube3d v-if="item.data" roi-clip sync-camera auto-live :key="'l'+item.data" :url="item.data"/>
              <div class="w-[120px] h-[120px]" v-else></div>
            </div>
            <div class="place-self-center">
              <Cube3d v-if="item.model" roi-clip sync-camera auto-live :key="'u'+item.model" :url="item.model"/>
              <div class="w-[120px] h-[120px]" v-else></div>
            </div>
        </template>
      </div>

      <div v-if="!dataList.length" class="flex flex-col items-center justify-center text-gray-400 text-[13px] text-center h-[70%]">
        <div class="text-3xl mb-2">🫙</div>
        <p>No prediction yet —<br/>submit parameters on the left; each run adds a row here<br/>for interval rendering and conformal calibration.</p>
      </div>
    </div>
  </div>
</template>
<script setup lang="ts">
import {ref, watch, defineExpose} from 'vue';
import Cube3d from "./Cube3d2.vue";
import ChartView from './ChartView.vue';
import {ElLoading, ElMessage} from "element-plus";
import {calibrationApi, generateApi} from "@/api";
import {paramsUsecontext} from "@/contexts/paramsContext.ts";
import Cube3d1 from "./Cube3d1.vue";

const value = paramsUsecontext();
// Column headers: name + one-line description of what the column shows
const titleList = ref([
  { name: "Confidence level", desc: "Student-t interval selector" },
  { name: "Interval width", desc: "upper − lower bound" },
  { name: "Lower bound", desc: "of prediction interval" },
  { name: "Upper bound", desc: "of prediction interval" },
])
 const dataList = ref([
     // {  output:"/nyx/20250324152211219543_result.vit",model:"/nyx/20250325175157611181_upper_bound.vti",data:"/nyx/20250325175157611181_lower_bound.vti",show:true,dataType:"render"},
     // {  output:"/nyx/20250324154754381531_result.vit",model:"/nyx/20250325175157611181upper_bound.vti",data:"/nyx/20250325175157611181_lower_bound.vti",show:true,dataType:"render"},

])




// render: request the lower/upper bounds using this row's history record parameters + the slider confidence level (the backend caches; hits return immediately)
const genaration = async (value:number,index:number)=>{
  const row = dataList.value[index]
  if(!row || !row.params) return
  let loading
  try {
    loading = ElLoading.service({lock:true,text:'Rendering',background:'rgba(0, 0, 0, 0.7)'})
    const {data} = await generateApi.create({data:{dataname:"nyx",param:[row.params.omM,row.params.omB,row.params.h],datatype:2,confidence_level:value}})
    Object.assign(row,{data:"/nyx/"+data[0],model:"/nyx/"+data[1]})
  }catch(err){
    console.error(err)
  }finally{
    loading?.close()
  }
}

// calibration: likewise uses this row's parameters + confidence level; returns calibrated lower/upper bounds and replaces the display
// (the backend /calibration is currently a placeholder; once the calibration formula lands in server.py, no further frontend changes are needed)
const calibration = async (value:number,index:number)=>{
  const row = dataList.value[index]
  if(!row || !row.params) return
  let loading
  try {
    loading = ElLoading.service({lock:true,text:'Calibrating',background:'rgba(0, 0, 0, 0.7)'})
    const res:any = await calibrationApi.create({data:{dataname:"nyx",param:[row.params.omM,row.params.omB,row.params.h],confidence_level:value}})
    Object.assign(row,{data:"/nyx/"+res.data[0],model:"/nyx/"+res.data[1]})
    // The backend snaps to the nearest available calibration level (0.1/0.2/0.5/0.75/0.9); tell the user which level was actually used
    if(res.calibration_level != null && Math.abs(res.calibration_level - value) > 1e-6){
      ElMessage.info(`Confidence level ${value} used the nearest calibration data at level ${res.calibration_level}`)
    }
  }catch(err){
    console.error(err)
  }finally{
    loading?.close()
  }
}

watch(()=>value.value,(n,o)=>{
    if(n && n.data.type == "nyx"){
     // Add a placeholder row on submit and remember its parameters; the volume rendering only appears after clicking render
     dataList.value.push({params:{...n.data.data},data:"",model:""})
    }
})
const callBack = ()=>{
  dataList.value = []
}
defineExpose({
  callBack
})
</script>
