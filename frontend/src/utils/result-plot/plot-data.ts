import type { QueryProp } from "../sparql/representation"

export enum PropType {
    CONTINOUS = 'continous',
    DISCRETE = 'discrete'
}
export enum PropSpecificType {
    DATE = 'date',
    NUMBER = 'linear',
    STRING = 'category'
}
export enum ChartMode {
    BAR = 'bar',
    SCATTER = 'scatter',
    HEATMAP = 'heatmap'
}
export class BucketSpecifier {
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
export interface AnalyzedProp {
    prop: QueryProp,
    prop_data: any[],
    prop_type: PropType,
    prop_specific_type: PropSpecificType,
    query_id: string
}