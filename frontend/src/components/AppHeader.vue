<template>
  <header class="shadow-[0px_2px_20px_0px_rgba(0,0,0,0.25)] shrink-0">
    <div class="text-2xl font-semibold text-center italic pt-2">Conformalized Evidential Surrogate Exploration Tool</div>
    <!-- Three feature tabs: one service, three pages -->
    <nav class="flex items-center justify-center gap-2 py-1.5">
      <router-link
        v-for="t in tabs" :key="t.path" :to="t.path"
        class="px-5 py-1.5 rounded-full text-[14px] font-semibold border-2 transition-colors"
        :class="isActive(t.path)
          ? 'bg-[#ACACFF] text-white border-[#ACACFF]'
          : 'bg-white text-[#666] border-[#ddd] hover:border-[#ACACFF] hover:text-[#ACACFF]'"
      >{{ t.label }}</router-link>
    </nav>
  </header>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router'

// Emoji match each page's title, so tab ↔ page identity is visually consistent
const tabs = [
  { path: '/explore', label: '🗺 1 · Data Exploration' },
  { path: '/index', label: '🔭 2 · Uncertainty Model Prediction' },
  { path: '/paraspace', label: '🧭 3 · Para-space Exploration' },
]
const route = useRoute()
const isActive = (p: string) => route.path === p
</script>
