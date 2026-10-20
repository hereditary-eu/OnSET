// Message protocol of the agent chat WebSocket (`/{config_id}/agent/ws`).
// Hand-written mirror of backend/src/agent/protocol.py (WebSockets are not part of
// the OpenAPI schema, so src/api/client.ts/Api.ts does not contain these types);
// the protocol is documented there.
import type { Subject, SubjectLink } from '@/api/client.ts/Api'

// --- graph payloads (backend assistant/assistant_model.py) ---

/** A subquery of a subject, see AnyAssistantSubQuery; only `type` and `property_id` are shared by all. */
export interface AgentSubQuery {
    type: string
    id?: string | null
    property_id?: string | null
    [key: string]: unknown
}

export interface AgentSubject {
    uri: string
    label: string
    id: string
    subqueries?: AgentSubQuery[]
}

export interface AgentLink {
    uri: string
    label: string
    id: string
    from_subject_id: string
    to_subject_id: string
    from_subject_label?: string | null
    from_subject_uri?: string | null
    to_subject_label?: string | null
    to_subject_uri?: string | null
}

/** The canonical query graph of the backend (QueryGraph). */
export interface AgentQueryGraph {
    subjects: AgentSubject[]
    links: AgentLink[]
}

/** Ontology data of agent-added elements, keyed by graph id. */
export interface GraphDetails {
    subjects: Record<string, Subject>
    links: Record<string, SubjectLink>
}

export interface GraphChange {
    added: AgentQueryGraph
    removed: AgentQueryGraph
    /** unchanged subjects the changed links attach to */
    context: AgentSubject[]
}

// --- client -> server ---

export type ClientMessage =
    | { type: 'user_message', content: string }
    | { type: 'graph_sync', graph: AgentQueryGraph }
    | { type: 'cancel' }
    | { type: 'clear' }

// --- server -> client ---

export interface SessionInfoMessage {
    type: 'session'
    session_id: string
    resumed: boolean
}

interface StreamedText {
    id: string
    delta: string
    content: string | null
    final: boolean
}

export interface ThinkingMessage extends StreamedText {
    type: 'thinking'
}

export interface AssistantTextMessage extends StreamedText {
    type: 'assistant_message'
}

export type ToolCallStatus = 'running' | 'success' | 'error'

export interface ToolCallMessage {
    type: 'tool_call'
    call_id: string
    name: string
    arguments: Record<string, unknown>
    status: ToolCallStatus
    result: unknown
    error: string | null
    changes: GraphChange | null
    details: GraphDetails | null
}

export interface GraphStateMessage {
    type: 'graph_state'
    graph: AgentQueryGraph
    details: GraphDetails
}

export interface ErrorMessage {
    type: 'error'
    message: string
    fatal: boolean
}

export type DoneReason = 'completed' | 'max_steps' | 'cancelled' | 'error' | 'cleared'

export interface DoneMessage {
    type: 'done'
    reason: DoneReason
}

export type ServerMessage =
    | SessionInfoMessage
    | ThinkingMessage
    | AssistantTextMessage
    | ToolCallMessage
    | GraphStateMessage
    | ErrorMessage
    | DoneMessage

export function emptyGraph(): AgentQueryGraph {
    return { subjects: [], links: [] }
}
