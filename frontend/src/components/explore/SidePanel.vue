<template>
    <!-- Collapsible, tabbed side panel of the explore view (third panel next to the editor and results).
         Each tab's content is passed as a named slot with the tab's id, e.g. <template #topics>. -->
    <aside class="panel side_panel" :class="{ side_panel_collapsed: collapsed }">
        <header class="panel_header side_panel_header">
            <template v-if="!collapsed">
                <div class="toolbar side_panel_tabs">
                    <OnsetBtn v-for="tab in tabs" :key="tab.id" :toggleable="false" size="small"
                        :class="{ onset_btn_selected: active == tab.id }" :icon="tab.icon" :title="tab.label"
                        @click="active = tab.id">
                        {{ tab.label }}
                    </OnsetBtn>
                </div>
                <span class="toolbar_spacer"></span>
            </template>
            <OnsetBtn class="side_panel_toggle" size="small" :toggleable="false" :icon="collapsed ? 'mdi-chevron-left' : 'mdi-chevron-right'"
                :title="collapsed ? 'Expand panel' : 'Collapse panel'" @click="collapsed = !collapsed" />
        </header>
        <!-- collapsed: a narrow rail of tab icons that re-opens the panel on the chosen tab -->
        <div v-if="collapsed" class="side_panel_rail">
            <OnsetBtn v-for="tab in tabs" :key="tab.id" size="small" :toggleable="false" :icon="tab.icon"
                :title="tab.label" @click="open(tab.id)" />
        </div>
        <template v-else>
            <div v-for="tab in tabs" :key="tab.id" v-show="active == tab.id" class="panel_body side_panel_body">
                <!-- tabs are mounted lazily on first activation and then kept alive -->
                <slot v-if="visited.has(tab.id)" :name="tab.id"></slot>
            </div>
        </template>
    </aside>
</template>
<script setup lang="ts">
import { reactive, watch } from 'vue'
import OnsetBtn from '@/components/ui/OnsetBtn.vue'

export interface SidePanelTab {
    id: string
    label: string
    icon: string
}

const { tabs } = defineProps<{
    tabs: SidePanelTab[]
}>()
// id of the visible tab
const active = defineModel<string>('active', { required: true })
const collapsed = defineModel<boolean>('collapsed', { default: false })

const visited = reactive(new Set<string>())
watch([active, collapsed], () => {
    if (!collapsed.value && active.value) {
        visited.add(active.value)
    }
}, { immediate: true })

const open = (id: string) => {
    active.value = id
    collapsed.value = false
}
</script>
<style scoped>
.side_panel {
    width: var(--side-panel-width, 18rem);
    flex: 0 0 auto;
}

.side_panel_collapsed {
    width: auto;
}

.side_panel_header {
    padding-left: var(--space-1);
}

.side_panel_tabs {
    min-width: 0;
    overflow: hidden;
}

.side_panel_rail {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--space-1);
    padding: var(--space-1);
}

.side_panel_body {
    padding: var(--space-1);
}
</style>
