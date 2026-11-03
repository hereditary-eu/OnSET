// Where the progressive panel gets its (modification, count) records from.
//
// `progressiveSource` is the backend's streaming WebSocket (/{config_id}/progressive/ws,
// protocol.ts): the panel shows the modifications as placeholders (`pending`) as soon as
// they are known and fills in each count the moment it arrives.
// The mock source below invents candidate links and counts locally, for an offline demo:
// build/serve with ONSET_PROGRESSIVE_MOCK=1, or pass `mockProgressiveSource` as the
// `source` option of useProgressive.
import { OperationType, type ProgressiveModification as ApiProgressiveModification } from '@/api/client.ts/Api'
import type { AgentLink, AgentSubject, GraphDetails } from '@/utils/agent/protocol'
import { configWebSocketUrl, requireActiveConfig } from '@/utils/api'
import type { ProgressiveClientMessage, ProgressiveServerEvent } from './protocol'
import type { ProgressiveModification, ProgressiveRequest, ProgressiveResult } from './types'

export interface ProgressiveSource {
    /** short name shown in the panel header, e.g. "mock data" ('' for the backend) */
    readonly label: string
    /**
     * count the request graph and a sample of its modifications; `onUpdate` receives the
     * result so far whenever counts or modifications arrived (at most once per frame).
     * Resolves with the complete result, rejects with an AbortError when aborted.
     */
    fetch(request: ProgressiveRequest, signal: AbortSignal,
        onUpdate?: (partial: ProgressiveResult) => void): Promise<ProgressiveResult>
}

// --- backend source ----------------------------------------------------------------

const RECONNECT_MIN_MS = 500
const RECONNECT_MAX_MS = 15000

const abortError = () => new DOMException('Aborted', 'AbortError')

/** A modification with the defaults of the backend model filled in. */
export function normalizeModification(m: ApiProgressiveModification, pending = false): ProgressiveModification {
    return {
        ...m,
        kind: m.kind ?? 'link',
        operations: m.operations ?? [],
        details: m.details ? { subjects: m.details.subjects ?? {}, links: m.details.links ?? {} } : null,
        depth: m.depth ?? 1,
        parent_id: m.parent_id ?? null,
        step_operations: m.step_operations ?? null,
        pending,
    }
}

interface Run {
    request: ProgressiveRequest
    /** id of the last sample message of the run (a new one after a reconnect) */
    request_id: string | null
    result: ProgressiveResult | null
    by_id: Map<string, ProgressiveModification>
    frame: ReturnType<typeof setTimeout> | null
    onUpdate?: (partial: ProgressiveResult) => void
    resolve: (result: ProgressiveResult) => void
    reject: (error: unknown) => void
}

/** A snapshot of the result (new objects, so the panel's reactive state picks it up). */
function snapshot(result: ProgressiveResult): ProgressiveResult {
    return { ...result, expanded_ids: [...result.expanded_ids], modifications: result.modifications.map((m) => ({ ...m })) }
}

/**
 * One WebSocket of the active configuration, with at most one running request: a new
 * request (or an abort) cancels the running one on the server. The socket is opened on the
 * first request and re-opened with backoff when it closes during a request, which is then
 * sent again.
 */
class ProgressiveSocket {
    private socket: WebSocket | null = null
    private config_id: string | null = null
    private current: Run | null = null
    private reconnect_timer: ReturnType<typeof setTimeout> | null = null
    private reconnect_attempt = 0
    private counter = 0

    run(request: ProgressiveRequest, signal: AbortSignal,
        onUpdate?: (partial: ProgressiveResult) => void): Promise<ProgressiveResult> {
        return new Promise((resolve, reject) => {
            if (signal.aborted) {
                reject(abortError())
                return
            }
            this.current?.reject(abortError())
            const run: Run = {
                request, request_id: null, result: null, by_id: new Map(), frame: null, onUpdate, resolve, reject,
            }
            this.current = run
            signal.addEventListener('abort', () => {
                if (this.current === run) {
                    this.finish(run)
                    this.send({ type: 'cancel' })
                }
                reject(abortError())
            }, { once: true })
            this.connect(requireActiveConfig())
            this.sendSample(run)
        })
    }

    private connect(config_id: string) {
        if (config_id == this.config_id && this.socket) {
            return
        }
        if (config_id != this.config_id) {
            this.close()
            this.config_id = config_id
            this.reconnect_attempt = 0
        }
        if (!this.reconnect_timer) {
            this.open()
        }
    }

    private close() {
        if (this.reconnect_timer) {
            clearTimeout(this.reconnect_timer)
            this.reconnect_timer = null
        }
        const socket = this.socket
        this.socket = null
        if (socket) {
            socket.onclose = null
            socket.close()
        }
    }

    private open() {
        if (!this.config_id) {
            return
        }
        const socket = new WebSocket(configWebSocketUrl(this.config_id, '/progressive/ws'))
        this.socket = socket
        socket.onopen = () => {
            this.reconnect_attempt = 0
            // the request sent before the socket was open, or lost with the last socket
            if (this.current) {
                this.sendSample(this.current)
            }
        }
        socket.onmessage = (evt) => {
            try {
                this.handle(JSON.parse(evt.data) as ProgressiveServerEvent)
            } catch (e) {
                console.error('Invalid progressive message', evt.data, e)
            }
        }
        socket.onclose = () => {
            if (this.socket !== socket) {
                return
            }
            this.socket = null
            // re-request the running sampling; otherwise the next request re-opens
            if (this.current) {
                const delay = Math.min(RECONNECT_MAX_MS, RECONNECT_MIN_MS * 2 ** this.reconnect_attempt)
                this.reconnect_attempt++
                this.reconnect_timer = setTimeout(() => {
                    this.reconnect_timer = null
                    this.open()
                }, delay)
            }
        }
    }

    private send(message: ProgressiveClientMessage): boolean {
        if (!this.socket || this.socket.readyState != WebSocket.OPEN) {
            return false
        }
        this.socket.send(JSON.stringify(message))
        return true
    }

    private sendSample(run: Run) {
        const request_id = `p${++this.counter}`
        if (this.send({ type: 'sample', request_id, request: run.request })) {
            // a re-sent request starts over
            run.request_id = request_id
            run.result = null
            run.by_id.clear()
        }
    }

    private finish(run: Run) {
        if (run.frame) {
            clearTimeout(run.frame)
            run.frame = null
        }
        if (this.current === run) {
            this.current = null
        }
    }

    /** an update of the result so far, at most once per frame */
    private scheduleUpdate(run: Run) {
        if (run.frame || !run.onUpdate) {
            return
        }
        run.frame = setTimeout(() => {
            run.frame = null
            if (this.current === run && run.result) {
                run.onUpdate!(snapshot(run.result))
            }
        }, 16)
    }

    private handle(event: ProgressiveServerEvent) {
        const run = this.current
        if (!run || event.request_id == null || event.request_id != run.request_id) {
            if (event.type == 'error' && event.request_id == null) {
                console.warn('Progressive discovery:', event.message)
            }
            return
        }
        if (event.type == 'error') {
            this.finish(run)
            run.reject(new Error(event.message))
            return
        }
        if (event.type == 'start') {
            const modifications = event.modifications.map((m) =>
                normalizeModification(m, !event.cached && m.count == null))
            run.by_id = new Map(modifications.map((m) => [m.id, m]))
            run.result = {
                base_count: event.base_count ?? null,
                base_pending: !event.cached && event.count_subject != null && event.base_count == null,
                candidate_count: event.candidate_count,
                count_limit: event.count_limit,
                count_subject: event.count_subject ?? null,
                seed: event.seed,
                constraint_candidate_count: event.constraint_candidate_count ?? null,
                query_budget: event.query_budget ?? null,
                depth: 1,
                expanded_ids: [],
                modifications,
            }
            this.scheduleUpdate(run)
            return
        }
        const result = run.result
        if (!result) {
            return
        }
        switch (event.type) {
            case 'count':
                if (event.id == null) {
                    result.base_count = event.count
                    result.base_pending = false
                } else {
                    const modification = run.by_id.get(event.id)
                    if (modification) {
                        modification.count = event.count
                        modification.pending = false
                    }
                }
                break
            case 'modifications':
                for (const m of event.modifications) {
                    const modification = normalizeModification(m, true)
                    run.by_id.set(modification.id, modification)
                    result.modifications.push(modification)
                }
                if (event.parent_id != null && !result.expanded_ids.includes(event.parent_id)) {
                    result.expanded_ids.push(event.parent_id)
                }
                result.depth = Math.max(result.depth, event.depth)
                break
            case 'level':
                break
            case 'done': {
                const { type: _type, request_id: _id, complete: _complete, cached: _cached, ...summary } = event
                Object.assign(result, summary, {
                    depth: summary.depth ?? result.depth,
                    expanded_ids: summary.expanded_ids ?? result.expanded_ids,
                    base_pending: false,
                })
                for (const modification of result.modifications) {
                    modification.pending = false
                }
                this.finish(run)
                run.resolve(snapshot(result))
                return
            }
        }
        this.scheduleUpdate(run)
    }
}

const progressiveSocket = new ProgressiveSocket()

/** The streaming WebSocket of the active configuration. */
export const apiProgressiveSource: ProgressiveSource = {
    label: '',
    fetch: (request, signal, onUpdate) => progressiveSocket.run(request, signal, onUpdate),
}

// --- MOCK fixture source -----------------------------------------------------------

const DBO = 'http://dbpedia.org/ontology/'
// (property, range class) pairs the mock proposes as outgoing links of every subject
const MOCK_LINKS: [string, string, string, string][] = [
    ['birthPlace', 'birth place', 'Place', 'place'],
    ['country', 'country', 'Country', 'country'],
    ['location', 'location', 'Place', 'place'],
    ['author', 'author', 'Person', 'person'],
    ['director', 'director', 'Person', 'person'],
    ['genre', 'genre', 'Genre', 'genre'],
    ['homeport', 'homeport', 'Settlement', 'settlement'],
    ['builder', 'builder', 'Company', 'company'],
    ['team', 'team', 'SportsTeam', 'sports team'],
    ['spouse', 'spouse', 'Person', 'person'],
    ['language', 'language', 'Language', 'language'],
    ['recordLabel', 'record label', 'RecordLabel', 'record label'],
    ['starring', 'starring', 'Actor', 'actor'],
    ['influencedBy', 'influenced by', 'Person', 'person'],
    ['capital', 'capital', 'City', 'city'],
    ['operator', 'operator', 'Organisation', 'organisation'],
]
// start classes the mock proposes for an empty graph
const MOCK_ROOTS = ['Ship', 'Film', 'Person', 'City', 'Book', 'Band', 'Building', 'Company', 'River', 'Album',
    'Mountain', 'University']

/** Deterministic PRNG (mulberry32), seeded from the request, so re-runs are stable. */
function random(seed: number) {
    let a = seed >>> 0
    return () => {
        a = (a + 0x6d2b79f5) >>> 0
        let t = a
        t = Math.imul(t ^ (t >>> 15), t | 1)
        t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296
    }
}

function hash(text: string): number {
    let h = 2166136261
    for (let i = 0; i < text.length; i++) {
        h = Math.imul(h ^ text.charCodeAt(i), 16777619)
    }
    return h >>> 0
}

const n3 = (name: string) => `<${DBO}${name}>`
const emptyDetails = (): GraphDetails => ({ subjects: {}, links: {} })
// the mock samples the first level only (no tree expansion)
const FIRST_LEVEL = { depth: 1, parent_id: null, step_operations: null }

function mockModifications(request: ProgressiveRequest): ProgressiveResult {
    const { graph } = request
    const rand = random(request.seed ?? hash(JSON.stringify([graph.subjects.map((s) => s.uri), graph.links.map((l) => l.uri)])))
    // log-uniform count in [10^lo, 10^hi], sometimes 0 (an empty join)
    const logCount = (lo: number, hi: number) => rand() < 0.06 ? 0 : Math.round(10 ** (lo + rand() * (hi - lo)))
    const modifications: ProgressiveModification[] = []

    if (graph.subjects.length == 0) {
        for (const name of MOCK_ROOTS.slice(0, request.sample_size)) {
            const subject: AgentSubject = { id: `prog_${name}`, uri: n3(name), label: name, subqueries: [] }
            modifications.push({
                id: `root_${name}`,
                kind: 'start',
                operations: [{ operation: OperationType.Add, data: subject }],
                count: logCount(3, 6),
                label: name,
                description: `Start from ${name}`,
                details: emptyDetails(),
                ...FIRST_LEVEL,
            })
        }
        return { base_count: null, modifications, candidate_count: MOCK_ROOTS.length, depth: 1, expanded_ids: [] }
    }

    const base_count = logCount(3, 6) || 1000
    const subjects = request.subject_ids
        ? graph.subjects.filter((s) => request.subject_ids!.includes(s.id))
        : graph.subjects
    const candidates = subjects.flatMap((s) => MOCK_LINKS.map((link) => [s, link] as const))
    // sample without replacement
    for (let i = candidates.length - 1; i > 0; i--) {
        const j = Math.floor(rand() * (i + 1));
        [candidates[i], candidates[j]] = [candidates[j], candidates[i]]
    }
    for (const [from, [property, property_label, range, range_label]] of candidates.slice(0, request.sample_size)) {
        const id = `${from.id}_${property}`
        const to: AgentSubject = { id: `prog_${id}`, uri: n3(range), label: range_label, subqueries: [] }
        const link: AgentLink = {
            id: `prog_link_${id}`, uri: n3(property), label: property_label,
            from_subject_id: from.id, to_subject_id: to.id,
            from_subject_label: from.label, from_subject_uri: from.uri,
            to_subject_label: to.label, to_subject_uri: to.uri,
        }
        // an added (inner-joined) link mostly filters rows, multi-valued properties can multiply them
        const factor = 10 ** (-3.5 + rand() * 4)
        modifications.push({
            id,
            kind: 'link',
            operations: [
                { operation: OperationType.Add, data: to },
                { operation: OperationType.Add, data: link },
            ],
            count: rand() < 0.04 ? null : rand() < 0.08 ? 0 : Math.round(base_count * factor),
            label: `${from.label} → ${property_label} → ${range_label}`,
            details: emptyDetails(),
            ...FIRST_LEVEL,
        })
    }
    return {
        base_count, modifications, candidate_count: candidates.length, count_subject: graph.subjects[0].id,
        depth: 1, expanded_ids: [],
    }
}

/** MOCK: invents candidate links/counts locally, with a small delay like a count query. */
export const mockProgressiveSource: ProgressiveSource = {
    label: 'mock data',
    fetch(request, signal) {
        return new Promise((resolve, reject) => {
            const timer = setTimeout(() => resolve(mockModifications(request)), 350)
            signal.addEventListener('abort', () => {
                clearTimeout(timer)
                reject(new DOMException('Aborted', 'AbortError'))
            }, { once: true })
        })
    },
}

/** The source the panel uses: the backend, or the mock with ONSET_PROGRESSIVE_MOCK set. */
export const progressiveSource: ProgressiveSource = ['1', 'true'].includes(String(import.meta.env.ONSET_PROGRESSIVE_MOCK ?? ''))
    ? mockProgressiveSource
    : apiProgressiveSource
