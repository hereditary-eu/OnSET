<template>
    <span class="loading_wrapper">
        <svg class="loading_svg" viewBox="0 0 150 67">
            <g>
                <rect v-for="(node, i) of nodes" class="node_loading" :x="node.x" :y="node.y" :width="node.width"
                    :style="`animation-delay: ${animationDelay(i, nodes.length)};`" :height="node.height">
                </rect>
                <path v-for="(link, i) of links" class="link_loading" :d="`M ${link.left.x + link.left.width},${link.left.y + link.left.height / 2} 
                C ${link.right.x},${link.left.y + link.left.height / 2} 
                ${link.left.x + link.left.width},${link.right.y + link.right.height / 2} 
                ${link.right.x},${link.right.y + link.right.height / 2}`"
                    :style="`animation-delay: ${animationDelay(i, links.length)};`"></path>
            </g>
        </svg>
    </span>
</template>
<script setup lang="ts">

import { ref } from 'vue'

// height of the animation; the width follows from the aspect ratio
const { height , fixed} = defineProps({
    height: {
        type: String,
        default: "2rem"
    },
    fixed: {
        type: Boolean,
        default: false
    }
})
class NodeLoading {
    x: number
    y: number
    width: number
    height: number
    constructor(x: number, y: number, width: number, height: number) {
        this.x = x
        this.y = y
        this.width = width
        this.height = height
    }
}
class LinkLoading {
    left: NodeLoading
    right: NodeLoading
    constructor(left: NodeLoading, right: NodeLoading) {
        this.left = left
        this.right = right
    }
}
const nodes = ref([new NodeLoading(2, 2, 50, 25),
new NodeLoading(75, 20, 50, 25),
new NodeLoading(10, 40, 50, 25)])
const links = ref([new LinkLoading(nodes.value[0], nodes.value[1]), new
    LinkLoading(nodes.value[2], nodes.value[1])])

function animationDelay(index: number, total: number) {
    if (fixed){
        return "0s"
    }
    return `${index / total}s`
}
function animationIterationCount() {
    if (fixed){
        return "1"
    }
    return "infinite"
}
</script>
<style lang="scss" scoped>
@keyframes loading_transition {
    0% {
        stroke: #5aa574;
    }

    50% {
        stroke: #ffffff;
    }

    100% {
        stroke: #5aa574;
    }

}

.node_loading {
    fill: #ffffff;
    stroke: #5aa574;
    animation-name: loading_transition;
    animation-duration: 2s;
    animation-timing-function: ease-in-out;
    animation-iteration-count: v-bind(animationIterationCount);
    stroke-width: 1.5px;
}

.link_loading {
    fill: none;
    stroke: #5aa574;
    animation-name: loading_transition;
    animation-duration: 2s;
    animation-timing-function: ease-in-out;
    animation-iteration-count: v-bind(animationIterationCount);
    stroke-width: 1.5px;
}

.loading_wrapper {
    display: flex;
    justify-content: center;
    align-items: center;
    flex: 0 0 auto;
    height: v-bind(height);
    margin: var(--space-1);
}

.loading_svg {
    height: 100%;
    aspect-ratio: 150 / 67;
}
</style>
