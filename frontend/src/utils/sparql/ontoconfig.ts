import type { ConfigCollection } from "@/api/client.ts/Api"
import { api, requireActiveConfig } from "../api"

/**
 * Property types that hold images for the active configuration.
 * Updated in place on config changes, as the subquery registry keeps a reference to this array.
 */
export const ALLOWED_IMAGE_PROP_TYPES: string[] = []

export class OntoConfig {
    static config: OntoConfig | null = null
    private static loading: { configId: string, promise: Promise<OntoConfig> } | null = null

    /** Loads (once per configuration) the ontology config of the active configuration. */
    static async ensureConfig(): Promise<OntoConfig> {
        const configId = requireActiveConfig()
        if (OntoConfig.config?.config.id === configId) {
            return OntoConfig.config
        }
        if (OntoConfig.loading?.configId !== configId) {
            const promise = api.ontology.getOntologyConfigOntologyConfigGet().then((resp) => {
                const config = new OntoConfig(resp.data)
                // ignore responses for a configuration that is no longer active
                if (requireActiveConfig() === configId) {
                    OntoConfig.config = config
                    ALLOWED_IMAGE_PROP_TYPES.splice(0, ALLOWED_IMAGE_PROP_TYPES.length, ...config.config.multimodal.image_types)
                    console.log("Allowed image prop types", ALLOWED_IMAGE_PROP_TYPES)
                }
                return config
            }).finally(() => {
                if (OntoConfig.loading?.configId === configId) {
                    OntoConfig.loading = null
                }
            })
            OntoConfig.loading = { configId, promise }
        }
        return OntoConfig.loading!.promise
    }
    constructor(public config: ConfigCollection) { }
}
