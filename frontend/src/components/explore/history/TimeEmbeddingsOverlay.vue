<template>
    <div class="history_view_overview" ref="history_overview_box">
        <svg class="history_overview_svg" ref="svg_ref" width="100%" height="100%">

        </svg>
    </div>
</template>
<script setup lang="ts">
import { watch, reactive, defineProps, onMounted, ref } from 'vue'
import { HistoryEntry, QueryHistory } from '@/utils/sparql/history';
import HistoryElement from './HistoryElement.vue';
import * as d3 from 'd3'
import { Vector2 } from 'three';
import { CatmullRomSplits } from '@/utils/d3-man/CatmullRomSplits';
import { ManifoldAlg } from '@/api/client.ts/Api';
import type { HistoryTooltipEvent } from '@/utils/sparql/helpers';
const svg_ref = ref(null as SVGSVGElement | null)
const tooltip_div = ref(null as HTMLDivElement | null)
const history_overview_box = ref(null as SVGGElement | null)
enum HistoryMode {
    OVERVIEW = 'Overview',
    DETAILED = 'Detailed',
}
const { history } = defineProps({
    history: {
        type: Object as () => QueryHistory,
        required: true
    },
})
const ui_state = reactive({
    history_mode: HistoryMode.DETAILED,
    tooltip: {
        visible: false,
        position: { x: 0, y: 0 },
        entry: null as HistoryEntry | null,
    }
})

const emit = defineEmits<{
    showTooltip: [HistoryTooltipEvent],
}>()

function updateSvgSize() {
    const rect = history_overview_box.value?.getBoundingClientRect();
    if (svg_ref.value && rect) {
        svg_ref.value.setAttribute("width", `${rect.width}px`)
        svg_ref.value.setAttribute("height", `${rect.height}px`)
    }
    return rect;
}
function recomputeEmbeddings() {
    const rect = updateSvgSize();
    const PADDING = 20;
    (async () => {
        const embeddings = await history.dimReduceEmbeddings(2, ManifoldAlg.Smacof)

        const embeddings_mapped = embeddings.map((emb, idx) => {
            return {
                ...emb,
                r: 5 + Math.log(history.entries[idx].query.nodes.length || 0 + 1) * 3 || 5,
            }
        })
        type embeddings_rval = typeof embeddings[0]
        //normalize embeddings to [0,1] and scale to fit in svg
        const xExtent = d3.extent(embeddings, (d) => d.v.x);
        const yExtent = d3.extent(embeddings, (d) => d.v.y);
        const rect = updateSvgSize();
        const xScale = d3.scaleLinear()
            .domain([xExtent[0] || 0, xExtent[1] || 1])
            .range([PADDING, (rect?.width || 100) - PADDING]);
        const yScale = d3.scaleLinear()
            .domain([yExtent[0] || 0, yExtent[1] || 1])
            .range([PADDING, (rect?.height || 100) - PADDING]);
        if (svg_ref.value) {
            const root_element = d3.select(svg_ref.value)
            root_element.selectAll("g").remove();
            const root_g = root_element.append("g");
            // connect circles with lines in order of history entries
            // split lines into segments with colors for addition/removal
            let scaled_embeddings = embeddings.map(
                emb => new Vector2(xScale(emb.v.x), yScale(emb.v.y))
            )
            let catmulSplits = new CatmullRomSplits(scaled_embeddings, 0.3);
            let splitPaths = catmulSplits.getPaths();
            for (const segment of splitPaths) {
                let entry = embeddings[segment.idx + 1].entry;
                let segment_color = "darkorange"
                let change_size = 0
                if (entry.previous_diff) {
                    const diff = entry.previous_diff
                    change_size = Object.keys(diff.change_set).length || 1
                    if (diff.diff_nodes.added.length > 0 || diff.diff_links.added.length > 0) {
                        segment_color = "darkgreen"

                    } else if (diff.diff_nodes.changed.length > 0 || diff.diff_links.changed.length > 0) {
                        segment_color = "darkred"
                    }

                }
                const segment_path = root_g.append("path")
                    .attr("d", segment.path.toString() || "")
                    .attr("stroke", segment_color)
                    .attr("stroke-width", 2 + Math.log(change_size + 1) * 2)
                    .attr("fill", "none")
                    .attr("opacity", 0.7)
                if (segment.idx === 0) {
                    segment_path.attr("marker-start", "url(#start_arrow)")

                }
            }
            const circles = root_g.selectAll("circle")
                .data(embeddings_mapped)
                .join("circle")
                .attr("cx", (d) => xScale(d.v.x))
                .attr("cy", (d) => yScale(d.v.y))
                .attr("r", (d) => {
                    return d.r
                })
                .attr("stroke", "white")
                .attr("fill", "darkgrey")
                .attr("opacity", 0.9)
                .on("mouseover", function (event: MouseEvent, d) {

                    console.log("Hovering over entry", d, embeddings_mapped)
                    const coord = new Vector2(xScale(d.v.x), yScale(d.v.y));
                    const tooltip_div_pos = new Vector2(tooltip_div.value?.clientLeft || 0, tooltip_div.value?.clientTop || 0)
                    // const offset_pos = new Vector2(150, 100)
                    // const margin_pos = new Vector2(5, 5)
                    const r_offset = new Vector2(d.r, d.r)
                    const relative_pos = coord
                        .add(tooltip_div_pos)
                        // .add(offset_pos)
                        .add(r_offset)
                    // .add(margin_pos)
                    emit("showTooltip", {
                        position: relative_pos, entry: d.entry, event: event
                    })
                })
                .on("mouseleave", function () {
                    // ui_state.tooltip.visible = false
                    // ui_state.tooltip.entry = null
                });
        }


    })().catch((e) => {
        console.error(e)
    })
}

onMounted(() => {


    const markerBoxWidth = 8;
    const markerBoxHeight = 8;
    const refX = markerBoxWidth / 2;
    const refY = markerBoxHeight / 2;
    const arrowPoints = [
        [0, 0],
        [markerBoxWidth, markerBoxHeight / 2],
        [0, markerBoxHeight],
    ];

    if (svg_ref.value) {
        const root_element = d3.select(svg_ref.value)
        root_element.selectAll("defs").remove();
        root_element.append('defs')
            .append('marker')
            .attr('id', 'start_arrow')
            .attr('viewBox', [0, 0, markerBoxWidth, markerBoxHeight])
            .attr('refX', refX * 2)
            .attr('refY', refY)
            .attr('markerWidth', markerBoxWidth)
            .attr('markerHeight', markerBoxHeight)
            .attr('orient', 'auto')
            .append('path')
            .attr('d', d3.line()(arrowPoints as [number, number][]))
            .attr('class', 'starting_arrow');

    }
    recomputeEmbeddings()
    svg_ref.value?.addEventListener("resize", () => {
        recomputeEmbeddings()
    })
})

watch(() => history, (new_length) => {
    console.log("History entries changed, recomputing embeddings", new_length)
    recomputeEmbeddings()
}, { deep: true })

</script>
<style lang="scss">
.history_view_overview {
    display: flex;
    position: relative;
    flex-direction: column;
    align-items: center;
    justify-content: start;
    height: 100%;
    width: 100%;
}

.starting_arrow {
    fill: rgba(6, 151, 35, 0.608);
    stroke: rgba(255, 255, 255, 0.99);
}

.history_tooltip {
    position: absolute;
    background-color: rgba(255, 255, 255, 0.95);
    border: 1px solid rgb(192, 213, 191);
    padding: 10px;
    z-index: 100;
    box-shadow: 2px 2px 5px rgba(0, 0, 0, 0.3);

    min-width: 400px;
    max-width: 400px;

    min-height: 200px;
    max-height: 200px;
}
</style>
