import { Api, type ConfigCollection } from "@/api/client.ts/Api"
import { BACKEND_URL } from "../config"

const api = new Api({
    baseURL: BACKEND_URL
})
export class OntoConfig {
    static config: OntoConfig = null
    static async ensureConfig(): Promise<OntoConfig> {
        if (!OntoConfig.config) {
            OntoConfig.config = new OntoConfig((await api.ontology.getOntologyConfigOntologyConfigGet()).data)
        }
        return OntoConfig.config
    }
    constructor(public config: ConfigCollection) { }
}