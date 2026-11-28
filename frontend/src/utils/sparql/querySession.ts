// Query sessions of the explore view (backend query_session.py, /{config_id}/query-sessions): the
// editor's query (SPARQL and the serialized visual query) and its edit history, saved on the
// server so a session can be reopened by its id, after a restart or in another browser. The calls
// of a session name its configuration, so a delayed save never goes to another one.
import type { HistoryRecord, QuerySessionState, QuerySessionSummary } from '@/api/client.ts/Api'
import { api, configBaseUrl } from '@/utils/api'
import type { HistoryUpdate, StoredHistoryEntry } from '@/utils/historySync'

export type { QuerySessionState, QuerySessionSummary }

/** Session ids the backend accepts (they name its save files). */
export const QUERY_SESSION_ID_PATTERN = /^[A-Za-z0-9_-]{1,64}$/

export function newQuerySessionId(): string {
    return crypto.randomUUID()
}

export function querySessions(config_id: string) {
    const params = { baseURL: configBaseUrl(config_id) }
    const s = api.querySessions
    return {
        list: (limit = 50) => s.listQuerySessionsQuerySessionsGet({ limit }, params).then((r) => r.data),
        /** ``create: false``: fails with 404 instead of creating an unknown session */
        state: (sid: string, create = true) =>
            s.getQuerySessionQuerySessionsSessionIdGet(sid, { create }, params).then((r) => r.data),
        setQuery: (sid: string, query: string, visual_query: string | null) =>
            s.putQuerySessionQueryQuerySessionsSessionIdQueryPut(sid, { query, visual_query }, params).then((r) => r.data),
        history: (sid: string): Promise<StoredHistoryEntry[]> =>
            s.getQuerySessionHistoryQuerySessionsSessionIdHistoryGet(sid, params).then((r) => r.data as HistoryRecord[]),
        patchHistory: (sid: string, update: HistoryUpdate) =>
            s.patchQuerySessionHistoryQuerySessionsSessionIdHistoryPatch(sid, update, params).then((r) => r.data),
    }
}
