# Onto-builder end-to-end test (real backend and frontend, no mocks)

Drives `/onto-builder` with Puppeteer against the real FastAPI backend and Vite frontend. Extraction uses the real
LFM2-350M-Extract model, and the judge uses LFM2.5-350M (llama.cpp CPU build, no CUDA in this env).
No Redis or Postgres is needed. The builder routes don't touch them, and the KG config in `config.json` is a
placeholder that is never loaded.

## Setup

- `make_texts.py` writes `texts/mails/*.txt`: 8 short e-mails with name variants (Jeff/Jeffrey/Jeffrey K. Skilling,
  Ken/Kenneth/Kenneth L. Lay, Enron Corp/Corporation/enron corp., Andy/Andrew/Andrew S. Fastow, ...).
- `config.json` holds the minimal config with one builder `e2e`: the text set above, 1 extraction instance
  (`ONSET_E2E_INSTANCES`) so a build takes ~23 s and refreshes can be observed during it, and saves in
  `/tmp/onset-e2e-saves`.
- Backend: `cd backend/src && ONSET_CONFIG=<this dir>/config.json UV_PROJECT_ENVIRONMENT=../.uv-agent uv run --no-sync python -m uvicorn api:app --port 8123`
- Frontend: `cd frontend && npx vite --port 5199`
- Test: `bun exploration/e2e-builder/e2e.mjs`. It writes the screenshots and `results.json`, which holds all
  measured numbers.

## Steps (final run, all PASS)

| # | Step | Screenshots | Result | Observed |
|---|------|-------------|--------|----------|
| 1 | Builder list at `/onto-builder` | 01 | PASS | card "E2E Enron mini" |
| 2 | Open the builder, which creates a new session | 02 | PASS | empty ontology, session id in localStorage |
| 3 | Ontology: classes Person and Company typed in the UI, link drawn in the UI (card link button, then target card); field `role` and link id/name `worksFor`/"works for" set via `PUT .../ontology` | 03 | PASS | cards Person, Company; link "works for" |
| 4 | Pan, zoom, fit in the ontology view | 04 zoomed, 05 panned, 06 fit | PASS | k 1 → 1.647 after 3 wheel steps; a background drag of (+120, −80) moved the view by exactly (+120, −80); fit → k = 1, both cards inside the viewport |
| 5 | Initial build (default mode `normalized`) | 07 running, 08 done | PASS | 8/8 docs, 106 triples, 0 errors, TentrisStore, ~24 s |
| 6a | Merging → Off, Apply & rebuild | 09 popup, 10, 11 | PASS | restarts at 0/8 docs; 106 triples, 0 merged |
| 6b | Merging → Normalized | 12, 13 | PASS | restarts; 106 triples, 0 merged (no name that differs only in case or punctuation reached the resolver in the build) |
| 6c | Merging → Edit distance | 14, 15 | PASS | restarts; 104 triples, **2 merged**: "Andrew S. Fastow" → "Andrew Fastow", "Jeffrey K. Skilling" → "Jeffrey Skilling" |
| 6d | Merging → LLM judge | 16, 17 | PASS | restarts; 98 triples, **8 merged, 6 judged**, build 36 s (vs. ~23 s): "Arthur Andersen LLP" → "Arthur Andersen", "Andrew Fastow" → "Andy Fastow", "Kennet Lay"/"Ken Lay" → "Kenneth L. Lay", "Enron Corp" → "Enron Corporation", "Jeffrey Skilling" → "Jeff Skilling", plus 2 edit-distance merges |
| 7a | Visual results (Instances of… Person): expand a miniature | 18, 19 | PASS | 10 miniatures; node centre = window centre (800, 513), offset (0, 0) |
| 7b | Rebuild, expand a miniature mid-build (3/8 docs, 43 triples), let the build finish (3 result queries while open) | 20, 21 | PASS | still open on the same instance ("Chuck Watson"), still centred (offset (0, 0)) |
| 8 | Source button in the expanded miniature header opens the sources panel | 22 | PASS (after fix f3cfcea) | "Chuck Watson: Extracted from 1 document: Merger talks 05.txt" |
| 9a | SPARQL table: click an IRI cell, which opens the sources panel | 23, 24 | PASS | Andy Fastow, also extracted as "Andrew Fastow", "Andrew S. Fastow"; 3 documents (03, 04, 08) |
| 9b | Open a document in DocumentViewer | 25 | PASS | "LJM partnership" (03.txt), 1 match, "Andy Fastow" marked |
| 10 | Reload the page | 26 | PASS | same session; mode `llm_judge` and all parameters unchanged; LLM judge button selected; 8 merges listed |

## Bugs found

1. **Visual queries failed with HTTP 500 on the Tentris store** (step 7, present before these commits). The
   Tentris store keeps no namespace bindings, so the `foaf:name` that the visual query mapper uses for labels
   was an unknown prefix ("Parse Error: foaf is invalid: unknown prefix"). No miniatures appeared. The earlier
   mocked checks mocked `/sparql` and so missed it. Fixed in 899bb37: `builder/kg.py` declares foaf, prov,
   skos and dcterms with onto.
2. **The miniature header's source button sent `<http://…>`** (step 8). The node `instance_id` is a SPARQL term,
   so the panel title showed "chuck-watson>" and `GET .../provenance?iri=<…>` returned 500 (Tentris rejects
   the bracketed IRI). The browser reported this as "Network Error", because a 500 carries no CORS header.
   Fixed in f3cfcea: Miniature.vue strips the brackets. The endpoint still answers 500 rather than 400 to a
   bracketed IRI.

## Other observations (not bugs in the tested commits)

- An expanded miniature closes when its instance disappears from the results. This happens on a
  from-scratch rebuild, e.g. after a Merging change. The window stays open across refreshes while the KG grows (7b).
- The canonical name is the first one extracted. In an earlier run, Edit distance merged "Kenneth Lay" into the
  model's typo "Kennet Lay". Which variant comes first depends on thread order, so the merge lists differ slightly between runs.
- LFM2-350M-Extract left every `worksFor` list empty, so the `company` column is empty. It also typed
  "Dynegy Inc" and "Arthur Andersen" as Person.
- The MDI icon font gets 403 from Vite because `frontend/node_modules` is a symlink outside the worktree. That
  is why the icons render as boxes in the screenshots. This comes from the environment.
