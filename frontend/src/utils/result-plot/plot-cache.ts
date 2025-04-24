import type { NodeLinkRepository } from "../sparql/store";
import type { AnalyzedProp, ChartMode } from "./plot-types";

export class PlotCacheEntry {
    traces: Plotly.PlotData[]
    results: Record<string, any>[]
    chart_mode: ChartMode
    chart_options: Plotly.Layout
    store: NodeLinkRepository
    analyzed_props: AnalyzedProp[]
}
export class PlotCache {
    private cache: Map<string, PlotCacheEntry> = new Map();

    constructor() {
        this.cache = new Map();
    }

    get(query: string) {
        return this.cache.get(query);
    }
    getByStore(store: NodeLinkRepository) {
        let query = store.generateQuery()
        return this.cache.get(query);
    }
    has(query: string): boolean {
        return this.cache.has(query);
    }
    set(query: string, value: PlotCacheEntry): void {
        this.cache.set(query, value);
    }
    setByStore(store: NodeLinkRepository, value: PlotCacheEntry): void {
        let query = store.generateQuery()
        this.cache.set(query, value);
    }

    clear(): void {
        this.cache.clear();
    }
}