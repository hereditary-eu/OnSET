<template>
    <div class="constraint">
        <img v-if="query.is_image_prop" :src="image_data" alt="Image property" />
        <template v-else>
            <OnsetIcon icon="mdi-tag" />
            <span class="constraint_label">{{ query.value }}</span>
        </template>
    </div>
</template>
<script setup lang="ts">
import { InstanceQueryProp } from '@/utils/sparql/representation';
import { onMounted, ref, watch } from 'vue'
import OnsetIcon from '@/components/ui/OnsetIcon.vue';
import { api } from '@/utils/api'
const { query } = defineProps({
    query: {
        type: Object as () => InstanceQueryProp,
        required: true
    }
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
