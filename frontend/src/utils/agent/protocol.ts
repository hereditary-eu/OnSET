// Message protocol of the agent chat WebSocket (`/{config_id}/agent/ws`).
// Hand-written mirror of backend/src/agent/protocol.py (WebSockets are not part of
// the OpenAPI schema, so src/api/client.ts/Api.ts does not contain these types);
// the protocol is documented there.
import type { Subject, SubjectLink } from '@/api/client.ts/Api'
import type { GraphLink, GraphSubject, GraphSubQuery } from '@/utils/sparql/querygraph'

// --- graph payloads (backend assistant/assistant_model.py) ---
// QueryGraph is part of the OpenAPI schema, so these are the generated types with the
// ids the editor always assigns (see utils/sparql/querygraph.ts).

/** A subquery of a subject, see AnyAssistantSubQuery. */
export type AgentSubQuery = GraphSubQuery
export type AgentSubject = Omit<GraphSubject, 'subqueries'> & { subqueries?: GraphSubQuery[] }
export type AgentLink = GraphLink

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

/** A subquery added to/removed from a subject (by its id). */
export interface SubQueryChange {
    operation: 'add' | 'remove'
    subject_id: string
    subquery: AgentSubQuery
}

export interface GraphChange {
    added: AgentQueryGraph
    removed: AgentQueryGraph
    /** unchanged subjects the changed links (and subqueries) attach to */
    context: AgentSubject[]
    /** subquery changes of existing subjects (the agent's constraint tools, progressive constraints) */
    subqueries?: SubQueryChange[]
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
