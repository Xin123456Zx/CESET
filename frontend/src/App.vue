<template>
    <!-- keep-alive: switching between the three modules does not destroy page state
         (Module 3's recommendations, Module 2's history rows, etc. are all kept).
         The WebGL context quota is managed by onActivated/onDeactivated in
         useVtkView / RoiSelect3d: release on leave, rebuild on return -->
    <router-view v-slot="{ Component }">
      <keep-alive>
        <component :is="Component" />
      </keep-alive>
    </router-view>
</template>
<script lang="ts" setup>


</script>
