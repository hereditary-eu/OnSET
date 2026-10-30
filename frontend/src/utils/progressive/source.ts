// Where the progressive panel gets its (modification, count) records from.
//
// `progressiveSource` is the backend endpoint (POST /{config_id}/progressive/sample).
// The mock source below invents candidate links and counts locally, for an offline demo:
// build/serve with ONSET_PROGRESSIVE_MOCK=1, or pass `mockProgressiveSource` as the
// `source` option of useProgressive.
import axios from 'axios'
import { OperationType, type ProgressiveResult as ApiProgressiveResult } from '@/api/client.ts/Api'
import type { AgentLink, AgentSubject, GraphDetails } from '@/utils/agent/protocol'
import { api } from '@/utils/api'
import type { ProgressiveModification, ProgressiveRequest, ProgressiveResult } from './types'

export interface ProgressiveSource {
    /** short name shown in the panel header, e.g. "mock data" ('' for the backend) */
    readonly label: string
    /** count the request graph and a sample of its modifications; rejects with an AbortError when aborted */
    fetch(request: ProgressiveRequest, signal: AbortSignal): Promise<ProgressiveResult>
}

// --- backend source ----------------------------------------------------------------

/** The response with the defaults of the backend model filled in. */
export function normalizeResult(result: ApiProgressiveResult): ProgressiveResult {
    return {
        ...result,
        modifications: (result.modifications ?? []).map((m) => ({
            ...m,
            operations: m.operations ?? [],
            details: m.details ? { subjects: m.details.subjects ?? {}, links: m.details.links ?? {} } : null,
        })),
    }
}

/** POST /progressive/sample of the active configuration. */
export const apiProgressiveSource: ProgressiveSource = {
    label: '',
    async fetch(request, signal) {
        try {
            const response = await api.progressive.sampleModificationsProgressiveSamplePost(request, { signal })
            return normalizeResult(response.data)
        } catch (e) {
            if (axios.isCancel(e) || signal.aborted) {
                throw new DOMException('Aborted', 'AbortError')
            }
            // the backend's message (e.g. an invalid count_subject) instead of the status text
            const detail = axios.isAxiosError(e) ? e.response?.data?.detail : null
            throw typeof detail == 'string' ? new Error(detail) : e
        }
    },
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
                operations: [{ operation: OperationType.Add, data: subject }],
                count: logCount(3, 6),
                label: name,
                description: `Start from ${name}`,
                details: emptyDetails(),
            })
        }
        return { base_count: null, modifications, candidate_count: MOCK_ROOTS.length }
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
            operations: [
                { operation: OperationType.Add, data: to },
                { operation: OperationType.Add, data: link },
            ],
            count: rand() < 0.04 ? null : rand() < 0.08 ? 0 : Math.round(base_count * factor),
            label: `${from.label} → ${property_label} → ${range_label}`,
            details: emptyDetails(),
        })
    }
    return { base_count, modifications, candidate_count: candidates.length, count_subject: graph.subjects[0].id }
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
