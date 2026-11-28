// What the time embedding curve (TimeEmbeddingsOverlay) needs of a history: its entries with an
// embedding and a provenance, their size and their change from the previous entry. Implemented by
// the query history (history.ts) and the ontology builder's history (utils/builder/history.ts).
import { Vector2 } from 'three'
import { ManifoldAlg } from '@/api/client.ts/Api'
import { api } from '@/utils/api'
import type { EditProvenance } from './provenance'

export interface TimelineEntry {
    timestamp: number
    /** null while it is computed (it is not drawn then) */
    embedding: number[] | null
    provenance: EditProvenance
}

/** The change leading to an entry: colours and widens the curve segment ending at it. */
export interface TimelineChange {
    /** number of changed elements */
    size: number
    added: boolean
    changed: boolean
}

export interface TimelineHistory<E extends TimelineEntry = TimelineEntry> {
    readonly entries: E[]
    dimReduceEmbeddings(n_out?: number, alg?: ManifoldAlg): Promise<{ v: Vector2, entry: E }[]>
    /** number of elements of the entry's state (subjects, classes), for the point radius */
    entrySize(entry: E): number
    entryChange(entry: E): TimelineChange | null
}

/** A history the history panel (HistoryView) lists and searches. */
export interface SearchableHistory<E extends TimelineEntry = TimelineEntry> extends TimelineHistory<E> {
    /** newest first */
    readonly reverse_entries: E[]
    searchSimilarEntries(query: string, n_results?: number): Promise<{ entry: E }[]>
}

/**
 * 2D positions of the entries with an embedding (manifold of the backend, which needs no
 * configuration services); up to two entries are put on a line, the manifolds need more.
 */
export async function dimReduceEntries<E extends TimelineEntry>(
    entries: E[], n_out: number = 2, alg: ManifoldAlg = ManifoldAlg.TSNE,
): Promise<{ v: Vector2, entry: E }[]> {
    const embedded = entries.filter((e) => e.embedding !== null)
    if (embedded.length <= 2) {
        return embedded.map((entry, i) => ({ v: new Vector2(i, 0), entry }))
    }
    const response = await api.nlp.nlpEmbeddingsManifoldNlpEmbeddingsManifoldPost({
        embeddings: embedded.map((e) => e.embedding!),
        n_out: n_out,
        alg: alg,
    })
    return response.data.map((v, i) => ({ v: new Vector2(v[0], v[1]), entry: embedded[i] }))
}
