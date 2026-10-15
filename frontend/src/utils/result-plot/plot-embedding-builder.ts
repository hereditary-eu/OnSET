import { Api, type Subject } from "@/api/client.ts/Api";
import { colormaps_d3 } from "../colormaps";
import type { BuildTrace } from "./plot-builder";
import type { PlotCacheEntry } from "./plot-cache";
import { ChartMode, PropType, type AnalyzedProp } from "./plot-types";
import * as d3 from "d3";
import type { Link, SubjectNode } from "../sparql/representation";
import type { NodeLinkRepository } from "../sparql/store";
import { BACKEND_URL } from "../config";
const api = new Api<any>({ baseURL: BACKEND_URL });
export function buildEmbeddingPlotData(analyzed_props: AnalyzedProp[], result_set: Record<string, any>[], query_limitless: string, store: NodeLinkRepository<SubjectNode, Link<Subject>>): BuildTrace {
    let vector_props = analyzed_props.filter(p => p.prop_type == PropType.VECTOR)
    if (vector_props.length == 0) {
        throw new Error("No vector properties found for embedding plot")
    }
    let non_vector_props = analyzed_props.filter(p => p.prop_type != PropType.VECTOR)

    let description = vector_props.map(p => p.prop.link.label).join(" and ")
    let cmap = colormaps_d3["Roma"]

    let color_prop = analyzed_props.find(p => p.prop_type == PropType.DISCRETE || p.prop_type == PropType.CONTINOUS)
    let colors: string[] = null
    if (color_prop) {
        let color_values = result_set.map(r => r[color_prop.query_id])
        if (color_prop.prop_type == PropType.DISCRETE) {
            let unique_values = Array.from(new Set(color_values))
            let scale = d3.scalePoint<string>(unique_values, [0, 1])
            colors = color_values.map(v => cmap(scale(v)))
        } else if (color_prop.prop_type == PropType.CONTINOUS) {
            let min = Math.min(...color_values)
            let max = Math.max(...color_values)
            let scale = d3.scaleLinear([min, max], [0, 1])
            colors = color_values.map(v => cmap(scale(v)))
        }
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
        text: result_set.map(r => {
            let label = non_vector_props.map(p => `${p.prop.link.label}: ${r[p.query_id]}\n`).join("<br>")
            return label
        }),
        mode: 'markers',
        type: 'scatter',
        marker: { size: 8, color: colors || "blue" },
        

    } as Plotly.PlotData
    return {
        trace,
        chart_mode: ChartMode.DIM_REDUCED,
        chart_options
    }

}
