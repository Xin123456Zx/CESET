<template>
  <div class="h-full flex flex-col border border-[#e5e5e5] rounded-[10px] p-3 bg-white">
    <h3 class="font-semibold text-[15px] mb-2">🔍 Search members</h3>
    <el-input
      v-model="query" clearable size="default"
      placeholder="member id / dir / parameter value…"
    />
    <div class="text-[12px] text-gray-400 mt-2 mb-1">
      <template v-if="query">{{ results.length }} match(es) — click ▸ to focus</template>
      <template v-else>top outliers (by Mahalanobis) — click ▸ to focus</template>
    </div>

    <div class="flex-1 overflow-y-auto flex flex-col gap-1.5 min-h-0">
      <button
        v-for="m in shown" :key="m.id"
        class="text-left border rounded-[8px] px-3 py-1.5 text-[12.5px] leading-5 transition-colors"
        :class="m.id === selectedId
          ? 'border-[#ACACFF] bg-[#ACACFF]/10'
          : 'border-[#e5e5e5] hover:border-[#ACACFF] hover:bg-[#ACACFF]/5'"
        @click="$emit('select', m.id)"
      >
        <span class="font-mono font-semibold">▸ #{{ m.id }}</span>
        <span
          v-if="m.outlier_maha > 2.146 || m.outlier_struct > 2.5"
          class="ml-1 text-[10.5px] text-white bg-[#d03050] rounded-full px-1.5 py-[1px] align-middle"
        >outlier</span>
        <br/>
        <span class="text-gray-500">
          OmM={{ f(m.OmM, 3) }} · OmB={{ f(m.OmB, 4) }} · h={{ f(m.h, 3) }}
        </span><br/>
        <span class="text-gray-400">mean={{ f(m.mean, 3) }} · std={{ f(m.std, 3) }}</span>
      </button>
      <div v-if="query && !results.length" class="text-gray-400 text-[13px] text-center py-6">
        no member matches “{{ query }}”
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

const props = defineProps<{
  members: any[]
  selectedId: number | null
}>()
defineEmits<{ (e: 'select', id: number): void }>()

const query = ref('')
const f = (v: number, d = 3) => v == null ? '-' : Number(v).toFixed(d)

// No input → show top outliers (the points most worth clicking on the landscape); with input → fuzzy match by id / dir / parameter values
const results = computed(() => {
  const q = query.value.trim().toLowerCase().replace(/^#/, '')
  if (!q) return []
  return props.members.filter(m =>
    String(m.id) === q ||
    String(m.id).includes(q) ||
    m.dir?.toLowerCase().includes(q) ||
    [m.OmM, m.OmB, m.h].some(v => String(v).includes(q)))
})

const shown = computed(() =>
  query.value.trim()
    ? results.value.slice(0, 40)
    : [...props.members].sort((a, b) => b.outlier_maha - a.outlier_maha).slice(0, 10))
</script>
