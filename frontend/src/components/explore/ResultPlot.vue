<template>
    <div class="result_plot_wrapper">
        <div v-if="!ui_data.loading" class="result_plot_container">
            <Bar v-if="ui_data.chart_mode == ChartMode.BAR" :data="chart_data as any" :options="chart_options as any" />
        </div>
        <Loading v-if="ui_data.loading"></Loading>
    </div>
</template>
<script setup lang="ts">
import { ref, onMounted, defineProps, watch, computed, reactive } from 'vue'
import { Bar } from 'vue-chartjs'
import { Chart as ChartJS, Title, Tooltip, Legend, BarElement, CategoryScale, LinearScale, TimeScale, type ChartData, type ChartOptions } from 'chart.js'
import type { NodeLinkRepository } from '@/utils/sparql/store';
import { Api } from '@/api/client.ts/Api';
import { BACKEND_URL } from '@/utils/config';
import { QueryProp, SubQueryType } from '@/utils/sparql/representation';
import type { Chart } from 'node_modules/chart.js/dist';
import Loading from '../ui/Loading.vue';
ChartJS.register(Title, Tooltip, Legend, BarElement, CategoryScale, LinearScale, TimeScale)
import 'chartjs-adapter-date-fns';
enum PropType {
    CONTINOUS = 'continous',
    DISCRETE = 'discrete'
}
enum PropSpecificType {
    DATE = 'linear',
    NUMBER = 'linear',
    STRING = 'category'
}
enum ChartMode {
    BAR = 'bar',
    SCATTER = 'scatter',
    HEATMAP = 'heatmap'
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
const chart_data = ref({
    labels: [],
    datasets: [
        {
            label: 'Count',
            data: [],
            backgroundColor: [],
            borderColor: [],
            borderWidth: 1
        }
    ]
} as ChartData)
const chart_options = ref({
    responsive: true,
    maintainAspectRatio: false,
    scales: {
        y: {
            beginAtZero: true
        },
        x: {
            beginAtZero: true
        }
    }
} as ChartOptions)
const ui_data = reactive({
    chart_mode: ChartMode.BAR,
    loading: false,
})
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

    let analyzed_props = props_of_interest.map((prop) => {
        const query_id = prop.link.outputId().replace('?', '')
        let prop_data = result_set.value.map((row) => row[query_id])
        let prop_type = PropType.DISCRETE
        let prop_specific_type = PropSpecificType.STRING
        if (prop_data.length > 0) {
            if (typeof prop_data[0] == 'number') {
                prop_type = PropType.CONTINOUS
                prop_specific_type = PropSpecificType.NUMBER
            }
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
        return {
            prop: prop,
            prop_data: prop_data,
            prop_type: prop_type,
            prop_specific_type,
            query_id
        }
    })
    console.log('Analyzed props', analyzed_props, result_set.value)
    switch (props_of_interest.length) {
        case 1:
            ui_data.chart_mode = ChartMode.BAR
            let prop = analyzed_props[0]
            let labels = []
            let data = []
            let backgroundColor = []
            let borderColor = []
            let buckets = 20
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
                        let step = (max - min) / buckets
                        for (let i = 0; i < buckets; i++) {
                            let lower = min + i * step
                            let upper = min + (i + 1) * step
                            
                            data.push(prop.prop_data.filter((val) => val >= lower && val < upper).length)
                            backgroundColor.push('rgba(255, 99, 132, 0.2)')
                            borderColor.push('rgba(255, 99, 132, 1)')
                        }
                        switch (prop.prop_specific_type) {
                            case PropSpecificType.DATE:
                                labels = data.map((val, idx) => {
                                    let lower = min + idx * step
                                    let upper = min + (idx + 1) * step
                                    return `${new Date(lower).toLocaleDateString()} - ${new Date(upper).toLocaleDateString()}`
                                })
                                break
                            default:
                                labels = data.map((val, idx) => {
                                    let lower = min + idx * step
                                    let upper = min + (idx + 1) * step
                                    return `${lower.toFixed(2)} - ${upper.toFixed(2)}`
                                })
                                break
                        }
                        break
                case PropType.DISCRETE:
                    let value_counts = prop.prop_data.reduce((acc, val) => {
                        if (val in acc) {
                            acc[val] += 1
                        } else {
                            acc[val] = 1
                        }
                        return acc
                    }, {} as Record<string, number>) as Record<string, number>
                    let sorted_counts = Object.entries(value_counts).sort((a, b) => b[1] - a[1])
                    labels = sorted_counts.slice(0, buckets).map((entry) => entry[0])
                    data = sorted_counts.slice(0, buckets).map((entry) => entry[1])
                    backgroundColor = Array.from({ length: labels.length }, () => 'rgba(255, 99, 132, 0.2)')
                    borderColor = Array.from({ length: labels.length }, () => 'rgba(255, 99, 132, 1)')
                    break
            }
            chart_options.value.scales.x = {
                title: {
                    display: true,
                    text: prop.prop.link.label
                },
                // type: prop.prop_specific_type == PropSpecificType.DATE ? 'time' : undefined
            }
            chart_data.value = {
                labels: labels,
                datasets: [
                    {
                        label: prop.prop.link.label,
                        data: data,
                        backgroundColor: backgroundColor,
                        borderColor: borderColor,
                        borderWidth: 1
                    }
                ]
            }
            break
        case 2:
            break
        default:
        case 3:
            alert('Not implemented yet')
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