<template>
  <!-- Compact layout: all content fits in a normal viewport; on very short viewports only this card scrolls internally, never the page -->
  <div class="flex flex-col min-h-0 overflow-y-auto">
    <!-- EQUINE-style verdict sentence -->
    <p class="text-[12px] leading-[18px] mb-1">
      Member <span class="font-mono text-[#d6336c] font-semibold">#{{ member.id }}</span> is
      <b>{{ verdictText }}</b> — Mahalanobis {{ f(member.outlier_maha, 2) }}
      ({{ member.outlier_maha > 2.146 ? 'outside' : 'inside' }} the 90% ellipse), structural score
      {{ f(member.outlier_struct, 2) }}
      ({{ member.outlier_struct > 2.5 ? 'anomalous' : 'typical' }}).
    </p>

    <!-- Data split role + outlier scores: merged into one row to save height -->
    <div class="flex items-center justify-between mb-1">
      <span v-if="role" class="text-[11.5px]">
        <span class="text-gray-500">INR split:</span>
        <span class="font-semibold ml-1" :style="{ color: role.color }">● {{ role.label }}</span>
      </span>
      <span class="flex gap-1">
        <span class="rounded-full px-2 py-0 text-[10.5px] text-white"
              :class="member.outlier_maha > 2.146 ? 'bg-[#d03050]' : 'bg-[#8fbf6f]'">
          stat {{ f(member.outlier_maha, 2) }}
        </span>
        <span class="rounded-full px-2 py-0 text-[10.5px] text-white"
              :class="member.outlier_struct > 2.5 ? 'bg-[#d03050]' : 'bg-[#8fbf6f]'">
          struct {{ f(member.outlier_struct, 2) }}
        </span>
      </span>
    </div>

    <!-- Parameters -->
    <h4 class="font-bold text-[12.5px] mt-1 mb-0.5">Simulation Parameters</h4>
    <div class="flex gap-1.5 flex-wrap">
      <span v-for="(v, k) in { OmM: member.OmM, OmB: member.OmB, h: member.h }" :key="k"
            class="bg-[#ACACFF] text-white rounded-full px-2.5 py-0 text-[11.5px]">
        {{ k }} = {{ v }}
      </span>
    </div>

    <!-- Statistics (corresponds to EQUINE's Class Confidence Scores section) -->
    <h4 class="font-bold text-[12.5px] mt-1.5 mb-0.5">Spatial Statistics (log10 ρ)</h4>
    <table class="w-full text-[12px] leading-[17px]">
      <tbody>
        <tr v-for="row in statRows" :key="row[0]" class="border-b border-gray-100">
          <td class="text-gray-500 py-[1px]">{{ row[0] }}</td>
          <td class="text-right font-mono">{{ row[1] }}</td>
          <td class="text-gray-500 py-[1px] pl-3">{{ row[2] }}</td>
          <td class="text-right font-mono">{{ row[3] }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  member: any
  role?: { label: string; color: string } | null   // evidential INR data split role
}>()

const f = (v: number, d = 3) => v == null ? '-' : Number(v).toFixed(d)

const verdictText = computed(() => {
  const m = props.member
  if (m.outlier_maha > 2.146 && m.outlier_struct > 2.5) return 'a statistical AND structural outlier'
  if (m.outlier_maha > 2.146) return 'a statistical outlier'
  if (m.outlier_struct > 2.5) return 'a structural outlier'
  return 'in distribution'
})

const statRows = computed(() => {
  const m = props.member
  return [
    ['mean', f(m.mean), 'std', f(m.std)],
    ['median', f(m.median), 'w90', f(m.w90)],
    ['min', f(m.min), 'max', f(m.max)],
    ['q05', f(m.q05), 'q95', f(m.q95)],
    ['q25', f(m.q25), 'q75', f(m.q75)],
    ['skew', f(m.skew, 2), 'kurt', f(m.kurt, 2)],
    ['grad_mean', f(m.grad_mean, 4), 'corr_to_mean', f(m.corr_to_mean, 3)],
  ]
})
</script>
