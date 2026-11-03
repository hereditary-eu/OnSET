<template>
    <!-- Histogram of the modifications' row counts on a log axis (bar heights log-scaled too),
         with a scrubber: dragging over the chart (or the slider below it) selects a row count. Bars stack the levels of
         the tree expansion (depth 1 at the bottom, deeper levels lighter), links below
         constraints within a level; the bin of the selected modification is outlined. -->
    <div ref="container" class="prog_hist">
        <svg :width="width" :height="HEIGHT" class="prog_hist_svg" @pointerdown="startScrub" @pointermove="moveScrub"
            @pointerup="endScrub" @pointercancel="endScrub">
            <!-- per level (bottom up): links (and starting points), then constraints -->
            <g v-for="bin in bins" :key="bin.index"
                :class="{ prog_hist_bin_near: bin.ids.some((id) => nearest_ids.has(id)) }">
                <title>{{ bin_title(bin) }}</title>
                <rect v-for="segment in bin.segments" :key="`${segment.depth}:${segment.constraint}`"
                    class="prog_hist_bar" :class="{ prog_hist_bar_constraint: segment.constraint }"
                    :fill-opacity="depthOpacity(segment.depth)"
                    :x="x(bin.x0) + 0.5" :y="segmentTop(segment)" :width="Math.max(1, x(bin.x1) - x(bin.x0) - 1)"
                    :height="y(segment.y0) - segmentTop(segment)" />
                <rect v-if="selected_id != null && bin.ids.includes(selected_id)" class="prog_hist_selected"
                    :x="x(bin.x0) - 0.5" :y="Math.min(y(bin.ids.length), y(0) - MIN_BAR) - 1.5" :width="Math.max(1, x(bin.x1) - x(bin.x0)) + 1"
                    :height="Math.max(y(0) - y(bin.ids.length), MIN_BAR) + 1.5" />
            </g>

            <line class="prog_hist_axis" :x1="x(extent[0])" :x2="x(extent[1])" :y1="y(0)" :y2="y(0)" />
            <g v-for="tick in ticks" :key="tick.position">
                <line class="prog_hist_axis" :x1="x(tick.position)" :x2="x(tick.position)" :y1="y(0)" :y2="y(0) + 3" />
                <text class="prog_hist_tick" :x="x(tick.position)" :y="y(0) + 12">{{ tick.label }}</text>
            </g>
            <text class="prog_hist_tick prog_hist_ymax" :x="MARGIN.left - 3" :y="y(y_max) + 3">{{ y_max }}</text>
            <g v-if="base_count != null">
                <line class="prog_hist_base" :x1="x(countPosition(base_count))" :x2="x(countPosition(base_count))"
                    :y1="MARGIN.top" :y2="y(0)" />
                <text class="prog_hist_tick prog_hist_base_label" :x="x(countPosition(base_count))" :y="MARGIN.top - 2">
                    current</text>
            </g>
            <line class="prog_hist_scrub" :x1="x(countPosition(scrub_count))" :x2="x(countPosition(scrub_count))"
                :y1="MARGIN.top" :y2="y(0)" />
        </svg>
        <input class="prog_hist_slider" type="range" :min="extent[0]" :max="extent[1]" step="0.01"
            :value="countPosition(scrub_count)" :title="`${formatCount(scrub_count)} rows`"
            :style="{ marginLeft: `${MARGIN.left}px`, marginRight: `${MARGIN.right}px` }"
            @input="scrub = countAtPosition(Number(($event.target as HTMLInputElement).value))" />
        <div v-if="has_constraints || depth > 1" class="prog_hist_legend">
            <span><i class="prog_hist_swatch"></i>links</span>
            <span v-if="has_constraints"><i class="prog_hist_swatch prog_hist_swatch_constraint"></i>constraints</span>
            <template v-if="depth > 1">
                <span class="prog_hist_legend_sep">depth</span>
                <span v-for="d in depth" :key="d" :title="`Modifications with ${d} step${d > 1 ? 's' : ''}`">
                    <i class="prog_hist_swatch prog_hist_swatch_depth" :style="{ opacity: depthOpacity(d) }"></i>{{ d }}</span>
            </template>
        </div>
    </div>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import * as d3 from 'd3'
import {
    countAtPosition, countPosition, depthOpacity, formatCount, type BinSegment, type HistogramBin,
} from '@/utils/progressive/histogram'

const { bins, extent, base_count = null, scrub_count, nearest_ids, selected_id = null } = defineProps<{
    bins: HistogramBin[]
    extent: [number, number]
    base_count?: number | null
    scrub_count: number
    nearest_ids: Set<string>
    /** the modification selected in the tree, its bin is outlined */
    selected_id?: string | null
}>()
// the selected row count
const scrub = defineModel<number | null>('scrub')

const HEIGHT = 96
const MARGIN = { top: 12, right: 14, bottom: 16, left: 22 }

const container = ref<HTMLElement | null>(null)
const width = ref(300)
let observer: ResizeObserver | null = null
onMounted(() => {
    observer = new ResizeObserver(([entry]) => {
        width.value = Math.max(120, Math.floor(entry.contentRect.width))
    })
    if (container.value) {
        observer.observe(container.value)
    }
})
onBeforeUnmount(() => observer?.disconnect())

const x = computed(() => d3.scaleLinear().domain(extent).range([MARGIN.left, width.value - MARGIN.right]))
const y_max = computed(() => Math.max(1, ...bins.map((b) => b.ids.length)))
// bar heights on a log scale (log(1 + n)): with all candidates counted, one bin (often the
// empty joins at 0 rows) can hold hundreds of modifications, on a linear scale the other bins
// would shrink to sub-pixel bars as the counts stream in
const y = computed(() => d3.scaleSymlog().domain([0, y_max.value]).range([HEIGHT - MARGIN.bottom, MARGIN.top]))
// smallest height of a non-empty bar segment, in px
const MIN_BAR = 2
const segmentTop = (segment: BinSegment) => Math.min(y.value(segment.y0 + segment.n), y.value(segment.y0) - MIN_BAR)
// a tick per decade (thinned to fit), labelled with the row count
const ticks = computed(() => {
    const decades = d3.range(Math.floor(extent[0]), Math.floor(extent[1]) + 1)
    const every = Math.ceil(decades.length / Math.max(1, Math.floor((width.value - MARGIN.left) / 36)))
    // the first decade starts at 0 rows (position 0), the others at 10^k rows
    return decades.filter((_, i) => i % every == 0)
        .map((k) => k == 0 ? { position: 0, label: '0' } : { position: countPosition(10 ** k), label: formatCount(10 ** k) })
})
const has_constraints = computed(() => bins.some((b) => b.constraints > 0))
// deepest level among the bins
const depth = computed(() => Math.max(1, ...bins.flatMap((b) => b.segments.map((s) => s.depth))))
const bin_title = (bin: HistogramBin) => {
    const levels = depth.value > 1
        ? '; ' + d3.range(1, depth.value + 1)
            .map((d) => [d, d3.sum(bin.segments.filter((s) => s.depth == d), (s) => s.n)])
            .filter(([, n]) => n > 0).map(([d, n]) => `${n} at depth ${d}`).join(', ')
        : ''
    return `${bin.ids.length} modification${bin.ids.length > 1 ? 's' : ''}`
        + (bin.constraints ? ` (${bin.constraints} constraint${bin.constraints > 1 ? 's' : ''})` : '')
        + `, ${formatCount(countAtPosition(bin.x0))}–${formatCount(countAtPosition(bin.x1))} rows` + levels
}

// --- scrubbing on the chart ---
let scrubbing = false
const scrubTo = (evt: PointerEvent) => {
    const svg = evt.currentTarget as SVGSVGElement
    const px = evt.clientX - svg.getBoundingClientRect().left
    const position = Math.min(extent[1], Math.max(extent[0], x.value.invert(px)))
    scrub.value = countAtPosition(position)
}
const startScrub = (evt: PointerEvent) => {
    scrubbing = true;
    (evt.currentTarget as SVGSVGElement).setPointerCapture(evt.pointerId)
    scrubTo(evt)
}
const moveScrub = (evt: PointerEvent) => {
    if (scrubbing) {
        scrubTo(evt)
    }
}
const endScrub = () => {
    scrubbing = false
}
</script>
<style scoped>
.prog_hist {
    display: flex;
    flex-direction: column;
    width: 100%;
}

.prog_hist_svg {
    display: block;
    cursor: ew-resize;
    touch-action: none;
    user-select: none;
}

.prog_hist_bar {
    fill: var(--c-node-normal);
}

.prog_hist_bin_near .prog_hist_bar {
    fill: var(--c-accent);
}

.prog_hist_bar {
    /* separates the stacked levels */
    stroke: var(--c-surface);
    stroke-width: 0.5;
}

.prog_hist_bar_constraint {
    fill: var(--c-constraint);
    opacity: 0.55;
}

.prog_hist_bin_near .prog_hist_bar_constraint {
    fill: var(--c-constraint);
    opacity: 1;
}

.prog_hist_selected {
    fill: none;
    stroke: currentColor;
    stroke-width: 1.5;
    pointer-events: none;
}

.prog_hist_legend {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-2);
    font-size: 9px;
    opacity: 0.8;
}

.prog_hist_swatch {
    display: inline-block;
    width: 7px;
    height: 7px;
    margin-right: 2px;
    background: var(--c-node-normal);
}

.prog_hist_swatch_constraint {
    background: var(--c-constraint);
}

.prog_hist_swatch_depth {
    background: var(--c-link-normal);
}

.prog_hist_legend_sep {
    margin-left: var(--space-1);
}

.prog_hist_axis {
    stroke: var(--c-link-normal);
    stroke-width: 1;
}

.prog_hist_tick {
    font-size: 9px;
    fill: currentColor;
    opacity: 0.75;
    text-anchor: middle;
}

.prog_hist_ymax {
    text-anchor: end;
}

.prog_hist_base {
    stroke: var(--c-link-normal);
    stroke-dasharray: 3 2;
}

.prog_hist_base_label {
    font-size: 8px;
}

.prog_hist_scrub {
    stroke: var(--c-node-removed);
    stroke-width: 2;
    pointer-events: none;
}

.prog_hist_slider {
    accent-color: var(--c-accent);
    height: 1rem;
}
</style>
