import type { Subject } from "@/api/client.ts/Api";
import { getMax, getMin } from "../helpers";
import { Link, SubjectNode, VectorData, type QueryProp } from "../sparql/representation";
import type { NodeLinkRepository } from "../sparql/store";
import type { PlotCacheEntry } from "./plot-cache";
import { buildEmbeddingPlotData as buildEmbeddingPlotTraces } from "./plot-embedding-builder";
import { BucketSpecifier, ChartMode, ContinuousBucketSpecifier, DiscreteBucketSpecifier, PropSpecificType, PropType, type AnalyzedProp } from "./plot-types";

import * as Plotly from "plotly.js-dist";
//https://stackoverflow.com/questions/12303989/cartesian-product-of-multiple-arrays-in-javascript
function cartesianProduct<T>(arr: T[][]): T[][] {
    return arr.reduce(function (a, b) {
        return a.map(function (x) {
            return b.map(function (y) {
                return x.concat([y]);
            })
        }).reduce(function (a, b) { return a.concat(b) }, [])
    }, [[]])
}
const MAX_DISCRETE_BUCKETS = 20
const MAX_CONTINUOUS_BUCKETS = 50
/**
 * Number of bins by Scott's rule: bin width h = 3.49 * sd * n^(-1/3), so the bins get
 * narrower the more data points there are. Clamped to [1, max_buckets].
 */
export function scottBucketCount(data: number[], max_buckets = MAX_CONTINUOUS_BUCKETS) {
    const n = data.length
    if (n < 2) {
        return 1
    }
    const mean = data.reduce((acc, val) => acc + val, 0) / n
    const sd = Math.sqrt(data.reduce((acc, val) => acc + (val - mean) ** 2, 0) / (n - 1))
    const range = getMax(data) - getMin(data)
    if (!(sd > 0) || !(range > 0)) {
        return 1
    }
    const width = 3.49 * sd * Math.pow(n, -1 / 3)
    return Math.max(1, Math.min(max_buckets, Math.ceil(range / width)))
}
/**
 * Buckets of each prop: the most common values of discrete props, equal-width bins of
 * continuous props. `n_buckets` fixes the number of continuous bins, null picks it by
 * Scott's rule.
 */
export function bucketizeData(props: AnalyzedProp[], n_buckets: number | null = 20) {
    let buckets: Record<string, BucketSpecifier[]> = {}

    for (let i = 0; i < props.length; i++) {
        let bucket_prop: BucketSpecifier[] = []
        let prop = props[i]
        switch (prop.prop_type) {
            case PropType.CONTINOUS:
                let continous_data = prop.prop_data as number[]
                switch (prop.prop_specific_type) {
                    case PropSpecificType.DATE:
                        continous_data = prop.prop_data.map((val) => val.getTime())
                        break
                    default:
                        break
                }
                let min = getMin(continous_data)
                let max = getMax(continous_data)
                let n_continuous = max > min ? (n_buckets ?? scottBucketCount(continous_data)) : 1
                let step = (max - min) / n_continuous
                for (let i = 0; i < n_continuous; i++) {
                    let lower = min + i * step
                    // the last bin is closed so that it contains the maximum
                    let last = i == n_continuous - 1
                    let upper = last ? max : min + (i + 1) * step
                    let bucket = new ContinuousBucketSpecifier(lower, upper, 0, prop, last, step)
                    bucket.count = continous_data.filter((val) => bucket.inside(val)).length
                    bucket_prop.push(bucket)
                }
                break
            default:
            case PropType.DISCRETE:
                let value_counts = prop.prop_data.reduce((acc, val) => {
                    if (val in acc) {
                        acc[val] += 1
                    } else {
                        acc[val] = 1
                    }
                    return acc
                }, {} as Record<string, number>) as Record<string, number>
                let sorted_keys = Object.keys(value_counts).sort((a, b) => value_counts[b] - value_counts[a])
                bucket_prop.push(...sorted_keys.splice(0, n_buckets ?? MAX_DISCRETE_BUCKETS).map((key) => {
                    return new DiscreteBucketSpecifier(key, value_counts[key], prop)
                }))
                break
        }
        //convert bucket lower and upper to string if date
        // if (prop.prop_specific_type == PropSpecificType.DATE) {
        //     bucket_prop = bucket_prop.map((bucket) => {
        //         return new BucketSpecifier(new Date(bucket.lower).toLocaleDateString(), new Date(bucket.upper).toLocaleDateString(), bucket.count, bucket.prop)
        //     })
        // }
        buckets[prop.query_id] = bucket_prop
    }
    console.log('Buckets', buckets)
    return buckets
}

export function analyzeProps(prop: QueryProp, result_set: Record<string, any>[]) {
    const query_id = prop.link.outputId().replace('?', '')
    let prop_data = result_set.map((row) => row[query_id])
    let prop_type = PropType.DISCRETE
    let prop_specific_type = PropSpecificType.STRING
    if (prop.link.to_proptype == VectorData.propType) {
        prop_type = PropType.VECTOR
        prop_specific_type = PropSpecificType.VECTOR
    } else if (prop_data.length > 0) {
        if (typeof prop_data[0] == 'number') {
            prop_type = PropType.CONTINOUS
            prop_specific_type = PropSpecificType.NUMBER
        } else {
            try {
                let date_data = prop_data.map((val) => new Date(val))
                if (date_data.every((val) => !isNaN(val.getTime()))) {
                    prop_data = date_data
                    prop_type = PropType.CONTINOUS
                    prop_specific_type = PropSpecificType.DATE
                }
            } catch (error) {
                console.error('Error while analyzing prop', prop, error)
            }
        }
    }
    return {
        prop: prop,
        prop_data: prop_data,
        prop_type: prop_type,
        prop_specific_type,
        query_id
    } as AnalyzedProp
}
export type TraceData = Plotly.ScatterData | Plotly.BarData | Plotly.HeatmapData 
export interface BuildTrace {
    trace: TraceData
    chart_mode: ChartMode
    chart_options: Plotly.Layout
}

/**
 * Lets do some heuristics
 * - 1 var:
 *   - 1 continous prop: bar chart in order, 15-20 buckets
 *   - 1 discrete prop: bar chart in order, 15-20 most common buckets
 * - 2 vars:
 *   - 2 continous props: scatter plot, maybe background as distribution...
 *   - 1 continous, 1 discrete: ??
 *   - 2 discrete props: heatmap, 15-20 most common buckets
 * - 3 vars:
 *   - 2 continous, 1 discrete: scatter plot, color by discrete
 *   - 1 continous, 2 discrete: ??
 *   - 3 discrete: ??
 * - 1 var vector
 *   - embedding plot, calculate umap in backend, return x,y coordinates
 *   - 1+ continous props: color by continous
 *   - 1+ discrete props: color by discrete
 */
export function buildChartTraces(analyzed_props: AnalyzedProp[], result_set: Record<string, any>[], query_limitless: string, store: NodeLinkRepository<SubjectNode, Link<Subject>>): BuildTrace {
    let continous_props = analyzed_props.filter((prop) => prop.prop_type == PropType.CONTINOUS)
    let trace = {} as TraceData
    let chart_mode = ChartMode.BAR
    let chart_options = {} as Plotly.Layout
    if (analyzed_props.filter((prop) => prop.prop_type == PropType.VECTOR).length > 0) {
        return buildEmbeddingPlotTraces(analyzed_props, result_set, query_limitless, store)
    }
    switch (analyzed_props.length) {
        case 0:
            throw Error('No properties to display')
            break
        case 1:
            chart_mode = ChartMode.BAR
            let bar_trace = {} as Plotly.BarData
            bar_trace.type = 'bar'

            let prop = analyzed_props[0]


            chart_options = {
                height: 600,
                title: {
                    text: prop.prop.link.label
                },
                xaxis: {

                    title: {
                        text: prop.prop.link.label
                    },
                    automargin: true,
                },
                yaxis: {
                    title: {
                        text: "Count"
                    }
                }
            } as Plotly.Layout
            let buckets = bucketizeData(analyzed_props, null)
            bar_trace.x = buckets[prop.query_id].map((bucket) => bucket.display())
            bar_trace.y = buckets[prop.query_id].map((bucket) => bucket.count)
            bar_trace.marker = {
                color: '#8fa88f',
            }
            trace = bar_trace
            break
        case 2: {
            if (continous_props.length == 2 && continous_props[0].prop_data.length < 1024) {
                chart_mode = ChartMode.SCATTER
                //TODO: Add background distribution/switch to heatmap beyond 1000 points
                chart_options = {
                    title: {
                        text: `${continous_props[0].prop.link.label} vs ${continous_props[1].prop.link.label}`
                    },
                    xaxis: {
                        title: {
                            text: continous_props[0].prop.link.label
                        },
                        automargin: true,
                    },
                    yaxis: {
                        title: {
                            text: continous_props[1].prop.link.label
                        }
                    }
                } as Plotly.Layout
                let scatter_trace = {} as Plotly.ScatterData
                scatter_trace.type = 'scatter'
                scatter_trace.mode = 'markers'
                scatter_trace.x = continous_props[0].prop_data
                scatter_trace.y = continous_props[1].prop_data
                scatter_trace.marker = {
                    color: '#8fa88f',
                }
                trace = scatter_trace
            } else {
                console.log("Using heatmap", continous_props)
                chart_mode = ChartMode.HEATMAP
                chart_options = {
                    title: {
                        text: `${analyzed_props[0].prop.link.label} vs ${analyzed_props[1].prop.link.label}`
                    },
                    xaxis: {
                        title: {
                            text: analyzed_props[0].prop.link.label
                        }
                    },
                    yaxis: {
                        title: {
                            text: analyzed_props[1].prop.link.label
                        }
                    }
                } as Plotly.Layout
                let buckets = bucketizeData(analyzed_props)
                let x_buckets = buckets[analyzed_props[0].query_id]
                let y_buckets = buckets[analyzed_props[1].query_id]
                let heatmap_trace = {} as Plotly.HeatmapData
                heatmap_trace.x = x_buckets.map((bucket) => bucket.display())
                heatmap_trace.y = y_buckets.map((bucket) => bucket.display())
                let heatmap_data = new Array(heatmap_trace.y.length).fill(0).map(() => new Array(heatmap_trace.x.length).fill(0))
                heatmap_trace.type = 'heatmap'
                for (let row of result_set) {
                    let bucket_assocs = Object.entries(buckets).map((bucket_prop) => {
                        let value = row[bucket_prop[0]]
                        let buckets = bucket_prop[1]
                        if (buckets[0].prop.prop_specific_type == PropSpecificType.DATE)
                            value = new Date(value).getTime()
                        let value_bucket = null as number | null
                        switch (buckets[0].prop.prop_type) {
                            case PropType.CONTINOUS:
                                value_bucket = buckets.findIndex((bucket) => bucket.lower <= value && bucket.upper > value)
                                break
                            case PropType.DISCRETE:
                                value_bucket = buckets.findIndex((bucket) => bucket.lower === value)
                                break
                        }
                        return value_bucket
                    })
                    // console.log(bucket_assocs) 
                    if (bucket_assocs[0] !== null && bucket_assocs[1] !== null
                        && bucket_assocs[0] >= 0 && bucket_assocs[1] >= 0) {
                        heatmap_data[bucket_assocs[1]][bucket_assocs[0]] += 1
                    }
                }
                heatmap_trace.z = heatmap_data
                trace = heatmap_trace
            }
            // console.log('Trace', trace)

            break
        }
        default:
        case 3:
            throw new Error('3D+ charts not supported yet')
            break
    }
    return {
        trace: trace,
        chart_mode: chart_mode,
        chart_options: chart_options
    }
}

export function combineTraces(caches: PlotCacheEntry[]) {
    let guiding_cache = caches[0]
    let combined_props: AnalyzedProp[] = guiding_cache.analyzed_props.map((prop) => {
        let prop_data = []
        for (let cache of caches) {
            let prop_data_cache = cache.analyzed_props.find((p) => p.query_id == prop.query_id)
            if (prop_data_cache) {
                prop_data = prop_data.concat(prop_data_cache.prop_data)
            }
        }
        return {
            ...prop,
            prop_data: prop_data
        }
    })
    console.log('Combined props', combined_props)
    let traces = [] as TraceData[]
    let chart_mode = caches[0].chart_mode
    let chart_options = caches[0].chart_options
    switch (guiding_cache.chart_mode) {
        case ChartMode.BAR:
            // bins over the data of all caches, so the previous and current counts line up
            let combined_buckets = bucketizeData(combined_props, null)
            for (let i = 0; i < caches.length; i++) {
                let cache = caches[i]
                let prop = combined_props[0]

                let trace = {} as Plotly.BarData
                trace.type = 'bar'
                trace.x = combined_buckets[prop.query_id].map((bucket) => bucket.display())
                trace.y = combined_buckets[prop.query_id].map((bucket) => {
                    return cache.results.filter((row) => bucket.inside(row[prop.query_id])).length
                })
                trace.name = cache.store.generateQuery()
                trace.marker = {
                    color: '#8fa88f',
                }
                traces.push(trace)
            }
            break;
        case ChartMode.SCATTER:
            traces = caches.map((cache) => {
                let trace = {} as Plotly.ScatterData
                trace.type = 'scatter'
                trace.mode = 'markers'
                trace.x = cache.analyzed_props[0].prop_data
                trace.y = cache.analyzed_props[1].prop_data
                trace.name = cache.store.generateQuery()
                trace.marker = {
                    color: '#8fa88f',
                }
                return trace
            })
            break
    }


    return {
        traces,
        chart_mode: chart_mode,
        chart_options: chart_options
    }

}
import { saveAs } from 'file-saver';

export function downloadDataAsCSV(entry: PlotCacheEntry, old?: PlotCacheEntry) {
    let combined_props = entry.analyzed_props
    let prop_labels = combined_props.map((prop) => prop.prop.link.label)
    if (old) {
        prop_labels = ["previous", ...prop_labels]
    }
    let csv = prop_labels.join(',') + '\n'
    const rowToString = (row: Record<string, any>, props: AnalyzedProp[]) => {
        let prop_data = props.map((prop) => {
            let value = row[prop.query_id]
            if (prop.prop_specific_type == PropSpecificType.DATE) {
                value = new Date(value).toLocaleDateString()
            } else if (prop.prop_specific_type == PropSpecificType.NUMBER) {
                value = parseFloat(value).toLocaleString()
            } else if (prop.prop_specific_type == PropSpecificType.STRING) {
                value = value.replace(/,/g, ';')
            }
            return value as string
        })
        return prop_data
    }
    for (let i = 0; i < entry.results.length; i++) {
        let row = entry.results[i]
        let row_strings = rowToString(row, combined_props)
        if (old) {
            row_strings = ["false", ...row_strings]
        }
        csv += row_strings.join(",") + '\n'
    }

    if (old) {
        for (let i = 0; i < old.results.length; i++) {
            let row = old.results[i]
            let row_strings = rowToString(row, combined_props)
            row_strings = ["true", ...row_strings]
            csv += row_strings.join(",") + '\n'
        }
    }
    let blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    let filename = `data_${new Date().toISOString()}.csv`
    saveAs(blob, filename)
}