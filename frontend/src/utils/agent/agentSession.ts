// Client side of the agent chat: one WebSocket per browser session and configuration.
//
// - connects to `${BACKEND_URL}/${configId}/agent/ws` (re-connects with backoff when the
//   connection drops, and switches the socket when the configuration changes);
// - keeps the chat entries (user/assistant messages, thinking blocks, tool calls);
// - keeps the server's graph in sync with the editor: `graph_sync` whenever the editor
//   graph differs from what the server has (debounced) and before every user message;
// - applies `graph_state` from the agent to the editor through the bound GraphBinding,
//   as a diff against the graph the server had before.
//
// Echo loops are avoided by comparing graphKey()s: after a `graph_state` is applied the
// editor graph equals the server graph, so the editor's change does not sync back.
import { reactive, watch, onBeforeUnmount, type Ref } from 'vue'
import { configWebSocketUrl } from '@/utils/api'
import { diffAgentGraphs, graphKey, isEmptyChange } from './graph_sync'
import {
    emptyGraph,
    type AgentQueryGraph, type ClientMessage, type GraphChange, type GraphDetails,
    type ServerMessage, type ToolCallMessage,
} from './protocol'

export type ChatEntry =
    | { kind: 'user', id: string, content: string }
    | { kind: 'assistant', id: string, content: string, streaming: boolean }
    | { kind: 'thinking', id: string, content: string, streaming: boolean, expanded: boolean, toggled: boolean }
    | { kind: 'tool', id: string, call: ToolCallMessage }
    | { kind: 'notice', id: string, content: string, level: 'info' | 'error' }

export type ConnectionStatus = 'idle' | 'connecting' | 'open' | 'reconnecting'

/** How the session reads and changes the editor graph. */
export interface GraphBinding {
    /** current editor graph */
    read(): AgentQueryGraph
    /** apply the agent's change (diff against the previous server graph) to the editor */
    apply(change: GraphChange, graph: AgentQueryGraph, details: GraphDetails): void
}

const SYNC_DEBOUNCE_MS = 400
const RECONNECT_MIN_MS = 500
const RECONNECT_MAX_MS = 15000

let entry_counter = 0
const nextEntryId = (prefix: string) => `${prefix}_${++entry_counter}`

function newSessionId(): string {
    return globalThis.crypto?.randomUUID?.() ?? `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`
}

interface ConfigSession {
    session_id: string
    entries: ChatEntry[]
}

export class AgentSession {
    readonly state = reactive({
        config_id: null as string | null,
        session_id: null as string | null,
        status: 'idle' as ConnectionStatus,
        busy: false,
        entries: [] as ChatEntry[],
    })

    private socket: WebSocket | null = null
    private binding: GraphBinding | null = null
    // the graph the server has, as last synced or received
    private server_graph: AgentQueryGraph = emptyGraph()
    private server_key = graphKey(emptyGraph())
    private sync_timer: ReturnType<typeof setTimeout> | null = null
    private reconnect_timer: ReturnType<typeof setTimeout> | null = null
    private reconnect_attempt = 0
    private clearing = false
    // chats of other configurations, restored when switching back
    private config_sessions = new Map<string, ConfigSession>()

    get connected(): boolean {
        return this.state.status == 'open'
    }

    bind(binding: GraphBinding | null) {
        this.binding = binding
        if (binding) {
            this.scheduleSync()
        }
    }

    /** Connect to the chat of a configuration (no-op if already connected to it). */
    connect(config_id: string | null) {
        if (config_id == this.state.config_id && this.socket) {
            return
        }
        this.disconnect()
        if (this.state.config_id) {
            this.config_sessions.set(this.state.config_id, {
                session_id: this.state.session_id!, entries: this.state.entries,
            })
        }
        this.state.config_id = config_id
        if (!config_id) {
            return
        }
        const saved = this.config_sessions.get(config_id)
        this.state.session_id = saved?.session_id ?? newSessionId()
        this.state.entries = saved?.entries ?? []
        this.reconnect_attempt = 0
        this.open()
    }

    disconnect() {
        if (this.reconnect_timer) {
            clearTimeout(this.reconnect_timer)
            this.reconnect_timer = null
        }
        if (this.sync_timer) {
            clearTimeout(this.sync_timer)
            this.sync_timer = null
        }
        const socket = this.socket
        this.socket = null
        if (socket) {
            socket.onclose = null
            socket.close()
        }
        this.state.status = 'idle'
        this.state.busy = false
    }

    private open() {
        const config_id = this.state.config_id
        if (!config_id) {
            return
        }
        const url = configWebSocketUrl(config_id, '/agent/ws')
        url.searchParams.set('session_id', this.state.session_id!)
        this.state.status = this.reconnect_attempt > 0 ? 'reconnecting' : 'connecting'
        const socket = new WebSocket(url)
        this.socket = socket
        socket.onopen = () => {
            this.reconnect_attempt = 0
            this.state.status = 'open'
            // the server may have lost or never had the graph: always sync after connecting
            this.syncNow(true)
        }
        socket.onmessage = (evt) => {
            try {
                this.handle(JSON.parse(evt.data) as ServerMessage)
            } catch (e) {
                console.error('Invalid agent message', evt.data, e)
            }
        }
        socket.onclose = () => {
            if (this.socket !== socket) {
                return
            }
            this.socket = null
            if (this.state.busy) {
                this.state.busy = false
                this.notice('Connection lost while the agent was working.', 'error')
            }
            this.scheduleReconnect()
        }
    }

    private scheduleReconnect() {
        this.state.status = 'reconnecting'
        const delay = Math.min(RECONNECT_MAX_MS, RECONNECT_MIN_MS * 2 ** this.reconnect_attempt)
        this.reconnect_attempt++
        this.reconnect_timer = setTimeout(() => {
            this.reconnect_timer = null
            this.open()
        }, delay)
    }

    private sendRaw(message: ClientMessage): boolean {
        if (!this.socket || this.socket.readyState != WebSocket.OPEN) {
            return false
        }
        this.socket.send(JSON.stringify(message))
        return true
    }

    /** Sync the editor graph after it changed (debounced). */
    scheduleSync() {
        if (this.sync_timer) {
            clearTimeout(this.sync_timer)
        }
        this.sync_timer = setTimeout(() => {
            this.sync_timer = null
            this.syncNow()
        }, SYNC_DEBOUNCE_MS)
    }

    /** Send the editor graph if the server's differs; the server rejects syncs during a turn. */
    private syncNow(force = false) {
        if (!this.binding || !this.connected || this.state.busy) {
            return
        }
        const graph = this.binding.read()
        const key = graphKey(graph)
        if (!force && key == this.server_key) {
            return
        }
        if (this.sendRaw({ type: 'graph_sync', graph })) {
            this.server_graph = graph
            this.server_key = key
        }
    }

    send(content: string): boolean {
        content = content.trim()
        if (!content || this.state.busy || !this.connected) {
            return false
        }
        if (this.sync_timer) {
            clearTimeout(this.sync_timer)
            this.sync_timer = null
        }
        this.syncNow()
        if (!this.sendRaw({ type: 'user_message', content })) {
            return false
        }
        this.state.entries.push({ kind: 'user', id: nextEntryId('user'), content })
        this.state.busy = true
        return true
    }

    cancel() {
        this.sendRaw({ type: 'cancel' })
    }

    /** Reset the chat and the server session (the editor graph is kept and synced again). */
    clear() {
        this.state.entries = []
        if (this.sendRaw({ type: 'clear' })) {
            this.clearing = true
        }
    }

    private notice(content: string, level: 'info' | 'error' = 'info') {
        this.state.entries.push({ kind: 'notice', id: nextEntryId('notice'), content, level })
    }

    private streamed<K extends 'assistant' | 'thinking'>(kind: K, id: string) {
        return this.state.entries.find((e) => e.kind == kind && e.id == id) as Extract<ChatEntry, { kind: K }> | undefined
    }

    private handle(message: ServerMessage) {
        switch (message.type) {
            case 'session':
                this.state.session_id = message.session_id
                if (this.clearing) {
                    this.clearing = false
                    // the server graph was reset: sync the editor graph again
                    this.server_graph = emptyGraph()
                    this.server_key = graphKey(this.server_graph)
                    this.syncNow(true)
                } else if (!message.resumed && this.state.entries.length > 0) {
                    this.notice('The server started a new session; the agent does not remember the earlier messages.')
                }
                break
            case 'thinking': {
                let entry = this.streamed('thinking', message.id)
                if (!entry) {
                    // expanded while streaming, collapsed when done unless the user toggled it
                    this.state.entries.push({ kind: 'thinking', id: message.id, content: '', streaming: true, expanded: true, toggled: false })
                    entry = this.streamed('thinking', message.id)!
                }
                entry.content += message.delta
                if (message.final) {
                    entry.content = message.content ?? entry.content
                    entry.streaming = false
                    if (!entry.toggled) {
                        entry.expanded = false
                    }
                }
                break
            }
            case 'assistant_message': {
                let entry = this.streamed('assistant', message.id)
                if (!entry) {
                    if (message.final && !message.content) {
                        break
                    }
                    this.state.entries.push({ kind: 'assistant', id: message.id, content: '', streaming: true })
                    entry = this.streamed('assistant', message.id)!
                }
                entry.content += message.delta
                if (message.final) {
                    entry.content = message.content ?? entry.content
                    entry.streaming = false
                }
                break
            }
            case 'tool_call': {
                const entry = this.state.entries.find((e) => e.kind == 'tool' && e.id == message.call_id)
                if (entry && entry.kind == 'tool') {
                    entry.call = message
                } else {
                    this.state.entries.push({ kind: 'tool', id: message.call_id, call: message })
                }
                break
            }
            case 'graph_state': {
                const change = diffAgentGraphs(this.server_graph, message.graph)
                this.server_graph = message.graph
                this.server_key = graphKey(message.graph)
                if (this.binding && !isEmptyChange(change)) {
                    this.binding.apply(change, message.graph, message.details)
                }
                break
            }
            case 'error':
                this.notice(message.message, 'error')
                break
            case 'done':
                if (message.reason == 'cleared') {
                    break
                }
                this.state.busy = false
                for (const entry of this.state.entries) {
                    if ((entry.kind == 'assistant' || entry.kind == 'thinking') && entry.streaming) {
                        entry.streaming = false
                    }
                }
                if (message.reason == 'cancelled') {
                    this.notice('Stopped.')
                }
                // edits made while the agent was busy were not synced yet
                this.scheduleSync()
                break
        }
    }
}

/** The single agent chat session of this browser tab. */
export const agentSession = new AgentSession()

/**
 * Use the agent session in a view: connects to the chat of `configId` (and switches on
 * changes), binds the editor graph, and syncs whenever `graphSource` changes.
 */
export function useAgentSession(configId: Ref<string | null>, binding: GraphBinding, graphSource: () => unknown) {
    agentSession.bind(binding)
    watch(configId, (id) => agentSession.connect(id), { immediate: true })
    watch(graphSource, () => agentSession.scheduleSync(), { deep: true })
    onBeforeUnmount(() => {
        agentSession.bind(null)
        agentSession.disconnect()
    })
    return agentSession
}
