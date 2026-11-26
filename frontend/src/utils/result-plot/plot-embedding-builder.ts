import { type Subject } from "@/api/client.ts/Api";
import { colormaps_d3 } from "../colormaps";
import type { BuildTrace } from "./plot-builder";
import type { PlotCacheEntry } from "./plot-cache";
import { ChartMode, PropType, type AnalyzedProp } from "./plot-types";
import * as d3 from "d3";
import type { Link, SubjectNode } from "../sparql/representation";
import type { NodeLinkRepository } from "../sparql/store";
import { api } from "@/utils/api"
import type { ScatterData } from "plotly.js-dist";
import * as Plotly from "plotly.js-dist";
const hasCoordinates = (row: Record<string, any>) => Array.isArray(row["dim_reduced"])
const hoverText = (row: Record<string, any>, props: AnalyzedProp[]) =>
    props.map(p => `${p.prop.link.label}: ${row[p.query_id]}\n`).join("<br>")

export function buildEmbeddingPlotData(analyzed_props: AnalyzedProp[], result_set: Record<string, any>[], query_limitless: string, store: NodeLinkRepository<SubjectNode, Link<Subject>>): BuildTrace {
    let vector_props = analyzed_props.filter(p => p.prop_type == PropType.VECTOR)
    if (vector_props.length == 0) {
        throw new Error("No vector properties found for embedding plot")
    }
    let non_vector_props = analyzed_props.filter(p => p.prop_type != PropType.VECTOR)

    let description = vector_props.map(p => p.prop.link.label).join(" and ")
    let cmap = colormaps_d3["Roma"]

    // rows without all their tensors have no coordinates
    result_set = result_set.filter(hasCoordinates)
    let color_prop = analyzed_props.find(p => p.prop_type == PropType.DISCRETE || p.prop_type == PropType.CONTINOUS)
    let colors: string[] = null
    if (color_prop) {
        let color_values = result_set.map(r => r[color_prop.query_id])
        if (color_prop.prop_type == PropType.DISCRETE) {
            let unique_values = Array.from(new Set(color_values))
            let scale = d3.scalePoint<string>(unique_values, [0, 1])
            colors = color_values.map(v => cmap(scale(v)))
        } else if (color_prop.prop_type == PropType.CONTINOUS) {
            color_values = color_values.map(v => parseFloat(v))
            const filtered_values = color_values.filter(v => !isNaN(v));
            let min = Math.min(...filtered_values)
            let max = Math.max(...filtered_values)
            let scale = d3.scaleLinear([min, max], [0, 1])
            colors = color_values.map(v => {
                try {
                    return cmap(scale(v))
                } catch (e) {
                    console.error("Error in color mapping", e, "min, max", min, max, "value", v)
                    return "gray"
                }
            })
        }
        console.log("Color values", color_values, "color prop", color_prop, "colors", colors)
    }

    let chart_options = {
        height: 600,
        title: {
            text: description
        },
        xaxis: {
            title: {
                text: "Dimension 1"
            },
            automargin: true,
        },
        yaxis: {
            title: {
                text: "Dimension 2"
            }
        },
        legend: {
            title: {
                text: color_prop ? color_prop.prop.link.label : ""
            }
        },
    } as Plotly.Layout
    let trace = {
        x: result_set.map(r => r["dim_reduced"][0]),
        y: result_set.map(r => r["dim_reduced"][1]),
        text: result_set.map(r => hoverText(r, non_vector_props)),
        mode: 'markers',
        type: 'scatter',
        marker: { size: 8, color: colors || "blue" },


    } as ScatterData
    return {
        trace,
        chart_mode: ChartMode.DIM_REDUCED,
        chart_options
    }

}

/**
 * Difference view of the embedding plot: the previous and the current results as two traces,
 * both with coordinates of one dimensionality reduction (dim-reduce with `compare`), so that
 * they are comparable. The rows are coloured by their query, not by a property.
 */
export function buildEmbeddingDiffTraces(analyzed_props: AnalyzedProp[], previous_rows: Record<string, any>[],
    current_rows: Record<string, any>[], chart_options: Plotly.Layout): { traces: ScatterData[], chart_options: Plotly.Layout } {
    const non_vector_props = analyzed_props.filter(p => p.prop_type != PropType.VECTOR)
    const trace = (rows: Record<string, any>[], name: string, color: string) => {
        rows = rows.filter(hasCoordinates)
        return {
            x: rows.map(r => r["dim_reduced"][0]),
            y: rows.map(r => r["dim_reduced"][1]),
            text: rows.map(r => hoverText(r, non_vector_props)),
            name,
            mode: 'markers',
            type: 'scatter',
            marker: { size: 8, color, opacity: 0.5 },
        } as ScatterData
    }
    return {
        traces: [trace(previous_rows, "Previous", "red"), trace(current_rows, "Current", "#8fa88f")],
        chart_options: { ...chart_options, showlegend: true, legend: { title: { text: "" } } } as Plotly.Layout,
    }
}
