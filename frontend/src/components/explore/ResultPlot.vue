<template>
    <div class="result_plot_wrapper">
        <h3 v-if="ui_data.message">{{ ui_data.message }}</h3>
        <div v-else-if="!ui_data.loading" class="result_plot_container">
            <VuePlotly :data="chart_data" :layout="chart_options" :config="{
                displayModeBar: false,
            }"></VuePlotly>
        </div>
        <Loading v-if="ui_data.loading"></Loading>
    </div>
</template>
<script setup lang="ts">
import { ref, onMounted, defineProps, watch, computed, reactive } from 'vue'
import { Bar } from 'vue-chartjs'
import type { NodeLinkRepository } from '@/utils/sparql/store';
import { Api } from '@/api/client.ts/Api';
import { BACKEND_URL } from '@/utils/config';
import { QueryProp, SubQueryType } from '@/utils/sparql/representation';
import Loading from '../ui/Loading.vue';
import type * as  Plotly from 'plotly.js';
import { VuePlotly } from '@clalarco/vue3-plotly';
enum PropType {
    CONTINOUS = 'continous',
    DISCRETE = 'discrete'
}
enum PropSpecificType {
    DATE = 'date',
    NUMBER = 'linear',
    STRING = 'category'
}
enum ChartMode {
    BAR = 'bar',
    SCATTER = 'scatter',
    HEATMAP = 'heatmap'
}
class BucketSpecifier {
    constructor(public lower: number | string,
        public upper: number | string,
        public count: number,
        public prop: AnalyzedProp) { }
    id() {
        return `${this.prop.query_id}~${this.lower}-${this.upper}`
    }
    display() {
        if (this.lower == this.upper) {
            return `${this.lower}`
        }
        if (this.prop.prop_specific_type == PropSpecificType.DATE) {
            return `${new Date(this.lower).toLocaleDateString()} - ${new Date(this.upper).toLocaleDateString()}`
        }
        return `${this.lower} - ${this.upper} `
    }
}
interface AnalyzedProp {
    prop: QueryProp,
    prop_data: any[],
    prop_type: PropType,
    prop_specific_type: PropSpecificType,
    query_id: string
}
const api = new Api(
    {
        baseURL: BACKEND_URL
    }
)

const { store, query_string } = defineProps({
    store: {
        type: Object as () => NodeLinkRepository,
        required: true
    },
    query_string: {
        type: String,
        required: true
    }
})
const chart_mode = ref(ChartMode.BAR)
const result_set = ref([] as Record<string, any>[])
const chart_data = ref([] as Plotly.Data[])
const chart_options = ref({
    bargap: 0.05,
    bargroupgap: 0.2,
    title: {
        text: ""
    },
    xaxis: {
        title: {
            text: "Value"
        }
    },
    yaxis: {
        title: {
            text: "Count"
        }
    },
    dragmode: false,
    hovermode: 'closest'
} as Plotly.Layout)
const ui_data = reactive({
    chart_mode: ChartMode.BAR,
    loading: false,
    message: null as string | null,
    buckets: 20
})
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
const aggregateData = (props: AnalyzedProp[]) => {
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
                let min = Math.min(...continous_data)
                let max = Math.max(...continous_data)
                let step = (max - min) / ui_data.buckets
                for (let i = 0; i < ui_data.buckets; i++) {
                    let lower = min + i * step
                    let upper = min + (i + 1) * step

                    bucket_prop.push(new BucketSpecifier(lower, upper, continous_data.filter((val) => val >= lower && val < upper).length, prop))
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
                bucket_prop.push(...sorted_keys.splice(0, ui_data.buckets).map((key) => {
                    return new BucketSpecifier(key, key, value_counts[key], prop)
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
const loadData = async () => {
    ui_data.loading = true

    let query_limitless = store.generateQuery(null, null);
    let data = await api.sparql.sparqlQuerySparqlPost({
        query: query_limitless
    })
    result_set.value = data.data
    let props_of_interest = store.nodes
        .map((node) => node.subqueries
            .filter((subquery) => subquery.constraint_type == SubQueryType.QUERY_PROP))
        .flat() as QueryProp[]
    let analyzed_props = props_of_interest.map((prop) => {
        const query_id = prop.link.outputId().replace('?', '')
        let prop_data = result_set.value.map((row) => row[query_id])
        let prop_type = PropType.DISCRETE
        let prop_specific_type = PropSpecificType.STRING
        if (prop_data.length > 0) {
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
    })
    console.log('Analyzed props', analyzed_props, result_set.value)
    let continous_props = analyzed_props.filter((prop) => prop.prop_type == PropType.CONTINOUS)
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
     *  
     */

    ui_data.message = null
    switch (analyzed_props.length) {
        case 0:
            ui_data.message = 'No properties to display'
            break
        case 1:
            ui_data.chart_mode = ChartMode.BAR
            let trace = {} as Plotly.PlotData
            trace.type = 'bar'

            let prop = analyzed_props[0]


            chart_options.value = {
                title: {
                    text: prop.prop.link.label
                },
                xaxis: {

                    title: {
                        text: prop.prop.link.label
                    }
                },
                yaxis: {
                    title: {
                        text: "Count"
                    }
                }
            } as Plotly.Layout
            let buckets = aggregateData(analyzed_props)
            trace.x = buckets[prop.query_id].map((bucket) => bucket.display())
            trace.y = buckets[prop.query_id].map((bucket) => bucket.count)
            chart_data.value = [trace]
            break
        case 2: {
            ui_data.chart_mode = ChartMode.SCATTER
            let trace = {} as Plotly.PlotData
            if (continous_props.length == 2 && continous_props[0].prop_data.length < 128) {
                //TODO: Add background distribution/switch to heatmap beyond 1000 points
                chart_options.value = {
                    title: {
                        text: `${continous_props[0].prop.link.label} vs ${continous_props[1].prop.link.label}`
                    },
                    xaxis: {
                        title: {
                            text: continous_props[0].prop.link.label
                        }
                    },
                    yaxis: {
                        title: {
                            text: continous_props[1].prop.link.label
                        }
                    }
                } as Plotly.Layout
                trace.type = 'scatter'
                trace.mode = 'markers'
                trace.x = continous_props[0].prop_data
                trace.y = continous_props[1].prop_data
                trace.marker = {
                    color: '#8fa88f',
                }
            } else {

                ui_data.chart_mode = ChartMode.HEATMAP
                chart_options.value = {
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
                let buckets = aggregateData(analyzed_props)
                let x_buckets = buckets[analyzed_props[0].query_id]
                let y_buckets = buckets[analyzed_props[1].query_id]
                trace.x = x_buckets.map((bucket) => bucket.display())
                trace.y = y_buckets.map((bucket) => bucket.display())
                let heatmap_data = new Array(trace.x.length).fill(0).map(() => new Array(trace.y.length).fill(0))
                trace.type = 'heatmap'
                for (let row of result_set.value) {
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
                        heatmap_data[bucket_assocs[0]][bucket_assocs[1]] += 1
                    }
                }
                trace.z = heatmap_data
            }
            console.log('Trace', trace)
            chart_data.value = [trace]
            break
        }
        default:
        case 3:
            ui_data.message = 'Too many properties to display'
            break
    }
    ui_data.loading = false
}
onMounted(() => {
    loadData().catch((e) => {
        console.error(e)

        ui_data.loading = false
    })
})
watch(() => query_string, () => {
    loadData().catch((e) => {
        console.error(e)

        ui_data.loading = false
    })
})

</script>
<style lang="scss" scoped>
.result_plot_wrapper {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    width: 100%;
}

.result_plot_container {
    width: 100%;
    height: 100%;
}
</style>