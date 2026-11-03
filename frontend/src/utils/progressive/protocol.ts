// Message protocol of the progressive discovery WebSocket (`/{config_id}/progressive/ws`).
// Hand-written mirror of the "streaming protocol" models of
// backend/src/assistant/progressive.py (WebSockets are not part of the OpenAPI schema);
// the protocol is documented there. Modifications and summary fields are the generated
// REST types (ProgressiveModification, ProgressiveResult).
import type {
    ProgressiveModification as ApiProgressiveModification,
    ProgressiveRequest as ApiProgressiveRequest,
    ProgressiveResult as ApiProgressiveResult,
} from '@/api/client.ts/Api'

// --- client -> server ---

export interface ProgressiveSampleMessage {
    type: 'sample'
    request_id: string
    request: ApiProgressiveRequest
}

export interface ProgressiveCancelMessage {
    type: 'cancel'
}

export type ProgressiveClientMessage = ProgressiveSampleMessage | ProgressiveCancelMessage

// --- server -> client (every event carries the request_id of its sample message) ---

interface Event {
    request_id: string | null
}

export interface ProgressiveStartEvent extends Event {
    type: 'start'
    seed: number
    candidate_count: number
    count_limit: number
    count_subject?: string | null
    constraint_candidate_count?: number | null
    /** requested levels and query cap of the tree expansion */
    depth: number
    query_budget?: number | null
    /** null in a live run (a count event follows), set in a cached replay */
    base_count?: number | null
    /** first-level link/start modifications; uncounted (count null) in a live run */
    modifications: ApiProgressiveModification[]
    cached: boolean
}

export interface ProgressiveCountEvent extends Event {
    type: 'count'
    /** modification id, null for the base count */
    id: string | null
    /** null if the count failed or timed out */
    count: number | null
}

export interface ProgressiveModificationsEvent extends Event {
    type: 'modifications'
    depth: number
    parent_id: string | null
    /** uncounted modifications that became known (constraints, children of a parent) */
    modifications: ApiProgressiveModification[]
}

export interface ProgressiveLevelEvent extends Event {
    type: 'level'
    depth: number
    parent_ids: string[]
}

export type ProgressiveDoneEvent = Event & Omit<ApiProgressiveResult, 'modifications'> & {
    type: 'done'
    complete: boolean
    cached: boolean
}

export interface ProgressiveErrorEvent extends Event {
    type: 'error'
    message: string
}

export type ProgressiveServerEvent =
    | ProgressiveStartEvent
    | ProgressiveCountEvent
    | ProgressiveModificationsEvent
    | ProgressiveLevelEvent
    | ProgressiveDoneEvent
    | ProgressiveErrorEvent
