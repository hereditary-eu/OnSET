<template>
    <div class="expandable_frame">

        <div class="expandable_container">
            <slot>


            </slot>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, defineModel } from 'vue'
const expanded = defineModel<boolean>()

</script>
<style lang="css">
.expandable_frame {
    border: 1px solid ;
    border-color: #92ae92;
    border-radius: 5px;
    margin: 5px;
    padding: 5px;
    width: 100%;
}

</style>