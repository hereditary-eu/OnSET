import { Vector2, type Vector2Like } from "three"
import { NodeLinkRepositoryDiff } from "./diff"
import { NodeLinkRepository, RepositoryState } from "./store"
import { scalingFactors } from "./querymapper"
import { jsonClone, registerClass } from "../parsing"
import { Api } from "@/api/client.ts/Api"
import { BACKEND_URL } from "../config"
@registerClass
export class HistoryEntry {
    query: NodeLinkRepository
    previous_diff: NodeLinkRepositoryDiff | null
    timestamp: number

    text_representation: string
    embedding: number[] | null

    offset: Vector2Like = { x: 0, y: 0 }
    scale: number = 1.0
    size: Vector2Like = { x: 0, y: 0 }

    constructor(
        query?: NodeLinkRepository,
        previous_diff?: NodeLinkRepositoryDiff | null,
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

        this.embedding = null
        this.fillEmbedding()
    }
    private fillEmbedding() {
        if (this.embedding === null) {
            (async () => {
                this.text_representation = this.query.queryReadable()
                let api = new Api({
                    baseURL: BACKEND_URL,
                })
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
export class QueryHistory {
    private history: Record<number, HistoryEntry> = {};
    get length(): number { return Object.keys(this.history).length }
    get reverse_entries(): HistoryEntry[] { return Object.values(this.history).reverse() }
    get entries(): HistoryEntry[] { return Object.values(this.history) }
    tryAddEntry(
        query: NodeLinkRepository): NodeLinkRepositoryDiff | null {
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
            let new_entry = new HistoryEntry(query, diff)
            this.history[new_entry.timestamp] = new_entry
        }
        return add ? diff : null
    }
    async dimReduceEmbeddings(n_out: number = 2, alg: "TSNE" | "MDS" = "TSNE") {
        let api = new Api({
            baseURL: BACKEND_URL,
        })
        let embeddings: number[][] = []
        let entries = this.entries
        for (let entry of entries) {
            if (entry.embedding !== null) {
                embeddings.push(entry.embedding)
            }
        }
        const response = await api.nlp.nlpEmbeddingsManifoldNlpEmbeddingsManifoldPost({
            embeddings: embeddings,
            n_out: n_out,
            alg: alg,
        })
        return response.data.map((v, i) => {
            return { v: new Vector2(v[0], v[1]), entry: entries[i] }
        })
    }
}
