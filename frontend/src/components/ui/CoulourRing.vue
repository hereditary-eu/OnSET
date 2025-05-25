<template>

    <div class="colour-ring">
        <div id="colour_ring_cylinder">

        </div>
        <div id="colour_ring_plane_view">

        </div>
    </div>
</template>
<script setup lang="ts">
import { CylinderMan } from '@/utils/clour-ring/man-cylinder';
import { onMounted, ref } from 'vue'
const cylinder_man = new CylinderMan('#colour_ring_cylinder')

onMounted(() => {
    cylinder_man.init()
})

</script>
<style scoped lang="scss">
.colour-ring {
    width: 40vh;
    height: 80vh;
    justify-items: center;
    align-items: center;
    flex-direction: column;
    display: flex;
}

#colour_ring_cylinder {
    width: 100%;
    height: 50%;
    margin: 5px;
}

#colour_ring_cylinder {
    width: 100%;
    height: 50%;
    margin: 5px;
}

.threed_graph {
    width: 100%;
    height: 100%;
}
</style>