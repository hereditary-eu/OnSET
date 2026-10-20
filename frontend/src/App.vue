<script setup lang="ts">
import { RouterView, useRoute } from 'vue-router'
import AppHeader from '@/components/ui/AppHeader.vue'

const route = useRoute()
</script>

<template>
  <div class="app_root">
    <AppHeader />
    <!-- Remount the page when the configuration changes, so no state leaks between configurations -->
    <div class="page">
      <RouterView :key="(route.params.configId as string | undefined) ?? 'root'" />
    </div>
  </div>
</template>

<style>
body {
  font-family: var(--font-mono);
  margin: 0px;
}
</style>
