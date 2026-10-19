import axios from "axios"
import { ref } from "vue"
import { Api } from "@/api/client.ts/Api"
import { BACKEND_URL } from "./config"

/** Summary of a configuration as returned by `GET /configs` (outside the generated, config-scoped client). */
export interface ConfigSummary {
    id: string
    name: string
    description: string
    multimodal: boolean
    default: boolean
}

/** Id of the configuration addressed by the current route (`/:configId/...`). */
export const activeConfigId = ref<string | null>(null)

export function setActiveConfig(configId: string | null) {
    activeConfigId.value = configId
}

export function requireActiveConfig(): string {
    if (!activeConfigId.value) {
        throw new Error("No configuration selected")
    }
    return activeConfigId.value
}

export function configBaseUrl(configId: string): string {
    return `${BACKEND_URL}/${encodeURIComponent(configId)}`
}

/**
 * The single client for all configuration-scoped backend operations.
 * Every request is routed to `${BACKEND_URL}/${activeConfigId}` at the time it is sent.
 */
export const api = new Api<unknown>({ baseURL: BACKEND_URL })
api.instance.interceptors.request.use((request) => {
    request.baseURL = configBaseUrl(requireActiveConfig())
    return request
})

let configListPromise: Promise<ConfigSummary[]> | null = null

/** Lists the available configurations (cached; a failed request is retried on the next call). */
export function listConfigs(): Promise<ConfigSummary[]> {
    if (!configListPromise) {
        configListPromise = axios
            .get<ConfigSummary[]>(`${BACKEND_URL}/configs`)
            .then((resp) => resp.data)
            .catch((e) => {
                configListPromise = null
                throw e
            })
    }
    return configListPromise
}

/** localStorage key scoped to the active configuration, so saved state never leaks between configs. */
export function configStorageKey(key: string): string {
    return `onset:${requireActiveConfig()}:${key}`
}
