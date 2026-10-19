<script setup lang="ts">
import { RouterView, useRoute } from 'vue-router'
import AppHeader from '@/components/ui/AppHeader.vue'

const route = useRoute()
</script>

<template>
  <v-app>
    <AppHeader />
    <!-- Remount the page when the configuration changes, so no state leaks between configurations -->
    <div class="page">
      <RouterView :key="(route.params.configId as string | undefined) ?? 'root'" />
    </div>
  </v-app>
</template>

<style>
body {
  font-family: 'Roboto Mono', monospace;
  margin: 0px;
}
text{
  font-family: 'Roboto Mono', monospace;
}
</style>
