<template>
    <div class="query">
        <div class="image_property" v-if="query.is_image_prop">
            <img :src="image_data" alt="Image property" style="max-width: 100%; max-height: 100%;" />

        </div>
        <div v-else>
            <span> <v-icon icon="mdi-tag"></v-icon>
            </span>
            <span class="query_label">{{ query.value }}</span>
        </div>
    </div>
</template>
<script setup lang="ts">
import { InstanceQueryProp } from '@/utils/sparql/representation';
import { computed, defineProps, onMounted, ref, watch } from 'vue'
import { api } from '@/utils/api'
const { query } = defineProps({
    query: {
        type: Object as () => InstanceQueryProp,
        required: true
    }
})
onMounted(() => {
    // console.log("InstanceProperty mounted with query", query, "is image prop?", query.is_image_prop)
})
const image_data = ref<string | null>(null)
const loadImage = async () => {
    if (query.is_image_prop) {
        try {
            let image_link = /<([^>]+)>/.exec(query.value)?.[1];
            if (!image_link) {
                console.error("Could not extract image link from query value", query.value);
                image_link = query.value; // fallback to the original value
            }
            // replace http with https
            image_link = image_link.replace(/^http:/, 'https:');
            const response = await api.search.wikimediaProxySearchWikimediaProxyGet({ url: image_link }, { format: 'blob' });
            let reader = new FileReader();
            reader.onloadend = () => {
                image_data.value = reader.result as string;
            };
            reader.readAsDataURL(response.data);
        } catch (error) {
            console.error("Error loading image:", error);
        }
    }
};
watch(() => query.value, () => {
    loadImage();
})
onMounted(() => {
    loadImage();
})
</script>
<style lang="scss" scoped>
.query_label {
    margin-right: 5px;
}

.query_select {
    margin-right: 5px;
    border: rgb(105, 132, 99) 1px solid;
    border-radius: 0px;
}

.image_property {
    margin: 5px;
}
</style>
