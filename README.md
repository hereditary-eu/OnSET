# OnSET

## Live Demo

> In progress...

## Description

OnSET should enable a more explorative ontology querying experience for non-expert users, and to build a quick understanding of the scale and nature of a KG that is in use. The toolkit consists of multiple smaller systems, complimenting each other. We have three default views ready:

* a query view; where users can construct queries either from topics or from natural language prompts,
* the explorative view; enabling users to view the ontology as a whole, view sparse relations and explore the named instances, and
* the linked view; showing users the hierarchical ontology *and* topic model at the same time, creating a rich visualization of multiple dimensions within the ontology. 


## Setup instruction

1. Install Apache Fuseki such that you have a working `riot` command line tool (https://jena.apache.org/documentation/fuseki2/)
2. Setup a local `qlever` instance (https://github.com/ad-freiburg/qlever-control) (the used configurations can be found in `docker/bto-data` and `docker/dbpedia-data`), you should be able to just run from the `docker/*-data`-directories:
```bash
qlever get-data
qlever index
qlever start
```
3. Start auxiliary DB using `cd docker/onset-data && docker-compose up -d`
4. Backend setup:
   - install `uv` (https://docs.astral.sh/uv/getting-started/installation/)
   - install dependencies using `CMAKE_ARGS="-DGGML_CUDA=on" uv sync` (or `CMAKE_ARGS="-DGGML_METAL=on" uv sync` on Mac)
   - start backend (should initialize DB on first start) using the correct Python  installation using `python -m uvicorn api:app --reload --port 8001`
5. Frontend setup:
   - install a somewhat recent Node version
   - install dependencies by first `cd frontend && npm i -D`
   - then start the frontend using `npm run dev`
* Profit?

## Configuration

All knowledge graph configurations live in `backend/config.json` (path overridable with `ONSET_CONFIG`), which is used by the backend and the `exploration` scripts alike:

```jsonc
{
  "default": "dbpedia",                  // pre-selected configuration
  "defaults": { "model_id": "...", ... },  // shared by every configuration
  "configs": {
    "dbpedia": {
      "name": "DBpedia", "description": "...", "sparql_endpoint": "...", "conn_str": "...",
      "variants": [ { "name": "DBpedia Mistral", "model_id": "...", "model_quant": "..." } ]
    }
  }
}
```

- Each configuration resolves to `defaults <- config <- variant`; `eval_config.ALL_CONFIG_MAP[key]` lists the variants followed by the base configuration, so `[-1]` (or `get_config(key)`) is the base configuration served by the API.
- String values may reference environment variables as `${VAR}` or `${VAR:-fallback}`, e.g. `ONSET_DB_HOST`, `ONSET_SPARQL_HOST`, `REDIS_CACHE_URL`, `LLM_MODEL_ID`, `LLM_MODEL_QUANT`, `ONSET_DEFAULT_CONFIG`.
- The API lists configurations at `GET /configs`; every other endpoint is scoped to a configuration as `/{config_id}/...` (e.g. `/dbpedia/classes/roots`, docs at `/dbpedia/docs`). Configurations are loaded lazily on first use; `ONSET_MAX_LOADED_CONFIGS` limits how many stay loaded at once (0 = unlimited).
- The frontend mirrors this: `/` selects a configuration, `/:configId/explore` and `/:configId/circles` are the pages for it. Regenerate the API client from any configuration's schema, e.g. `sta generate -p http://localhost:8123/dbpedia/openapi.json -o ./src/api/client.ts --axios`.

