<template>
  <div class="panel flex flex-col min-h-0">
    <div class="panel-head">
      <h2 class="panel-title">🧊 Predicted Field &amp; Uncertainty</h2>
      <span class="hint truncate">one row per run · drag to rotate, scroll to zoom</span>
    </div>

    <div class="flex-1 min-h-0 overflow-y-auto px-2 pb-2">
      <div class="grid grid-cols-[44px_2fr_2fr_2fr] gap-y-3 w-full place-items-center">
        <!-- Column headers: what each rendering shows (sticky while the rows scroll) -->
        <div v-for="(item,index) in titleList" :key="index"
             class="col-title sticky top-0 bg-white w-full py-1.5 z-10 border-b border-[#f0f0f0]">
          <span class="name">{{ item.name }}</span>
          <span class="desc">{{ item.desc }}</span>
        </div>

        <template v-for="(item,index) in dataList" :key="index">
            <div class="justify-center flex items-center">
              <span class="bg-[#ACACFF] text-white rounded-full w-[24px] h-[24px] inline-flex items-center justify-center text-[12px] font-bold"
                    :title="`Run #${index + 1} of the Prediction History`">{{ index + 1 }}</span>
            </div>
            <div class="h-[150px] w-full flex items-center justify-center">
              <Cube3d2 v-if="item.output" roi-clip sync-camera auto-live class="h-[150px] flex items-center" :url="item.output"/>
              <span v-else class="hint" :class="item.error && 'text-red-400'">{{item.error ? 'render failed' : 'rendering volume…'}}</span>
            </div>
            <div class="h-[150px] w-full flex items-center justify-center">
              <Cube3dData v-if="item.data" roi-clip sync-camera auto-live class="h-[150px] flex items-center" :url="item.data"/>
              <span v-else class="hint" :class="item.error && 'text-red-400'">{{item.error ? 'render failed' : 'rendering volume…'}}</span>
            </div>
            <div class="h-[150px] w-full flex items-center justify-center">
              <Cube3d v-if="item.model" roi-clip sync-camera auto-live class="h-[150px] flex items-center" :url="item.model"/>
              <span v-else class="hint" :class="item.error && 'text-red-400'">{{item.error ? 'render failed' : 'rendering volume…'}}</span>
            </div>
        </template>
      </div>

      <div v-if="!dataList.length" class="flex flex-col items-center justify-center text-gray-400 text-[13px] text-center h-[70%]">
        <div class="text-3xl mb-2">🫙</div>
        <p>No prediction yet —<br/>set parameters on the left and click <b>▶ Predict</b>.</p>
      </div>
    </div>
  </div>
</template>
<script setup lang="ts">
import {paramsUsecontext} from '../contexts/paramsContext';
import {onMounted, ref,watch,defineExpose} from "vue"
import { generateApi  } from "@/api"
import Cube3d from "./Cube3dModel.vue";
import Cube3dData from "@/components/Cube3dData.vue";
import { ElLoading } from 'element-plus'
import Cube3d2 from "./Cube3d2.vue";


const value = paramsUsecontext();

// Column headers: name + one-line description of what the rendering shows
const titleList = ref([
  { name: "Run", desc: "history row" },
  { name: "Predicted field", desc: "mean of log10 density" },
  { name: "Aleatoric uncertainty", desc: "noise inherent in the data" },
  { name: "Epistemic uncertainty", desc: "model's lack of knowledge" },
])

const dataList = ref([
       // {  output:"/nyx/20250324152211219543_result.vti",data:"/nyx/20250325163416148423_data_uncertainty.vti",model:"/nyx/20250325163416148423_model_uncertainty.vti",show:true,dataType:"render"},
       // {  output:"/nyx/20250324152211219543_result.vti",data:"/nyx/20250325163416148423_data_uncertainty.vti",model:"/nyx/20250325163416148423_model_uncertainty.vti",show:true,dataType:"render"},

])

// Fill results back in by row index so rows stay strictly aligned with History Records
const nyxFunc = async (item:{omM:number,omB:number,h:number}, index:number)=>{
  try {
     const {data} = await generateApi.create({data:{dataname:"nyx",param:[item.omM,item.omB,item.h],datatype:1}})
     Object.assign(dataList.value[index],{output:"/nyx/"+data[0],data:"/nyx/"+data[1],model:"/nyx/"+data[2],error:false})
  }catch(err){
     Object.assign(dataList.value[index],{error:true})
  }
}

watch(()=>value.value,(n,o)=>{
    if(n&&n.data.type == "nyx"){
      // Add a placeholder row immediately on submit; fill it back in by index once the result returns
      dataList.value.push({output:"",data:"",model:"",error:false})
      nyxFunc(n.data.data, dataList.value.length-1)
    }
})

const callBack = ()=>{
  dataList.value = []
}

defineExpose({
  callBack
})

onMounted(()=>{

})

</script>
