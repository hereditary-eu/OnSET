// Client of the ontology builder API (`${BACKEND_URL}/onto-builder`, backend api/router/builder.py).
// Hand-typed: these routes are on the main app, not in the generated per-config client.
import axios from 'axios'
import { BACKEND_URL } from '@/utils/config'

export const FIELD_TYPES = ['string', 'integer', 'float', 'date', 'boolean', 'vector'] as const
export type FieldType = typeof FIELD_TYPES[number]
export type ExportContent = 'all' | 'ontology' | 'kg'

export interface BuilderSummary { id: string, name: string, description: string, prefix: string }
export interface Snippet { doc_id: string, title: string, text: string, score: number }
export interface BuilderDocument { id: string, title: string, text: string }
export interface OntoField { name: string, type: FieldType, description: string }
export interface OntoClass { id: string, label: string, description: string, fields: OntoField[], x: number | null, y: number | null }
export interface OntoLink { id: string, label: string, source: string, target: string, description: string }
export interface Ontology { prefix: string, classes: OntoClass[], links: OntoLink[] }
/** ``merged``: extracted names merged into an instance with another name (disambiguation) */
export interface BuildStatus { running: boolean, processed: number, total: number, triples: number, errors: number, last_error: string | null, store: string, merged: number }
/** How extracted names are merged into one instance per class (backend builder/disambiguate.py); each mode adds a step to the previous ones. */
export const DISAMBIGUATION_MODES = ['off', 'normalized', 'levenshtein', 'llm_judge'] as const
export type DisambiguationMode = typeof DISAMBIGUATION_MODES[number]
export interface DisambiguationSettings {
    mode: DisambiguationMode
    /** at most this many edits, and at most ``max_ratio`` of the longer name */
    max_distance: number
    max_ratio: number
    /** TF-IDF cosine a name needs to be put to the judge, and how many of the closest are */
    judge_min_similarity: number
    judge_candidates: number
    /** the judge's P(yes) a merge needs */
    judge_threshold: number
}
export interface Merge { class_id: string, alias: string, canonical: string, iri: string, method: 'normalized' | 'levenshtein' | 'llm_judge' }
/** ``merges``: the latest merges of the current build, newest first */
export interface DisambiguationState { settings: DisambiguationSettings, merged: number, judged: number, merges: Merge[] }
export interface SessionState { session_id: string, version: number, ontology: Ontology, query: string, visual_query: string | null, status: BuildStatus, disambiguation: DisambiguationSettings }
/** Triples of an ontology link (``to_id`` null: of a field) in the KG, ids prefixed (``onto:Person``). */
export interface LinkCount { from_id: string, property_id: string, to_id: string | null, count: number }
export interface LinkCounts { triples: number, links: LinkCount[] }
export interface Cell { value: string, kind: 'uri' | 'literal' | 'bnode', label: string | null }
export interface QueryResult { columns: string[], rows: (Cell | null)[][], error: string | null, status: BuildStatus }

export const BUILDER_URL = `${BACKEND_URL}/onto-builder`

const get = <T>(path: string, params?: object) => axios.get<T>(`${BUILDER_URL}${path}`, { params }).then((r) => r.data)

export const listBuilders = () => get<BuilderSummary[]>('/configs')
export const searchText = (bid: string, q: string, k = 20) => get<Snippet[]>(`/${bid}/search`, { q, k })
// doc ids may contain slashes (e.g. Enron paths): encode each segment
export const getDocument = (bid: string, doc_id: string) =>
    get<BuilderDocument>(`/${bid}/documents/${doc_id.split('/').map(encodeURIComponent).join('/')}`)

/** Calls of one builder session (created by the backend on first access, restored from its save after a restart). */
export function builderSession(bid: string, sid: string) {
    const base = `/${encodeURIComponent(bid)}/sessions/${encodeURIComponent(sid)}`
    const put = (path: string, body: unknown) => axios.put<SessionState>(`${BUILDER_URL}${base}${path}`, body).then((r) => r.data)
    const post = <T>(path: string, params?: object, body?: unknown) =>
        axios.post<T>(`${BUILDER_URL}${base}${path}`, body, { params }).then((r) => r.data)
    return {
        /** ``create: false``: fails with 404 instead of creating an unknown session */
        state: (create = true) => get<SessionState>(base, create ? undefined : { create }),
        setOntology: (ontology: Ontology) => put('/ontology', ontology),
        /** ``visual_query``: the serialized visual query (NodeLinkRepository) that generated ``query`` */
        setQuery: (query: string, visual_query: string | null = null) => put('/query', { query, visual_query }),
        classQuery: (class_id: string) => get<{ query: string }>(`${base}/class-query/${encodeURIComponent(class_id)}`),
        results: (limit = 500) => get<QueryResult>(`${base}/results`, { limit }),
        /** cached on the server until the KG changes: refetch when ``status.triples`` changes */
        linkCounts: () => get<LinkCounts>(`${base}/link-counts`),
        rebuild: () => post<SessionState>('/rebuild'),
        disambiguation: () => get<DisambiguationState>(`${base}/disambiguation`),
        /** a change rebuilds the KG from scratch */
        setDisambiguation: (settings: DisambiguationSettings) =>
            axios.put<DisambiguationState>(`${BUILDER_URL}${base}/disambiguation`, settings).then((r) => r.data),
        save: (content: ExportContent, prefix: string) => post<{ path: string }>('/save', { content, prefix }),
        import: (file: File, prefix?: string) => {
            const form = new FormData()
            form.append('file', file)
            return post<SessionState>('/import', prefix ? { prefix } : undefined, form)
        },
        exportUrl: (content: ExportContent, prefix: string) =>
            `${BUILDER_URL}${base}/export?${new URLSearchParams({ content, prefix })}`,
        wsUrl: () => {
            const url = new URL(`${BUILDER_URL}/${encodeURIComponent(bid)}/agent/ws`, window.location.href)
            url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
            return url
        },
    }
}
export type BuilderSessionApi = ReturnType<typeof builderSession>

/** Session ids the backend accepts (they name its save files). */
export const SESSION_ID_PATTERN = /^[A-Za-z0-9_-]{1,64}$/

/** An IRI-safe camel-case id from what the user typed, e.g. "birth date" -> "birthDate" (upper: "BirthDate"). */
export function toId(text: string, upper = false): string {
    const words = text.split(/[^A-Za-z0-9]+/).filter((w) => w)
    let id = words.map((w, i) => i == 0 && !upper ? w[0].toLowerCase() + w.slice(1) : w[0].toUpperCase() + w.slice(1)).join('')
    if (/^[0-9]/.test(id)) {
        id = (upper ? 'C' : 'p') + id
    }
    return id
}

/** `id`, or `id2`, `id3`, ... if it is taken. */
export function uniqueId(id: string, taken: string[]): string {
    let candidate = id
    for (let i = 2; taken.includes(candidate); i++) {
        candidate = `${id}${i}`
    }
    return candidate
}

/** Readable cell text: its label, or the local name of an IRI, or the value. */
export function cellText(cell: Cell | null, raw: boolean): string {
    if (!cell) {
        return ''
    }
    if (raw) {
        return cell.value
    }
    return cell.label ?? (cell.kind == 'uri' ? cell.value.split(/[/#]/).pop() || cell.value : cell.value)
}
