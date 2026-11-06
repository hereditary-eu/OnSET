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
export interface BuildStatus { running: boolean, processed: number, total: number, triples: number, errors: number, last_error: string | null, store: string }
export interface SessionState { session_id: string, version: number, ontology: Ontology, query: string, visual_query: string | null, status: BuildStatus }
export interface Cell { value: string, kind: 'uri' | 'literal' | 'bnode', label: string | null }
export interface QueryResult { columns: string[], rows: (Cell | null)[][], error: string | null, status: BuildStatus }

export const BUILDER_URL = `${BACKEND_URL}/onto-builder`

const get = <T>(path: string, params?: object) => axios.get<T>(`${BUILDER_URL}${path}`, { params }).then((r) => r.data)

export const listBuilders = () => get<BuilderSummary[]>('/configs')
export const searchText = (bid: string, q: string, k = 20) => get<Snippet[]>(`/${bid}/search`, { q, k })
// doc ids may contain slashes (e.g. Enron paths): encode each segment
export const getDocument = (bid: string, doc_id: string) =>
    get<BuilderDocument>(`/${bid}/documents/${doc_id.split('/').map(encodeURIComponent).join('/')}`)

/** Calls of one builder session (created by the backend on first access). */
export function builderSession(bid: string, sid: string) {
    const base = `/${encodeURIComponent(bid)}/sessions/${encodeURIComponent(sid)}`
    const put = (path: string, body: unknown) => axios.put<SessionState>(`${BUILDER_URL}${base}${path}`, body).then((r) => r.data)
    const post = <T>(path: string, params?: object, body?: unknown) =>
        axios.post<T>(`${BUILDER_URL}${base}${path}`, body, { params }).then((r) => r.data)
    return {
        state: () => get<SessionState>(base),
        setOntology: (ontology: Ontology) => put('/ontology', ontology),
        /** ``visual_query``: the serialized visual query (NodeLinkRepository) that generated ``query`` */
        setQuery: (query: string, visual_query: string | null = null) => put('/query', { query, visual_query }),
        classQuery: (class_id: string) => get<{ query: string }>(`${base}/class-query/${encodeURIComponent(class_id)}`),
        results: (limit = 500) => get<QueryResult>(`${base}/results`, { limit }),
        rebuild: () => post<SessionState>('/rebuild'),
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
