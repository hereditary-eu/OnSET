# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

OnSET (Ontology and Semantic Exploration Toolkit, SIGIR 2025 demo): a FastAPI backend plus a Vue 3/Vuetify frontend. With it, users explore knowledge graphs served by QLever SPARQL endpoints and build queries visually or from natural language, using a local llama.cpp model with grammar-constrained output. It calls no hosted LLM API. See README.md for the full setup.

## Commands

Backend (Python 3.13, `uv`, run from `backend/src` because imports are relative to that directory):
```bash
cd backend && CMAKE_ARGS="-DGGML_CUDA=on" uv sync          # -DGGML_METAL=on on macOS
cd backend/src && uv run python -m uvicorn api:app --reload --port 8123
```
Port 8123 is what `frontend/.env.development` (`ONSET_API_BASE_URL`), the VS Code launch config and `npm run generate-client` expect. The README says 8001, which only matches `generate-client-mac`.

Frontend (`frontend/`):
```bash
npm install && npm run dev
npm run build          # vue-tsc type-check + vite build in parallel
npm run type-check
npm run generate-client   # regenerate src/api/client.ts/Api.ts from the running backend's /dbpedia/openapi.json
```

Infrastructure: `cd docker/onset-data && docker compose up -d` starts Postgres (pgvector/PostGIS) and Redis. Each KG is a QLever instance started from its `docker/<kg>-data` folder (`qlever get-data && qlever index && qlever start`). DBpedia runs on port 7012.

Backend tests: `cd backend && uv run pytest` (offline fakes in `tests/fakes.py`; `-m live` for tests against real services; refresh OpenAPI snapshots with `ONSET_UPDATE_SNAPSHOTS=1`).

## Architecture

**Configurations drive everything.** `backend/config.json` (overridable via `ONSET_CONFIG`) defines one entry per KG: SPARQL endpoint, Postgres `conn_str`, LLM model and multimodal settings. Values may contain `${VAR:-fallback}`. `backend/src/eval_config.py` resolves each entry as `defaults <- config <- variant` (nested objects merged field by field). Sub-models: `multimodal_config`, `agent`, `progressive` (progressive discovery timeout/parallelism/sample and count caps, env-overridable as `ONSET_PROGRESSIVE_<FIELD>` through `${VAR:-fallback}` in `config.json`). `CONFIG_FILE.base(key)` / `get_config(key)` returns the base config that the API serves. `ALL_CONFIG_MAP` lists variants, which the evaluation scripts use.

**Per-config service bundle ("ManMan").** `backend/src/api/app.py` mounts a sub-app at `/{config_id}`. Every route under it takes `ManManDep`, which resolves the config from the URL. `api/config.py` lazily builds one `ManMan` per config (an LRU capped by `ONSET_MAX_LOADED_CONFIGS`). A ManMan wires up:
- `OntologyManager` (`ontology.py`): rdflib `Graph` over a `SPARQLStore`. Handles class hierarchy, instances, labels and SPARQL→DataFrame.
- `GuidanceManager` (`explorative/explorative_support.py`): sentence embeddings stored in Postgres/pgvector (SQLAlchemy models in `explorative/exp_model.py`), fuzzy class/link search, topic tree. It lazily loads the llama.cpp model and the embedding models from the Hugging Face Hub.
- `LLMQuery` (`explorative/llm_query.py`): NL → entities/relations/constraints → prototype query graph, with a grammar restricted to ontology classes/relations (via the `llama-cpp-agent` fork). The results are cached in Redis.
- `IterativeAssistant` (`assistant/`, under active development): a turn-based agent. It takes an NL request plus the current editor `QueryGraph` and returns `Operations` (add/remove subjects/links) to apply to the graph. The steps are: candidate retrieval → constrained op generation → correction. It is exposed at `POST /{config_id}/classes/search/assistant` and cached in Redis.
- `InitatorManager` (`initiator.py`): registers components that need one-time DB/embedding initialisation.

Routers live in `api/router/`: `classes` (hierarchy, search, instances, LLM search), `nlp` (embeddings/manifold), `search` (multimodal text/image encoding, dim-reduction). `GET /configs` is the only top-level, unscoped endpoint.

**Frontend.** Routes are `/:configId/{explore,circles,graph,linked-circles}`. A router guard in `src/router/index.ts` sets the active config. A single generated `Api` client (`src/utils/api.ts`) rewrites each request's base URL to `${BACKEND_URL}/${activeConfigId}`. `src/api/client.ts/Api.ts` is generated: regenerate it, don't hand-edit it, after backend schema changes. The visual query editor's model is in `src/utils/sparql/`: node/link representation, `NodeLinkRepository` store, diff/history, and `querymapper.ts`, which turns the graph into SPARQL. Visualisations use d3 (`utils/d3-man`) and three.js (`utils/three-man`).

**Ontology builder** (`backend/src/builder/`, `api/router/builder.py`, frontend `/onto-builder`). Builds an ontology for a text collection instead of querying a KG. The `builders` section of `config.json` (`BuilderConfig`) holds the text set (`files` glob, e.g. Enron maildir, or a `json` dict of records, e.g. GutBrainIE; paths resolve against the config file's directory, `ONSET_TEXT_SETS` points to `data/text-sets`) and the extraction model. Each session (`BuilderSession`) holds an `Ontology` (classes with typed fields, links), a SPARQL query and a triple store. The store is native Tentris where its wheel exists (x86_64 Linux) and rdflib's memory store elsewhere. Every schema change restarts a background build: `LlamaExtractor` (LFM2-350M-Extract, output constrained to `extraction_schema`) reads the documents one by one, and queries see the partial KG. `BuilderAgent` reuses the `GraphAgent` loop (state hooks `describe_state`/`state_message`/`call_tool`). Its tools edit the ontology, search the text (`Corpus.search`, TF-IDF sentence snippets), set or read the query, and prepare downloads. Routes live on the main app under `/onto-builder`, which is included before the `/{config_id}` mount.

**Exploration / evaluation.** `exploration/` holds notebooks and the paper's query-generation evaluation (`exploration/querying/querygen.py`, `query-eval.py`, `init-db.py`, plus SLURM scripts). These scripts add `backend/src` to `sys.path` and use `ALL_CONFIG_MAP`. The generated `.tex` tables and figures are copied to the paper.

**Submodules / vendored.** `llama-cpp-agent` is a git submodule (Dakantz fork), but `uv` installs it from the `add-literal-support` branch on GitHub. `rdflib/` is a local checkout and is not wired into `pyproject.toml`.
