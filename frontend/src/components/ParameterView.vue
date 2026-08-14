<template>
  <div class="panel flex flex-col min-h-0">
    <div class="panel-head">
      <h2 class="panel-title">🔧 Simulation Parameters</h2>
      <el-select @change="change" v-model="selected" size="small" class="!w-[110px]">
        <el-option
          v-for="item in options"
          :key="item.value"
          :label="item.label"
          :value="item.value"
        />
      </el-select>
    </div>

    <div class="px-3 py-2 flex-1 min-h-0 overflow-y-auto">
      <!-- Parameter sliders -->
      <div class="flex items-baseline justify-between">
        <h3 class="font-semibold text-[13px]">{{ title }} input parameters</h3>
        <span class="hint">drag a slider or type a value</span>
      </div>

      <template v-if="selected != 'cloverleaf'">
        <div v-for="item in dataList[selected]" :key="item.key" class="flex items-center gap-2 mt-1">
          <span class="text-[12px] font-semibold w-[48px] text-right shrink-0" :title="item.desc">{{ item.name }}</span>
          <el-slider :step="item.step" :max="item.max" :min="item.min" v-model="item.value" size="small" class="flex-1 !my-0" />
          <el-input-number v-model="item.value" :min="item.min" :max="item.max" :step="item.step"
                           :controls="false" size="small" class="!w-[84px] shrink-0" />
        </div>
      </template>
      <template v-else>
        <div v-for="item in dataList[selected]" :key="item.name" class="mt-1.5">
          <div class="text-[11.5px] font-semibold text-gray-500 uppercase tracking-wide">{{ item.name }}</div>
          <div v-for="itm in item.list" :key="itm.key" class="flex items-center gap-2 mt-0.5">
            <span class="text-[12px] font-semibold w-[70px] text-right shrink-0">{{ itm.name }}</span>
            <el-slider :step="itm.step" :max="itm.max" :min="itm.min" v-model="itm.value" size="small" class="flex-1 !my-0" />
            <el-input-number v-model="itm.value" :min="itm.min" :max="itm.max" :step="itm.step"
                             :controls="false" size="small" class="!w-[84px] shrink-0" />
          </div>
        </div>
      </template>

      <div class="flex items-center gap-2 mt-2">
        <el-button type="primary" size="small" class="flex-1" @click="add">▶ Predict with these parameters</el-button>
        <el-button size="small" @click="cleanAll">✕ Clear all</el-button>
      </div>

      <!-- Region of Interest: viewing region shared by all volume renderings in the middle/right views -->
      <h3 class="font-semibold text-[13px] mt-4">
        📦 Region of Interest
        <span class="hint font-normal">(voxel index range, applied to every 3D view)</span>
      </h3>
      <div class="grid grid-cols-[24px_1fr_1fr] gap-x-2 gap-y-1.5 items-center mt-1">
        <span></span>
        <span class="text-[11px] text-gray-400 text-center">from (voxel)</span>
        <span class="text-[11px] text-gray-400 text-center">to (voxel)</span>
        <template v-for="(axis, ai) in ['X', 'Y', 'Z']" :key="axis">
          <span class="font-semibold text-gray-600 text-[12px]">{{ axis }}</span>
          <el-input-number v-model="viewRoi.roi[ai * 2]" :min="0" :max="viewRoi.roi[ai * 2 + 1]" :step="1" size="small" class="!w-full" />
          <el-input-number v-model="viewRoi.roi[ai * 2 + 1]" :min="viewRoi.roi[ai * 2]" :max="255" :step="1" size="small" class="!w-full" />
        </template>
      </div>
      <div class="flex items-center justify-between mt-1.5">
        <el-checkbox v-model="viewRoi.crop" label="Crop views to ROI" size="small" />
        <el-button size="small" @click="resetViewRoi">Reset ROI</el-button>
      </div>

      <!-- History Records Table -->
      <div class="flex items-baseline justify-between mt-4">
        <h3 class="font-semibold text-[13px]">📜 Prediction History</h3>
        <span class="hint">run #n = row #n in the two views on the right</span>
      </div>
      <el-table max-height="230px" :data="tableData[selected].data" size="small" style="width: 100%"
                class="mt-1 rounded-[8px] border border-[#eee]"
                header-cell-class-name="!bg-gray-50 !text-gray-600">
        <el-table-column align="center" width="48" label="Run" type="index" />

        <el-table-column v-if="selected != 'cloverleaf'" align="center"
                         v-for="item in tableData[selected].column" :key="item.prop" :prop="item.prop">
          <template #header>
            <span class="font-semibold">{{ item.label }}</span>
            <span v-if="item.desc" class="block text-[10px] text-gray-400 font-normal leading-tight">{{ item.desc }}</span>
          </template>
        </el-table-column>
        <el-table-column v-else align="center" v-for="item in tableData[selected].column" :label="item.name">
          <el-table-column align="center" :prop="itm.prop" :label="itm.label" v-for="(itm,index) in item.list" :key="index" />
        </el-table-column>

        <!-- Reverse handoff: carry this row's parameters to Module 3 as the Context Field and auto Load Field -->
        <el-table-column v-if="selected == 'nyx'" align="center" width="96">
          <template #header>
            <span class="font-semibold">Send to</span>
            <span class="block text-[10px] text-gray-400 font-normal leading-tight">Module 3</span>
          </template>
          <template #default="scope">
            <el-button size="small" type="primary" plain class="!rounded-full"
                       title="Use these parameters as context and recommend parameters in Module 3 (Para-space)"
                       @click="optimizeInParaspace(scope.row)">Optimize</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, onMounted, onActivated } from "vue";
import { useRouter } from "vue-router";
import { generateApi, cleanApi } from "@/api"
import { ElMessage, ElMessageBox } from "element-plus"
import {paramsUsecontext} from "../contexts/paramsContext";
import { viewRoi, resetViewRoi } from "@/store/viewRoi";
const selected = ref("nyx");
const tableDataList = paramsUsecontext();

const options = ref([
  { value: "nyx", label: "Nyx" },
  { value: "mpas", label: "Mpas" },
  {value:"cloverleaf",label:"Cloverleaf"}
]);

const dataList = ref({
  mpas:[
    {name:'BwsA',min:0,max:5,value:2.5,step:0.01,key:"bwsa",desc:'bulk wind stress amplification'},
    {name:'GM',min:600,max:1500,value:900,step:1,key:"gm",desc:'GM eddy transport coefficient'},
    {name:'CbrN',min:0.25,max:1,value:0.625,step:0.01,key:'cbrN',desc:'critical bulk Richardson number'},
    {name:'HV',min:100,max:300,value:200,step:1,key:"hv",desc:'horizontal viscosity'}
  ],
  nyx:[
    {name:'OmM',min:0.12,max:0.155,value:0.149,step:0.001,key:'omM',desc:'total matter density Ωm'},
    {name:'OmB',min:0.0215,max:0.0235,value:0.0218,step:0.0001,key:"omB",desc:'baryon density Ωb'},
    {name:'h',min:0.55,max:0.85,value:0.685,step:0.01,key:"h",desc:'Hubble constant'}
  ],
  cloverleaf:[
   {
     name:'state1',
      list:[
      {name:'Density 1',min:0.01,max:1.0,value:0.1,step:0.01,key:'dencity1'},
      {name:'Energy 1',min:0.75,max:2,value:0.8,step:0.01,key:'energy1'},
    ]
   },
    {name:'state2',
     list:[
      {name:'Density 2',min:0.5,max:2.0,value:0.7,step:0.01,key:'dencity2'},
      {name:'Energy 2',min:1.5,max:3,value:0.6,step:0.01,key:'energy2'},
    ]
   },
   {
    name:'state3',
    list:[
     {name:'Density 3',min:1.5,max:3,value:1.6,step:0.01,key:'dencity3'},
     {name:'Energy 3',min:4,max:7,value:5,step:0.01,key:'energy3'},
   ]
  }
  ]
})


const change = (value) =>{
   tableDataList.value.methods.call1()
   tableDataList.value.methods.call2()
   tableData.value.nyx.data = []
   tableData.value.mpas.data = []
   tableData.value.cloverleaf.data = []

}

const title = computed(()=>options.value.find(item=>item.value == selected.value)?.label??"")

const tableData = ref({
  nyx:{
    column:[
      {
         prop:"omM",
         label:"OmM",
         desc:"matter density Ωm"
      },{
         prop:"omB",
         label:"OmB",
         desc:"baryon density Ωb"
      },{
         prop:"h",
         label:"h",
         desc:"Hubble constant"
      }
    ],
    data:[

    ]

  },
  mpas:{
    column:[
      {
        prop:"bwsa",
        label:"BwsA",
        desc:"wind stress"
     },{
        prop:"gm",
        label:"GM",
        desc:"eddy transport"
     },{
        prop:"cbrN",
        label:"CbrN",
        desc:"bulk Richardson"
     } ,
     {
      prop:"hv",
      label:"HV",
      desc:"horizontal viscosity"
     }

    ],
    data:[

    ]

  },
  cloverleaf:{
    column:[
      {
        name:"State 1",
        list:[
          {
            prop:"dencity1",
            label:"Density"
          },{
            prop:"energy1",
            label:"Energy"
          }
        ]
      },
      {
        name:"State 2",
        list:[
          {
            prop:"dencity2",
            label:"Density"
          },
          {
            prop:"energy2",
            label:"Energy"
          }
        ]
      },
      {
        name:'State 3',
        list:[
          {
            prop:"dencity3",
            label:"Density"
           },
           {
            prop:"energy3",
            label:"Energy"
           }
        ]
      }


    ],
    data:[

    ]
  }
})
const getResult = ()=>{
  const result = tableData.value[selected.value].column.reduce((result,current)=>{
    const data = dataList.value[selected.value].find(item=>item.key == current.prop)
      result  = {...result,[data.key]:data.value}
      return result
  },{})
  return result
}
function transformData(data) {
  let result = {};

  data.forEach(state => {
      state.list.forEach(item => {
          result[item.key] = item.value;
      });
  });

  return result;
}
const add = async ()=>{
  if("cloverleaf" == selected.value){
    transformData(dataList.value[selected.value])
    tableData.value[selected.value].data = [...tableData.value[selected.value].data,  transformData(dataList.value[selected.value])]

    console.log(    tableData.value[selected.value].data)
    // This passes the values to other components

  }else{
    tableData.value[selected.value].data = [...tableData.value[selected.value].data,getResult()]
   // This passes the values to other components
   //  tableDataList.value =   tableData.value.map
  }
  if(selected.value == "nyx"){
     // tableDataList.value =   tableData.value
     console.log( tableData.value['nyx']['data'])


    Object.assign( tableDataList.value.data,{
          "data": tableData.value['nyx']['data'][tableData.value['nyx']['data'].length-1],
          "type":'nyx'

       })
     tableDataList.value = {
        ...tableDataList.value,
       data:{
          "data": tableData.value['nyx']['data'][tableData.value['nyx']['data'].length-1],
          "type":'nyx'

       }
     }
  }

   //
   // tableDataList.value =


}

// One-click clean: delete all backend-generated files (vti/bin/model cache) and clear the history records and both visualization views
const cleanAll = async ()=>{
  try {
    await ElMessageBox.confirm('Clear all history records, visualization results, and backend-generated files?','Clean',{type:'warning'})
  }catch(e){
    return // user cancelled
  }
  try {
    await cleanApi.create({data:{}})
    tableData.value.nyx.data = []
    tableData.value.mpas.data = []
    tableData.value.cloverleaf.data = []
    tableDataList.value.methods.call1()
    tableDataList.value.methods.call2()
    ElMessage.success('All records and files cleared')
  }catch(err){
    ElMessage.error('Clean failed: ' + err)
  }
}

// Parameter handoff: parameters recommended by View3 (Para-space) arrive via localStorage, get auto-filled
// and submitted, triggering View1/View2 to re-render with them.
// Under keep-alive the component isn't remounted when returning from Module 3, so both onMounted and onActivated must consume
const consumePendingParams = ()=>{
  try {
    const raw = localStorage.getItem('nyx_pending_params')
    if(!raw) return
    localStorage.removeItem('nyx_pending_params')
    const p = JSON.parse(raw)
    selected.value = 'nyx'
    dataList.value.nyx.find(i=>i.key=='omM').value = p.omM
    dataList.value.nyx.find(i=>i.key=='omB').value = p.omB
    dataList.value.nyx.find(i=>i.key=='h').value = p.h
    add()
  }catch(e){
    console.warn('pending params handoff failed', e)
  }
}
onMounted(consumePendingParams)
onActivated(consumePendingParams)

// Reverse handoff: Module 2 history row → Module 3's Context Field (symmetric with nyx_pending_params);
// ParaSpace consumes nyx_pending_ctx in onMounted/onActivated and auto-runs Load Field
const router = useRouter()
const optimizeInParaspace = (row)=>{
  localStorage.setItem('nyx_pending_ctx', JSON.stringify({ omM: row.omM, omB: row.omB, h: row.h }))
  router.push('/paraspace')
}

defineExpose({
  tableData
})
</script>
