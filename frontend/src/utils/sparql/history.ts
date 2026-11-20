import { type Vector2Like } from "three"
import { NodeLinkRepositoryDiff } from "./diff"
import { NodeLinkRepository, RepositoryState } from "./store"
import { scalingFactors } from "./querymapper"
import { jsonClone, parseJSON, ReconstructableClass, registerClass, stringifyJSON } from "../parsing"
import type { StoredHistoryEntry } from "../historySync"
import { ManifoldAlg } from "@/api/client.ts/Api"
import { api } from "@/utils/api"
import { userProvenance, type EditProvenance } from "./provenance"
import { dimReduceEntries, type TimelineChange, type TimelineHistory } from "./timeline"



@registerClass
export class HistoryEntry implements ReconstructableClass {
    query: NodeLinkRepository
    previous_diff: NodeLinkRepositoryDiff | null
    timestamp: number

    text_representation: string
    embedding: number[] | null
    /** who made the change (user, agent with its ops, ...); entries saved before it existed are the user's */
    provenance: EditProvenance


    offset: Vector2Like = { x: 0, y: 0 }
    scale: number = 1.0
    size: Vector2Like = { x: 0, y: 0 }

    constructor(
        query?: NodeLinkRepository,
        previous_diff?: NodeLinkRepositoryDiff | null,
        provenance?: EditProvenance | null,
    ) {
        if (!query) {
            this.query = new NodeLinkRepository()
        }
        if (!previous_diff) {
            this.previous_diff = null
        }
        this.query = jsonClone(query)
        this.previous_diff = jsonClone(previous_diff)
        this.timestamp = Date.now()
        this.provenance = provenance ? jsonClone(provenance) : userProvenance()

        this.embedding = null
        this.fillEmbedding()
    }
    postConstruct(): void {
        if (!this.provenance) {
            this.provenance = userProvenance()
        }
    }
    private fillEmbedding() {
        if (this.embedding === null) {
            console.log("Generating embedding for history entry:", this);
            (async () => {
                if(!this.query){
                    return
                }
                this.text_representation = this.query.queryReadable()
                const response = await api.nlp.nlpEmbeddingsNlpEmbeddingsGet({
                    query: this.text_representation,
                })
                this.embedding = response.data.embedding
            })().catch((e) => {
                console.error("Error generating embedding for history entry:", e)
            })
        }
    }
    rescale(target_size: Vector2Like,) {
        let { offset, scale, size } = scalingFactors(this.previous_diff || this.query, target_size)
        if (isNaN(scale)) {
            scale = 1.0
            offset = { x: 0, y: 0 }
            size = { x: 0, y: 0 }
        }
        this.offset = offset
        this.scale = scale
        this.size = size
    }
}
@registerClass
export class QueryHistory implements ReconstructableClass, TimelineHistory<HistoryEntry> {
    private history: Record<number, HistoryEntry> = {};
    get length(): number { return Object.keys(this.history).length }
    get reverse_entries(): HistoryEntry[] { return Object.values(this.history).reverse() }
    get entries(): HistoryEntry[] { return Object.values(this.history) }
    /** Adds the query as an entry if it differs from the last one; `provenance` tags who changed it. */
    tryAddEntry(
        query: NodeLinkRepository, provenance?: EditProvenance | null): NodeLinkRepositoryDiff | null {
        let diff: NodeLinkRepositoryDiff | null = null
        let add = false
        if (query.state === RepositoryState.EDITING) {
            // do not add entries while editing
            return null
        }
        if (Object.keys(this.history).length === 0) {
            add = true
        } else {
            let last_key = Object.keys(this.history)[Object.keys(this.history).length - 1]
            let last = this.history[last_key]
            diff = new NodeLinkRepositoryDiff(last.query, query)
            console.log("diff", diff)
            if (diff.diff_links.added.length > 0 ||
                diff.diff_links.removed.length > 0 ||
                diff.diff_links.changed.length > 0) {
                add = true
            }
            if (diff.diff_nodes.added.length > 0 ||
                diff.diff_nodes.removed.length > 0 ||
                diff.diff_nodes.changed.length > 0) {
                add = true
            }
        }
        if (add) {
            let new_entry = new HistoryEntry(query, diff, provenance)
            this.history[new_entry.timestamp] = new_entry
        }
        return add ? diff : null
    }
    async dimReduceEmbeddings(n_out: number = 2, alg: ManifoldAlg = ManifoldAlg.TSNE) {
        return dimReduceEntries(this.entries, n_out, alg)
    }
    entrySize(entry: HistoryEntry): number {
        return entry.query?.nodes?.length ?? 0
    }
    entryChange(entry: HistoryEntry): TimelineChange | null {
        const diff = entry.previous_diff
        if (!diff) {
            return null
        }
        return {
            size: Object.keys(diff.change_set).length || 1,
            added: diff.diff_nodes.added.length > 0 || diff.diff_links.added.length > 0,
            changed: diff.diff_nodes.changed.length > 0 || diff.diff_links.changed.length > 0,
        }
    }
    async searchSimilarEntries(query: string, n_results: number = 5) {
        const response = await api.nlp.nlpEmbeddingsClosestNlpEmbeddingsClosestPost({
            query: query,
            n_closest: n_results,
            all_embeddings: this.entries.map(e => e.embedding || []),
            embedding: null,
        })
        return response.data.map(r => {
            return { entry: this.entries[r.index], distance: r.distance }
        })
    }
    postConstruct(): void {

    }
    /** The entries to save in the query session (utils/historySync.ts), each serialized on its own. */
    toStored(): StoredHistoryEntry<string>[] {
        return Object.entries(this.history).map(([timestamp, entry]) => ({
            timestamp: Number(timestamp), entry: stringifyJSON(entry),
        }))
    }
    static fromStored(stored: StoredHistoryEntry[]): QueryHistory {
        const history = new QueryHistory()
        for (const s of stored) {
            try {
                history.history[s.timestamp] = parseJSON<HistoryEntry>(s.entry as string)
            } catch (e) {
                console.warn('Ignoring a saved history entry', s.timestamp, e)
            }
        }
        return history
    }
}
