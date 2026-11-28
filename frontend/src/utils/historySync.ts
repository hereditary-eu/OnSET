// Saves an edit history in its backend session (backend session_history.py): the ontology
// builder's (utils/builder/history.ts) and the query editor's (utils/sparql/history.ts).
//
// The backend keeps the entries keyed by their own ``timestamp`` and adds when it first stored
// and last updated each (``created_at``/``updated_at``). A sync sends only the difference to the
// last synced state: entries that are new or changed (a coalesced edit keeps its timestamp, so it
// replaces its entry) and the timestamps of entries that are gone (coalesced, trimmed, cleared).

/** An entry as the backend keeps it; ``entry`` is the history's own serialization. */
export interface StoredHistoryEntry<T = unknown> {
    timestamp: number
    entry: T
    /** server epoch ms of the first and last time it was stored (absent before the first sync) */
    created_at?: number
    updated_at?: number
}

export interface HistoryUpdate {
    clear?: boolean
    remove: number[]
    upsert: { timestamp: number, entry: unknown }[]
}

export class HistorySync {
    /** timestamp -> JSON of the entry as last sent (or loaded) */
    private synced = new Map<number, string>()
    private timer: ReturnType<typeof setTimeout> | null = null
    private running: Promise<void> = Promise.resolve()
    /** the last sync failed (it is retried with the next one) */
    failed = false

    /**
     * @param snapshot the entries of the history now, serialized for the backend (null: skip,
     *   e.g. the history is no longer the session's)
     * @param send PATCHes an update to the session's history
     */
    constructor(
        private readonly snapshot: () => StoredHistoryEntry[] | null,
        private readonly send: (update: HistoryUpdate) => Promise<unknown>,
        private readonly debounce_ms = 1000,
    ) { }

    /** Marks ``entries`` (e.g. loaded from the backend) as synced. */
    reset(entries: StoredHistoryEntry[]) {
        this.synced = new Map(entries.map((e) => [e.timestamp, JSON.stringify(e.entry)]))
    }

    /** Syncs after the debounce time (restarted by every call). */
    schedule() {
        if (this.timer) {
            clearTimeout(this.timer)
        }
        this.timer = setTimeout(() => this.flush(), this.debounce_ms)
    }

    /** Syncs now (after a sync that is still running); resolves when the backend has it. */
    flush(): Promise<void> {
        if (this.timer) {
            clearTimeout(this.timer)
            this.timer = null
        }
        this.running = this.running.then(() => this.sync())
        return this.running
    }

    private async sync() {
        const entries = this.snapshot()
        if (!entries) {
            return
        }
        const current = new Map(entries.map((e) => [e.timestamp, JSON.stringify(e.entry)]))
        const upsert = [...current].filter(([t, json]) => this.synced.get(t) !== json)
            .map(([timestamp, json]) => ({ timestamp, entry: JSON.parse(json) }))
        const remove = [...this.synced.keys()].filter((t) => !current.has(t))
        if (!upsert.length && !remove.length) {
            return
        }
        try {
            await this.send({ upsert, remove })
            this.synced = current
            this.failed = false
        } catch (e) {
            this.failed = true
            console.warn('Saving the history in the session failed', e)
        }
    }
}
